#!/usr/bin/env python3
"""Run one manual train -> eval -> ClearML report sequence.

The training and evaluation commands remain project-owned.  This runner only
orders them and invokes the existing post-run reporters, without a ClearML
Agent or shell execution.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _command(value: str, label: str) -> list[str]:
    command = shlex.split(value)
    if not command:
        raise ValueError(f'{label} must not be empty')
    return command


def _run(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def _run_reporter(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end='')
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        raise RuntimeError(f'reporter failed with exit code {result.returncode}')
    for line in reversed(result.stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError('reporter did not return a JSON result')


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run_pipeline(
    *,
    profile: Path,
    run_id: str,
    experiment_root: Path,
    train_command: str,
    eval_command: str,
    train_summary: Path | None = None,
    workdir: Path | None = None,
    skip_train_report: bool = False,
    pipeline_receipt: Path | None = None,
) -> dict[str, Any]:
    """Execute project commands and bind their outputs through existing reporters."""

    root = experiment_root.expanduser().resolve()
    cwd = (workdir or Path.cwd()).expanduser().resolve()
    if not cwd.is_dir():
        raise FileNotFoundError(cwd)
    if root.exists() and not root.is_dir():
        raise ValueError(f'experiment_root is not a directory: {root}')
    root.mkdir(parents=True, exist_ok=True)
    train_argv = _command(train_command, 'train_command')
    eval_argv = _command(eval_command, 'eval_command')
    profile = profile.expanduser().resolve()
    if not profile.is_file():
        raise FileNotFoundError(profile)
    summary = (train_summary or root / 'train_summary.json').expanduser().resolve()
    receipt = (pipeline_receipt or root / 'pipeline_receipt.json').expanduser().resolve()
    reporter_root = Path(__file__).resolve().parents[2] / 'ms-swift'
    train_reporter = reporter_root / 'scripts' / 'sidewalk_nav' / 'clearml_report_train.py'
    eval_reporter = reporter_root / 'scripts' / 'sidewalk_nav' / 'clearml_report_eval.py'
    if not skip_train_report and not train_reporter.is_file():
        raise FileNotFoundError(train_reporter)
    if not eval_reporter.is_file():
        raise FileNotFoundError(eval_reporter)
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(
        item for item in (str(reporter_root), env.get('PYTHONPATH', '')) if item)

    started_at = datetime.now(timezone.utc).isoformat()
    payload = {
        'schema_version': 'clearml_train_eval_report_pipeline_v1',
        'run_id': run_id,
        'started_at': started_at,
        'workdir': str(cwd),
        'experiment_root': str(root),
        'train_command': train_argv,
        'eval_command': eval_argv,
        'train_report': None,
        'eval_report': None,
        'status': 'running',
    }
    _write_json(receipt, payload)
    stage = 'train'
    try:
        _run(train_argv, cwd=cwd, env=env)
        train_result: dict[str, Any] | None = None
        if not skip_train_report:
            stage = 'train_report'
            if not summary.is_file():
                raise FileNotFoundError(f'train summary: {summary}')
            train_linkage = root / 'clearml_train_task_linkage.json'
            train_result = _run_reporter(
                [
                    sys.executable,
                    str(train_reporter),
                    '--profile', str(profile),
                    '--run-id', run_id,
                    '--summary-json', str(summary),
                    '--linkage-out', str(train_linkage),
                ],
                cwd=cwd,
                env=env,
            )
            payload['train_report'] = train_result

        stage = 'eval'
        _run(eval_argv, cwd=cwd, env=env)
        stage = 'eval_report'
        eval_linkage = root / 'clearml_eval_task_linkage.json'
        eval_report_command = [
            sys.executable,
            str(eval_reporter),
            '--profile', str(profile),
            '--run-id', run_id,
            '--experiment-root', str(root),
            '--pipeline-receipt', str(receipt),
            '--linkage-out', str(eval_linkage),
        ]
        if train_result and train_result.get('task_id'):
            eval_report_command.extend([
                '--pipeline-parent-task-id',
                str(train_result['task_id']),
            ])
        eval_result = _run_reporter(
            eval_report_command,
            cwd=cwd,
            env=env,
        )
        payload['eval_report'] = eval_result
        payload['status'] = 'completed'
        payload['finished_at'] = datetime.now(timezone.utc).isoformat()
        _write_json(receipt, payload)
        return payload
    except Exception as exc:
        payload.update({
            'status': 'failed',
            'failed_stage': stage,
            'error_type': type(exc).__name__,
            'error': str(exc),
            'finished_at': datetime.now(timezone.utc).isoformat(),
        })
        _write_json(receipt, payload)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--experiment-root', required=True, type=Path)
    parser.add_argument('--train-command', required=True)
    parser.add_argument('--eval-command', required=True)
    parser.add_argument('--train-summary', type=Path)
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--skip-train-report', action='store_true')
    parser.add_argument('--pipeline-receipt', type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_pipeline(
        profile=args.profile,
        run_id=args.run_id,
        experiment_root=args.experiment_root,
        train_command=args.train_command,
        eval_command=args.eval_command,
        train_summary=args.train_summary,
        workdir=args.workdir,
        skip_train_report=args.skip_train_report,
        pipeline_receipt=args.pipeline_receipt,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
