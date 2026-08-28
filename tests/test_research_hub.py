"""Focused tests for the local research management and review control plane."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote

import pytest

PORTFOLIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORTFOLIO_ROOT))

from research_hub.catalog import load_catalog, scan_and_write, search_catalog
from research_hub.config import load_config, read_source_registry, sha256_file, write_source_registry
from research_hub.documents import DocumentConflictError, DocumentError, DocumentStore
from research_hub.experiment_frontend import render_experiment_page
from research_hub.frontend import render_index
from research_hub.lifecycle import LifecycleError, LifecycleStore
from research_hub.rendering import render_document_pages
from research_hub.reviews import ReviewStore
from research_hub.server import make_server


def _valid_record() -> str:
    """Return the smallest record accepted by the existing structural validator."""

    return """# Test experiment

experiment_record_version: 1

## 实验元数据

| 字段 | 记录 |
| --- | --- |
| 实验 ID | `test-experiment` |
| 状态 | `planned` |

## 实验的目的

验证 Hub 文档保护。

## 实验的 setting

### 可视化与导出计划

N/A，文档测试不启动运行。

## 记录实验结果

### 可视化与产物

N/A，文档测试没有产物。

## 分析实验结果，可能的原因

inconclusive。

## 用户讨论与决策记录

| 时间 | 用户讨论/关注点 | 最终决定 | 对实验的影响 | 未解决问题 |
| --- | --- | --- | --- | --- |
| `2026-08-11` | Hub test | 采用 | 验证写回 | 无 |

## 接下来要做的实验

| 优先级 | 下一实验 | 假设 | 唯一主要变量 | 所需证据 | 通过/停止条件 | 依赖或授权 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | save test | 写回安全 | 文本 | diff | 保存成功 | 无 |
"""


@pytest.fixture()
def hub_config(tmp_path: Path):
    """Build a disposable workspace that follows the real source registry layout."""

    portfolio = tmp_path / "ResearchWorkflow"
    portfolio.mkdir()
    review = tmp_path / "review_outputs"
    review.mkdir()
    ms_docs = tmp_path / "ms-swift" / "docs" / "Experiments"
    ms_docs.mkdir(parents=True)
    route_docs = tmp_path / "Urban-Nav-SR" / "Agent_part" / "RouteServer" / "docs"
    route_docs.mkdir(parents=True)
    (portfolio / "runs").mkdir()
    status = portfolio / "workstreams" / "test" / "STATUS.html"
    status.parent.mkdir(parents=True)
    status.write_text(
        '<body data-workflow-doc="STATUS"><div data-field="workstream-id"><p data-value="true">test</p></div></body>',
        encoding="utf-8",
    )
    scripts = portfolio / "scripts"
    scripts.mkdir()
    (scripts / "validate_experiment_record.py").write_text(
        "def validate_experiment_record(path):\n"
        "    text = path.read_text(encoding='utf-8')\n"
        "    return [] if 'experiment_record_version: 1' in text and '## 接下来要做的实验' in text else ['invalid record']\n",
        encoding="utf-8",
    )
    (portfolio / "research_hub_sources.json").write_text(
        json.dumps(
            {
                "schema_version": "research_hub_source_registry_v2",
                "artifact_root": "../review_outputs",
                "hub_state_relative": "_research_hub",
                "scan_roots": [
                    {
                        "id": "review_outputs",
                        "path": "../review_outputs",
                        "mode": "read_only_artifacts",
                        "project_id": "shared-evidence",
                        "workstream_id": "research-review-hub",
                    },
                    {
                        "id": "ms_swift_experiments",
                        "path": "../ms-swift/docs/Experiments",
                        "mode": "experiment_documents",
                        "project_id": "ms-swift",
                        "workstream_id": "core-framework",
                    },
                    {
                        "id": "urbannav_routeserver_docs",
                        "path": "../Urban-Nav-SR/Agent_part/RouteServer/docs",
                        "mode": "experiment_documents",
                        "project_id": "urbannav-sr",
                        "workstream_id": "core-framework",
                    },
                    {
                        "id": "portfolio_evidence",
                        "path": ".",
                        "mode": "portfolio_evidence",
                        "project_id": "research-workflow",
                        "workstream_id": "research-review-hub",
                    },
                ],
                "limits": {"json_parse_bytes": 2097152, "jsonl_summary_bytes": 5242880, "queue_read_bytes": 16777216, "attachment_upload_bytes": 1048576},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_config(portfolio)


def test_scan_catalog_and_static_index(hub_config) -> None:
    """Scanner should discover reports, canonical records, and immutable queues."""

    review = hub_config.artifact_root
    (review / "report.html").write_text("<title>Historical review</title>", encoding="utf-8")
    (review / "checkpoint.safetensors").write_bytes(b"not exposed")
    queue = review / "diagnosis.jsonl"
    queue.write_text(
        json.dumps({"schema_version": "urbannav_benchmark_slice_review_diagnosis_v1", "sample_id": "case-1", "review_status": "pending"}) + "\n",
        encoding="utf-8",
    )
    document = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "test.md"
    document.write_text(_valid_record() + "\n![example](figure.png)\n\n公式 $E=mc^2$。\n", encoding="utf-8")
    (document.parent / "figure.png").write_bytes(b"not-a-real-png")
    catalog = scan_and_write(hub_config)
    assert catalog["summary"]["html_count"] == 1
    assert catalog["summary"]["queue_count"] == 1
    assert catalog["summary"]["writable_document_count"] == 1
    assert catalog["settings"]["source_registry"]["artifact_root"] == "../review_outputs"
    assert next(item for item in catalog["artifacts"] if item["relative_path"] == "checkpoint.safetensors")["openable"] is False
    assert search_catalog(hub_config, "Historical")[0]["title"] == "Historical review"
    render_document_pages(hub_config, catalog)
    rendered_document = next(item for item in catalog["documents"] if item["writable"])
    assert rendered_document["static_content"].startswith("# Test experiment")
    rendered = hub_config.artifact_root / rendered_document["rendered_href"]
    assert rendered.is_file()
    rendered_text = rendered.read_text(encoding="utf-8")
    assert (document.parent / "figure.png").resolve().as_uri() in rendered_text
    assert "../vendor/katex/katex.min.js" in rendered_text
    assert "renderMathInElement" in rendered_text
    assert (hub_config.state_root / "vendor" / "katex" / "katex.min.css").is_file()
    static = render_index(catalog, live=False)
    assert "Historical review" in static
    assert "static · file:// local preview" in static
    assert 'id="homeSidebar"' in static
    assert 'data-home-tab="experiments"' in static
    assert 'research-hub-home-theme' in static


def test_experiment_bundle_is_aggregated_and_routed_metadata_is_renderable(hub_config) -> None:
    """A bundle binds its canonical record and manifest-selected media."""

    root = hub_config.artifact_root / "bundle-1"
    (root / "images").mkdir(parents=True)
    (root / "videos").mkdir()
    (root / "report.md").write_text(
        "# Bundle report\n\n| 实验 ID | `bundle-experiment-1` |\n",
        encoding="utf-8",
    )
    (root / "report.html").write_text("<html><body>full report</body></html>", encoding="utf-8")
    (root / "scorecard.json").write_text('{"metric": 0.75}\n', encoding="utf-8")
    (root / "clearml_task_linkage.json").write_text(
        json.dumps({
            "schema_version": "clearml_task_linkage_v1",
            "project_id": "fixture",
            "clearml_project": "Fixture",
            "run_id": "bundle-run-1",
            "task_kind": "evaluate",
            "task_id": "0123456789abcdef0123456789abcdef",
        }),
        encoding="utf-8",
    )
    (root / "clearml_ui_acceptance_task_linkage.json").write_text(
        json.dumps({
            "schema_version": "clearml_task_linkage_v1",
            "project_id": "fixture",
            "clearml_project": "Fixture",
            "run_id": "bundle-ui-acceptance-1",
            "task_kind": "evaluate",
            "task_id": "fedcba9876543210fedcba9876543210",
        }),
        encoding="utf-8",
    )
    (root / "report_manifest.json").write_text(
        json.dumps({"sections": {"成功案例": [{"title": "case", "path": "images/case.jpg"}]}}),
        encoding="utf-8",
    )
    for name in (
        "attention_review_manifest.json",
        "goal_sweep.json",
        "goal_sweep.predictions.npz",
    ):
        (root / name).write_bytes(b"{}" if name.endswith(".json") else b"npz")
    (root / "attention_maps").mkdir()
    (root / "attention_maps" / "decoder_step_0001.npz").write_bytes(b"npz")
    (root / "images" / "case.jpg").write_bytes(b"jpg")
    second = hub_config.artifact_root / "bundle-2"
    second.mkdir()
    (second / "report.md").write_text("# Second bundle\n", encoding="utf-8")
    (second / "clearml_task_linkage.json").write_text(
        json.dumps({"run_id": "bundle-run-2", "clearml_project": "FWTW"}),
        encoding="utf-8",
    )
    canonical = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "bundle.md"
    canonical.write_text(_valid_record().replace("test-experiment", "bundle-experiment-1"), encoding="utf-8")
    catalog = scan_and_write(hub_config)
    assert len(catalog["experiments"]) == 2
    assert next(item for item in catalog["experiments"] if item["run_id"] == "bundle-run-2")["project_id"] == "fwtw"
    experiment = next(item for item in catalog["experiments"] if item["run_id"] == "bundle-run-1")
    assert experiment["canonical_document_id"]
    assert experiment["media"][0]["relative_path"] == "images/case.jpg"
    assert any(item["relative_path"] == "report.html" for item in experiment["files"])
    assert any(item["task_id"] == "fedcba9876543210fedcba9876543210" for item in experiment["task_links"])
    assert any(item["relative_path"] == "attention_review_manifest.json" for item in experiment["files"])
    assert any(item["relative_path"] == "goal_sweep.predictions.npz" for item in experiment["files"])
    assert any(item["relative_path"] == "attention_maps/decoder_step_0001.npz" for item in experiment["files"])
    page = render_experiment_page(experiment, base_path="/research")
    assert "完整 HTML 校阅报告" in page
    assert '"/research"' in page
    assert "bundle-run-1" in page
    assert 'id="limoSidebar"' in page
    assert 'id="sectionNav"' in page
    assert 'id="mediaLightbox"' in page
    assert 'research-hub-limo-theme' in page
    assert 'id="mediaSectionFilter"' in page
    assert 'media-section--attention' in page
    assert 'media-card--attention' in page


def test_source_registry_rejects_escape_and_preserves_previous(hub_config) -> None:
    """The settings editor may not expand the Hub beyond the Code workspace."""

    before = read_source_registry(hub_config.portfolio_root)
    escaped = json.loads(json.dumps(before))
    escaped["artifact_root"] = "../../outside-review"
    escaped["scan_roots"][0]["path"] = "../../outside-review"
    with pytest.raises(ValueError, match="Code workspace"):
        write_source_registry(hub_config.portfolio_root, escaped)
    assert read_source_registry(hub_config.portfolio_root) == before


def test_catalog_groups_projects_and_allows_general_markdown(hub_config) -> None:
    """Project sources should stay grouped and expose an explicit Markdown mode."""

    canonical = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "canonical.md"
    canonical.write_text(_valid_record(), encoding="utf-8")
    general = (
        hub_config.workspace_root
        / "Urban-Nav-SR"
        / "Agent_part"
        / "RouteServer"
        / "docs"
        / "guide.md"
    )
    general.write_text("# RouteServer guide\n\nOriginal text.\n", encoding="utf-8")
    catalog = scan_and_write(hub_config)
    assert catalog["schema_version"] == "research_review_hub_catalog_v2"
    project_by_id = {item["id"]: item for item in catalog["projects"]}
    assert project_by_id["ms-swift"]["counts"]["writable_documents"] == 1
    assert project_by_id["urbannav-sr"]["counts"]["writable_documents"] == 1
    document = next(item for item in catalog["documents"] if item["path"] == str(general.resolve()))
    assert document["edit_mode"] == "markdown"
    assert document["writable"] is True
    assert document["project_id"] == "urbannav-sr"
    store = DocumentStore(hub_config, b"general-markdown-session")
    current = store.get(document["id"])
    changed = current["content"].replace("Original text.", "Reviewed text.")
    preview = store.preview(document["id"], current["sha256"], changed)
    assert preview["ok"] is True
    store.save(document["id"], current["sha256"], changed, preview["preview_token"])
    assert "Reviewed text." in general.read_text(encoding="utf-8")


def test_recoverable_archive_restore_and_guarded_delete(hub_config) -> None:
    """Active files must archive first, restore cleanly, and require exact deletion text."""

    source = hub_config.artifact_root / "obsolete.txt"
    source.write_text("recoverable evidence\n", encoding="utf-8")
    catalog = scan_and_write(hub_config)
    artifact = next(item for item in catalog["artifacts"] if item["relative_path"] == "obsolete.txt")
    store = LifecycleStore(hub_config)
    archived = store.archive("artifact", artifact["id"], catalog)
    assert archived["status"] == "archived"
    assert not source.exists()
    refreshed = scan_and_write(hub_config)
    assert refreshed["summary"]["archived_count"] == 1
    assert all(item["relative_path"] != "obsolete.txt" for item in refreshed["artifacts"])
    restored = store.restore(archived["archive_id"])
    assert restored["status"] == "restored"
    assert source.read_text(encoding="utf-8") == "recoverable evidence\n"

    catalog = scan_and_write(hub_config)
    artifact = next(item for item in catalog["artifacts"] if item["relative_path"] == "obsolete.txt")
    archived = store.archive("artifact", artifact["id"], catalog)
    with pytest.raises(LifecycleError, match="exact confirmation"):
        store.permanently_delete(archived["archive_id"], "DELETE")
    deleted = store.permanently_delete(
        archived["archive_id"],
        f"DELETE {archived['archive_id']}",
    )
    assert deleted["status"] == "deleted"
    assert not source.exists()
    assert next(
        item for item in store.records() if item["archive_id"] == archived["archive_id"]
    )["status"] == "deleted"


def test_document_preview_conflict_and_atomic_save(hub_config) -> None:
    """Document writeback must reject stale bases and preserve a Hub-owned backup."""

    path = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "test.md"
    path.write_text(_valid_record(), encoding="utf-8")
    catalog = scan_and_write(hub_config)
    document_id = next(item["id"] for item in catalog["documents"] if item["writable"])
    store = DocumentStore(hub_config, b"test-session")
    current = store.get(document_id)
    changed = current["content"].replace("验证 Hub 文档保护。", "验证 Hub 文档保护与备份。")
    preview = store.preview(document_id, current["sha256"], changed)
    assert preview["ok"] is True
    path.write_text(current["content"] + "\nexternal change\n", encoding="utf-8")
    with pytest.raises(DocumentConflictError):
        store.save(document_id, current["sha256"], changed, preview["preview_token"])
    refreshed = store.get(document_id)
    changed = refreshed["content"].replace("external change", "reviewed change")
    preview = store.preview(document_id, refreshed["sha256"], changed)
    saved = store.save(document_id, refreshed["sha256"], changed, preview["preview_token"])
    assert saved["sha256"] == hashlib.sha256(changed.encode("utf-8")).hexdigest()
    assert (hub_config.artifact_root / saved["backup_path"] / "before.md.gz").is_file()


def test_document_symlink_escape_is_rejected(hub_config, tmp_path: Path) -> None:
    """A catalog entry must not turn into a writable symlink after scanning."""

    path = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "test.md"
    path.write_text(_valid_record(), encoding="utf-8")
    catalog = scan_and_write(hub_config)
    document_id = next(item["id"] for item in catalog["documents"] if item["writable"])
    outside = tmp_path / "outside.md"
    outside.write_text(_valid_record(), encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(DocumentError, match="regular file"):
        DocumentStore(hub_config, b"test-session").get(document_id)


def test_review_events_export_without_source_mutation(hub_config) -> None:
    """Review events should fold into a derived export while source bytes stay exact."""

    source = hub_config.artifact_root / "citywalker_diagnosis.jsonl"
    source.write_text(
        json.dumps(
            {
                "schema_version": "urbannav_benchmark_slice_review_diagnosis_v1",
                "sample_id": "case-1",
                "review_status": "pending",
                "final_diagnosis": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    original = sha256_file(source)
    catalog = scan_and_write(hub_config)
    queue_id = catalog["queues"][0]["id"]
    store = ReviewStore(hub_config)
    first = store.append(queue_id, "case-1", "pass", "tester", "looks consistent", event_id="9b7c6d04-9575-489d-97ec-2cb4bb4be9ce")
    assert first["duplicate"] is False
    duplicate = store.append(queue_id, "case-1", "pass", "tester", "looks consistent", event_id="9b7c6d04-9575-489d-97ec-2cb4bb4be9ce")
    assert duplicate["duplicate"] is True
    exported = store.export(queue_id)
    assert sha256_file(source) == original
    assert exported["decision_counts"] == {"pass": 1}
    reviewed = hub_config.artifact_root / exported["reviewed_path"]
    assert json.loads(reviewed.read_text(encoding="utf-8"))["hub_review"]["decision"] == "pass"


def test_loopback_api_requires_token_and_serves_range(hub_config) -> None:
    """HTTP API must protect writes while allowing immutable artifact range reads."""

    artifact = hub_config.artifact_root / "sample.txt"
    artifact.write_text("abcdef", encoding="utf-8")
    html_artifact = hub_config.artifact_root / "report.html"
    html_artifact.write_text("<html><title>HTML report</title><body>Rendered report</body></html>", encoding="utf-8")
    document_path = hub_config.workspace_root / "ms-swift" / "docs" / "Experiments" / "test.md"
    document_path.write_text(_valid_record(), encoding="utf-8")
    catalog = scan_and_write(hub_config)
    document_id = next(item["id"] for item in catalog["documents"] if item["writable"])
    try:
        server = make_server(hub_config, "127.0.0.1", 0, token="test-token")
    except PermissionError:
        pytest.skip("sandbox does not permit loopback socket binding")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urlopen(base + "/api/health") as response:
            assert json.loads(response.read())["ok"] is True
        with urlopen(Request(base + "/", method="HEAD")) as response:
            assert response.status == 200
            assert int(response.headers["Content-Length"]) > 0
        with urlopen(base + "/api/settings") as response:
            settings = json.loads(response.read())
        assert settings["source_registry"]["artifact_root"] == "../review_outputs"
        catalog = load_catalog(hub_config)
        artifact_id = next(item["id"] for item in catalog["artifacts"] if item["relative_path"] == "sample.txt")
        request = Request(base + "/api/artifacts/" + artifact_id, headers={"Range": "bytes=1-3"})
        with urlopen(request) as response:
            assert response.status == 206
            assert response.read() == b"bcd"
        html_id = next(item["id"] for item in catalog["artifacts"] if item["relative_path"] == "report.html")
        with urlopen(base + "/api/artifacts/" + html_id) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert b"Rendered report" in response.read()
        request = Request(base + "/api/reindex", method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 403
        request.add_header("X-Research-Hub-Token", "test-token")
        with urlopen(request) as response:
            assert response.status == 200
        refreshed = load_catalog(hub_config)
        refreshed_document = next(item for item in refreshed["documents"] if item["id"] == document_id)
        assert refreshed_document["rendered_href"].startswith("_research_hub/rendered_documents/")
        assert (hub_config.artifact_root / refreshed_document["rendered_href"]).is_file()
        rendered_request = Request(
            base + "/api/hub-state/" + quote(refreshed_document["rendered_href"], safe=""),
            headers={"X-Research-Hub-Token": "test-token"},
        )
        with urlopen(rendered_request) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert b"Test experiment" in response.read()
        request = Request(
            base + "/api/settings",
            method="PUT",
            data=json.dumps({"source_registry": settings["source_registry"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Research-Hub-Token": "test-token"},
        )
        with urlopen(request) as response:
            updated_settings = json.loads(response.read())
        assert updated_settings["summary"]["writable_document_count"] == 1
        upload = Request(
            base + "/api/attachments?document_id=" + document_id,
            method="POST",
            data=b"tiny image payload",
            headers={
                "Content-Type": "image/png",
                "X-Filename": "figure.png",
                "X-Research-Hub-Token": "test-token",
            },
        )
        with urlopen(upload) as response:
            attachment = json.loads(response.read())
        assert attachment["markdown_link"].startswith("![figure.png]")
        assert (hub_config.artifact_root / attachment["path"]).is_file()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
