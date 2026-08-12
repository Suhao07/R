"""Loopback-only HTTP API and media server for the local research hub."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .catalog import load_catalog, scan_and_write, search_catalog, write_catalog
from .config import HubConfig, is_within, read_source_registry, sha256_file, stable_id, write_source_registry
from .documents import DocumentConflictError, DocumentError, DocumentStore, DocumentValidationError
from .frontend import render_index
from .reviews import ReviewError, ReviewStore
from .rendering import render_document_pages


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@dataclass
class HubServerContext:
    """State shared by all request handlers for one local server.

    Args:
        config: Resolved Hub filesystem configuration.
        token: Random per-process token required for all write requests.
    """

    config: HubConfig
    token: str

    def __post_init__(self) -> None:
        self.documents = DocumentStore(self.config, self.token.encode("utf-8"))
        self.reviews = ReviewStore(self.config)

    def replace_config(self, config: HubConfig) -> None:
        """Activate a validated source registry without restarting the server."""

        self.config = config
        self.documents = DocumentStore(config, self.token.encode("utf-8"))
        self.reviews = ReviewStore(config)


class HubRequestHandler(BaseHTTPRequestHandler):
    """Serve Hub static views, allowlisted artifacts, and protected local APIs."""

    context: HubServerContext
    server_version = "ResearchReviewHub/1"

    def do_GET(self) -> None:  # noqa: N802
        """Handle static homepage and read-only API requests."""

        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                self._html(render_index(load_catalog(self.context.config), live=True))
                return
            if parsed.path == "/api/health":
                self._json({"ok": True, "loopback_only": True})
                return
            if parsed.path == "/api/catalog":
                self._json(load_catalog(self.context.config))
                return
            if parsed.path == "/api/settings":
                self._json(_settings_payload(self.context.config))
                return
            if parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._json({"results": search_catalog(self.context.config, query)})
                return
            if parsed.path.startswith("/api/artifacts/"):
                self._serve_artifact(unquote(parsed.path.rsplit("/", 1)[-1]))
                return
            if parsed.path.startswith("/api/hub-state/"):
                self._serve_hub_state(unquote(parsed.path[len("/api/hub-state/") :]))
                return
            if parsed.path.startswith("/api/documents/"):
                self._json(self.context.documents.get(unquote(parsed.path.rsplit("/", 1)[-1])))
                return
            if parsed.path.startswith("/api/queues/"):
                self._json(self.context.reviews.records(unquote(parsed.path.rsplit("/", 1)[-1])))
                return
            self._error(HTTPStatus.NOT_FOUND, "not found")
        except DocumentError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except ReviewError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # defensive API boundary; no traceback disclosure
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_HEAD(self) -> None:  # noqa: N802
        """Return the same safe metadata as GET without transmitting a body."""

        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        """Handle token-protected write and refresh requests."""

        parsed = urlparse(self.path)
        try:
            self._authorize_write()
            if parsed.path == "/api/documents/preview":
                value = self._read_json()
                self._json(
                    self.context.documents.preview(
                        str(value.get("id", "")), str(value.get("base_sha256", "")), value.get("content", "")
                    )
                )
                return
            if parsed.path == "/api/reviews":
                value = self._read_json()
                self._json(
                    self.context.reviews.append(
                        queue_id=str(value.get("queue_id", "")),
                        sample_id=str(value.get("sample_id", "")),
                        decision=str(value.get("decision", "")),
                        reviewer=str(value.get("reviewer", "")),
                        note=str(value.get("note", "")),
                        fields=value.get("fields", {}),
                        event_id=value.get("event_id"),
                    )
                )
                return
            if parsed.path == "/api/reviews/export":
                value = self._read_json()
                self._json(self.context.reviews.export(str(value.get("queue_id", ""))))
                return
            if parsed.path == "/api/reindex":
                catalog = scan_and_write(self.context.config)
                render_document_pages(self.context.config, catalog)
                write_catalog(self.context.config, catalog)
                self._json({"summary": catalog["summary"], "generated_at": catalog["generated_at"]})
                return
            if parsed.path == "/api/attachments":
                document_id = parse_qs(parsed.query).get("document_id", [""])[0]
                self._json(self._store_attachment(document_id))
                return
            self._error(HTTPStatus.NOT_FOUND, "not found")
        except DocumentConflictError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except DocumentValidationError as exc:
            self._json({"error": "document validation failed", "validation_errors": exc.errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except (DocumentError, ReviewError, ValueError) as exc:
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except PermissionError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except Exception as exc:  # defensive API boundary; no traceback disclosure
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_PUT(self) -> None:  # noqa: N802
        """Atomically save a canonical record or local source configuration."""

        parsed = urlparse(self.path)
        try:
            self._authorize_write()
            if parsed.path == "/api/settings":
                value = self._read_json()
                raw = value.get("source_registry")
                if not isinstance(raw, dict):
                    raise ValueError("source_registry must be a JSON object")
                config = write_source_registry(self.context.config.portfolio_root, raw)
                self.context.replace_config(config)
                catalog = scan_and_write(config)
                render_document_pages(config, catalog)
                write_catalog(config, catalog)
                self._json({"settings": _settings_payload(config), "summary": catalog["summary"]})
                return
            if not parsed.path.startswith("/api/documents/"):
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            value = self._read_json()
            result = self.context.documents.save(
                unquote(parsed.path.rsplit("/", 1)[-1]),
                str(value.get("base_sha256", "")),
                value.get("content", ""),
                str(value.get("preview_token", "")),
            )
            self._json(result)
        except DocumentConflictError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except DocumentValidationError as exc:
            self._json({"error": "document validation failed", "validation_errors": exc.errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except (DocumentError, ValueError) as exc:
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except PermissionError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _authorize_write(self) -> None:
        """Require same-loopback client, trusted origin, and session-bound token."""

        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            raise PermissionError("write requests are accepted only from loopback")
        token = self.headers.get("X-Research-Hub-Token", "")
        if not hmac.compare_digest(token, self.context.token):
            raise PermissionError("missing or invalid Research Hub session token")
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme != "http" or (parsed.hostname or "") not in LOOPBACK_HOSTS:
                raise PermissionError("write Origin must be loopback")

    def _read_json(self) -> dict[str, Any]:
        """Read a small JSON request body with explicit type and size guards."""

        length = _content_length(self.headers, 6 * 1024 * 1024)
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _serve_artifact(self, artifact_id: str) -> None:
        """Serve one regular, openable artifact with single-range support."""

        catalog = load_catalog(self.context.config)
        record = next((item for item in catalog["artifacts"] if item["id"] == artifact_id), None)
        if record is None or not record.get("openable"):
            self._error(HTTPStatus.NOT_FOUND, "openable artifact not found")
            return
        path = Path(str(record["path"]))
        if path.is_symlink() or not path.is_file() or not is_within(path, self.context.config.artifact_root):
            self._error(HTTPStatus.NOT_FOUND, "artifact is no longer safely available")
            return
        _serve_file(self, path)

    def _serve_hub_state(self, relative_path: str) -> None:
        """Serve one generated Hub preview or vendored asset over loopback HTTP.

        Generated Markdown pages are stored below ``_research_hub``.  Static
        ``file://`` pages can load those files directly, but the live server
        needs an explicit safe route so iframe previews do not fall back to a
        404.  The route is intentionally limited to regular files inside the
        Hub-owned state directory and rejects traversal/symlink escapes.
        """

        relative = Path(relative_path)
        if not relative_path or relative.is_absolute() or ".." in relative.parts:
            self._error(HTTPStatus.NOT_FOUND, "Hub state file not found")
            return
        state_root = self.context.config.state_root.resolve()
        artifact_root = self.context.config.artifact_root.resolve()
        path = (artifact_root / relative).resolve(strict=False)
        if path.is_symlink() or not path.is_file() or not is_within(path, state_root):
            self._error(HTTPStatus.NOT_FOUND, "Hub state file not found")
            return
        _serve_file(self, path)

    def _store_attachment(self, document_id: str) -> dict[str, Any]:
        """Store one browser-uploaded attachment in Hub-owned artifact state.

        The caller must already pass document lookup, token, and loopback checks.
        Large media is deliberately rejected here; users should place it in a
        durable artifact root and link it instead of copying it through a browser.
        """

        document = self.context.documents.get(document_id)
        length = _content_length(self.headers, self.context.config.limits["attachment_upload_bytes"])
        raw_name = unquote(self.headers.get("X-Filename", "attachment"))
        filename = _safe_filename(raw_name)
        if not filename:
            raise ValueError("attachment filename is invalid")
        self.context.config.ensure_state_root()
        directory = self.context.config.state_root / "media" / stable_id("document", document_id)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload.", dir=str(directory))
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        try:
            remaining = length
            with os.fdopen(descriptor, "wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("attachment body ended before Content-Length")
                    handle.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            target = directory / f"{digest.hexdigest()[:16]}_{filename}"
            if target.exists():
                temporary.unlink()
            else:
                os.replace(temporary, target)
            mime = self.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
            markdown = f"![{filename}]({target.resolve().as_uri()})" if mime.startswith("image/") else f"[{filename}]({target.resolve().as_uri()})"
            catalog = scan_and_write(self.context.config)
            render_document_pages(self.context.config, catalog)
            write_catalog(self.context.config, catalog)
            return {
                "path": str(target.relative_to(self.context.config.artifact_root)),
                "sha256": digest.hexdigest(),
                "bytes": length,
                "mime_type": mime,
                "markdown_link": markdown,
            }
        finally:
            if temporary.exists():
                temporary.unlink()

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Write one UTF-8 JSON response."""

        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _html(self, value: str) -> None:
        """Write one live HTML catalog page."""

        data = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        """Return structured errors without leaking internal paths or tracebacks."""

        self._json({"error": message}, status)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep default access logs concise and free of token query strings."""

        safe = format.replace("?token=", "?token=redacted")
        super().log_message(safe, *args)


def make_server(config: HubConfig, host: str, port: int, token: str | None = None) -> ThreadingHTTPServer:
    """Create a loopback-only server without starting its request loop.

    Args:
        config: Resolved Hub configuration.
        host: Requested listening host, restricted to loopback literals.
        port: TCP port to bind.
        token: Optional test token; production callers should omit it.

    Returns:
        Configured threaded HTTP server with Hub context attached.

    Raises:
        ValueError: If host is non-loopback or port is invalid.
    """

    if host not in LOOPBACK_HOSTS:
        raise ValueError("Research Hub may bind only 127.0.0.1, ::1, or localhost")
    if not 0 <= port <= 65535:
        raise ValueError("port must be in 0..65535")
    context = HubServerContext(config=config, token=token or secrets.token_urlsafe(32))
    handler = type("BoundHubRequestHandler", (HubRequestHandler,), {"context": context})
    return ThreadingHTTPServer((host, port), handler)


def _settings_payload(config: HubConfig) -> dict[str, Any]:
    """Return the editable registry plus the active local boundary."""

    return {
        "registry_path": str(config.portfolio_root / "research_hub_sources.json"),
        "workspace_root": str(config.workspace_root),
        "source_registry": read_source_registry(config.portfolio_root),
        "write_mode": "loopback_service_required_for_reindex",
    }


def _content_length(headers: Any, maximum: int) -> int:
    """Validate Content-Length for a bounded local request body."""

    try:
        length = int(headers.get("Content-Length", ""))
    except ValueError as exc:
        raise ValueError("Content-Length is required") from exc
    if length < 0 or length > maximum:
        raise ValueError(f"request body must be between 0 and {maximum} bytes")
    return length


def _safe_filename(value: str) -> str:
    """Create a path-component-only attachment name without traversal characters."""

    name = Path(value).name.strip()
    name = re.sub(r"[^\w. -]", "_", name, flags=re.UNICODE)
    return name[:180].strip(". ")


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    """Serve a regular file with conservative single HTTP Range support."""

    total = path.stat().st_size
    start, end, status = 0, max(total - 1, 0), HTTPStatus.OK
    raw_range = handler.headers.get("Range")
    if raw_range:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
        if not match:
            handler.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return
        raw_start, raw_end = match.groups()
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else end
        elif raw_end:
            suffix = int(raw_end)
            start = max(total - suffix, 0)
        if start > end or start >= total:
            handler.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return
        end = min(end, total - 1)
        status = HTTPStatus.PARTIAL_CONTENT
    length = max(end - start + 1, 0)
    mime, _ = mimetypes.guess_type(str(path))
    handler.send_response(status)
    handler.send_header("Content-Type", mime or "application/octet-stream")
    handler.send_header("Content-Length", str(length))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if status == HTTPStatus.PARTIAL_CONTENT:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{total}")
    handler.end_headers()
    if handler.command == "HEAD" or not length:
        return
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)
