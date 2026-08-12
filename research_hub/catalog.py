"""Manifest-first catalog construction for immutable research artifacts."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from .config import HubConfig, SourceRoot, atomic_write_text, is_within, read_source_registry, stable_id


CATALOG_SCHEMA = "research_review_hub_catalog_v1"
TEXT_SUFFIXES = {".md", ".txt", ".log", ".yaml", ".yml"}
MEDIA_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".webm",
    ".mov", ".mkv", ".mp3", ".wav", ".ogg", ".pdf",
}
RESTRICTED_SUFFIXES = {".safetensors", ".pt", ".pth", ".ckpt", ".bin", ".tar", ".gz", ".zip"}
DOCUMENT_STATUS_RE = re.compile(r"^\|\s*状态\s*\|\s*([^|]+?)\s*\|\s*$", re.MULTILINE)
DOCUMENT_ID_RE = re.compile(r"^\|\s*实验 ID\s*\|\s*`?([^`|]+?)`?\s*\|\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"(?im)^#\s+(.+?)\s*$")
HTML_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")


class _WorkflowFieldParser(HTMLParser):
    """Extract simple data-field/data-value entries from recovery HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, list[str]] = {}
        self._field: str | None = None
        self._capture = False
        self._depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if "data-field" in attributes:
            self._field = attributes["data-field"]
        if attributes.get("data-value") == "true" and self._field:
            self._capture = True
            self._depth = 1
            self._text = []
        elif self._capture and tag not in {"meta", "link", "img", "br", "hr"}:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        self._depth -= 1
        if self._depth == 0:
            value = " ".join("".join(self._text).split())
            if self._field:
                self.fields.setdefault(self._field, []).append(value)
            self._field = None
            self._capture = False
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)


def build_catalog(config: HubConfig) -> dict[str, Any]:
    """Build a complete in-memory catalog without mutating source artifacts.

    Args:
        config: Resolved Hub configuration.

    Returns:
        JSON-serializable catalog containing source metadata and derived links.
    """

    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    for source in config.sources:
        if not source.path.exists():
            warnings.append(f"source_missing:{source.id}:{source.path}")
            continue
        if source.mode == "read_only_artifacts":
            for path in _iter_files(source.path, config.state_root):
                if path.resolve() == config.static_index.resolve():
                    continue
                record = _describe_artifact(config, source, path)
                artifacts.append(record)
                queue = _queue_from_artifact(config, record)
                if queue is not None:
                    queues.append(queue)
        elif source.mode == "experiment_documents":
            documents.extend(_scan_documents(config, source))
        elif source.mode == "portfolio_evidence":
            documents.extend(_scan_portfolio_workstreams(config, source))
    media_root = config.state_root / "media"
    if media_root.is_dir():
        hub_media = SourceRoot("hub_media", media_root, "hub_owned_media")
        for path in _iter_files(media_root, config.state_root / "media" / "_never_matches"):
            artifacts.append(_describe_artifact(config, hub_media, path))
    runs = _scan_runs(config, warnings)
    repositories = _repository_statuses(config)
    artifacts.sort(key=lambda item: (item["relative_path"], item["id"]))
    documents.sort(key=lambda item: (item["title"].casefold(), item["path"]))
    queues.sort(key=lambda item: (item["title"].casefold(), item["id"]))
    return {
        "schema_version": CATALOG_SCHEMA,
        "generated_at": _now(),
        "source_roots": [
            {"id": source.id, "path": str(source.path), "mode": source.mode, "exists": source.path.exists()}
            for source in config.sources
        ],
        "settings": {
            "registry_path": str(config.portfolio_root / "research_hub_sources.json"),
            "workspace_root": str(config.workspace_root),
            "source_registry": read_source_registry(config.portfolio_root),
            "write_mode": "loopback_service_required_for_reindex",
        },
        "summary": _summary(artifacts, documents, runs, queues),
        "repositories": repositories,
        "workstreams": _workstreams(config),
        "documents": documents,
        "runs": runs,
        "artifacts": artifacts,
        "queues": queues,
        "warnings": warnings,
    }


def write_catalog(config: HubConfig, catalog: dict[str, Any]) -> None:
    """Write derived JSON and SQLite catalog files atomically.

    Args:
        config: Resolved Hub configuration.
        catalog: Value returned by :func:`build_catalog`.
    """

    config.ensure_state_root()
    atomic_write_text(config.catalog_json, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    _write_sqlite(config.catalog_sqlite, catalog)


def scan_and_write(config: HubConfig) -> dict[str, Any]:
    """Rebuild and persist a catalog from all allowlisted sources."""

    catalog = build_catalog(config)
    write_catalog(config, catalog)
    return catalog


def load_catalog(config: HubConfig) -> dict[str, Any]:
    """Load the last generated catalog, or create one if absent."""

    if not config.catalog_json.is_file():
        return scan_and_write(config)
    return json.loads(config.catalog_json.read_text(encoding="utf-8"))


def search_catalog(config: HubConfig, query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search catalog records through SQLite FTS5 with a safe fallback.

    Args:
        config: Resolved Hub configuration.
        query: User search text.
        limit: Maximum number of records to return.

    Returns:
        Matching lightweight records ordered by FTS relevance when available.
    """

    if not config.catalog_sqlite.is_file():
        scan_and_write(config)
    normalized = " ".join(query.split())
    if not normalized:
        return []
    connection = sqlite3.connect(config.catalog_sqlite)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                "SELECT record_id, record_type, title, path, payload "
                "FROM search_fts WHERE search_fts MATCH ? LIMIT ?",
                (_fts_query(normalized), min(max(limit, 1), 200)),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = connection.execute(
                "SELECT record_id, record_type, title, path, payload FROM records "
                "WHERE lower(title || ' ' || body) LIKE lower(?) LIMIT ?",
                (f"%{normalized}%", min(max(limit, 1), 200)),
            ).fetchall()
    finally:
        connection.close()
    return [
        {
            "id": row["record_id"],
            "type": row["record_type"],
            "title": row["title"],
            "path": row["path"],
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]


def _iter_files(root: Path, excluded_root: Path) -> Iterator[Path]:
    """Yield files below a root while never descending into Hub state."""

    for directory, names, filenames in os.walk(root):
        current = Path(directory)
        names[:] = [name for name in names if not is_within(current / name, excluded_root)]
        for name in filenames:
            yield current / name


def _describe_artifact(config: HubConfig, source: SourceRoot, path: Path) -> dict[str, Any]:
    """Describe one artifact using bounded reads only.

    Large checkpoints and archives are intentionally represented as restricted
    metadata rather than browser-openable content.
    """

    stat = path.stat()
    relative = path.relative_to(config.artifact_root).as_posix()
    suffix = path.suffix.lower()
    kind = _artifact_kind(path, suffix)
    record: dict[str, Any] = {
        "id": stable_id("artifact", relative),
        "source_id": source.id,
        "relative_path": relative,
        "path": str(path.resolve()),
        "href": quote(relative, safe="/"),
        "extension": suffix,
        "kind": kind,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "openable": kind != "restricted",
        "title": path.name,
        "metadata": {},
    }
    if suffix == ".html":
        record["title"] = _html_title(path) or path.name
    elif suffix == ".json":
        record["metadata"] = _json_metadata(path, config.limits["json_parse_bytes"])
        record["title"] = str(record["metadata"].get("title") or path.name)
    elif suffix == ".jsonl":
        record["metadata"] = _jsonl_metadata(path, config.limits["jsonl_summary_bytes"])
        schema = record["metadata"].get("schema_version")
        record["title"] = str(schema or path.name)
    return record


def _artifact_kind(path: Path, suffix: str) -> str:
    """Classify artifact media without treating filename as scientific evidence."""

    lowered = path.name.lower()
    if suffix in RESTRICTED_SUFFIXES or "checkpoint" in lowered:
        return "restricted"
    if suffix == ".html":
        return "html"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in MEDIA_SUFFIXES:
        return "media"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return "other"


def _html_title(path: Path) -> str | None:
    """Read an HTML title from a bounded prefix, including one-line reports."""

    try:
        text = path.open("rb").read(256 * 1024).decode("utf-8", errors="replace")
    except OSError:
        return None
    match = HTML_TITLE_RE.search(text)
    return " ".join(match.group(1).split()) if match else None


def _json_metadata(path: Path, limit: int) -> dict[str, Any]:
    """Extract stable scalar JSON metadata when a report is small enough."""

    if path.stat().st_size > limit:
        return {"parse_state": "skipped_size"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"parse_state": "invalid", "error": type(exc).__name__}
    if not isinstance(value, dict):
        return {"parse_state": "non_object"}
    selected = {key: value[key] for key in ("schema_version", "run_id", "phase", "status", "title") if key in value}
    if "artifacts" in value and isinstance(value["artifacts"], list):
        selected["artifact_count"] = len(value["artifacts"])
    if "failure_count" in value:
        selected["failure_count"] = value["failure_count"]
    return selected


def _jsonl_metadata(path: Path, summary_limit: int) -> dict[str, Any]:
    """Read JSONL schema and small-queue status counts with bounded streaming."""

    result: dict[str, Any] = {"parse_state": "empty"}
    status_counts: Counter[str] = Counter()
    rows = 0
    if path.stat().st_size > summary_limit:
        result["parse_state"] = "schema_only_large"
        summary_limit = 512 * 1024
    consumed = 0
    try:
        with path.open("rb") as handle:
            for raw in handle:
                consumed += len(raw)
                if consumed > summary_limit:
                    break
                if not raw.strip():
                    continue
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    result["parse_state"] = "non_object_row"
                    break
                if "fields" not in result:
                    result["fields"] = sorted(value)[:96]
                    result["schema_version"] = value.get("schema_version")
                    result["id_field"] = _id_field(value)
                    result["parse_state"] = "ok"
                status = value.get("review_status") or value.get("status")
                if isinstance(status, str):
                    status_counts[status] += 1
                rows += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"parse_state": "invalid", "error": type(exc).__name__}
    if rows:
        result["sampled_row_count"] = rows
    if status_counts:
        result["status_counts"] = dict(sorted(status_counts.items()))
    return result


def _queue_from_artifact(config: HubConfig, artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Create a non-mutating review queue descriptor for recognized JSONL files."""

    if artifact["kind"] != "jsonl":
        return None
    metadata = artifact.get("metadata", {})
    fields = set(metadata.get("fields", []))
    filename = artifact["relative_path"].lower()
    is_queue = "review_status" in fields or "queue" in filename or "diagnosis" in filename
    if not is_queue or not metadata.get("id_field"):
        return None
    adapter = "generic_jsonl_review_v1"
    if metadata.get("schema_version") == "urbannav_benchmark_slice_review_diagnosis_v1":
        adapter = "citywalker_diagnosis_v1"
    elif "action_reconciliation" in filename:
        adapter = "reasoning_reconciliation_v1"
    return {
        "id": stable_id("queue", artifact["relative_path"]),
        "artifact_id": artifact["id"],
        "path": artifact["path"],
        "relative_path": artifact["relative_path"],
        "title": Path(artifact["relative_path"]).name,
        "adapter": adapter,
        "id_field": metadata["id_field"],
        "schema_version": metadata.get("schema_version"),
        "sampled_row_count": metadata.get("sampled_row_count"),
        "source_status_counts": metadata.get("status_counts", {}),
    }


def _scan_documents(config: HubConfig, source: SourceRoot) -> list[dict[str, Any]]:
    """Catalog Markdown experiments while allowing edits only for canonical records."""

    documents: list[dict[str, Any]] = []
    for path in sorted(source.path.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(config.workspace_root).as_posix()
        title_match = TITLE_RE.search(text)
        status_match = DOCUMENT_STATUS_RE.search(text)
        identifier_match = DOCUMENT_ID_RE.search(text)
        canonical = "experiment_record_version: 1" in text
        documents.append(
            {
                "id": stable_id("document", relative),
                "source_id": source.id,
                "path": str(path.resolve()),
                "relative_path": relative,
                "href": path.resolve().as_uri(),
                "title": title_match.group(1).strip() if title_match else path.stem,
                "experiment_id": identifier_match.group(1).strip() if identifier_match else None,
                "status": status_match.group(1).strip() if status_match else None,
                "canonical_experiment_record": canonical,
                "writable": canonical,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            }
        )
    return documents


def _scan_portfolio_workstreams(config: HubConfig, source: SourceRoot) -> list[dict[str, Any]]:
    """Expose recovery documents as read-only catalog documents."""

    documents: list[dict[str, Any]] = []
    for path in sorted((config.portfolio_root / "workstreams").glob("*/*.html")):
        relative = path.relative_to(config.workspace_root).as_posix()
        documents.append(
            {
                "id": stable_id("workflow", relative),
                "source_id": source.id,
                "path": str(path.resolve()),
                "relative_path": relative,
                "href": path.resolve().as_uri(),
                "title": _html_title(path) or path.stem,
                "canonical_experiment_record": False,
                "writable": False,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            }
        )
    return documents


def _scan_runs(config: HubConfig, warnings: list[str]) -> list[dict[str, Any]]:
    """Load small portfolio run manifests without dereferencing remote artifacts."""

    runs: list[dict[str, Any]] = []
    for path in sorted((config.portfolio_root / "runs").glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"run_invalid:{path}:{type(exc).__name__}")
            continue
        runs.append(
            {
                "id": str(raw.get("run_id", path.stem)),
                "path": str(path.resolve()),
                "href": path.resolve().as_uri(),
                "objective": str(raw.get("objective", "")),
                "status": raw.get("status"),
                "implementation_state": raw.get("implementation_state"),
                "verification_level": raw.get("verification_level"),
                "validation_scope": raw.get("validation_scope"),
                "workstream_id": raw.get("workstream_id"),
                "experiment_record": raw.get("experiment_record"),
                "artifact_count": len(raw.get("artifacts", [])),
                "gate_count": len(raw.get("gates", [])),
            }
        )
    return runs


def _workstreams(config: HubConfig) -> list[dict[str, Any]]:
    """Extract current state fields from all workstream STATUS documents."""

    result: list[dict[str, Any]] = []
    for path in sorted((config.portfolio_root / "workstreams").glob("*/STATUS.html")):
        parser = _WorkflowFieldParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        fields = {key: values[0] for key, values in parser.fields.items() if len(values) == 1}
        result.append(
            {
                "id": fields.get("workstream-id", path.parent.name),
                "path": str(path.resolve()),
                "href": path.resolve().as_uri(),
                "project": fields.get("project"),
                "execution_state": fields.get("execution-state"),
                "implementation_state": fields.get("implementation-state"),
                "verification_level": fields.get("verification-level"),
                "validation_scope": fields.get("validation-scope"),
                "next_atomic_step": fields.get("next-atomic-step"),
            }
        )
    return result


def _repository_statuses(config: HubConfig) -> list[dict[str, Any]]:
    """Return live Git summaries without changing any checkout."""

    candidates = [config.portfolio_root, config.workspace_root / "ms-swift", config.workspace_root / "Urban-Nav-SR"]
    records: list[dict[str, Any]] = []
    for path in candidates:
        command = ["git", "-C", str(path), "status", "--short", "--branch"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        records.append(
            {
                "name": path.name,
                "path": str(path),
                "git_available": result.returncode == 0,
                "status": result.stdout.splitlines() if result.returncode == 0 else [],
            }
        )
    return records


def _summary(
    artifacts: list[dict[str, Any]], documents: list[dict[str, Any]], runs: list[dict[str, Any]], queues: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return dashboard-safe aggregate counts only."""

    kinds = Counter(item["kind"] for item in artifacts)
    return {
        "artifact_count": len(artifacts),
        "artifact_kinds": dict(sorted(kinds.items())),
        "document_count": len(documents),
        "writable_document_count": sum(1 for item in documents if item.get("writable")),
        "run_count": len(runs),
        "queue_count": len(queues),
        "html_count": kinds.get("html", 0),
    }


def _write_sqlite(path: Path, catalog: dict[str, Any]) -> None:
    """Build a fresh SQLite FTS5 index and replace the previous cache atomically."""

    descriptor, temporary_name = tempfile.mkstemp(prefix=".catalog.", suffix=".sqlite", dir=str(path.parent))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                "CREATE TABLE records (record_id TEXT PRIMARY KEY, record_type TEXT, title TEXT, body TEXT, path TEXT, payload TEXT);"
                "CREATE VIRTUAL TABLE search_fts USING fts5(record_id UNINDEXED, record_type UNINDEXED, title, body, path UNINDEXED, payload UNINDEXED);"
            )
            for record_type, records in (("artifact", catalog["artifacts"]), ("document", catalog["documents"]), ("run", catalog["runs"]), ("queue", catalog["queues"]), ("workstream", catalog["workstreams"])):
                for record in records:
                    title = str(record.get("title") or record.get("id") or "")
                    body = " ".join(str(value) for key, value in record.items() if key not in {"path", "href", "payload"} and isinstance(value, (str, int, float)))
                    payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
                    row = (str(record["id"]), record_type, title, body, str(record.get("path", "")), payload)
                    connection.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", row)
                    connection.execute("INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)", row)
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _id_field(value: dict[str, Any]) -> str | None:
    """Select a stable review row identifier from known canonical fields."""

    for name in ("sample_id", "id", "source_group_id", "audit_id", "queue_key"):
        if isinstance(value.get(name), (str, int)):
            return name
    return None


def _fts_query(query: str) -> str:
    """Build a conservative AND query from user words for SQLite FTS5."""

    tokens = re.findall(r"[\w\u4e00-\u9fff.-]+", query, flags=re.UNICODE)
    return " AND ".join(f'"{token.replace(chr(34), "")}"' for token in tokens) or '""'


def _now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()
