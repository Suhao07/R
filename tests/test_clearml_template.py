from __future__ import annotations

import json
import importlib.util
import py_compile
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from render_clearml_payload_manifest import (  # noqa: E402
    build_payload_manifest, write_json,
)
from validate_clearml_project_profile import (  # noqa: E402
    load_profile, validate_profile,
)


def _profile(tmp_path: Path) -> Path:
    docs = tmp_path / 'docs'
    review = tmp_path / 'review'
    docs.mkdir()
    review.mkdir()
    (docs / 'experiment.md').write_text('# experiment\n', encoding='utf-8')
    (docs / 'embedded-plot.png').write_bytes(b'plot')
    (review / 'scorecard.json').write_text('{"ok": true}\n', encoding='utf-8')
    (review / 'failure.mp4').write_bytes(b'fixture-media')
    profile = tmp_path / 'profile.yaml'
    profile.write_text(
        f'''schema_version: clearml_project_profile_v1
project_id: fixture
clearml_project: Fixture
documents:
  experiment_roots:
    - {docs}
  review_root: {review}
artifacts:
  output_uri: ${{CLEARML_DEFAULT_OUTPUT_URI}}
  checkpoint_policy: link_only
  review_bundle_policy: upload_selected
  raw_data_policy: never_upload
tasks:
  evaluate:
    owner_repo: fixture-repo
    task_type: testing
metrics:
  evaluation:
    primary: eval/primary
media:
  max_debug_samples_per_series: 2
  upload: selected_review_only
''',
        encoding='utf-8',
    )
    return profile


def test_profile_validates_paths_and_policy(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    assert validate_profile(profile, profile_path,
                            workspace_root=tmp_path) == []


def test_profile_rejects_secret_fields_and_workspace_escape(
        tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    profile['network'] = {'api_key': 'do-not-store'}
    profile['documents']['review_root'] = '/tmp/outside'
    errors = validate_profile(profile,
                              profile_path,
                              workspace_root=tmp_path,
                              require_paths=False)
    assert any('secret-like field' in error for error in errors)
    assert any('escapes workspace root' in error for error in errors)


def test_profile_rejects_unknown_fields(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    profile['unexpected'] = True
    errors = validate_profile(profile, profile_path, workspace_root=tmp_path)
    assert 'unknown field: profile.unexpected' in errors


def test_profile_rejects_embedded_server_endpoint(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    profile['network'] = {
        'server_profile': 'local_ssh_tunnel',
        'api_url': 'http://private.example.invalid:8008',
    }
    errors = validate_profile(profile, profile_path, workspace_root=tmp_path)
    assert 'unknown field: network.api_url' in errors


def test_profile_accepts_metric_sources(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    profile['metric_sources'] = {'evaluation': {'primary': 'current.primary'}}
    assert validate_profile(profile, profile_path,
                            workspace_root=tmp_path) == []


def test_payload_manifest_is_local_only_and_bounded(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    output = tmp_path / 'payload.json'
    receipt = tmp_path / 'review' / 'finished_receipt.json'
    receipt.write_text('{"status": "finished"}\n', encoding='utf-8')
    scorecard = tmp_path / 'review' / 'scorecard.json'
    payload = build_payload_manifest(
        profile_path=profile_path,
        run_id='fixture-run',
        workspace_root=tmp_path,
        max_debug_samples=1,
        receipts=[receipt],
        scorecards=[scorecard],
    )
    write_json(output, payload)
    saved = json.loads(output.read_text(encoding='utf-8'))

    assert saved['schema_version'] == 'clearml_payload_manifest_v1'
    assert saved['summary']['document_files'] == 1
    assert saved['summary']['review_files'] == 3
    assert len(saved['debug_sample_candidates']) == 1
    assert saved['summary']['required_evidence'] == 2
    assert {item['role']
            for item in saved['required_evidence']
            } == {'receipt', 'scorecard'}
    assert saved['clearml']['upload_policies']['raw_data'] == 'never_upload'


def test_payload_manifest_enforces_media_series_limit_and_review_root(
        tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    media_a = tmp_path / 'review' / 'series-a' / 'case.png'
    media_a.parent.mkdir()
    media_a.write_bytes(b'a')
    media_b = tmp_path / 'review' / 'series-a' / 'case-2.png'
    media_b.write_bytes(b'b')

    with pytest.raises(ValueError, match='exceeds the limit'):
        build_payload_manifest(
            profile_path=profile_path,
            run_id='fixture-run',
            workspace_root=tmp_path,
            media_specs=[
                f'fpv=series-a={media_a}', f'fpv=series-a={media_b}',
                f'fpv=series-a={media_a}'
            ],
        )

    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'outside')
    with pytest.raises(ValueError, match='under documents.review_root'):
        build_payload_manifest(
            profile_path=profile_path,
            run_id='fixture-run',
            workspace_root=tmp_path,
            media_specs=[f'fpv=series-b={outside}'],
        )


def test_payload_manifest_rejects_invalid_profile(tmp_path: Path) -> None:
    profile_path = _profile(tmp_path)
    profile = load_profile(profile_path)
    profile['artifacts']['raw_data_policy'] = 'upload_all'
    profile_path.write_text(json.dumps(profile), encoding='utf-8')

    with pytest.raises(ValueError, match='raw_data_policy'):
        build_payload_manifest(profile_path=profile_path, run_id='fixture-run')


def test_generic_reporter_template_supports_local_dry_run(
        tmp_path: Path) -> None:
    template_root = Path(__file__).parents[1] / 'templates' / 'clearml'
    adapter_path = tmp_path / 'clearml_adapter.py'
    reporter_path = tmp_path / 'report_payload.py'
    shutil.copyfile(template_root / 'clearml_adapter.py.template',
                    adapter_path)
    shutil.copyfile(template_root / 'report_payload.py.template',
                    reporter_path)
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location('template_reporter',
                                                      reporter_path)
        assert spec is not None and spec.loader is not None
        reporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reporter)
        profile_path = _profile(tmp_path)
        summary = tmp_path / 'summary.json'
        summary.write_text('{"primary": 0.75}\n', encoding='utf-8')
        linkage = tmp_path / 'linkage.json'
        result = reporter.report_payload(
            profile_path=profile_path,
            run_id='fixture-run',
            task_kind='evaluate',
            summary_path=summary,
            artifact_specs=[],
            linkage_path=linkage,
            dry_run=True,
        )
    finally:
        sys.path.pop(0)
    assert result['mode'] == 'dry_run'
    assert result['metrics']['evaluation.primary'] == 0.75
    assert json.loads(linkage.read_text(encoding='utf-8'))['task_id'] is None


def test_generic_reporter_auto_discovers_experiment_bundle(tmp_path: Path) -> None:
    template_root = Path(__file__).parents[1] / 'templates' / 'clearml'
    adapter_path = tmp_path / 'clearml_adapter.py'
    reporter_path = tmp_path / 'report_payload.py'
    shutil.copyfile(template_root / 'clearml_adapter.py.template', adapter_path)
    shutil.copyfile(template_root / 'report_payload.py.template', reporter_path)
    spec = importlib.util.spec_from_file_location('template_bundle_reporter', reporter_path)
    assert spec is not None and spec.loader is not None
    reporter = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tmp_path))
    try:
        spec.loader.exec_module(reporter)
        profile_path = _profile(tmp_path)
        profile = load_profile(profile_path)
        profile['experiment_bundle'] = {
            'markdown': 'report.md',
            'html': 'report.html',
            'manifest': 'report_manifest.json',
            'media_directories': ['charts'],
        }
        profile_path.write_text(json.dumps(profile), encoding='utf-8')

        root = tmp_path / 'review' / 'bundle-1'
        root.mkdir(parents=True)
        (root / 'report.md').write_text('# 实验\n', encoding='utf-8')
        (root / 'report.html').write_text('<h1>实验</h1>\n', encoding='utf-8')
        (root / 'scorecard.json').write_text('{"primary": 0.9}\n', encoding='utf-8')
        (root / 'receipt.json').write_text('{"status": "finished"}\n', encoding='utf-8')
        (root / 'charts').mkdir()
        (root / 'charts' / 'metrics.png').write_bytes(b'png')
        (root / 'raw').mkdir()
        (root / 'raw' / 'predictions.jsonl').write_text('{}\n', encoding='utf-8')
        (root / 'report_manifest.json').write_text(
            json.dumps({'sections': {'主要指标': [{'title': '指标', 'path': 'charts/metrics.png'}]}}),
            encoding='utf-8',
        )
        linkage = root / 'clearml_task_linkage.json'
        result = reporter.report_payload(
            profile_path=profile_path,
            run_id='bundle-1',
            task_kind='evaluate',
            summary_path=None,
            artifact_specs=[],
            linkage_path=None,
            experiment_root=root,
            dry_run=True,
        )
    finally:
        sys.path.pop(0)

    assert result['auto_discovered'] is True
    assert result['experiment_root'] == str(root.resolve())
    assert {
        'report_markdown', 'report_html', 'report_manifest', 'scorecard', 'receipt'
    } <= set(result['artifact_names'])
    assert result['media_candidates'] == 2
    assert json.loads(linkage.read_text(encoding='utf-8'))['task_id'] is None


def test_generic_adapter_requires_resolved_checkpoint_uri(
        monkeypatch, tmp_path: Path) -> None:
    template_root = Path(__file__).parents[1] / 'templates' / 'clearml'
    adapter_path = tmp_path / 'clearml_adapter.py'
    shutil.copyfile(template_root / 'clearml_adapter.py.template',
                    adapter_path)
    spec = importlib.util.spec_from_file_location('template_adapter',
                                                  adapter_path)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    class FakeTaskFactory:

        @staticmethod
        def init(**_kwargs):
            raise AssertionError('Task must not start without a resolved URI')

    monkeypatch.delenv('CLEARML_DEFAULT_OUTPUT_URI', raising=False)
    monkeypatch.setenv('RANK', '0')
    monkeypatch.setitem(sys.modules, 'clearml', type('ClearML', (), {
        'Task': FakeTaskFactory,
    }))
    profile = {
        'project_id': 'fixture',
        'clearml_project': 'Fixture',
        'artifacts': {
            'output_uri': '${CLEARML_DEFAULT_OUTPUT_URI}',
            'checkpoint_policy': 'upload_selected',
        },
    }
    run = adapter.ClearMLRun(profile, run_id='fixture-checkpoint', task_kind='train')
    with pytest.raises(ValueError, match='resolved artifacts.output_uri'):
        run.start()


def test_generic_adapter_uploads_checkpoint_directory(
        monkeypatch, tmp_path: Path) -> None:
    template_root = Path(__file__).parents[1] / 'templates' / 'clearml'
    adapter_path = tmp_path / 'clearml_adapter.py'
    shutil.copyfile(template_root / 'clearml_adapter.py.template',
                    adapter_path)
    spec = importlib.util.spec_from_file_location('template_adapter_upload',
                                                  adapter_path)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    calls: list[tuple[str, object]] = []

    class FakeTask:

        def get_logger(self):
            return type('Logger', (), {})()

        def connect(self, config, name):
            calls.append(('connect', (config, name)))

        def upload_artifact(self, **kwargs):
            calls.append(('upload', kwargs))

    class FakeTaskFactory:

        @staticmethod
        def init(**_kwargs):
            return FakeTask()

    monkeypatch.setenv('CLEARML_DEFAULT_OUTPUT_URI', 's3://fixture/output')
    monkeypatch.setenv('RANK', '0')
    monkeypatch.setitem(sys.modules, 'clearml', type('ClearML', (), {
        'Task': FakeTaskFactory,
    }))
    checkpoint = tmp_path / 'checkpoint-1'
    checkpoint.mkdir()
    (checkpoint / 'weights.bin').write_bytes(b'weights')
    profile = {
        'project_id': 'fixture',
        'clearml_project': 'Fixture',
        'artifacts': {
            'output_uri': '${CLEARML_DEFAULT_OUTPUT_URI}',
            'checkpoint_policy': 'upload_selected',
        },
    }
    run = adapter.ClearMLRun(profile, run_id='fixture-checkpoint', task_kind='train')
    run.start()
    run.record_checkpoint(checkpoint, step=1)
    assert calls == [
        ('connect', ({
            'global_step': 1,
            'path': str(checkpoint),
            'policy': 'upload_selected',
        }, 'checkpoint')),
        ('upload', {
            'name': 'checkpoint_step_1',
            'artifact_object': str(checkpoint),
        }),
    ]


def test_generic_adapter_downloads_checkpoint_directory(monkeypatch, tmp_path: Path) -> None:
    template_root = Path(__file__).parents[1] / 'templates' / 'clearml'
    adapter_path = tmp_path / 'clearml_adapter.py'
    shutil.copyfile(template_root / 'clearml_adapter.py.template', adapter_path)
    spec = importlib.util.spec_from_file_location('template_adapter_download', adapter_path)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    cached = tmp_path / 'cache' / 'checkpoint-1'
    cached.mkdir(parents=True)
    (cached / 'weights.bin').write_bytes(b'weights')

    class FakeArtifact:

        def get_local_copy(self, **_kwargs):
            return str(cached)

    class FakeTask:
        artifacts = {'checkpoint_step_1': FakeArtifact()}

    class FakeTaskFactory:

        @staticmethod
        def get_task(**kwargs):
            assert kwargs == {'task_id': 'task-fixture'}
            return FakeTask()

    monkeypatch.setitem(sys.modules, 'clearml', type('ClearML', (), {'Task': FakeTaskFactory}))
    restored = tmp_path / 'restored' / 'checkpoint-1'
    manifest = adapter.download_clearml_artifact('task-fixture', 'checkpoint_step_1', restored)

    assert (restored / 'weights.bin').read_bytes() == b'weights'
    assert manifest['files'] == 1
    assert manifest['task_id'] == 'task-fixture'
    assert manifest['artifact_name'] == 'checkpoint_step_1'


def test_training_hook_template_compiles() -> None:
    path = (Path(__file__).parents[1] / 'templates' / 'clearml' /
            'train_hook.py.template')
    py_compile.compile(
        str(path),
        cfile='/tmp/clearml_train_hook_template.pyc',
        doraise=True,
    )
