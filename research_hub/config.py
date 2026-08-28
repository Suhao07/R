"""Configuration and filesystem invariants for the local research hub."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_PORTFOLIO_ROOT = PACKAGE_ROOT.parent
SOURCE_REGISTRY_SCHEMA = "research_hub_source_registry_v2"
SOURCE_MODES = {"read_only_artifacts", "experiment_documents", "portfolio_evidence"}


@dataclass(frozen=True)
class SourceRoot:
    """One allowlisted source tree and its mutation policy.

    Args:
        id: Stable identifier used by catalog records.
        path: Resolved local filesystem root.
        mode: Source ownership and mutability category.
        project_id: Project grouping key shown in the Hub.
        workstream_id: Default workstream grouping key for records in the root.
    """

    id: str
    path: Path
    mode: str
    project_id: str = "unassigned"
    workstream_id: str = "unassigned"


@dataclass(frozen=True)
class HubConfig:
    """Resolved paths and conservative size limits for one Hub instance.

    Args:
        portfolio_root: The Git-managed ResearchWorkflow control repository.
        workspace_root: Parent directory containing the independent checkouts.
        artifact_root: External, non-Git review artifact directory.
        state_root: Hub-owned derived state under the artifact root.
        sources: Allowlisted read/write source roots.
        limits: Byte limits used to avoid loading large raw evidence files.
    """

    portfolio_root: Path
    workspace_root: Path
    artifact_root: Path
    state_root: Path
    sources: tuple[SourceRoot, ...]
    limits: dict[str, int]

    @property
    def catalog_json(self) -> Path:
        """Return the portable catalog snapshot path."""

        return self.state_root / "catalog.json"

    @property
    def catalog_sqlite(self) -> Path:
        """Return the rebuildable SQLite index path."""

        return self.state_root / "catalog.sqlite"

    @property
    def static_index(self) -> Path:
        """Return the user-facing static homepage path."""

        return self.artifact_root / "index.html"

    @property
    def document_roots(self) -> tuple[Path, ...]:
        """Return roots whose canonical experiment Markdown may be edited."""

        return tuple(source.path for source in self.sources if source.mode == "experiment_documents")

    def source_for(self, path: Path) -> SourceRoot | None:
        """Return the allowlisted source containing ``path`` when any.

        Args:
            path: Existing or candidate path to classify.

        Returns:
            Matching source root, or ``None`` if the path is outside all roots.
        """

        candidate = path.resolve()
        for source in self.sources:
            if is_within(candidate, source.path):
                return source
        return None

    def ensure_state_root(self) -> None:
        """Create only Hub-owned state directories when a write is requested."""

        self.state_root.mkdir(parents=True, exist_ok=True)
        for name in ("review_events", "exports", "history", "media"):
            (self.state_root / name).mkdir(exist_ok=True)


def load_config(portfolio_root: Path | None = None) -> HubConfig:
    """Load and resolve the versioned source registry.

    Args:
        portfolio_root: Optional alternate control-repository root, mainly for
            isolated tests.

    Returns:
        Fully resolved configuration with no untrusted relative paths.

    Raises:
        ValueError: If the registry schema or its conservative limits are invalid.
    """

    root = (portfolio_root or DEFAULT_PORTFOLIO_ROOT).resolve()
    raw = read_source_registry(root)
    return _config_from_registry(root, raw)


def read_source_registry(portfolio_root: Path) -> dict[str, Any]:
    """Load the versioned, user-facing local-source configuration.

    Args:
        portfolio_root: ResearchWorkflow repository containing the registry.

    Returns:
        A JSON-safe registry that has passed the Hub boundary checks.
    """

    root = portfolio_root.resolve()
    registry_path = root / "research_hub_sources.json"
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unreadable Hub source registry: {registry_path}") from exc
    return validate_source_registry(root, raw)


def write_source_registry(portfolio_root: Path, raw: dict[str, Any]) -> HubConfig:
    """Validate then atomically persist source configuration owned by the Hub.

    The registry may only point to local paths inside this ``Code`` workspace.
    This avoids turning a convenience settings UI into a reader for arbitrary
    home-directory files.  A successful save returns the newly active config.

    Args:
        portfolio_root: ResearchWorkflow repository containing the registry.
        raw: Candidate JSON object supplied by the local settings UI.

    Returns:
        Newly resolved configuration.
    """

    root = portfolio_root.resolve()
    normalized = validate_source_registry(root, raw)
    atomic_write_text(root / "research_hub_sources.json", json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    return _config_from_registry(root, normalized)


def validate_source_registry(portfolio_root: Path, raw: Any) -> dict[str, Any]:
    """Normalize and validate the editable local-source registry.

    Args:
        portfolio_root: ResearchWorkflow repository containing the registry.
        raw: Candidate decoded JSON value.

    Returns:
        A normalized registry safe to persist or resolve.

    Raises:
        ValueError: If schema, paths, modes, or scanning limits are invalid.
    """

    root = portfolio_root.resolve()
    workspace = root.parent
    if not isinstance(raw, dict) or raw.get("schema_version") != SOURCE_REGISTRY_SCHEMA:
        raise ValueError("Unsupported Hub source registry schema")
    artifact_value = raw.get("artifact_root")
    if not isinstance(artifact_value, str) or not artifact_value.strip():
        raise ValueError("artifact_root must be a non-empty path string")
    artifact_root = _resolve_registry_path(root, artifact_value)
    if not is_within(artifact_root, workspace):
        raise ValueError("artifact_root must stay inside the local Code workspace")
    state_relative = Path(str(raw.get("hub_state_relative", "_research_hub")))
    if state_relative.is_absolute() or ".." in state_relative.parts or not state_relative.parts:
        raise ValueError("hub_state_relative must stay inside artifact_root")
    raw_sources = raw.get("scan_roots")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Hub source registry has no scan_roots")
    normalized_sources: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    artifact_sources = 0
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("each scan_roots entry must be an object")
        source_id, path_value, mode = item.get("id"), item.get("path"), item.get("mode")
        project_id, workstream_id = item.get("project_id"), item.get("workstream_id")
        if not isinstance(source_id, str) or not source_id or not source_id.replace("_", "").isalnum():
            raise ValueError("scan root id must use letters, digits, or underscores")
        if source_id in seen_ids:
            raise ValueError(f"duplicate scan root id: {source_id}")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError(f"scan root {source_id} needs a path")
        if mode not in SOURCE_MODES:
            raise ValueError(f"scan root {source_id} has unsupported mode: {mode}")
        for field, value in (("project_id", project_id), ("workstream_id", workstream_id)):
            if not isinstance(value, str) or not value or not value.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"scan root {source_id} needs a slug-like {field}")
        resolved = _resolve_registry_path(root, path_value)
        if not is_within(resolved, workspace):
            raise ValueError(f"scan root {source_id} must stay inside the local Code workspace")
        if mode == "read_only_artifacts":
            artifact_sources += 1
            if resolved != artifact_root:
                raise ValueError("the read_only_artifacts path must equal artifact_root")
        seen_ids.add(source_id)
        normalized_sources.append(
            {
                "id": source_id,
                "path": path_value,
                "mode": mode,
                "project_id": project_id,
                "workstream_id": workstream_id,
            }
        )
    if artifact_sources != 1:
        raise ValueError("exactly one read_only_artifacts root is required")
    raw_limits = raw.get("limits")
    if not isinstance(raw_limits, dict):
        raise ValueError("Hub source registry needs a limits object")
    required_limits = {
        "json_parse_bytes",
        "jsonl_summary_bytes",
        "queue_read_bytes",
        "attachment_upload_bytes",
    }
    try:
        normalized_limits = {key: int(raw_limits[key]) for key in required_limits}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Hub source registry has invalid limits") from exc
    if any(value <= 0 for value in normalized_limits.values()):
        raise ValueError("Hub source registry limits must be positive")
    return {
        "schema_version": SOURCE_REGISTRY_SCHEMA,
        "artifact_root": artifact_value,
        "hub_state_relative": state_relative.as_posix(),
        "scan_roots": normalized_sources,
        "limits": {key: normalized_limits[key] for key in sorted(normalized_limits)},
    }


def _config_from_registry(root: Path, raw: dict[str, Any]) -> HubConfig:
    """Resolve a previously validated registry into immutable path settings."""

    workspace = root.parent
    artifact_root = _resolve_registry_path(root, raw["artifact_root"])
    state_relative = Path(str(raw.get("hub_state_relative", "_research_hub")))
    if state_relative.is_absolute() or ".." in state_relative.parts:
        raise ValueError("hub_state_relative must stay inside artifact_root")
    state_root = artifact_root / state_relative
    sources = tuple(
        SourceRoot(
            id=str(item["id"]),
            path=_resolve_registry_path(root, item["path"]),
            mode=str(item["mode"]),
            project_id=str(item["project_id"]),
            workstream_id=str(item["workstream_id"]),
        )
        for item in raw.get("scan_roots", [])
    )
    limits = {key: int(value) for key, value in raw.get("limits", {}).items()}
    return HubConfig(root, workspace, artifact_root, state_root, sources, limits)


def is_within(candidate: Path, root: Path) -> bool:
    """Return whether ``candidate`` resolves inside ``root``.

    This guards document writes and artifact serving against traversal and
    symlink escapes without relying on Python 3.10's ``Path.is_relative_to``.
    """

    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def stable_id(prefix: str, value: str) -> str:
    """Build a deterministic opaque identifier from a local relative path."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest without materializing a file.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text file in its existing directory.

    Args:
        path: Destination path.
        text: Complete UTF-8 content to store.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve_registry_path(root: Path, value: Any) -> Path:
    """Resolve one registry path relative to the control repository."""

    candidate = Path(str(value))
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def json_safe(value: Any) -> Any:
    """Return a JSON-safe version of values assembled from filesystem metadata."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [json_safe(item) for item in value]
    return value
