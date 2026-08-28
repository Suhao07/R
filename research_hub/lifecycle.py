"""Recoverable archive, restore, and guarded deletion for Hub records."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import HubConfig, atomic_write_text, is_within, sha256_file, stable_id


LIFECYCLE_SCHEMA = "research_hub_archive_record_v1"
ARCHIVABLE_RECORD_TYPES = {"artifact", "document", "experiment"}


class LifecycleError(RuntimeError):
    """Raised when an archive operation would cross a configured safety boundary."""


class LifecycleStore:
    """Manage recoverable lifecycle actions in Hub-owned state.

    Args:
        config: Resolved Hub filesystem configuration.
    """

    def __init__(self, config: HubConfig) -> None:
        self.config = config

    def records(self) -> list[dict[str, Any]]:
        """Return retained archive manifests, newest first.

        Returns:
            JSON-safe lifecycle records. Invalid manifests are ignored so one
            damaged record cannot make the whole catalog unavailable.
        """

        root = self.config.state_root / "archive"
        if not root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in root.glob("*/manifest.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("schema_version") == LIFECYCLE_SCHEMA:
                records.append(value)
        records.sort(key=lambda item: str(item.get("archived_at", "")), reverse=True)
        return records

    def archive(
        self,
        record_type: str,
        record_id: str,
        catalog: dict[str, Any],
    ) -> dict[str, Any]:
        """Move one active record into recoverable Hub-owned archive state.

        Args:
            record_type: One of ``document``, ``artifact``, or ``experiment``.
            record_id: Stable active catalog identifier.
            catalog: Current catalog used to resolve the exact source path.

        Returns:
            Persisted archive manifest.

        Raises:
            LifecycleError: If the record is absent, not archivable, unsafe, or
                already moved.
        """

        record = self._active_record(record_type, record_id, catalog)
        source = self._safe_active_path(record_type, record)
        if not record.get("archivable"):
            raise LifecycleError(str(record.get("read_only_reason") or "record is not archivable"))
        self.config.ensure_state_root()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive_id = stable_id("archive", f"{record_type}:{record_id}:{stamp}")
        directory = self.config.state_root / "archive" / archive_id
        directory.mkdir(parents=True, exist_ok=False)
        payload = directory / "payload"
        manifest: dict[str, Any] = {
            "schema_version": LIFECYCLE_SCHEMA,
            "archive_id": archive_id,
            "status": "preparing",
            "record_type": record_type,
            "record_id": record_id,
            "title": str(record.get("title") or record_id),
            "project_id": str(record.get("project_id") or "unassigned"),
            "workstream_id": str(record.get("workstream_id") or "unassigned"),
            "source_id": record.get("source_id"),
            "original_path": str(source),
            "original_relative_path": str(
                record.get("relative_path") or record.get("relative_root") or source.name
            ),
            "archived_path": str(payload.relative_to(self.config.artifact_root)),
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "is_directory": source.is_dir(),
            "size_bytes": source.stat().st_size if source.is_file() else None,
            "sha256": sha256_file(source) if source.is_file() else None,
        }
        self._write_manifest(directory, manifest)
        try:
            shutil.move(str(source), str(payload))
        except (OSError, shutil.Error) as exc:
            manifest["status"] = "archive_failed"
            manifest["error"] = type(exc).__name__
            self._write_manifest(directory, manifest)
            raise LifecycleError("unable to move record into recoverable archive") from exc
        manifest["status"] = "archived"
        self._write_manifest(directory, manifest)
        return manifest

    def restore(self, archive_id: str) -> dict[str, Any]:
        """Restore one archived payload to its original allowlisted path.

        Args:
            archive_id: Stable archive identifier.

        Returns:
            Updated lifecycle manifest.

        Raises:
            LifecycleError: If the archive is missing, unsafe, already consumed,
                or its original path is occupied.
        """

        directory, manifest = self._manifest(archive_id)
        if manifest.get("status") != "archived":
            raise LifecycleError("archive is not available for restore")
        payload = self._safe_payload(directory, manifest)
        target = self._safe_restore_target(str(manifest.get("record_type")), manifest)
        if target.exists() or target.is_symlink():
            raise LifecycleError("original path is occupied; restore refused")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(payload), str(target))
        except (OSError, shutil.Error) as exc:
            raise LifecycleError("unable to restore archived payload") from exc
        manifest["status"] = "restored"
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        self._write_manifest(directory, manifest)
        return manifest

    def permanently_delete(self, archive_id: str, confirmation: str) -> dict[str, Any]:
        """Destroy only an already archived payload after exact confirmation.

        Args:
            archive_id: Stable archive identifier.
            confirmation: Must equal ``DELETE <archive_id>`` exactly.

        Returns:
            Updated lifecycle manifest retained as an audit tombstone.

        Raises:
            LifecycleError: If confirmation, lifecycle state, or payload path is
                invalid.
        """

        expected = f"DELETE {archive_id}"
        if confirmation != expected:
            raise LifecycleError(f"permanent deletion requires exact confirmation: {expected}")
        directory, manifest = self._manifest(archive_id)
        if manifest.get("status") != "archived":
            raise LifecycleError("only an archived payload may be permanently deleted")
        payload = self._safe_payload(directory, manifest)
        if payload.is_dir():
            shutil.rmtree(payload)
        else:
            payload.unlink()
        manifest["status"] = "deleted"
        manifest["deleted_at"] = datetime.now(timezone.utc).isoformat()
        self._write_manifest(directory, manifest)
        return manifest

    def _active_record(
        self,
        record_type: str,
        record_id: str,
        catalog: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve one record from its type-specific active catalog collection."""

        collections = {
            "artifact": "artifacts",
            "document": "documents",
            "experiment": "experiments",
        }
        collection = collections.get(record_type)
        if collection is None:
            raise LifecycleError(f"unsupported lifecycle record type: {record_type}")
        record = next(
            (item for item in catalog.get(collection, []) if item.get("id") == record_id),
            None,
        )
        if not isinstance(record, dict):
            raise LifecycleError("active record not found")
        return record

    def _safe_active_path(self, record_type: str, record: dict[str, Any]) -> Path:
        """Revalidate active path ownership without trusting catalog bytes alone."""

        raw = record.get("root") if record_type == "experiment" else record.get("path")
        path = Path(str(raw))
        if path.is_symlink() or not path.exists():
            raise LifecycleError("record path is missing or is a symlink")
        if record_type == "document":
            source = self.config.source_for(path)
            if source is None or source.mode != "experiment_documents" or not path.is_file():
                raise LifecycleError("document is outside an editable project source")
        else:
            if is_within(path, self.config.state_root) or not is_within(path, self.config.artifact_root):
                raise LifecycleError("artifact path is outside the active artifact root")
            if record_type == "artifact" and not path.is_file():
                raise LifecycleError("artifact must be a regular file")
            if record_type == "experiment" and not path.is_dir():
                raise LifecycleError("experiment must be a regular directory")
        return path.resolve()

    def _manifest(self, archive_id: str) -> tuple[Path, dict[str, Any]]:
        """Load one exact manifest below the Hub archive root."""

        if not archive_id.startswith("archive_"):
            raise LifecycleError("invalid archive identifier")
        directory = self.config.state_root / "archive" / archive_id
        path = directory / "manifest.json"
        if path.is_symlink() or not path.is_file() or not is_within(path, self.config.state_root / "archive"):
            raise LifecycleError("archive manifest not found")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LifecycleError("archive manifest is unreadable") from exc
        if not isinstance(value, dict) or value.get("archive_id") != archive_id:
            raise LifecycleError("archive manifest identity mismatch")
        return directory.resolve(), value

    def _safe_payload(self, directory: Path, manifest: dict[str, Any]) -> Path:
        """Resolve the one payload owned by an archive record."""

        payload = directory / "payload"
        if payload.is_symlink() or not payload.exists() or not is_within(payload, directory):
            raise LifecycleError("archived payload is missing or unsafe")
        expected = Path(str(manifest.get("archived_path", "")))
        try:
            expected_path = (self.config.artifact_root / expected).resolve()
        except OSError as exc:
            raise LifecycleError("archive payload path is invalid") from exc
        if expected_path != payload.resolve():
            raise LifecycleError("archive payload identity mismatch")
        return payload.resolve()

    def _safe_restore_target(self, record_type: str, manifest: dict[str, Any]) -> Path:
        """Validate the original path against the currently active source registry."""

        if record_type not in ARCHIVABLE_RECORD_TYPES:
            raise LifecycleError("unsupported archived record type")
        target = Path(str(manifest.get("original_path", "")))
        if not target.is_absolute():
            raise LifecycleError("archive original path must be absolute")
        if record_type == "document":
            source = self.config.source_for(target)
            if source is None or source.mode != "experiment_documents":
                raise LifecycleError("document restore target is no longer editable")
        elif is_within(target, self.config.state_root) or not is_within(target, self.config.artifact_root):
            raise LifecycleError("artifact restore target is outside the active artifact root")
        return target.resolve(strict=False)

    @staticmethod
    def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
        """Atomically persist one lifecycle manifest."""

        atomic_write_text(
            directory / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
