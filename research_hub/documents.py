"""Safe canonical experiment Markdown preview and atomic writeback."""

from __future__ import annotations

import difflib
import gzip
import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import load_catalog
from .config import HubConfig, atomic_write_text, is_within, sha256_file, stable_id


class DocumentError(RuntimeError):
    """Base exception for a rejected document operation."""


class DocumentConflictError(DocumentError):
    """Raised when on-disk bytes changed after the editor loaded a document."""


class DocumentValidationError(DocumentError):
    """Raised when candidate Markdown fails the existing record contract."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class DocumentStore:
    """Constrain all Markdown mutations to canonical experiment records.

    Args:
        config: Resolved Hub filesystem configuration.
        session_token_key: Per-server random key used to bind preview approvals
            to exact content and base SHA-256 values.
    """

    def __init__(self, config: HubConfig, session_token_key: bytes) -> None:
        self.config = config
        self.session_token_key = session_token_key

    def get(self, document_id: str) -> dict[str, Any]:
        """Load one allowlisted canonical record and its content digest.

        Args:
            document_id: Stable catalog document identifier.

        Returns:
            Document metadata, UTF-8 content, and current SHA-256.

        Raises:
            DocumentError: If the ID is absent, read-only, outside the allowlist,
                a symlink, or no longer a canonical experiment record.
        """

        record = self._record(document_id)
        path = self._safe_path(record)
        content = path.read_text(encoding="utf-8")
        return {
            "id": record["id"],
            "title": record["title"],
            "relative_path": record["relative_path"],
            "content": content,
            "sha256": _sha256_text(content),
        }

    def preview(self, document_id: str, base_sha256: str, content: str) -> dict[str, Any]:
        """Validate candidate content and return a content-bound save token.

        Args:
            document_id: Catalog document identifier.
            base_sha256: Hash returned by :meth:`get`.
            content: Full proposed Markdown content.

        Returns:
            Validation result, unified diff, and token required by :meth:`save`.

        Raises:
            DocumentConflictError: If the source changed before preview.
        """

        current = self.get(document_id)
        if current["sha256"] != base_sha256:
            raise DocumentConflictError("document changed on disk; reload before saving")
        errors = _validate_candidate(self.config, content)
        token = self._token(document_id, base_sha256, content)
        return {
            "ok": not errors,
            "validation_errors": errors,
            "diff": _unified_diff(current["content"], content, current["relative_path"]),
            "preview_token": token,
        }

    def save(
        self, document_id: str, base_sha256: str, content: str, preview_token: str
    ) -> dict[str, str]:
        """Back up then atomically replace one validated experiment record.

        Args:
            document_id: Catalog document identifier.
            base_sha256: Hash read by the editor.
            content: Candidate Markdown bytes.
            preview_token: Token returned for precisely this content by preview.

        Returns:
            New digest and Hub-relative backup path.

        Raises:
            DocumentConflictError: If bytes changed since preview.
            DocumentValidationError: If the final candidate violates the contract.
            DocumentError: If the preview token is not content-bound.
        """

        if not hmac.compare_digest(preview_token, self._token(document_id, base_sha256, content)):
            raise DocumentError("preview token does not match this content")
        current = self.get(document_id)
        if current["sha256"] != base_sha256:
            raise DocumentConflictError("document changed on disk; reload before saving")
        errors = _validate_candidate(self.config, content)
        if errors:
            raise DocumentValidationError(errors)
        record = self._record(document_id)
        path = self._safe_path(record)
        backup = self._backup(record, current["content"], base_sha256)
        _atomic_replace(path, content, path.stat().st_mode)
        return {"sha256": _sha256_text(content), "backup_path": str(backup.relative_to(self.config.artifact_root))}

    def _record(self, document_id: str) -> dict[str, Any]:
        """Resolve a writable document only from the latest catalog."""

        catalog = load_catalog(self.config)
        record = next((item for item in catalog["documents"] if item["id"] == document_id), None)
        if not record or not record.get("writable"):
            raise DocumentError("document is not a writable canonical experiment record")
        return record

    def _safe_path(self, record: dict[str, Any]) -> Path:
        """Enforce source root and no-symlink invariants for one record path."""

        path = Path(str(record["path"]))
        if path.is_symlink() or not path.is_file():
            raise DocumentError("document must be a regular file")
        if not any(is_within(path, root) for root in self.config.document_roots):
            raise DocumentError("document path is outside writable roots")
        text = path.read_text(encoding="utf-8")
        if "experiment_record_version: 1" not in text:
            raise DocumentError("document no longer declares experiment_record_version: 1")
        return path.resolve()

    def _token(self, document_id: str, base_sha256: str, content: str) -> str:
        """Bind a preview token to document identity, base bytes, and new bytes."""

        message = "\0".join((document_id, base_sha256, _sha256_text(content))).encode("utf-8")
        return hmac.new(self.session_token_key, message, hashlib.sha256).hexdigest()

    def _backup(self, record: dict[str, Any], content: str, digest: str) -> Path:
        """Store a recoverable, Hub-owned pre-write backup plus metadata."""

        self.config.ensure_state_root()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = self.config.state_root / "history" / record["id"] / stamp
        directory.mkdir(parents=True, exist_ok=False)
        backup = directory / "before.md.gz"
        with gzip.open(backup, "wt", encoding="utf-8", newline="") as handle:
            handle.write(content)
        atomic_write_text(
            directory / "metadata.json",
            json.dumps(
                {
                    "schema_version": "research_hub_document_backup_v1",
                    "document_id": record["id"],
                    "source_path": record["path"],
                    "sha256": digest,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        return directory


def _validate_candidate(config: HubConfig, content: str) -> list[str]:
    """Run the existing validator on temporary candidate bytes, never source files."""

    if not isinstance(content, str) or len(content.encode("utf-8")) > 5 * 1024 * 1024:
        return ["candidate Markdown must be UTF-8 text no larger than 5 MiB"]
    scripts_root = str(config.portfolio_root)
    import sys

    if scripts_root not in sys.path:
        sys.path.insert(0, scripts_root)
    from scripts.validate_experiment_record import validate_experiment_record

    descriptor, temporary_name = tempfile.mkstemp(prefix="research_hub_candidate_", suffix=".md")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return validate_experiment_record(temporary)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_replace(path: Path, content: str, mode: int) -> None:
    """Write a source-adjacent temporary file, fsync it, then replace atomically."""

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.research-hub-", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256_text(content: str) -> str:
    """Return the canonical UTF-8 digest of document content."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unified_diff(before: str, after: str, relative_path: str) -> str:
    """Create a bounded unified diff suitable for local human review."""

    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{relative_path}",
        tofile=f"b/{relative_path}",
        n=3,
    )
    diff = "".join(lines)
    return diff if len(diff) <= 512 * 1024 else diff[:512 * 1024] + "\n… diff truncated …\n"
