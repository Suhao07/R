from __future__ import annotations

import json
import sys
from unittest.mock import patch
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from clearml_server_preflight import (  # noqa: E402
    check_endpoint, parse_endpoint, run_preflight,
)


class _Response:

    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _profile(tmp_path: Path) -> Path:
    docs = tmp_path / 'docs'
    review = tmp_path / 'review'
    docs.mkdir()
    review.mkdir()
    (docs / 'record.md').write_text('# record\n', encoding='utf-8')
    profile = tmp_path / 'profile.json'
    profile.write_text(
        json.dumps({
            'schema_version': 'clearml_project_profile_v1',
            'project_id': 'fixture',
            'clearml_project': 'Fixture',
            'documents': {
                'experiment_roots': [str(docs)],
                'review_root': str(review),
            },
            'artifacts': {
                'output_uri': 'file:///tmp/clearml',
                'checkpoint_policy': 'link_only',
                'review_bundle_policy': 'upload_selected',
                'raw_data_policy': 'never_upload',
            },
            'tasks': {
                'evaluate': {
                    'owner_repo': 'fixture',
                    'task_type': 'testing'
                }
            },
            'metrics': {
                'evaluation': {
                    'primary': 'eval/primary'
                }
            },
            'media': {
                'max_debug_samples_per_series': 1,
                'upload': 'selected_review_only',
            },
        }),
        encoding='utf-8',
    )
    return profile


def test_parse_endpoint_rejects_non_http() -> None:
    with pytest.raises(ValueError, match='http'):
        parse_endpoint('api=file:///tmp/server')


def test_check_endpoint_reports_service_without_body() -> None:
    with patch('clearml_server_preflight.urllib.request.urlopen',
               return_value=_Response()):
        result = check_endpoint('http://127.0.0.1:8008', timeout=1)
    assert result['reachable'] is True
    assert result['status'] == 200
    assert 'body' not in result


def test_preflight_validates_profile_and_endpoint(tmp_path: Path) -> None:
    config = tmp_path / 'clearml.conf'
    config.write_text('# fixture only\n', encoding='utf-8')
    with patch('clearml_server_preflight.urllib.request.urlopen',
               return_value=_Response()):
        report = run_preflight(
            profile_path=_profile(tmp_path),
            workspace_root=tmp_path,
            endpoints=['api=http://127.0.0.1:8008'],
            clearml_config=config,
        )
    assert report['ready'] is True
    assert report['profile']['valid'] is True
    assert report['clearml_config']['configured'] is True
