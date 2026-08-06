from __future__ import annotations

from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'

import sys

sys.path.insert(0, str(SCRIPTS_DIR))

from experiment_visualization_manifest import build_visualization_manifest, write_manifest


def test_planned_manifest_allows_future_outputs(tmp_path: Path) -> None:
    output = tmp_path / 'visualization_manifest.json'
    future_scorecard = tmp_path / 'scorecard.json'
    manifest = build_visualization_manifest(
        run_id='fixture-run',
        run_kind='evaluation',
        run_root=tmp_path,
        phase='planned',
        tensorboard_logdir=None,
        dashboard_url=None,
        planned_outputs=[f'scorecard={future_scorecard}'],
        artifacts=[],
    )
    write_manifest(output, manifest)

    assert output.is_file()
    assert manifest['planned_outputs'][0]['exists'] is False


def test_finished_index_requires_existing_artifacts(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.json'

    with pytest.raises(ValueError, match='Visualization artifact does not exist'):
        build_visualization_manifest(
            run_id='fixture-run',
            run_kind='training',
            run_root=tmp_path,
            phase='finished',
            tensorboard_logdir=None,
            dashboard_url=None,
            planned_outputs=[],
            artifacts=[f'log={missing}'],
        )
