#!/usr/bin/env python3
"""Validate a reusable ClearML project profile without contacting ClearML.

The profile is intentionally a small project-specific configuration layer.
Secrets belong in the local ClearML configuration, never in this file.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 'clearml_project_profile_v1'
TASK_TYPES = {
    'training',
    'testing',
    'inference',
    'data_processing',
    'application',
    'custom',
}
POLICIES = {'link_only', 'upload_selected', 'upload_all'}
SECRET_KEY_PARTS = {
    'api_key',
    'access_key',
    'secret_key',
    'password',
    'token',
    'credentials',
    'private_key',
}
SECRET_VALUE_PATTERNS = (
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
)
ALLOWED_TOP_LEVEL = {
    'schema_version',
    'project_id',
    'clearml_project',
    'network',
    'documents',
    'experiment_bundle',
    'artifacts',
    'tasks',
    'metrics',
    'metric_sources',
    'media',
}


def load_profile(path: Path) -> dict[str, Any]:
    """Load JSON-compatible YAML, with JSON as a dependency-free fallback."""

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    raw = path.read_text(encoding='utf-8')
    if yaml is not None:
        value = yaml.safe_load(raw)
    else:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                'PyYAML is required for non-JSON YAML profiles; install '
                'pyyaml or use JSON syntax.') from exc
    if not isinstance(value, dict):
        raise ValueError('The ClearML profile root must be a mapping/object.')
    return value


def resolve_profile_path(raw_path: str, profile_path: Path) -> Path:
    """Resolve a profile path relative to the profile file."""

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = profile_path.parent / path
    return path.resolve(strict=False)


def _walk_values(value: Any,
                 prefix: str = '') -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f'{prefix}.{key}' if prefix else str(key)
            yield key_path, str(key), child
            yield from _walk_values(child, key_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f'{prefix}[{index}]')


def _require_string(mapping: dict[str, Any], key: str, location: str,
                    errors: list[str]) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f'{location}.{key} must be a non-empty string')
        return None
    return value


def _check_unknown_fields(mapping: dict[str, Any], allowed: set[str],
                          location: str, errors: list[str]) -> None:
    """Keep the executable validator aligned with the checked-in schema."""

    for key in sorted(set(mapping) - allowed):
        errors.append(f'unknown field: {location}.{key}')


def validate_profile(
    profile: dict[str, Any],
    profile_path: Path,
    *,
    workspace_root: Path | None = None,
    require_paths: bool = True,
) -> list[str]:
    """Return errors without raising for ordinary configuration mistakes."""

    errors: list[str] = []
    _check_unknown_fields(profile, ALLOWED_TOP_LEVEL, 'profile', errors)
    required = {
        'schema_version', 'project_id', 'clearml_project', 'documents',
        'artifacts', 'tasks', 'metrics', 'media'
    }
    missing = sorted(required - set(profile))
    errors.extend(f'missing required field: {name}' for name in missing)

    if profile.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION!r}')
    for key in ('project_id', 'clearml_project'):
        _require_string(profile, key, 'profile', errors)

    network = profile.get('network', {})
    if not isinstance(network, dict):
        errors.append('network must be a mapping')
    else:
        _check_unknown_fields(network, {'server_profile'}, 'network', errors)
        if 'server_profile' in network:
            _require_string(network, 'server_profile', 'network', errors)

    documents = profile.get('documents')
    if not isinstance(documents, dict):
        errors.append('documents must be a mapping')
        documents = {}
    _check_unknown_fields(documents, {'experiment_roots', 'review_root'},
                          'documents', errors)
    roots = documents.get('experiment_roots')
    if not isinstance(roots, list) or not roots or not all(
            isinstance(item, str) and item.strip() for item in roots):
        errors.append(
            'documents.experiment_roots must be a non-empty list of strings')
        roots = []
    review_root = documents.get('review_root')
    if not isinstance(review_root, str) or not review_root.strip():
        errors.append('documents.review_root must be a non-empty string')

    bundle = profile.get('experiment_bundle', {})
    if not isinstance(bundle, dict):
        errors.append('experiment_bundle must be a mapping')
        bundle = {}
    _check_unknown_fields(bundle, {'markdown', 'html', 'manifest', 'media_directories'},
                          'experiment_bundle', errors)
    for key in ('markdown', 'html', 'manifest'):
        if key in bundle:
            _require_string(bundle, key, 'experiment_bundle', errors)
    media_directories = bundle.get('media_directories', [])
    if not isinstance(media_directories, list) or not all(
            isinstance(item, str) and item.strip() for item in media_directories):
        errors.append('experiment_bundle.media_directories must be a list of strings')

    artifacts = profile.get('artifacts')
    if not isinstance(artifacts, dict):
        errors.append('artifacts must be a mapping')
        artifacts = {}
    _check_unknown_fields(
        artifacts,
        {
            'output_uri', 'checkpoint_policy', 'review_bundle_policy',
            'raw_data_policy'
        },
        'artifacts',
        errors,
    )
    _require_string(artifacts, 'output_uri', 'artifacts', errors)
    for key in ('checkpoint_policy', 'review_bundle_policy'):
        if artifacts.get(key) not in POLICIES:
            errors.append(f'artifacts.{key} must be one of {sorted(POLICIES)}')
    if artifacts.get('raw_data_policy') != 'never_upload':
        errors.append('artifacts.raw_data_policy must be never_upload')

    tasks = profile.get('tasks')
    if not isinstance(tasks, dict) or not tasks:
        errors.append('tasks must be a non-empty mapping')
        tasks = {}
    for task_id, task in tasks.items():
        if not isinstance(task_id, str) or not task_id.strip():
            errors.append('tasks contains an empty task id')
            continue
        if not isinstance(task, dict):
            errors.append(f'tasks.{task_id} must be a mapping')
            continue
        _check_unknown_fields(task, {'owner_repo', 'task_type', 'capture_git_diff'},
                              f'tasks.{task_id}', errors)
        _require_string(task, 'owner_repo', f'tasks.{task_id}', errors)
        if task.get('task_type') not in TASK_TYPES:
            errors.append(f'tasks.{task_id}.task_type must be one of '
                          f'{sorted(TASK_TYPES)}')
        if 'capture_git_diff' in task and not isinstance(task['capture_git_diff'], bool):
            errors.append(f'tasks.{task_id}.capture_git_diff must be boolean')

    metrics = profile.get('metrics')
    if not isinstance(metrics, dict) or not metrics:
        errors.append('metrics must be a non-empty mapping')
        metrics = {}
    metric_targets: dict[str, str] = {}
    for group, mapping in metrics.items():
        if not isinstance(mapping, dict) or not mapping:
            errors.append(f'metrics.{group} must be a non-empty mapping')
            continue
        for name, target in mapping.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(
                    target, str) or not target.strip():
                errors.append(
                    f'metrics.{group} entries must map non-empty names '
                    'to non-empty strings')
                continue
            previous = metric_targets.get(target)
            if previous is not None:
                errors.append(f'duplicate ClearML metric target {target!r}: '
                              f'{previous} and {group}.{name}')
            metric_targets[target] = f'{group}.{name}'

    metric_sources = profile.get('metric_sources', {})
    if not isinstance(metric_sources, dict):
        errors.append('metric_sources must be a mapping')
        metric_sources = {}
    for group, mapping in metric_sources.items():
        if not isinstance(mapping, dict):
            errors.append(f'metric_sources.{group} must be a mapping')
            continue
        for name, source in mapping.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(
                    source, str) or not source.strip():
                errors.append(f'metric_sources.{group} entries must map names '
                              'to non-empty paths')

    media = profile.get('media')
    if not isinstance(media, dict):
        errors.append('media must be a mapping')
        media = {}
    _check_unknown_fields(
        media,
        {'max_debug_samples_per_series', 'upload'},
        'media',
        errors,
    )
    limit = media.get('max_debug_samples_per_series')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        errors.append(
            'media.max_debug_samples_per_series must be a positive integer')
    if media.get('upload') not in {
            'selected_review_only', 'all_review_media', 'never'
    }:
        errors.append('media.upload has an unsupported policy')

    for path, key, value in _walk_values(profile):
        key_normalized = key.lower().replace('-', '_')
        if any(part in key_normalized for part in SECRET_KEY_PARTS):
            errors.append(f'secret-like field is forbidden in profile: {path}')
        if isinstance(value, str) and any(
                pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            errors.append(
                'private key or cloud credential material is forbidden '
                f'in profile: {path}')

    if workspace_root is not None:
        workspace = workspace_root.resolve(strict=False)
        raw_paths = list(roots)
        if isinstance(review_root, str):
            raw_paths.append(review_root)
        for raw_path in raw_paths:
            resolved = resolve_profile_path(raw_path, profile_path)
            try:
                resolved.relative_to(workspace)
            except ValueError:
                errors.append(
                    f'configured path escapes workspace root: {raw_path} '
                    f'-> {resolved}')

    if require_paths:
        for raw_path in list(roots) + ([review_root] if isinstance(
                review_root, str) else []):
            resolved = resolve_profile_path(raw_path, profile_path)
            if not resolved.exists():
                errors.append(
                    f'configured path does not exist: {raw_path} -> {resolved}'
                )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--allow-missing', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile_path = args.profile.resolve()
    try:
        profile = load_profile(profile_path)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    errors = validate_profile(
        profile,
        profile_path,
        workspace_root=args.workspace_root,
        require_paths=not args.allow_missing,
    )
    if errors:
        print(
            json.dumps(
                {
                    'valid': False,
                    'profile': str(profile_path),
                    'errors': errors
                },
                ensure_ascii=False,
                indent=2))
        return 1
    print(
        json.dumps({
            'valid': True,
            'profile': str(profile_path)
        },
                   ensure_ascii=False,
                   indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
