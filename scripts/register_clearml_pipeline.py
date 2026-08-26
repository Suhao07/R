#!/usr/bin/env python3
"""Register an explicit ClearML train -> eval -> report pipeline.

The three base Task IDs and every parameter override are supplied by the
project.  This keeps the template independent of a project's CLI parameter
names while preserving ClearML's native task/queue/DAG execution model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from validate_clearml_project_profile import load_profile, validate_profile


def _resolve_output_uri(profile: Mapping[str, Any]) -> str | None:
    value = str(profile.get('artifacts', {}).get('output_uri', '')).strip()
    if value.startswith('${') and value.endswith('}'):
        return os.environ.get(value[2:-1]) or None
    return value or None


def _load_overrides(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    value = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(value, Mapping):
        raise ValueError('parameter overrides must be a JSON object')
    result: dict[str, dict[str, Any]] = {}
    for step, overrides in value.items():
        if not isinstance(step, str) or not step.strip():
            raise ValueError('parameter override step names must be non-empty strings')
        if not isinstance(overrides, Mapping):
            raise ValueError(f'parameter overrides for {step!r} must be an object')
        result[step] = dict(overrides)
    return result


def build_pipeline_plan(
    *,
    profile_path: Path,
    run_id: str,
    pipeline_name: str,
    queue: str,
    train_task_id: str,
    eval_task_id: str,
    report_task_id: str,
    version: str = '1.0.0',
    parameter_overrides: Path | None = None,
    monitor_artifacts: Sequence[str] = (),
) -> dict[str, Any]:
    """Validate inputs and return the native pipeline definition."""

    profile_path = profile_path.expanduser().resolve()
    profile = load_profile(profile_path)
    errors = validate_profile(profile, profile_path, require_paths=False)
    if errors:
        raise ValueError('Invalid ClearML profile:\n- ' + '\n- '.join(errors))
    values = {
        'run_id': run_id,
        'pipeline_name': pipeline_name,
        'queue': queue,
        'train_task_id': train_task_id,
        'eval_task_id': eval_task_id,
        'report_task_id': report_task_id,
        'version': version,
    }
    for name, value in values.items():
        if not str(value).strip():
            raise ValueError(f'{name} must not be empty')
    overrides = _load_overrides(parameter_overrides)
    steps = [
        {
            'name': 'train',
            'base_task_id': train_task_id,
            'parents': [],
            'parameter_override': overrides.get('train', {}),
        },
        {
            'name': 'eval',
            'base_task_id': eval_task_id,
            'parents': ['train'],
            'parameter_override': overrides.get('eval', {}),
        },
        {
            'name': 'report',
            'base_task_id': report_task_id,
            'parents': ['eval'],
            'parameter_override': overrides.get('report', {}),
        },
    ]
    return {
        'schema_version': 'clearml_native_pipeline_plan_v1',
        'run_id': run_id,
        'pipeline_name': pipeline_name,
        'project': profile['clearml_project'],
        'queue': queue,
        'version': version,
        'output_uri': _resolve_output_uri(profile),
        'parameters': {
            'run_id': run_id,
            'profile': str(profile_path),
        },
        'steps': steps,
        'monitor_artifacts': list(monitor_artifacts),
    }


def register_pipeline(plan: Mapping[str, Any], *, start: bool = False) -> dict[str, Any]:
    """Register the plan with ClearML and optionally start its controller Task."""

    try:
        from clearml.automation import PipelineController
    except ImportError as exc:
        raise RuntimeError('native pipeline registration requires the ClearML SDK') from exc

    kwargs: dict[str, Any] = {
        'name': plan['pipeline_name'],
        'project': plan['project'],
        'version': plan['version'],
        'abort_on_failure': True,
    }
    if plan.get('output_uri'):
        kwargs['output_uri'] = plan['output_uri']
    controller = PipelineController(**kwargs)
    controller.set_default_execution_queue(plan['queue'])
    for name, default in plan['parameters'].items():
        controller.add_parameter(name=name, default=default)
    for step in plan['steps']:
        step_kwargs: dict[str, Any] = {
            'name': step['name'],
            'base_task_id': step['base_task_id'],
            'parents': step['parents'],
            'execution_queue': plan['queue'],
            'parameter_override': step['parameter_override'],
        }
        if plan['monitor_artifacts']:
            step_kwargs['monitor_artifacts'] = plan['monitor_artifacts']
        controller.add_step(**step_kwargs)
    result = {
        'mode': 'registered',
        'run_id': plan['run_id'],
        'pipeline_name': plan['pipeline_name'],
        'queue': plan['queue'],
        'steps': [step['name'] for step in plan['steps']],
    }
    if start:
        started = controller.start()
        result['controller_task_id'] = getattr(started, 'id', started)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--pipeline-name', required=True)
    parser.add_argument('--queue', required=True)
    parser.add_argument('--train-task-id', required=True)
    parser.add_argument('--eval-task-id', required=True)
    parser.add_argument('--report-task-id', required=True)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--parameter-overrides', type=Path)
    parser.add_argument('--monitor-artifact', action='append', default=[])
    parser.add_argument('--plan-out', type=Path)
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--start', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.start and not args.register:
        raise SystemExit('--start requires --register')
    plan = build_pipeline_plan(
        profile_path=args.profile,
        run_id=args.run_id,
        pipeline_name=args.pipeline_name,
        queue=args.queue,
        train_task_id=args.train_task_id,
        eval_task_id=args.eval_task_id,
        report_task_id=args.report_task_id,
        version=args.version,
        parameter_overrides=args.parameter_overrides,
        monitor_artifacts=args.monitor_artifact,
    )
    if args.plan_out:
        args.plan_out.expanduser().resolve().write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
    result: dict[str, Any] = {'plan': plan}
    if args.register:
        result['registration'] = register_pipeline(plan, start=args.start)
    else:
        result['mode'] = 'plan'
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
