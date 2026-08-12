#!/usr/bin/env python3
"""Render a bounded, explicit historical ClearML import plan.

Only directories named on the command line are inspected.  The command does
not create Tasks, upload files, or alter historical review artifacts.  A
directory without a started receipt is labelled ``historical_index_only`` so
the import cannot imply that the run was reproducible from its beginning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from validate_clearml_project_profile import (
    load_profile,
    resolve_profile_path,
    validate_profile,
)

SCHEMA_VERSION = 'clearml_historical_import_manifest_v1'
MAX_HASH_BYTES = 8 * 1024 * 1024
EVIDENCE_SUFFIXES = {
    '.json',
    '.jsonl',
    '.csv',
    '.tsv',
    '.html',
    '.htm',
    '.md',
    '.txt',
    '.yaml',
    '.yml',
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.gif',
    '.svg',
    '.mp4',
    '.webm',
    '.mov',
}
MEDIA_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.webm', '.mov'
}
STARTED_MARKERS = ('started', 'start_receipt', 'started_receipt')
FINISHED_MARKERS = ('finished', 'finish', 'receipt', 'results_record')


def sha256_file(path: Path) -> str:
    """Return a bounded-file SHA256 digest."""

    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _classify(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in MEDIA_SUFFIXES:
        return 'media'
    if 'scorecard' in name:
        return 'scorecard'
    if 'visualization_index' in name:
        return 'visualization_index'
    if 'visualization_manifest' in name:
        return 'visualization_manifest'
    if 'receipt' in name or 'results_record' in name:
        return 'receipt'
    if suffix in {'.md', '.markdown'}:
        return 'experiment_document'
    return 'report'


def _describe(path: Path, root: Path) -> dict[str, Any]:
    size = path.stat().st_size
    item: dict[str, Any] = {
        'path': str(path.resolve()),
        'relative_path': str(path.relative_to(root)),
        'kind': _classify(path),
        'bytes': size,
    }
    if size <= MAX_HASH_BYTES:
        item['sha256'] = sha256_file(path)
    else:
        item['sha256'] = None
        item['hash_skipped_reason'] = f'file exceeds {MAX_HASH_BYTES} bytes'
    return item


def _is_started(path: Path) -> bool:
    name = path.name.lower()
    return any(marker in name for marker in STARTED_MARKERS)


def _is_finished(path: Path) -> bool:
    name = path.name.lower()
    return any(marker in name for marker in FINISHED_MARKERS)


def inspect_history_root(
    root: Path,
    *,
    max_files: int = 500,
    max_media: int = 30,
) -> dict[str, Any]:
    """Inspect one explicitly selected historical review directory."""

    resolved = root.expanduser().resolve(strict=False)
    if not resolved.is_dir():
        raise FileNotFoundError(resolved)
    files: list[dict[str, Any]] = []
    truncated = False
    for path in sorted(resolved.rglob('*')):
        if any(
                part.startswith('.') or part == '_research_hub'
                for part in path.relative_to(resolved).parts):
            continue
        if not path.is_file() or path.suffix.lower() not in EVIDENCE_SUFFIXES:
            continue
        if len(files) >= max_files:
            truncated = True
            break
        files.append(_describe(path, resolved))

    started = any(_is_started(Path(item['path'])) for item in files)
    finished = any(_is_finished(Path(item['path'])) for item in files)
    media = [item for item in files if item['kind'] == 'media'][:max_media]
    required = [
        item for item in files if item['kind'] in {
            'scorecard', 'visualization_index', 'visualization_manifest',
            'receipt', 'experiment_document'
        }
    ]
    return {
        'root':
        str(resolved),
        'import_label':
        'historical_import',
        'reproducibility': ('historical_run_with_started_receipt'
                            if started else 'historical_index_only'),
        'started_receipt_present':
        started,
        'finished_evidence_present':
        finished,
        'files':
        required,
        'debug_sample_candidates':
        media,
        'summary': {
            'files_scanned': len(files),
            'evidence_files': len(required),
            'media_candidates': len(media),
            'truncated': truncated,
        },
    }


def build_history_manifest(
    *,
    profile_path: Path,
    roots: Sequence[Path],
    workspace_root: Path | None = None,
    max_roots: int = 3,
    max_files: int = 500,
    max_media: int = 30,
) -> dict[str, Any]:
    """Build a no-upload import plan for selected historical roots."""

    if not roots:
        raise ValueError('at least one historical root is required')
    if len(roots) > max_roots:
        raise ValueError(
            f'at most {max_roots} historical roots may be selected')
    if max_files < 1 or max_media < 1:
        raise ValueError('max_files and max_media must be positive')
    profile_path = profile_path.expanduser().resolve()
    profile = load_profile(profile_path)
    errors = validate_profile(
        profile,
        profile_path,
        workspace_root=workspace_root,
        require_paths=True,
    )
    if errors:
        raise ValueError('Invalid ClearML profile:\n- ' + '\n- '.join(errors))
    review_root = resolve_profile_path(profile['documents']['review_root'],
                                       profile_path)
    review_root = review_root.resolve(strict=False)
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(review_root)
        except ValueError as exc:
            raise ValueError(
                f'historical root must be under documents.review_root: '
                f'{resolved}') from exc
        if resolved in seen:
            raise ValueError(f'duplicate historical root: {resolved}')
        seen.add(resolved)
        records.append(
            inspect_history_root(
                resolved,
                max_files=max_files,
                max_media=max_media,
            ))
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'project_id': profile['project_id'],
        'clearml_project': profile['clearml_project'],
        'profile_path': str(profile_path),
        'upload_required': False,
        'records': records,
        'summary': {
            'historical_roots':
            len(records),
            'historical_index_only':
            sum(item['reproducibility'] == 'historical_index_only'
                for item in records),
            'with_started_receipt':
            sum(item['started_receipt_present'] for item in records),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write a JSON manifest."""

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
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--root', action='append', required=True, type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--max-roots', type=int, default=3)
    parser.add_argument('--max-files', type=int, default=500)
    parser.add_argument('--max-media', type=int, default=30)
    parser.add_argument('--out', required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_history_manifest(
            profile_path=args.profile,
            roots=args.root,
            workspace_root=args.workspace_root,
            max_roots=args.max_roots,
            max_files=args.max_files,
            max_media=args.max_media,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    write_json(args.out, payload)
    print(f'WROTE {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
