from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / 'scripts' / 'register_clearml_pipeline.py'
sys.path.insert(0, str(SCRIPT.parent))


def _module():
    spec = importlib.util.spec_from_file_location('clearml_native_pipeline_fixture', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(path: Path) -> Path:
    path.write_text(
        json.dumps({
            'schema_version': 'clearml_project_profile_v1',
            'project_id': 'fixture',
            'clearml_project': 'Fixture',
            'documents': {'experiment_roots': ['docs'], 'review_root': 'review'},
            'experiment_bundle': {'markdown': 'report.md', 'html': 'report.html', 'manifest': 'report_manifest.json', 'media_directories': ['charts']},
            'artifacts': {
                'output_uri': '${CLEARML_DEFAULT_OUTPUT_URI}',
                'checkpoint_policy': 'link_only',
                'review_bundle_policy': 'upload_selected',
                'raw_data_policy': 'never_upload',
            },
            'tasks': {
                'train': {'owner_repo': 'fixture', 'task_type': 'training'},
                'evaluate': {'owner_repo': 'fixture', 'task_type': 'testing'},
                'review': {'owner_repo': 'fixture', 'task_type': 'application'},
            },
            'metrics': {'train': {'loss': 'train/loss'}, 'evaluation': {'primary': 'eval/primary'}},
            'media': {'max_debug_samples_per_series': 2, 'upload': 'selected_review_only'},
        }),
        encoding='utf-8',
    )
    return path


def _plan(module, tmp_path: Path, overrides: Path | None = None):
    profile = _profile(tmp_path / 'profile.json')
    return module.build_pipeline_plan(
        profile_path=profile,
        run_id='run-1',
        pipeline_name='UrbanNav pipeline',
        queue='srnav-train',
        train_task_id='train-task',
        eval_task_id='eval-task',
        report_task_id='report-task',
        parameter_overrides=overrides,
        monitor_artifacts=('scorecard',),
    )


def test_build_pipeline_plan_has_explicit_order_and_parents(tmp_path: Path) -> None:
    plan = _plan(_module(), tmp_path)
    assert [step['name'] for step in plan['steps']] == ['train', 'eval', 'report']
    assert plan['steps'][1]['parents'] == ['train']
    assert plan['steps'][2]['parents'] == ['eval']
    assert plan['monitor_artifacts'] == ['scorecard']


def test_build_pipeline_plan_preserves_project_parameter_overrides(tmp_path: Path) -> None:
    overrides = tmp_path / 'overrides.json'
    overrides.write_text(json.dumps({'eval': {'General/input': '${train.artifacts.summary.url}'}}), encoding='utf-8')
    plan = _plan(_module(), tmp_path, overrides)
    assert plan['steps'][1]['parameter_override'] == {'General/input': '${train.artifacts.summary.url}'}


def test_register_pipeline_uses_native_queue_and_abort_on_failure(monkeypatch, tmp_path: Path) -> None:
    module = _module()
    monkeypatch.setenv('CLEARML_DEFAULT_OUTPUT_URI', 's3://fixture/output')
    plan = _plan(module, tmp_path)
    calls: list[tuple[str, object]] = []

    class FakeController:

        def __init__(self, **kwargs):
            calls.append(('init', kwargs))

        def set_default_execution_queue(self, queue):
            calls.append(('queue', queue))

        def add_parameter(self, **kwargs):
            calls.append(('parameter', kwargs))

        def add_step(self, **kwargs):
            calls.append(('step', kwargs))

        def start(self):
            calls.append(('start', None))
            return types.SimpleNamespace(id='controller-task')

    automation = types.ModuleType('clearml.automation')
    automation.PipelineController = FakeController
    clearml = types.ModuleType('clearml')
    clearml.automation = automation
    monkeypatch.setitem(sys.modules, 'clearml', clearml)
    monkeypatch.setitem(sys.modules, 'clearml.automation', automation)
    result = module.register_pipeline(plan, start=True)

    assert result['controller_task_id'] == 'controller-task'
    assert calls[0] == ('init', {
        'name': 'UrbanNav pipeline',
        'project': 'Fixture',
        'version': '1.0.0',
        'abort_on_failure': True,
        'output_uri': 's3://fixture/output',
    })
    steps = [value for kind, value in calls if kind == 'step']
    assert [step['name'] for step in steps] == ['train', 'eval', 'report']
    assert steps[1]['parents'] == ['train']
    assert all(step['execution_queue'] == 'srnav-train' for step in steps)


def test_start_requires_register(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(SystemExit, match='--start requires --register'):
        module.main([
            '--profile', str(_profile(tmp_path / 'profile.json')),
            '--run-id', 'run-1',
            '--pipeline-name', 'pipeline',
            '--queue', 'queue',
            '--train-task-id', 'train',
            '--eval-task-id', 'eval',
            '--report-task-id', 'report',
            '--start',
        ])
