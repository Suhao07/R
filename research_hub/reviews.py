"""Append-only review sidecars for immutable JSONL evidence queues."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import load_catalog
from .config import HubConfig, atomic_write_text, is_within, sha256_file


class ReviewError(RuntimeError):
    """Raised when a review operation would violate evidence immutability."""


DECISIONS = {"pass", "reject", "pending"}
CITYWALKER_TRI_STATE = {
    "point_goal_prompt_consistent",
    "gt_trajectory_consistent",
    "prediction_coordinate_frame_consistent",
    "visible_domain_shift_plausible",
}
CITYWALKER_DIAGNOSES = {
    "static_wait_state_unmodeled",
    "moving_speed_or_geometry_transfer_error",
    "point_goal_or_prompt_interface_mismatch",
    "per_case_coordinate_or_adapter_issue",
    "source_gt_or_temporal_alignment_question",
    "insufficient_visible_evidence",
}


class ReviewStore:
    """Read immutable queues and write review events in a separate Hub root.

    Args:
        config: Resolved Hub configuration.
    """

    def __init__(self, config: HubConfig) -> None:
        self.config = config

    def queue(self, queue_id: str) -> dict[str, Any]:
        """Return a current catalog queue descriptor or reject an unknown ID."""

        catalog = load_catalog(self.config)
        queue = next((item for item in catalog["queues"] if item["id"] == queue_id), None)
        if queue is None:
            raise ReviewError("unknown review queue")
        return queue

    def records(self, queue_id: str) -> dict[str, Any]:
        """Load bounded queue records with their current sidecar-derived state.

        Args:
            queue_id: Stable catalog queue identifier.

        Returns:
            Queue descriptor, records keyed by their stable ID, and folded review
            state for the exact source digest.
        """

        queue = self.queue(queue_id)
        path = self._queue_path(queue)
        source_sha256 = sha256_file(path)
        records = _read_queue(path, queue["id_field"], self.config.limits["queue_read_bytes"])
        states = self._states(queue_id, source_sha256)
        return {"queue": queue, "source_sha256": source_sha256, "records": records, "states": states}

    def append(
        self,
        queue_id: str,
        sample_id: str,
        decision: str,
        reviewer: str,
        note: str = "",
        fields: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one immutable review event after source and row validation.

        Args:
            queue_id: Queue selected from the current catalog.
            sample_id: Stable row identifier from the original JSONL.
            decision: One of pass, reject, or pending.
            reviewer: Local reviewer label, not an authentication claim.
            note: Concise human rationale.
            fields: Adapter-constrained supplemental review fields.
            event_id: Optional client idempotency identifier.

        Returns:
            Persisted event and an idempotency indicator.
        """

        if decision not in DECISIONS:
            raise ReviewError("decision must be pass, reject, or pending")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ReviewError("sample_id is required")
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 128:
            raise ReviewError("reviewer must be non-empty and at most 128 characters")
        if not isinstance(note, str) or len(note) > 4000:
            raise ReviewError("note must be at most 4000 characters")
        queue_data = self.records(queue_id)
        row_ids = {item["id"] for item in queue_data["records"]}
        if sample_id not in row_ids:
            raise ReviewError("sample_id is not present in the current queue")
        validated_fields = _validate_fields(queue_data["queue"], fields or {})
        event = {
            "schema_version": "research_hub_review_event_v1",
            "event_id": event_id or str(uuid.uuid4()),
            "queue_id": queue_id,
            "artifact_id": queue_data["queue"]["artifact_id"],
            "sample_id": sample_id,
            "decision": decision,
            "reviewer": reviewer.strip(),
            "note": note,
            "fields": validated_fields,
            "source_sha256": queue_data["source_sha256"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            uuid.UUID(event["event_id"])
        except (ValueError, TypeError) as exc:
            raise ReviewError("event_id must be a UUID") from exc
        destination = self._event_path(queue_id)
        for existing in _read_events(destination):
            if existing.get("event_id") == event["event_id"]:
                return {"event": existing, "duplicate": True}
        self.config.ensure_state_root()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {"event": event, "duplicate": False}

    def export(self, queue_id: str) -> dict[str, Any]:
        """Export a derived review view without writing the original JSONL.

        Args:
            queue_id: Queue whose sidecar state should be materialized.

        Returns:
            Hub-relative JSONL and summary paths plus decision denominators.
        """

        data = self.records(queue_id)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.config.state_root / "exports" / queue_id / stamp
        target.mkdir(parents=True, exist_ok=False)
        output = target / "reviewed.jsonl"
        counts: Counter[str] = Counter()
        descriptor, temporary_name = tempfile.mkstemp(prefix=".reviewed.", suffix=".jsonl", dir=str(target))
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                for item in data["records"]:
                    state = data["states"].get(item["id"])
                    copied = dict(item["record"])
                    if state is not None:
                        copied["hub_review"] = state
                        counts[str(state["decision"])] += 1
                    else:
                        counts["unreviewed"] += 1
                    handle.write(json.dumps(copied, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
        summary = {
            "schema_version": "research_hub_review_export_v1",
            "queue_id": queue_id,
            "source_path": data["queue"]["path"],
            "source_sha256": data["source_sha256"],
            "source_row_count": len(data["records"]),
            "decision_counts": dict(sorted(counts.items())),
            "event_count": len(_read_events(self._event_path(queue_id))),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_mutated": False,
        }
        atomic_write_text(target / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return {
            "reviewed_path": str(output.relative_to(self.config.artifact_root)),
            "summary_path": str((target / "summary.json").relative_to(self.config.artifact_root)),
            "decision_counts": summary["decision_counts"],
        }

    def _queue_path(self, queue: dict[str, Any]) -> Path:
        """Ensure queue source is a regular artifact-root file before reading."""

        path = Path(str(queue["path"]))
        if path.is_symlink() or not path.is_file() or not is_within(path, self.config.artifact_root):
            raise ReviewError("queue source is no longer a regular artifact-root file")
        if path.stat().st_size > self.config.limits["queue_read_bytes"]:
            raise ReviewError("queue is too large for interactive review; create a bounded review subset first")
        return path.resolve()

    def _event_path(self, queue_id: str) -> Path:
        """Return the Hub-owned append-only event stream path for one queue."""

        return self.config.state_root / "review_events" / f"{queue_id}.jsonl"

    def _states(self, queue_id: str, source_sha256: str) -> dict[str, dict[str, Any]]:
        """Fold only sidecar events bound to the current immutable source digest."""

        state: dict[str, dict[str, Any]] = {}
        for event in _read_events(self._event_path(queue_id)):
            if event.get("source_sha256") == source_sha256:
                state[str(event.get("sample_id"))] = event
        return state


def _read_queue(path: Path, id_field: str, limit: int) -> list[dict[str, Any]]:
    """Read an interactive JSONL queue with a strict byte limit and unique IDs."""

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    consumed = 0
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            consumed += len(raw)
            if consumed > limit:
                raise ReviewError("queue exceeded configured interactive read limit")
            if not raw.strip():
                continue
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReviewError(f"invalid JSONL at line {line_number}") from exc
            if not isinstance(value, dict) or not isinstance(value.get(id_field), (str, int)):
                raise ReviewError(f"queue row {line_number} has no stable {id_field}")
            row_id = str(value[id_field])
            if row_id in seen:
                raise ReviewError(f"queue has duplicate {id_field}: {row_id}")
            seen.add(row_id)
            records.append({"id": row_id, "record": value})
    return records


def _read_events(path: Path) -> list[dict[str, Any]]:
    """Read syntactically valid existing event lines without mutating the stream."""

    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("schema_version") == "research_hub_review_event_v1":
            events.append(event)
    return events


def _validate_fields(queue: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Validate adapter-specific supplemental fields without altering source semantics."""

    if not isinstance(fields, dict):
        raise ReviewError("fields must be a JSON object")
    if queue["adapter"] != "citywalker_diagnosis_v1":
        if any(not isinstance(value, (str, int, float, bool, type(None))) for value in fields.values()):
            raise ReviewError("generic review fields must be scalar values")
        return {str(key): value for key, value in fields.items() if len(str(key)) <= 128}
    allowed = CITYWALKER_TRI_STATE | {"final_diagnosis", "reviewer_note"}
    unknown = set(fields) - allowed
    if unknown:
        raise ReviewError(f"unsupported CityWalker review fields: {sorted(unknown)}")
    for key in CITYWALKER_TRI_STATE & set(fields):
        if fields[key] not in {True, False, "inconclusive", None}:
            raise ReviewError(f"{key} must be true, false, inconclusive, or null")
    if "final_diagnosis" in fields and fields["final_diagnosis"] not in CITYWALKER_DIAGNOSES | {None}:
        raise ReviewError("invalid CityWalker final_diagnosis")
    if "reviewer_note" in fields and (not isinstance(fields["reviewer_note"], str) or len(fields["reviewer_note"]) > 4000):
        raise ReviewError("reviewer_note must be text no longer than 4000 characters")
    return fields
