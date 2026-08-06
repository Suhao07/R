#!/usr/bin/env python3
"""Bind a GPU experiment invocation to a validated Markdown record.

The receipt is deliberately small: it stores the validated experiment-record
digest plus hashes of the artifacts that existed at one lifecycle phase.  It
does not attempt to summarize model quality or replace the human-written
analysis in the experiment record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from validate_experiment_record import validate_experiment_record


REQUIRED_VISUAL_ARTIFACTS = {
    'started': frozenset({'visualization_manifest'}),
    'finished': frozenset({'visualization_index'}),
}


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest of one regular file."""

    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_artifact_spec(spec: str) -> tuple[str, Path]:
    """Parse an ``artifact_id=absolute_or_relative_path`` CLI value."""

    artifact_id, separator, raw_path = spec.partition('=')
    if not separator or not artifact_id or not raw_path:
        raise ValueError(
            f'Invalid artifact {spec!r}; expected artifact_id=path.'
        )
    return artifact_id, Path(raw_path)


def build_experiment_receipt(
    *,
    record: Path,
    run_id: str,
    workstream_id: str,
    phase: str,
    validation_scope: str,
    repository_ids: Sequence[str],
    command: str,
    artifact_specs: Sequence[str],
) -> dict[str, object]:
    """Validate a record and collect immutable metadata for one run phase.

    Args:
        record: The experiment Markdown file created before the run.
        run_id: Stable identifier shared by start and finish receipts.
        workstream_id: Portfolio workstream responsible for the run.
        phase: Lifecycle phase, normally ``started`` or ``finished``.
        validation_scope: Evidence scope declared by the run.
        repository_ids: Primary repositories participating in the run.
        command: Durable runner command or script path.
        artifact_specs: Existing ``id=path`` artifacts to fingerprint.

    Returns:
        A JSON-serializable receipt object.

    Raises:
        ValueError: If the record is structurally invalid or an artifact is
            absent.  This is the fail-closed boundary before expensive work.
    """

    errors = validate_experiment_record(record)
    if errors:
        raise ValueError('Invalid experiment record:\n- ' + '\n- '.join(errors))

    artifacts: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for spec in artifact_specs:
        artifact_id, artifact_path = parse_artifact_spec(spec)
        if artifact_id in seen_ids:
            raise ValueError(f'Duplicate artifact id: {artifact_id}')
        if not artifact_path.is_file():
            raise ValueError(f'Artifact does not exist: {artifact_path}')
        seen_ids.add(artifact_id)
        artifacts.append({
            'id': artifact_id,
            'path': str(artifact_path.resolve()),
            'bytes': artifact_path.stat().st_size,
            'sha256': sha256_file(artifact_path),
        })

    # 启动前绑定可视化计划，结束时绑定实际导出索引，避免只在实验文档中事后补写路径。
    required_artifacts = REQUIRED_VISUAL_ARTIFACTS.get(phase)
    if required_artifacts is None:
        raise ValueError(f'Unsupported experiment receipt phase: {phase}')
    missing_artifacts = sorted(required_artifacts - seen_ids)
    if missing_artifacts:
        raise ValueError(
            f'{phase} receipt is missing required visualization artifact(s): '
            + ', '.join(missing_artifacts)
        )

    return {
        'schema_version': 'research_experiment_receipt_v1',
        'run_id': run_id,
        'workstream_id': workstream_id,
        'phase': phase,
        'validation_scope': validation_scope,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'repository_ids': list(repository_ids),
        'command': command,
        # 记录文档哈希，防止启动后用另一份文档追认结果。
        'experiment_record': {
            'path': str(record.resolve()),
            'sha256': sha256_file(record),
        },
        'artifacts': artifacts,
    }


def write_receipt(path: Path, receipt: dict[str, object]) -> None:
    """Atomically write one receipt without leaving a partial JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI arguments for a lifecycle receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--workstream-id', required=True)
    parser.add_argument('--phase', required=True, choices=('started', 'finished'))
    parser.add_argument('--validation-scope', required=True)
    parser.add_argument('--repository-id', dest='repository_ids', action='append', required=True)
    parser.add_argument('--command', required=True)
    parser.add_argument('--artifact', dest='artifact_specs', action='append', required=True)
    parser.add_argument('--out', required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write one validated experiment lifecycle receipt."""

    args = build_parser().parse_args(argv)
    try:
        receipt = build_experiment_receipt(
            record=args.record,
            run_id=args.run_id,
            workstream_id=args.workstream_id,
            phase=args.phase,
            validation_scope=args.validation_scope,
            repository_ids=args.repository_ids,
            command=args.command,
            artifact_specs=args.artifact_specs,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_receipt(args.out, receipt)
    print(f'WROTE {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
