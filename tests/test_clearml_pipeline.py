from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / 'scripts' / 'run_clearml_pipeline.py'


def _module():
    spec = importlib.util.spec_from_file_location('clearml_pipeline_fixture', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_orders_commands_and_binds_final_receipt(monkeypatch, tmp_path: Path) -> None:
    module = _module()
    profile = tmp_path / 'profile.yaml'
    profile.write_text('profile\n', encoding='utf-8')
    root = tmp_path / 'experiment'
    root.mkdir()
    (root / 'train_summary.json').write_text('{}\n', encoding='utf-8')
    calls: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(module, '_run', lambda command, **_: calls.append(('run', tuple(command))))

    def fake_reporter(command, **_):
        calls.append(('report', tuple(command)))
        return {'task_id': f'task-{len([item for item in calls if item[0] == "report"])}'}

    monkeypatch.setattr(module, '_run_reporter', fake_reporter)
    result = module.run_pipeline(
        profile=profile,
        run_id='fixture-run',
        experiment_root=root,
        train_command='python train.py --steps 1',
        eval_command='python eval.py',
    )

    assert [kind for kind, _ in calls] == ['run', 'report', 'run', 'report']
    assert calls[0][1] == ('python', 'train.py', '--steps', '1')
    assert calls[2][1] == ('python', 'eval.py')
    assert '--pipeline-parent-task-id' in calls[3][1]
    assert 'task-1' in calls[3][1]
    assert '--pipeline-receipt' in calls[3][1]
    assert '--artifact' not in calls[3][1]
    saved = json.loads((root / 'pipeline_receipt.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'completed'
    assert saved['eval_report']['task_id'] == 'task-2'
    assert result['eval_report']['task_id'] == 'task-2'


def test_pipeline_writes_failed_stage_receipt(monkeypatch, tmp_path: Path) -> None:
    module = _module()
    profile = tmp_path / 'profile.yaml'
    profile.write_text('profile\n', encoding='utf-8')
    root = tmp_path / 'experiment'
    root.mkdir()
    (root / 'train_summary.json').write_text('{}\n', encoding='utf-8')

    def fail(command, **_):
        if tuple(command) == ('python', 'eval.py'):
            raise RuntimeError('evaluation command failed')

    monkeypatch.setattr(module, '_run', fail)
    monkeypatch.setattr(module, '_run_reporter', lambda *_args, **_kwargs: {'task_id': 'task-1'})

    with pytest.raises(RuntimeError, match='evaluation command failed'):
        module.run_pipeline(
            profile=profile,
            run_id='fixture-failed',
            experiment_root=root,
            train_command='python train.py',
            eval_command='python eval.py',
        )

    saved = json.loads((root / 'pipeline_receipt.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'failed'
    assert saved['failed_stage'] == 'eval'
    assert saved['error'] == 'evaluation command failed'


def test_pipeline_records_missing_train_summary_after_training(
        monkeypatch, tmp_path: Path) -> None:
    module = _module()
    profile = tmp_path / 'profile.yaml'
    profile.write_text('profile\n', encoding='utf-8')
    root = tmp_path / 'experiment'
    root.mkdir()
    monkeypatch.setattr(module, '_run', lambda *_args, **_kwargs: None)

    try:
        module.run_pipeline(
            profile=profile,
            run_id='fixture-run',
            experiment_root=root,
            train_command='python train.py',
            eval_command='python eval.py',
        )
    except FileNotFoundError as exc:
        assert 'train summary' in str(exc)
    else:
        raise AssertionError('missing train summary must stop the pipeline')
    saved = json.loads((root / 'pipeline_receipt.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'failed'
    assert saved['failed_stage'] == 'train_report'
