#!/usr/bin/env python3
"""Render a bidirectional ClearML-to-research-evidence binding sidecar.

The command never edits a canonical experiment record or receipt and never
contacts ClearML.  It combines a locally written ``clearml_task_linkage_v1``
file with bounded metadata for the explicitly selected evidence paths.  The
result can be committed beside a finished receipt or uploaded as a small
artifact after an operator has reviewed it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 'clearml_evidence_binding_v1'
MAX_HASH_BYTES = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return a bounded-file SHA256 digest."""

    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_named_path(spec: str) -> tuple[str, Path]:
    """Parse ``role=path`` for one explicitly selected evidence file."""

    role, separator, raw_path = spec.partition('=')
    if not separator or not role or not raw_path:
        raise ValueError(f'Invalid evidence {spec!r}; expected role=path')
    return role, Path(raw_path).expanduser()


def describe_evidence(
    role: str,
    path: Path,
    *,
    require_paths: bool = True,
) -> dict[str, Any]:
    """Describe one evidence file without copying its contents."""

    resolved = path.expanduser().resolve(strict=False)
    item: dict[str, Any] = {
        'role': role,
        'path': str(resolved),
        'exists': resolved.is_file(),
    }
    if not resolved.is_file():
        if require_paths:
            raise FileNotFoundError(resolved)
        return item
    size = resolved.stat().st_size
    item['bytes'] = size
    if size <= MAX_HASH_BYTES:
        item['sha256'] = sha256_file(resolved)
    else:
        item['sha256'] = None
        item['hash_skipped_reason'] = f'file exceeds {MAX_HASH_BYTES} bytes'
    return item


def load_linkage(path: Path) -> dict[str, Any]:
    """Load and validate the small adapter linkage payload."""

    value = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('ClearML linkage must be a JSON object')
    if value.get('schema_version') != 'clearml_task_linkage_v1':
        raise ValueError(
            'ClearML linkage schema_version must be clearml_task_linkage_v1')
    for field in ('project_id', 'clearml_project', 'run_id', 'task_kind'):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f'ClearML linkage field {field!r} is required')
    return value


def build_binding(
    *,
    linkage_path: Path,
    evidence_specs: Sequence[str],
    out_path: Path | None = None,
    task_url: str | None = None,
    require_paths: bool = True,
) -> dict[str, Any]:
    """Build a deterministic binding object for a Task and evidence files."""

    linkage = load_linkage(linkage_path)
    evidence: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for spec in evidence_specs:
        role, path = parse_named_path(spec)
        if role in seen_roles:
            raise ValueError(f'Duplicate evidence role: {role}')
        seen_roles.add(role)
        evidence.append(
            describe_evidence(role, path, require_paths=require_paths))

    task = {
        'id': linkage.get('task_id'),
        'url': task_url,
        'project': linkage['clearml_project'],
        'task_kind': linkage['task_kind'],
    }
    return {
        'schema_version':
        SCHEMA_VERSION,
        'created_at':
        datetime.now(timezone.utc).isoformat(),
        'project_id':
        linkage['project_id'],
        'run_id':
        linkage['run_id'],
        'clearml':
        task,
        'source_linkage': {
            'path': str(linkage_path.expanduser().resolve()),
            'schema_version': linkage['schema_version'],
        },
        'evidence':
        evidence,
        'relations': {
            'task_to_evidence': [item['role'] for item in evidence],
            'evidence_to_task':
            {item['role']: linkage.get('task_id')
             for item in evidence},
        },
        'canonical_sources_unchanged':
        True,
        'out_path': (str(out_path.expanduser().resolve())
                     if out_path is not None else None),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write one JSON sidecar."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) +
        '\n',
        encoding='utf-8',
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linkage', required=True, type=Path)
    parser.add_argument('--evidence', action='append', default=[])
    parser.add_argument('--task-url')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--allow-missing', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_binding(
            linkage_path=args.linkage,
            evidence_specs=args.evidence,
            out_path=args.out,
            task_url=args.task_url,
            require_paths=not args.allow_missing,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    write_json(args.out, payload)
    print(f'WROTE {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
