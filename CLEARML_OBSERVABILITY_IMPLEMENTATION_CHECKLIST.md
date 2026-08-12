# ClearML 无 Agent 观测模板实现清单

本清单对应 `workstreams/clearml-observability-template/`。第一阶段保持原有
SSH/tmux 训练和评测命令，不安装 GPU Agent，不自动上传原始数据。

## P0：责任边界

- [x] 旧 `research-review-hub` 标记为历史静态兼容层。
- [x] 新建 `clearml-observability-template` workstream。
- [x] 明确责任仓拥有 trainer、evaluator、实验 Markdown、receipt 和 benchmark contract。
- [x] 明确 ClearML 只作为 Task、指标、日志、媒体和 artifact 的运行索引。

## P1：可复用模板

- [x] `schemas/clearml-project-profile.schema.json`
- [x] `schemas/clearml-artifact-manifest.schema.json`
- [x] `templates/clearml/project-profile.example.yaml`
- [x] `templates/clearml/clearml.conf.example`
- [x] `templates/clearml/clearml_adapter.py.template`
- [x] `templates/clearml/train_hook.py.template`（live train 的 rank-zero hook）
- [x] `templates/clearml/report_payload.py.template`
- [x] `policies/clearml-observability.md`
- [x] `scripts/validate_clearml_project_profile.py`
- [x] `scripts/render_clearml_payload_manifest.py`
- [x] `scripts/clearml_server_preflight.py`（只读，不拉镜像、不启动服务、不读密钥）
- [x] `scripts/render_clearml_evidence_binding.py`（Task linkage ↔ canonical evidence sidecar）
- [x] `scripts/render_clearml_history_import.py`（显式目录、historical_index_only 标记、不上传）
- [x] profile 路径边界、敏感字段、artifact 策略和指标映射校验
- [x] bounded hash、媒体候选上限和本地-only dry-run
- [x] 显式收集 experiment record、finished receipt、scorecard、visualization manifest/index
- [x] 选择性媒体的 review-root 边界和每 series 限额
- [x] provenance-only Task configuration（Git commit/dirty-state、脱敏命令、fingerprint、证据 hash）
- [x] 可选 `metric_sources` JSON 路径映射，支持项目只改 profile

## P2：责任仓接入

- [x] `ms-swift/swift/sidewalk_nav/observability/clearml.py`
- [x] rank-zero Task 创建和写入守卫
- [x] 配置、scalar、artifact、media 和 linkage API
- [x] `ms-swift/scripts/sidewalk_nav/clearml_report_eval.py`
- [x] 不改 evaluator 的 post-run scorecard 上报路径
- [x] 评测上报器绑定 receipt/manifest、provenance 和有限媒体选择
- [x] `--dry-run` 在缺少 ClearML/transformers 时仍可运行

## P3：真实本地 Server smoke 与证据归档

- [x] 配置本地 loopback ClearML Server：Web 8080、API 8008、Fileserver 8081
- [x] 提供 SSH tunnel 模板；保持 Server 不公开监听
- [x] 配置本地 Fileserver artifact URI 和被忽略的本地凭据
- [x] 无 GPU 创建 testing/evaluation Task：`d205590a475b483ebd8b256980e8aa71`
- [x] 上传 scorecard、实验记录、receipt、visualization index 和选择性 review HTML
- [x] 生成 ClearML Task ID ↔ finished receipt ↔ experiment document binding sidecar
- [x] 核验真实 ClearML Task、artifact 和终态
- [x] 创建独立 evidence archive Task：`91a4d6e502d446ecb18be516a83055b7`
- [ ] 用户人工验收 Web UI 中的指标、artifact、文档和 Debug Sample

## P4：后续独立阶段（本轮明确延期）

- [ ] 手动 train 接入 TensorBoard、checkpoint URI 和恢复证据（本轮不做）
- [x] 提供 `ms-swift/scripts/sidewalk_nav/clearml_report_train.py` 的手动训练收尾入口；checkpoint 默认 link-only
- [x] 历史 review_outputs 选择性本地导入清单，标记 `historical_import`
- [ ] 将历史清单中的选定目录创建为真实 ClearML `historical_import` Task
- [ ] Pipeline 设计与 train → eval → report contract（本轮不做）
- [ ] GPU Agent/Queue 评估；不作为第一阶段前置条件
