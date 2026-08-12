#!/usr/bin/env python3
"""Build a local-only ClearML upload plan from a project profile.

This command never contacts ClearML and never uploads files.  It records paths,
sizes and bounded hashes so a project adapter can make an explicit upload
decision later.
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

SCHEMA_VERSION = 'clearml_payload_manifest_v1'
DOCUMENT_SUFFIXES = {'.md', '.markdown'}
MEDIA_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.webm', '.mov',
    '.avi', '.wav', '.mp3'
}
REPORT_SUFFIXES = {
    '.json', '.jsonl', '.csv', '.tsv', '.html', '.htm', '.log', '.txt',
    '.yaml', '.yml'
}
MAX_HASH_BYTES = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def classify_file(path: Path, source_kind: str) -> str:
    suffix = path.suffix.lower()
    if suffix in DOCUMENT_SUFFIXES:
        return ('experiment_document'
                if source_kind == 'documents' else 'markdown')
    if suffix in MEDIA_SUFFIXES:
        return 'media'
    if suffix in REPORT_SUFFIXES:
        return 'machine_report'
    return 'artifact'


def describe_file(path: Path, *, source_kind: str,
                  root: Path) -> dict[str, Any]:
    size = path.stat().st_size
    item: dict[str, Any] = {
        'path': str(path.resolve()),
        'relative_path': str(path.relative_to(root)),
        'source_kind': source_kind,
        'kind': classify_file(path, source_kind),
        'bytes': size,
    }
    if size <= MAX_HASH_BYTES:
        item['sha256'] = sha256_file(path)
    else:
        item['sha256'] = None
        item['hash_skipped_reason'] = f'file exceeds {MAX_HASH_BYTES} bytes'
    return item


def parse_named_path(spec: str) -> tuple[str, Path]:
    """Parse an explicitly selected ``name=path`` evidence item."""

    name, separator, raw_path = spec.partition('=')
    if not separator or not name or not raw_path:
        raise ValueError(f'Invalid artifact {spec!r}; expected name=path')
    return name, Path(raw_path).expanduser()


def parse_media_spec(spec: str) -> tuple[str, str, Path]:
    """Parse ``title=series=path`` media selections."""

    title, separator, rest = spec.partition('=')
    series, separator2, raw_path = rest.partition('=') if separator else ('',
                                                                          '',
                                                                          '')
    if (not title or not separator or not series or not separator2
            or not raw_path):
        raise ValueError(f'Invalid media {spec!r}; expected title=series=path')
    return title, series, Path(raw_path).expanduser()


def _workspace_relative_root(path: Path, workspace_root: Path | None) -> Path:
    """Choose a stable root for explicit evidence metadata."""

    if workspace_root is None:
        return path.parent
    workspace = workspace_root.resolve(strict=False)
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(
            f'explicit evidence escapes workspace root: {path}') from exc
    return workspace


def describe_explicit_file(
    path: Path,
    *,
    role: str,
    name: str | None = None,
    workspace_root: Path | None = None,
    require_paths: bool = True,
) -> dict[str, Any]:
    """Describe one operator-selected evidence path without uploading it."""

    resolved = path.expanduser().resolve(strict=False)
    root = _workspace_relative_root(resolved, workspace_root)
    if not resolved.is_file():
        if require_paths:
            raise FileNotFoundError(resolved)
        item: dict[str, Any] = {
            'path': str(resolved),
            'relative_path': str(resolved.relative_to(root)),
            'source_kind': 'explicit',
            'kind': 'missing',
            'role': role,
            'exists': False,
        }
    else:
        item = describe_file(resolved, source_kind='explicit', root=root)
        item['role'] = role
        item['exists'] = True
    if name is not None:
        item['name'] = name
    return item


def _media_series(relative_path: str) -> str:
    """Use the containing review directory as the default series."""

    parent = Path(relative_path).parent.as_posix()
    return parent if parent and parent != '.' else 'root'


def select_media_candidates(
    media: Sequence[dict[str, Any]],
    *,
    max_per_series: int,
) -> list[dict[str, Any]]:
    """Bound automatically discovered media independently for each series."""

    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for item in media:
        series = _media_series(str(item['relative_path']))
        if counts.get(series, 0) >= max_per_series:
            continue
        copy = dict(item)
        copy['series'] = series
        selected.append(copy)
        counts[series] = counts.get(series, 0) + 1
    return selected


def collect_root(root: Path, *, source_kind: str,
                 max_files: int) -> tuple[list[dict[str, Any]], bool]:
    if not root.is_dir():
        return [], False
    records: list[dict[str, Any]] = []
    truncated = False
    for path in sorted(root.rglob('*')):
        if any(
                part.startswith('.') or part == '_research_hub'
                for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        if source_kind == 'documents' and path.suffix.lower(
        ) not in DOCUMENT_SUFFIXES:
            continue
        if len(records) >= max_files:
            truncated = True
            break
        records.append(describe_file(path, source_kind=source_kind, root=root))
    return records, truncated


def build_payload_manifest(
        *,
        profile_path: Path,
        run_id: str,
        max_files: int = 4000,
        max_debug_samples: int | None = None,
        workspace_root: Path | None = None,
        require_paths: bool = True,
        experiment_records: Sequence[Path] = (),
        receipts: Sequence[Path] = (),
        scorecards: Sequence[Path] = (),
        visualization_manifests: Sequence[Path] = (),
        visualization_indexes: Sequence[Path] = (),
        artifact_specs: Sequence[str] = (),
        media_specs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a deterministic, local-only upload plan."""

    if not run_id or any(char.isspace() for char in run_id):
        raise ValueError(
            'run_id must be a non-empty string without whitespace')
    profile_path = profile_path.resolve()
    profile = load_profile(profile_path)
    errors = validate_profile(
        profile,
        profile_path,
        workspace_root=workspace_root,
        require_paths=require_paths,
    )
    if errors:
        raise ValueError('Invalid ClearML profile:\n- ' + '\n- '.join(errors))

    documents: list[dict[str, Any]] = []
    review_artifacts: list[dict[str, Any]] = []
    truncated = False
    for raw_root in profile['documents']['experiment_roots']:
        records, root_truncated = collect_root(
            resolve_profile_path(raw_root, profile_path),
            source_kind='documents',
            max_files=max_files - len(documents),
        )
        documents.extend(records)
        truncated = truncated or root_truncated
    review_root = resolve_profile_path(profile['documents']['review_root'],
                                       profile_path)
    review_artifacts, review_truncated = collect_root(
        review_root,
        source_kind='review',
        max_files=max(0, max_files - len(documents)))
    truncated = truncated or review_truncated

    media = [item for item in review_artifacts if item['kind'] == 'media']
    limit = max_debug_samples or int(
        profile['media']['max_debug_samples_per_series'])
    candidates = ([] if profile['media']['upload'] == 'never' else
                  select_media_candidates(media, max_per_series=limit))

    required_evidence: list[dict[str, Any]] = []
    for role, paths in (
        ('experiment_record', experiment_records),
        ('receipt', receipts),
        ('scorecard', scorecards),
        ('visualization_manifest', visualization_manifests),
        ('visualization_index', visualization_indexes),
    ):
        for path in paths:
            required_evidence.append(
                describe_explicit_file(
                    path,
                    role=role,
                    workspace_root=workspace_root,
                    require_paths=require_paths,
                ))
    for spec in artifact_specs:
        name, path = parse_named_path(spec)
        required_evidence.append(
            describe_explicit_file(
                path,
                role='selected_artifact',
                name=name,
                workspace_root=workspace_root,
                require_paths=require_paths,
            ))

    selected_media: list[dict[str, Any]] = []
    media_counts: dict[str, int] = {}
    review_root_resolved = review_root.resolve(strict=False)
    media_policy = profile['media']['upload']
    for index, spec in enumerate(media_specs):
        title, series, path = parse_media_spec(spec)
        if media_policy == 'never':
            raise ValueError(
                'media selection is forbidden by media.upload=never')
        if media_counts.get(series, 0) >= limit:
            raise ValueError(
                f'media series {series!r} exceeds the limit of {limit}')
        resolved_media = path.expanduser().resolve(strict=False)
        if media_policy == 'selected_review_only':
            try:
                resolved_media.relative_to(review_root_resolved)
            except ValueError as exc:
                raise ValueError('selected review media must be under '
                                 'documents.review_root: '
                                 f'{resolved_media}') from exc
        item = describe_explicit_file(
            path,
            role='debug_sample',
            workspace_root=workspace_root,
            require_paths=require_paths,
        )
        item.update({'title': title, 'series': series, 'iteration': index})
        selected_media.append(item)
        media_counts[series] = media_counts.get(series, 0) + 1

    return {
        'schema_version': SCHEMA_VERSION,
        'project_id': profile['project_id'],
        'run_id': run_id,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'profile_path': str(profile_path),
        'clearml': {
            'project': profile['clearml_project'],
            'output_uri': profile['artifacts']['output_uri'],
            'upload_policies': {
                'checkpoint': profile['artifacts']['checkpoint_policy'],
                'review_bundle': profile['artifacts']['review_bundle_policy'],
                'raw_data': profile['artifacts']['raw_data_policy'],
                'media': profile['media']['upload'],
            },
        },
        'tasks': profile['tasks'],
        'metrics': profile['metrics'],
        'metric_sources': profile.get('metric_sources', {}),
        'documents': documents,
        'review_artifacts': review_artifacts,
        'debug_sample_candidates': candidates,
        'required_evidence': required_evidence,
        'selected_media': selected_media,
        'summary': {
            'document_files': len(documents),
            'review_files': len(review_artifacts),
            'media_candidates': len(media),
            'debug_sample_candidates': len(candidates),
            'required_evidence': len(required_evidence),
            'selected_media': len(selected_media),
            'truncated': truncated,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) +
        '\n',
        encoding='utf-8')
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--max-files', type=int, default=4000)
    parser.add_argument('--max-debug-samples', type=int)
    parser.add_argument('--experiment-record', action='append', default=[])
    parser.add_argument('--receipt', action='append', default=[])
    parser.add_argument('--scorecard', action='append', default=[])
    parser.add_argument('--visualization-manifest',
                        action='append',
                        default=[])
    parser.add_argument('--visualization-index', action='append', default=[])
    parser.add_argument('--artifact', action='append', default=[])
    parser.add_argument('--media', action='append', default=[])
    parser.add_argument('--allow-missing', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_files < 1:
        raise SystemExit('--max-files must be positive')
    if args.max_debug_samples is not None and args.max_debug_samples < 1:
        raise SystemExit('--max-debug-samples must be positive')
    try:
        payload = build_payload_manifest(
            profile_path=args.profile,
            run_id=args.run_id,
            max_files=args.max_files,
            max_debug_samples=args.max_debug_samples,
            workspace_root=args.workspace_root,
            require_paths=not args.allow_missing,
            experiment_records=[Path(item) for item in args.experiment_record],
            receipts=[Path(item) for item in args.receipt],
            scorecards=[Path(item) for item in args.scorecard],
            visualization_manifests=[
                Path(item) for item in args.visualization_manifest
            ],
            visualization_indexes=[
                Path(item) for item in args.visualization_index
            ],
            artifact_specs=args.artifact,
            media_specs=args.media,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    write_json(args.out, payload)
    print(f'WROTE {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
