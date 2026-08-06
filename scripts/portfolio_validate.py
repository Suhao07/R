#!/usr/bin/env python3
"""Validate the research portfolio structure, policies and evidence records."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from validate_experiment_record import validate_experiment_record


SCRIPT_DIR = Path(__file__).resolve().parent
PORTFOLIO_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = PORTFOLIO_ROOT.parent
SCHEMA_PATH = PORTFOLIO_ROOT / "schemas" / "workflow_v3.schema.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[=:]\s*"
    r"(?!redacted\b|\$\{|<)[\"']?[A-Za-z0-9_-]{12,}"
)
VOID_TAGS = {
    "meta", "link", "img", "br", "hr", "input", "source", "area", "base",
    "col", "embed", "param", "track", "wbr",
}


@dataclass
class ParsedHTML:
    """Store workflow body metadata and stable field values."""

    body_attrs: dict[str, str] = field(default_factory=dict)
    fields: dict[str, list[str]] = field(default_factory=dict)


class WorkflowHTMLParser(HTMLParser):
    """Extract data-field/data-value pairs from recovery HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parsed = ParsedHTML()
        self.current_field: str | None = None
        self.capture = False
        self.capture_depth = 0
        self.capture_text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Handle one opening tag."""

        attr = {key: value or "" for key, value in attrs}
        if tag == "body":
            self.parsed.body_attrs = attr
        if self.capture and tag not in VOID_TAGS:
            self.capture_depth += 1
        if "data-field" in attr:
            self.current_field = attr["data-field"]
        if attr.get("data-value") == "true":
            if not self.current_field:
                raise ValueError("data-value found outside data-field")
            self.capture = True
            self.capture_depth = 1
            self.capture_text = []

    def handle_endtag(self, tag: str) -> None:
        """Handle one closing tag."""

        if not self.capture:
            return
        self.capture_depth -= 1
        if self.capture_depth == 0:
            value = " ".join("".join(self.capture_text).split())
            assert self.current_field is not None
            self.parsed.fields.setdefault(self.current_field, []).append(value)
            self.capture = False
            self.capture_text = []
            self.current_field = None

    def handle_data(self, data: str) -> None:
        """Capture text inside a stable value slot."""

        if self.capture:
            self.capture_text.append(data)


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _parse_html(path: Path) -> ParsedHTML:
    """Parse one recovery HTML document."""

    parser = WorkflowHTMLParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.parsed


def _value(parsed: ParsedHTML, field_name: str) -> str | None:
    """Return a unique field value."""

    values = parsed.fields.get(field_name, [])
    return values[0] if len(values) == 1 else None


def _valid_date(value: str) -> bool:
    """Return whether value is an ISO date or datetime."""

    try:
        if "T" in value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_html(path: Path, schema: dict[str, Any], template: bool) -> list[str]:
    """Validate one v3 recovery HTML document."""

    errors: list[str] = []
    try:
        parsed = _parse_html(path)
    except (OSError, ValueError) as exc:
        return [f"{path}: cannot parse HTML: {exc}"]
    doc = parsed.body_attrs.get("data-workflow-doc")
    if doc not in schema["html_documents"]:
        return [f"{path}: invalid workflow document type {doc!r}"]
    if parsed.body_attrs.get("data-schema-version") != "3":
        errors.append(f"{path}: data-schema-version must be 3")
    expected_status = "canonical" if template else "active"
    if parsed.body_attrs.get("data-template-status") != expected_status:
        errors.append(f"{path}: data-template-status must be {expected_status}")
    for field_name in schema["html_documents"][doc]["required_fields"]:
        values = parsed.fields.get(field_name, [])
        if len(values) != 1:
            errors.append(
                f"{path}: field {field_name!r} occurs {len(values)} times"
            )
        elif not values[0]:
            errors.append(f"{path}: field {field_name!r} is empty")
    instance = _value(parsed, "instance-status")
    expected_instance = "canonical-template" if template else "active-instance"
    if instance != expected_instance:
        errors.append(
            f"{path}: instance-status must be {expected_instance}, got {instance!r}"
        )
    if not template:
        for field_name in (
            "execution-state",
            "implementation-state",
            "verification-level",
            "validation-scope",
        ):
            value = _value(parsed, field_name)
            if value is not None and value not in schema["enums"][field_name]:
                errors.append(f"{path}: invalid {field_name}={value!r}")
        verified = _value(parsed, "last-verified-at")
        if verified and not _valid_date(verified):
            errors.append(f"{path}: last-verified-at is not ISO-8601")
    return errors


def validate_matrix(
    matrix_path: Path, policy_path: Path
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Validate repository roles, mutation policies and policy coverage."""

    errors: list[str] = []
    matrix = _load_json(matrix_path)
    policy = _load_json(policy_path)
    profiles = policy.get("profiles", {})
    repositories: dict[str, dict[str, Any]] = {}
    allowed_roles = {
        "primary_framework",
        "integration_control",
        "reference_method",
        "reference_dataset",
    }
    for repo in matrix.get("repositories", []):
        repo_id = str(repo.get("id", ""))
        if not repo_id or repo_id in repositories:
            errors.append(f"{matrix_path}: missing or duplicate id {repo_id!r}")
            continue
        repositories[repo_id] = repo
        path = Path(str(repo.get("path", "")))
        if not path.is_absolute() or not path.is_dir():
            errors.append(f"{matrix_path}: repository path missing: {path}")
        if repo.get("role") not in allowed_roles:
            errors.append(f"{matrix_path}: invalid role for {repo_id}")
        if repo.get("policy_profile") not in profiles:
            errors.append(f"{matrix_path}: unknown policy profile for {repo_id}")
        if not repo.get("responsibilities"):
            errors.append(f"{matrix_path}: {repo_id} has no responsibility")
        if str(repo.get("role", "")).startswith("reference_"):
            if repo.get("mutation_policy") != "read_only_by_default":
                errors.append(f"{matrix_path}: {repo_id} reference is not read-only")
        if repo.get("role") in {"primary_framework", "integration_control"}:
            instruction = repo.get("agent_instructions")
            if not instruction or not (path / str(instruction)).is_file():
                errors.append(f"{matrix_path}: {repo_id} AGENTS.md is missing")
    actual_primary = {
        repo_id
        for repo_id, repo in repositories.items()
        if repo.get("role") == "primary_framework"
    }
    expected_primary = set(matrix.get("primary_framework_ids", []))
    if actual_primary != expected_primary or actual_primary != {
        "urbannav-sr",
        "ms-swift",
    }:
        errors.append(f"{matrix_path}: primary frameworks must be exact")
    actual_integration = {
        repo_id
        for repo_id, repo in repositories.items()
        if repo.get("role") == "integration_control"
    }
    if actual_integration != set(matrix.get("integration_control_ids", [])):
        errors.append(f"{matrix_path}: integration ids do not match roles")
    for relative in policy.get("policy_documents", {}).values():
        path = PORTFOLIO_ROOT / relative
        if not path.is_file():
            errors.append(f"{policy_path}: missing policy document {path}")
    for profile_id, profile in profiles.items():
        if not profile.get("policies"):
            errors.append(f"{policy_path}: {profile_id} has no policies")
        for source in profile.get("executable_sources", []):
            if not Path(source).is_file():
                errors.append(
                    f"{policy_path}: missing executable source for "
                    f"{profile_id}: {source}"
                )
    return errors, repositories


def validate_policy_migration(root: Path) -> list[str]:
    """Validate that legacy engineering rules have durable portfolio targets."""

    errors: list[str] = []
    evidence_path = root / "evidence" / "policy-migration-20260726.json"
    evidence = _load_json(evidence_path)
    migrations = {
        item.get("rule_family"): item
        for item in evidence.get("migrations", [])
        if item.get("rule_family")
    }
    required_families = {
        "public docstrings and Args/Returns/Raises",
        "dataclass fields, private semantic helpers and mathematical definitions",
        "schema, IO, runner, evaluator, exporter and CLI separation",
        "offline deterministic evaluation and stable-ID matching",
        "acceptable destination and matched-route metric semantics",
        "targeted tests and non-rank-1 acceptable destination coverage",
        "ms-swift isort, YAPF, flake8 and pre-commit formatting",
        "editing discipline and narrow changes",
    }
    missing = required_families - set(migrations)
    if missing:
        errors.append(
            f"{evidence_path}: missing migrated rule families {sorted(missing)}"
        )
    for family in required_families & set(migrations):
        status = str(migrations[family].get("status", ""))
        if status not in {
            "migrated",
            "migrated_as_urbannav_specific",
            "registered_without_duplication",
        }:
            errors.append(
                f"{evidence_path}: rule family {family!r} is not migrated"
            )
    quality_text = (root / "policies" / "python-code-quality.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "public class",
        "`Args:`",
        "数学定义",
        "isort line length 120",
        "YAPF",
        "max line length 120",
    ):
        if marker not in quality_text:
            errors.append(
                f"policies/python-code-quality.md: missing contract {marker!r}"
            )
    benchmark_text = (root / "policies" / "benchmark-evaluation.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "`acceptable_destinations`",
        "rank-1",
        "`destination_success`",
        "`spl`",
    ):
        if marker not in benchmark_text:
            errors.append(
                f"policies/benchmark-evaluation.md: missing rule {marker!r}"
            )
    ms_setup = (WORKSPACE_ROOT / "ms-swift" / "setup.cfg").read_text(
        encoding="utf-8"
    )
    for marker in (
        "line_length = 120",
        "COLUMN_LIMIT = 120",
        "max-line-length = 120",
    ):
        if marker not in ms_setup:
            errors.append(f"ms-swift/setup.cfg: expected setting missing {marker!r}")
    ms_agents = (WORKSPACE_ROOT / "ms-swift" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    if "## 格式规范权威" not in ms_agents:
        errors.append("ms-swift/AGENTS.md: formatting routing section is missing")
    route_agents = (
        WORKSPACE_ROOT / "Urban-Nav-SR" / "Agent_part" / "RouteServer" / "AGENTS.md"
    ).read_text(encoding="utf-8")
    if "## UrbanNav 基准规则" not in route_agents:
        errors.append("RouteServer/AGENTS.md: benchmark rules are missing")
    return errors


def validate_snapshot(
    path: Path, repositories: dict[str, dict[str, Any]]
) -> list[str]:
    """Validate the saved portfolio snapshot."""

    errors: list[str] = []
    if not path.is_file():
        return [f"{path}: snapshot is missing"]
    snapshot = _load_json(path)
    seen: set[str] = set()
    for repo in snapshot.get("repositories", []):
        repo_id = str(repo.get("id", ""))
        seen.add(repo_id)
        configured = repositories.get(repo_id)
        if configured is None:
            continue
        for field_name in ("role", "mutation_policy", "policy_profile"):
            if repo.get(field_name) != configured.get(field_name):
                errors.append(f"{path}: {repo_id} {field_name} drift")
        if configured.get("git_expected"):
            if not repo.get("git_repository"):
                errors.append(f"{path}: {repo_id} is not a Git repository")
            if not COMMIT_RE.fullmatch(str(repo.get("commit", ""))):
                errors.append(f"{path}: invalid commit for {repo_id}")
        if configured.get("required") and not repo.get("exists"):
            errors.append(f"{path}: required repository missing: {repo_id}")
    if seen != set(repositories):
        errors.append(f"{path}: snapshot repository ids do not match matrix")
    return errors


def validate_runs(
    run_dir: Path, repositories: dict[str, dict[str, Any]]
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Validate portfolio bootstrap and future run records."""

    errors: list[str] = []
    runs: dict[str, dict[str, Any]] = {}
    paths = sorted(run_dir.glob("*.json"))
    if not paths:
        return [f"{run_dir}: no run manifests"], runs
    for path in paths:
        run = _load_json(path)
        required = {
            "schema_version",
            "run_id",
            "workstream_id",
            "objective",
            "status",
            "repository_ids",
            "commands",
            "artifacts",
            "gates",
            "known_limitations",
        }
        missing = sorted(required - set(run))
        if missing:
            errors.append(f"{path}: missing keys {missing}")
        # 新式实验 run 必须能回溯到一份通过结构校验的责任仓记录。
        if run.get("schema_version") == "research_experiment_run_v1":
            record_value = run.get("experiment_record")
            if not record_value:
                errors.append(f"{path}: experiment run is missing experiment_record")
            else:
                record_path = Path(str(record_value))
                for error in validate_experiment_record(record_path):
                    errors.append(f"{path}: experiment_record: {error}")
        if run.get("run_id") != path.stem:
            errors.append(f"{path}: run_id must match filename")
        elif path.stem in runs:
            errors.append(f"{path}: duplicate run id")
        else:
            runs[path.stem] = run
        unknown = set(run.get("repository_ids", [])) - set(repositories)
        if unknown:
            errors.append(f"{path}: unknown repository ids {sorted(unknown)}")
        gate_ids = [str(gate.get("id", "")) for gate in run.get("gates", [])]
        if not gate_ids or len(gate_ids) != len(set(gate_ids)):
            errors.append(f"{path}: run gate ids must be non-empty and unique")
        failed_required = [
            gate.get("id")
            for gate in run.get("gates", [])
            if gate.get("required") and not gate.get("passed")
        ]
        if run.get("status") == "passed" and failed_required:
            errors.append(
                f"{path}: passed run has failed required gates {failed_required}"
            )
        for artifact in run.get("artifacts", []):
            artifact_path = Path(str(artifact.get("path", "")))
            current = artifact_path.exists()
            if artifact.get("exists") is not None:
                if bool(artifact["exists"]) != current:
                    errors.append(f"{path}: artifact existence drift {artifact_path}")
            if (
                run.get("status") == "passed"
                and artifact.get("required")
                and not current
            ):
                errors.append(f"{path}: required artifact missing {artifact_path}")
    return errors, runs


def validate_claims_and_releases(
    root: Path,
    repositories: dict[str, dict[str, Any]],
    runs: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate evidence links and release gate semantics."""

    errors: list[str] = []
    for path in sorted((root / "claims").glob("*.json")):
        claim = _load_json(path)
        if claim.get("claim_id") != path.stem:
            errors.append(f"{path}: claim_id must match filename")
        unknown = set(claim.get("evidence_run_ids", [])) - set(runs)
        if unknown:
            errors.append(f"{path}: unknown evidence runs {sorted(unknown)}")
        if claim.get("status") == "supported":
            not_passed = [
                run_id
                for run_id in claim.get("evidence_run_ids", [])
                if runs.get(run_id, {}).get("status") != "passed"
            ]
            if not_passed:
                errors.append(
                    f"{path}: supported claim references non-passed runs "
                    f"{not_passed}"
                )
    for path in sorted((root / "releases").glob("*.json")):
        release = _load_json(path)
        if release.get("release_id") != path.stem:
            errors.append(f"{path}: release_id must match filename")
        unknown_runs = set(release.get("run_ids", [])) - set(runs)
        if unknown_runs:
            errors.append(f"{path}: unknown release runs {sorted(unknown_runs)}")
        unknown_repos = set(release.get("repository_ids", [])) - set(repositories)
        if unknown_repos:
            errors.append(
                f"{path}: unknown release repositories {sorted(unknown_repos)}"
            )
        gate_ids = [str(gate.get("id", "")) for gate in release.get("gates", [])]
        if not gate_ids or len(gate_ids) != len(set(gate_ids)):
            errors.append(
                f"{path}: release gate ids must be non-empty and unique"
            )
        failed_required = [
            gate.get("id")
            for gate in release.get("gates", [])
            if gate.get("required") and not gate.get("passed")
        ]
        if release.get("status") == "released" and failed_required:
            errors.append(
                f"{path}: released with failed required gates {failed_required}"
            )
        if release.get("status") == "released":
            for component_id, commit in release.get("components", {}).items():
                if not COMMIT_RE.fullmatch(str(commit or "")):
                    errors.append(
                        f"{path}: released component {component_id} has no commit"
                    )
    return errors


def validate_portfolio(root: Path = PORTFOLIO_ROOT) -> list[str]:
    """Validate the complete portfolio control plane."""

    errors: list[str] = []
    schema = _load_json(root / "schemas" / "workflow_v3.schema.json")
    for path in sorted((root / "templates" / "v3").glob("*.html")):
        errors.extend(validate_html(path, schema, template=True))
    instances = [root / "USER.html"]
    instances.extend(sorted((root / "workstreams").glob("*/*.html")))
    for path in instances:
        errors.extend(validate_html(path, schema, template=False))
    matrix_errors, repositories = validate_matrix(
        root / "repos.json", root / "policies" / "policy-matrix.json"
    )
    errors.extend(matrix_errors)
    errors.extend(validate_policy_migration(root))
    errors.extend(
        validate_snapshot(
            root / "snapshots" / "repo_snapshot_current.json", repositories
        )
    )
    run_errors, runs = validate_runs(root / "runs", repositories)
    errors.extend(run_errors)
    errors.extend(validate_claims_and_releases(root, repositories, runs))
    workspace_agent = WORKSPACE_ROOT / "AGENTS.md"
    mirror = root / "workspace" / "AGENTS.md"
    if not workspace_agent.is_file() or not mirror.is_file():
        errors.append("workspace AGENTS or versioned mirror is missing")
    elif workspace_agent.read_bytes() != mirror.read_bytes():
        errors.append("workspace AGENTS differs from versioned mirror")
    integration = _load_json(root / "integrations" / "workflows.json")
    for item in integration.get("integrations", []):
        for field_name in ("path", "status_document"):
            if not Path(str(item.get(field_name, ""))).exists():
                errors.append(
                    f"integrations/workflows.json: missing {field_name} "
                    f"for {item.get('id')}"
                )
    side_templates = WORKSPACE_ROOT / "SideWalkNavigation" / "workflow" / "templates" / "v3"
    for path in sorted((root / "templates" / "v3").iterdir()):
        source = side_templates / path.name
        if not source.is_file() or path.read_bytes() != source.read_bytes():
            errors.append(f"{path}: canonical template drift from SideWalk v3")
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() == ".json":
            try:
                _load_json(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{path}: invalid JSON: {exc}")
                continue
        if path.suffix.lower() not in {".html", ".md", ".json", ".py", ".sh"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_RE.search(text):
            errors.append(f"{path}: possible embedded secret")
    return errors


def main() -> int:
    """Run portfolio validation."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PORTFOLIO_ROOT)
    args = parser.parse_args()
    errors = validate_portfolio(args.root.resolve())
    if errors:
        print(f"portfolio validation: FAIL ({len(errors)} errors)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("portfolio validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
