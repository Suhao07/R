#!/usr/bin/env python3
"""Publish selected historical review roots as labelled ClearML Tasks.

Without ``--publish`` this command only renders the existing bounded import
manifest.  Publishing uploads the manifest's evidence files and media
candidates one file at a time; raw data and unlisted files remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from render_clearml_history_import import build_history_manifest
from validate_clearml_project_profile import load_profile, validate_profile


def _artifact_name(item: dict[str, Any]) -> str:
    relative = str(item['relative_path'])
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', relative).strip('_')
    return f"historical_{item['kind']}_{safe}"


def _run_id(root: Path) -> str:
    digest = hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:12]
    return f'historical-import-{root.name}-{digest}'


def publish_records(
    *,
    profile_path: Path,
    manifest: dict[str, Any],
    linkage_dir: Path,
) -> list[dict[str, Any]]:
    """Create one labelled Task per manifest record using the shared adapter."""

    profile_path = profile_path.expanduser().resolve()
    profile = load_profile(profile_path)
    errors = validate_profile(profile, profile_path, require_paths=True)
    if errors:
        raise ValueError('Invalid ClearML profile:\n- ' + '\n- '.join(errors))
    if 'review' not in profile.get('tasks', {}):
        raise ValueError('ClearML profile must define tasks.review for historical import')
    sys.path.insert(0, str(profile_path.parents[3] / 'ms-swift'))
    try:
        from swift.sidewalk_nav.observability.clearml import (
            ClearMLRun,
            build_run_configuration,
        )
    finally:
        sys.path.pop(0)

    linkage_dir = linkage_dir.expanduser().resolve()
    results: list[dict[str, Any]] = []
    for record in manifest['records']:
        root = Path(record['root']).resolve()
        run_id = _run_id(root)
        run = ClearMLRun(
            profile,
            run_id=run_id,
            task_kind='review',
            task_name=f'historical_import/{root.name}',
        )
        configuration = build_run_configuration(
            run_id=run_id,
            validation_scope='historical_import',
        )
        configuration['history_import'] = {
            'label': 'historical_import',
            'root': str(root),
            'reproducibility': record['reproducibility'],
            'summary': record['summary'],
        }
        try:
            run.start(
                configuration,
                tags=[profile['project_id'], 'historical_import', root.name],
                description=f'历史 review_outputs 导入：{root.name}',
            )
            for item in record['files']:
                run.upload_artifact(_artifact_name(item), Path(item['path']))
            for index, item in enumerate(record['debug_sample_candidates']):
                path = Path(item['path'])
                run.report_media(
                    title=path.name,
                    series='historical_import',
                    iteration=index,
                    path=path,
                )
            linkage_path = linkage_dir / f'{run_id}.json'
            run.write_linkage(linkage_path)
            run.finalize(success=True)
        except Exception:
            run.finalize(success=False)
            raise
        results.append({
            'run_id': run_id,
            'task_id': getattr(run.task, 'id', None),
            'root': str(root),
            'artifact_count': len(record['files']),
            'media_count': len(record['debug_sample_candidates']),
        })
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--root', action='append', required=True, type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--max-files', type=int, default=500)
    parser.add_argument('--max-media', type=int, default=30)
    parser.add_argument('--manifest-out', required=True, type=Path)
    parser.add_argument('--linkage-dir', type=Path, default=Path('_research_hub/history'))
    parser.add_argument('--publish', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_history_manifest(
        profile_path=args.profile,
        roots=args.root,
        workspace_root=args.workspace_root,
        max_files=args.max_files,
        max_media=args.max_media,
    )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    result: dict[str, Any] = {
        'mode': 'publish' if args.publish else 'plan',
        'manifest': str(args.manifest_out.resolve()),
        'records': manifest['records'],
    }
    if args.publish:
        result['tasks'] = publish_records(
            profile_path=args.profile,
            manifest=manifest,
            linkage_dir=args.linkage_dir,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
