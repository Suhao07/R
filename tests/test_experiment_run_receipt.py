from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from experiment_run_receipt import build_experiment_receipt, write_receipt
from experiment_visualization_manifest import build_visualization_manifest, write_manifest


def _write_record(path: Path) -> None:
    path.write_text(
        '''# 验证记录

experiment_record_version: 1

## 实验元数据

| 字段 | 记录 |
| --- | --- |
| 实验 ID | `fixture` |

## 实验的目的

验证 receipt。

## 实验的 setting

使用 fixture。

### 可视化与导出计划

`/tmp/fixture/visualization`。

## 记录实验结果

无。

### 可视化与产物

`/tmp/fixture/visualization/index.json`。

## 分析实验结果，可能的原因

无。

## 用户讨论与决策记录

| 时间 | 用户讨论/关注点 | 最终决定 | 对实验的影响 | 未解决问题 |
| --- | --- | --- | --- | --- |
| 2026-08-05 | 绑定记录 | 采用 | fail-closed | 无 |

## 接下来要做的实验

| 优先级 | 下一实验 | 假设 | 唯一主要变量 | 所需证据 | 通过/停止条件 | 依赖或授权 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | receipt | 可以写入 | receipt | JSON | 存在 | 无 |
''',
        encoding='utf-8',
    )


def _write_visualization_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create a planned manifest and a finished index for receipt tests."""

    manifest = tmp_path / 'visualization_manifest.json'
    index = tmp_path / 'visualization_index.json'
    write_manifest(
        manifest,
        build_visualization_manifest(
            run_id='fixture-run',
            run_kind='evaluation',
            run_root=tmp_path,
            phase='planned',
            tensorboard_logdir=None,
            dashboard_url=None,
            planned_outputs=['scorecard=' + str(tmp_path / 'scorecard.json')],
            artifacts=[],
        ),
    )
    scorecard = tmp_path / 'scorecard.json'
    scorecard.write_text('{"ok":true}\n', encoding='utf-8')
    write_manifest(
        index,
        build_visualization_manifest(
            run_id='fixture-run',
            run_kind='evaluation',
            run_root=tmp_path,
            phase='finished',
            tensorboard_logdir=None,
            dashboard_url=None,
            planned_outputs=['scorecard=' + str(scorecard)],
            artifacts=['scorecard=' + str(scorecard)],
        ),
    )
    return manifest, index


def test_receipt_binds_valid_record_and_artifact(tmp_path: Path) -> None:
    record = tmp_path / 'record.md'
    artifact = tmp_path / 'scorecard.json'
    _write_record(record)
    artifact.write_text('{"ok":true}\n', encoding='utf-8')
    _, visualization_index = _write_visualization_files(tmp_path)

    receipt = build_experiment_receipt(
        record=record,
        run_id='fixture-run',
        workstream_id='core-framework',
        phase='finished',
        validation_scope='full_split',
        repository_ids=['ms-swift'],
        command='fixture-command',
        artifact_specs=[
            f'scorecard={artifact}',
            f'visualization_index={visualization_index}',
        ],
    )
    output = tmp_path / 'receipt.json'
    write_receipt(output, receipt)

    saved = json.loads(output.read_text(encoding='utf-8'))
    assert saved['schema_version'] == 'research_experiment_receipt_v1'
    assert saved['experiment_record']['path'] == str(record.resolve())
    assert saved['artifacts'][0]['id'] == 'scorecard'
    assert len(saved['artifacts'][0]['sha256']) == 64


def test_receipt_rejects_missing_artifact(tmp_path: Path) -> None:
    record = tmp_path / 'record.md'
    _write_record(record)
    visualization_manifest, _ = _write_visualization_files(tmp_path)

    with pytest.raises(ValueError, match='Artifact does not exist'):
        build_experiment_receipt(
            record=record,
            run_id='fixture-run',
            workstream_id='core-framework',
            phase='started',
            validation_scope='full_split',
            repository_ids=['ms-swift'],
            command='fixture-command',
            artifact_specs=[
                f'visualization_manifest={visualization_manifest}',
                f'missing={tmp_path / "missing.json"}',
            ],
        )


def test_receipt_rejects_record_without_visualization_plan(tmp_path: Path) -> None:
    """A formal lifecycle receipt must not accept an unobservable run record."""

    record = tmp_path / 'record.md'
    _write_record(record)
    record.write_text(
        record.read_text(encoding='utf-8').replace(
            '### 可视化与导出计划\n\n`/tmp/fixture/visualization`。\n\n',
            '',
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='visual subsection'):
        build_experiment_receipt(
            record=record,
            run_id='fixture-run',
            workstream_id='core-framework',
            phase='started',
            validation_scope='mini_sample',
            repository_ids=['ms-swift'],
            command='fixture-command',
            artifact_specs=[],
        )


def test_started_receipt_requires_visualization_manifest(tmp_path: Path) -> None:
    record = tmp_path / 'record.md'
    source = tmp_path / 'source.jsonl'
    _write_record(record)
    source.write_text('{}\n', encoding='utf-8')

    with pytest.raises(ValueError, match='visualization_manifest'):
        build_experiment_receipt(
            record=record,
            run_id='fixture-run',
            workstream_id='core-framework',
            phase='started',
            validation_scope='full_split',
            repository_ids=['ms-swift'],
            command='fixture-command',
            artifact_specs=[f'source={source}'],
        )


def test_finished_receipt_requires_visualization_index(tmp_path: Path) -> None:
    record = tmp_path / 'record.md'
    scorecard = tmp_path / 'scorecard.json'
    _write_record(record)
    scorecard.write_text('{"ok":true}\n', encoding='utf-8')

    with pytest.raises(ValueError, match='visualization_index'):
        build_experiment_receipt(
            record=record,
            run_id='fixture-run',
            workstream_id='core-framework',
            phase='finished',
            validation_scope='full_split',
            repository_ids=['ms-swift'],
            command='fixture-command',
            artifact_specs=[f'scorecard={scorecard}'],
        )
