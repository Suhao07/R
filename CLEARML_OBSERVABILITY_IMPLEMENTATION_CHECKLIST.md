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

## P4：训练期诊断与后续独立阶段

### 2026-08-26 当前主线：UrbanNav 原始 Stage-II CFM（不含 DF-OPD）

本阶段先收敛到现有 `run_stage_ii_cfm_v2_4b.sh` →
`swift.sidewalk_nav.cli.train` 训练入口，不调用 `train_df_opd.py`，不加载 Teacher，
不使用 `df_opd_diagnostics_only`。目标是把训练中间信号接入现有 pipeline，并在 ClearML
和 Research Hub 中完成最小可验收展示。

- [ ] 用不带 DF-OPD 的 Stage-II CFM 小样本运行验证 `traj_collapse`、`flow_time` 和
  选定层 `traj_layer_activation`；当前已验证的 r12/r13/r31 不能替代这条范围明确的基线记录
- [ ] 在同一数据、seed、checkpoint 和 step 数下完成 diagnostics-off/on 对照，记录 step time、
  GPU memory、吞吐和 loss；1-step smoke 不足以判断训练影响
- [ ] 在上述非 OPD Task 中核验 ClearML Scalars、lifecycle manifest/index/linkage、checkpoint
  layout/input snapshot 和 Research Hub 入口
- [ ] 完成用户对 ClearML 与 Research Hub 的人工校阅，确认图表、artifact、Markdown/HTML 和媒体
  入口可用
- [ ] 如果“原始训练”指 Stage-I `run_stage_i_joint_4b_full.sh` 的 LM-only 路径，单独增加
  LM-only 训练信号适配；当前 `SidewalkSftArguments` 会要求 action head 和正 action loss，不能
  直接把现有 action diagnostics 插进去
- [ ] 用完整或固定代表性数据集跑一次非 OPD baseline，并绑定评测 JSON、scorecard 和实验报告

以下 DF-OPD 条目保留为后续专项，不作为当前非 OPD 可视化验收的依赖：

- [x] UrbanNav `cached_traj_query_v2` 两行、1-step 真实训练 smoke：TensorBoard、JSONL、checkpoint 和
  `traj_collapse`/CFM flow-time/选定层 TRAJ 激活已写出；详见
  `ms-swift/docs/Experiments/urbannav_diagnostics_mini_smoke_20260825.md`
- [x] 受信 tunnel 下手动 train 的 ClearML callback smoke：Task
  `a1b2e160171d44368393db9c30fea115` 已完成，Scalars 和两个诊断 artifact 已由 API 核验
- [x] 真实 Stage-II checkpoint attention replay：Task
  `a9c20770a367482687ba35039bcf43c6` 已完成；dense layer `23` 的 HTML Debug Sample、JSON
  receipt 和 linkage 已由 API 核验；Qwen3.5 linear-attention layers `0/12` 的明确不支持错误
  已保留
- [x] DF-OPD 8 行/1-step diagnostics-only smoke：在已核验 UrbanNav Python 3.10/CUDA 环境完成
  replay 首步，Task `7ddd5d881a994ab498361944d7ff4a85` 已产生实时 Scalars、receipt 和层/TRAJ/CFM
  诊断指标；Teacher certification 仍为 `insufficient_evidence`、`student_opd_eligible=false`，不构成
  正式 Student 晋级。Task 已通过远端 SDK 标记 `completed`，但 checkpoint 远端上传/恢复 parity
  尚未完成
- [x] `sidewalk_clearml` 生命周期自动写出 planned `visualization_manifest.json`、finished
  `visualization_index.json` 和 `clearml_task_linkage.json`；正确远程 Torch 环境的 callback
  lifecycle smoke 已实际生成三者并通过上传调用合同；真实无 GPU Task
  `40dad12ff8f44b75aded490e64f594a9` 已由服务器 API 核验为 `completed`，并包含三个生命周期 Artifact
- [x] post-encode 输入快照从展开后的 model-input mapping 生成；远程集成 smoke 已确认序列轴
  与 expanded `input_ids`/`attention_mask` 对齐，并保留视觉输入
- [x] 真实 UrbanNav Stage-II 2 行/1-step Task lifecycle smoke：Task
  `a777a230ff66430eaf13ac82c0cfdfc9` 在服务器端为 `completed`、iteration `1`，产生 `144` 个
  Scalars（含层/TRAJ/CFM/collapse/token norm）以及三个 lifecycle Artifact；本次显式不保存
  checkpoint，避免把实时诊断证据与 checkpoint URI 证据混为一谈
- [ ] 解决远程 `/mnt/volumes` 输出盘 100% quota 后，再执行带 checkpoint/layout/input snapshot
  的真实训练 Task；r11 的失败原因为 `Disk quota exceeded`，不构成代码失败
- [x] 在远端 `/tmp` 绕开持久盘 quota 执行带 checkpoint/layout/input snapshot 的真实 Task：Task
  `2a4c4954a4024c3687cf0bdd97373dbe` 已完成，并在同一任务中上传两个诊断 Artifact 和三个生命周期 Artifact；远端 `/mnt/volumes` quota 仍待清理
- [x] 使用 r13 的 checkpoint、layout 和 input snapshot 重新执行 attention CLI：CUDA/bfloat16 dense layer `23` 返回成功，生成 HTML/JSON/receipt
- [x] DF-OPD 精确 `_df_opd_decision_value_token_mask` 已绑定到 `TokenLayout.key_groups["decision_value"]`；远端正确 Torch 环境 focused smoke 输出 `REMOTE_DECISION_LAYOUT_OK`，未从序列位置推断语义
- [x] 修复单查询 `[B]` 与 TokenLayout `[B,Q]` 的轴契约；远端 post-encode smoke 输出 `REMOTE_POST_ENCODE_DECISION_LAYOUT_OK`，16-query 路径保持 `[B,16]`
- [x] 修复 Qwen BPE 标点/value 边界 token 的过度拒绝；真实 `checkpoint-6079` tokenizer 输出 `REMOTE_REAL_TOKENIZER_DECISION_OK`，每个 canonical value 保留完整 token 覆盖
- [x] 定位 DF-OPD 远端通用 `GKDTrainer` 误分派根因：远端 `swift/pipelines/train/sft.py` 未同步当前 `self._get_trainer_cls()` 入口；r20 已确认 `SidewalkDFOPDTrainer` 实例化，r31 已在正确远端环境完成真实 optimizer step 并产出 DF-OPD/层/TRAJ/CFM 诊断指标
- [x] 修复 DF-OPD replay 的 Qwen 模板对齐：FullCoT 使用既有 Stage-I `\\n\\n` payload suffix，Decision value mask 使用当前 template 的真实 `<|im_end|>\\n` suffix；r31 8 行/1-step 运行通过
- [ ] 通过晋级门禁的 Teacher 后重新执行 DF-OPD diagnostics Task
- [ ] 完整 checkpoint 的 ClearML URI、下载/恢复 parity 和长运行实时吞吐证据
- [x] 提供 `ms-swift/scripts/sidewalk_nav/clearml_report_train.py` 的手动训练收尾入口；checkpoint 默认 link-only
- [x] 历史 review_outputs 选择性本地导入清单，标记 `historical_import`
- [ ] 将历史清单中的选定目录创建为真实 ClearML `historical_import` Task
- [ ] Pipeline 设计与 train → eval → report contract（本轮不做）
- [ ] GPU Agent/Queue 评估；不作为第一阶段前置条件
