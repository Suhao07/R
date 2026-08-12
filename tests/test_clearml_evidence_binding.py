from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(
    __file__).parents[1] / 'scripts' / 'render_clearml_evidence_binding.py'


def _module():
    spec = importlib.util.spec_from_file_location('clearml_binding_fixture',
                                                  SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _linkage(path: Path) -> Path:
    path.write_text(
        json.dumps({
            'schema_version': 'clearml_task_linkage_v1',
            'project_id': 'fixture',
            'clearml_project': 'Fixture',
            'run_id': 'run-1',
            'task_kind': 'evaluate',
            'task_id': 'task-1',
            'enabled': True,
        }),
        encoding='utf-8',
    )
    return path


def test_binding_preserves_canonical_sources_and_maps_both_directions(
        tmp_path: Path) -> None:
    module = _module()
    linkage = _linkage(tmp_path / 'linkage.json')
    record = tmp_path / 'experiment.md'
    receipt = tmp_path / 'finished_receipt.json'
    record.write_text('# experiment\n', encoding='utf-8')
    receipt.write_text('{"phase": "finished"}\n', encoding='utf-8')
    binding = module.build_binding(
        linkage_path=linkage,
        evidence_specs=[f'experiment_record={record}', f'receipt={receipt}'],
        task_url='http://127.0.0.1:8080/projects/fixture/tasks/task-1',
        out_path=tmp_path / 'binding.json',
    )
    assert binding['clearml']['id'] == 'task-1'
    assert binding['clearml']['url'].endswith('task-1')
    assert binding['relations']['task_to_evidence'] == [
        'experiment_record', 'receipt'
    ]
    assert binding['relations']['evidence_to_task']['receipt'] == 'task-1'
    assert binding['canonical_sources_unchanged'] is True
    assert record.read_text(encoding='utf-8') == '# experiment\n'


def test_binding_rejects_duplicate_roles_and_missing_files(
        tmp_path: Path) -> None:
    module = _module()
    linkage = _linkage(tmp_path / 'linkage.json')
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate evidence role'):
        module.build_binding(
            linkage_path=linkage,
            evidence_specs=[f'receipt={evidence}', f'receipt={evidence}'],
        )
    with pytest.raises(FileNotFoundError):
        module.build_binding(
            linkage_path=linkage,
            evidence_specs=[f'receipt={tmp_path / "missing.json"}'],
        )


def test_binding_dry_metadata_can_allow_missing_without_uploading(
        tmp_path: Path) -> None:
    module = _module()
    linkage = _linkage(tmp_path / 'linkage.json')
    binding = module.build_binding(
        linkage_path=linkage,
        evidence_specs=[f'receipt={tmp_path / "missing.json"}'],
        require_paths=False,
    )
    assert binding['evidence'][0]['exists'] is False
    assert binding['clearml']['id'] == 'task-1'
