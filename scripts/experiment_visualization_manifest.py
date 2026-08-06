#!/usr/bin/env python3
"""Create a durable visualization plan or completion index for one run."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def sha256_file(path: Path) -> str:
    """Return the digest of one exported visualization file."""

    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_named_path(spec: str) -> tuple[str, Path]:
    """Parse one ``name=path`` entry used by a manifest."""

    name, separator, raw_path = spec.partition('=')
    if not separator or not name or not raw_path:
        raise ValueError(f'Invalid path entry {spec!r}; expected name=path.')
    return name, Path(raw_path)


def describe_artifact(name: str, path: Path, *, require_exists: bool) -> dict[str, object]:
    """Describe one exported path without recursively hashing large directories."""

    if require_exists and not path.exists():
        raise ValueError(f'Visualization artifact does not exist: {path}')

    resolved = path.resolve()
    item: dict[str, object] = {
        'id': name,
        'path': str(resolved),
        'exists': path.exists(),
    }
    if path.is_file():
        item['kind'] = 'file'
        item['bytes'] = path.stat().st_size
        item['sha256'] = sha256_file(path)
    elif path.is_dir():
        item['kind'] = 'directory'
    else:
        item['kind'] = 'missing'
    return item


def build_visualization_manifest(
    *,
    run_id: str,
    run_kind: str,
    run_root: Path,
    phase: str,
    tensorboard_logdir: Path | None,
    dashboard_url: str | None,
    planned_outputs: Sequence[str],
    artifacts: Sequence[str],
) -> dict[str, object]:
    """Build a machine-readable visualization plan or final export index."""

    if phase not in {'planned', 'finished'}:
        raise ValueError(f'Unsupported visualization manifest phase: {phase}')
    if phase == 'finished' and not artifacts:
        raise ValueError('A finished visualization index requires at least one artifact.')

    planned = [
        describe_artifact(name, path, require_exists=False)
        for name, path in (parse_named_path(spec) for spec in planned_outputs)
    ]
    exported = [
        describe_artifact(name, path, require_exists=phase == 'finished')
        for name, path in (parse_named_path(spec) for spec in artifacts)
    ]
    return {
        'schema_version': 'research_visualization_manifest_v1',
        'run_id': run_id,
        'run_kind': run_kind,
        'phase': phase,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'run_root': str(run_root.resolve()),
        'tensorboard_logdir': (
            str(tensorboard_logdir.resolve()) if tensorboard_logdir is not None else None
        ),
        'dashboard_url': dashboard_url,
        'planned_outputs': planned,
        'artifacts': exported,
    }


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Atomically write one manifest or index."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-kind', required=True, choices=('training', 'generation', 'evaluation'))
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--phase', required=True, choices=('planned', 'finished'))
    parser.add_argument('--tensorboard-logdir', type=Path)
    parser.add_argument('--dashboard-url')
    parser.add_argument('--planned-output', action='append', default=[])
    parser.add_argument('--artifact', action='append', default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write a visualization plan or final index."""

    args = build_parser().parse_args(argv)
    try:
        manifest = build_visualization_manifest(
            run_id=args.run_id,
            run_kind=args.run_kind,
            run_root=args.run_root,
            phase=args.phase,
            tensorboard_logdir=args.tensorboard_logdir,
            dashboard_url=args.dashboard_url,
            planned_outputs=args.planned_output,
            artifacts=args.artifact,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_manifest(args.out, manifest)
    print(f'WROTE {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
