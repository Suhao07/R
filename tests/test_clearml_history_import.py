from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(
    __file__).parents[1] / 'scripts' / 'render_clearml_history_import.py'
sys.path.insert(0, str(SCRIPT.parent))


def _module():
    spec = importlib.util.spec_from_file_location('clearml_history_fixture',
                                                  SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(tmp_path: Path) -> Path:
    review = tmp_path / 'review'
    review.mkdir()
    profile = tmp_path / 'profile.json'
    profile.write_text(
        '{\n'
        '  "schema_version": "clearml_project_profile_v1",\n'
        '  "project_id": "fixture",\n'
        '  "clearml_project": "Fixture",\n'
        f'  "documents": {{"experiment_roots": ["{tmp_path / "docs"}"], '
        f'"review_root": "{review}"}},\n'
        '  "artifacts": {"output_uri": "file:///tmp/out", '
        '"checkpoint_policy": "link_only", '
        '"review_bundle_policy": "upload_selected", '
        '"raw_data_policy": "never_upload"},\n'
        '  "tasks": {"evaluate": {"owner_repo": "fixture", '
        '"task_type": "testing"}},\n'
        '  "metrics": {"evaluation": {"primary": "eval/primary"}},\n'
        '  "media": {"max_debug_samples_per_series": 2, '
        '"upload": "selected_review_only"}\n'
        '}\n',
        encoding='utf-8',
    )
    (tmp_path / 'docs').mkdir()
    return profile


def test_history_import_labels_missing_started_receipt_as_index_only(
        tmp_path: Path) -> None:
    module = _module()
    profile = _profile(tmp_path)
    root = tmp_path / 'review' / 'historical-a'
    root.mkdir()
    (root / 'scorecard.json').write_text('{"primary": 0.5}\n',
                                         encoding='utf-8')
    (root / 'review.html').write_text('<html></html>\n', encoding='utf-8')
    (root / 'case.jpg').write_bytes(b'jpg')
    manifest = module.build_history_manifest(
        profile_path=profile,
        roots=[root],
        workspace_root=tmp_path,
    )
    record = manifest['records'][0]
    assert record['import_label'] == 'historical_import'
    assert record['reproducibility'] == 'historical_index_only'
    assert record['started_receipt_present'] is False
    assert record['summary']['media_candidates'] == 1
    assert manifest['upload_required'] is False


def test_history_import_records_started_and_finished_evidence(
        tmp_path: Path) -> None:
    module = _module()
    profile = _profile(tmp_path)
    root = tmp_path / 'review' / 'historical-b'
    root.mkdir()
    (root / 'started_receipt.json').write_text('{}\n', encoding='utf-8')
    (root / 'finished_results_record.json').write_text('{}\n',
                                                       encoding='utf-8')
    (root / 'visualization_index.json').write_text('{}\n', encoding='utf-8')
    manifest = module.build_history_manifest(
        profile_path=profile,
        roots=[root],
        workspace_root=tmp_path,
    )
    record = manifest['records'][0]
    assert record['reproducibility'] == 'historical_run_with_started_receipt'
    assert record['finished_evidence_present'] is True
    assert manifest['summary']['with_started_receipt'] == 1


def test_history_import_rejects_roots_outside_review_root(
        tmp_path: Path) -> None:
    module = _module()
    profile = _profile(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    with pytest.raises(ValueError, match='under documents.review_root'):
        module.build_history_manifest(
            profile_path=profile,
            roots=[outside],
            workspace_root=tmp_path,
        )
