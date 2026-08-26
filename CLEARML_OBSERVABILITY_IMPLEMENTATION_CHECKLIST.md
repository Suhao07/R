# ClearML 无 Agent 观测模板实现清单

本清单对应 `workstreams/clearml-observability-template/`。第一阶段保持原有
SSH/tmux 训练和评测命令，不安装 GPU Agent，不自动上传原始数据。

## 2026-08-26 清单核对结论

当前非 DF-OPD UrbanNav Stage-II CFM 的可视化闭环已经完成：训练期诊断、ClearML
生命周期、实验报告与章节媒体、持久 checkpoint URI/恢复 parity、共享 artifact URI、
本地 `train → eval → report` 和历史 `review_outputs` 导入均有代码与证据。旧清单中列为
“仍未完成”的这些条目已由本轮实现覆盖；尚未执行的是 ClearML-native Pipeline、GPU
Agent/Queue 和完整 test view，它们属于调度或规模扩展，不是可视化插件的运行依赖。

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
- [x] `train_hook.py.template` 提供 step 与 checkpoint 两个生命周期入口，checkpoint 遵循 profile 上传策略
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
- [x] 通用 `report_payload.py.template --experiment-root` 自动发现一实验目录中的 Markdown、HTML、scorecard、receipt、manifest 和章节媒体；不扫描 raw/predictions/checkpoint；dry-run 生成临时 HTML，不覆盖已有报告

## P2：责任仓接入

- [x] `ms-swift/swift/sidewalk_nav/observability/clearml.py`
- [x] rank-zero Task 创建和写入守卫
- [x] 配置、scalar、artifact、media 和 linkage API
- [x] `ms-swift/scripts/sidewalk_nav/clearml_report_eval.py`
- [x] 不改 evaluator 的 post-run scorecard 上报路径
- [x] 评测上报器绑定 receipt/manifest、provenance 和有限媒体选择
- [x] `--dry-run` 在缺少 ClearML/transformers 时仍可运行

## P3：真实本地 Server smoke 与证据归档

> 验证策略：本节已有的 connectivity/lifecycle Task 只作为一次性环境与上传合同证据，
> 不作为每个项目反复创建 Task 的前置步骤。后续责任仓接入只需要一次插件导入/配置检查，
> 再加一次短步数真实训练集成验证；正式训练直接复用同一个 ClearML profile 和训练入口。
> 远端归属：UrbanNav 的训练可视化验证固定在 lixiang 路由和已核验的 UrbanNav Python/CUDA
> 环境；`lyg0316` 仅用于 FWTW 的 ClearML 配置，不计入 UrbanNav 证据。

- [x] 配置本地 loopback ClearML Server：Web 8080、API 8008、Fileserver 8081
- [x] 提供 SSH tunnel 模板；保持 Server 不公开监听
- [x] 配置本地 Fileserver artifact URI 和被忽略的本地凭据
- [x] 无 GPU 创建 testing/evaluation Task：`d205590a475b483ebd8b256980e8aa71`
- [x] 上传 scorecard、实验记录、receipt、visualization index 和选择性 review HTML
- [x] 生成 ClearML Task ID ↔ finished receipt ↔ experiment document binding sidecar
- [x] 核验真实 ClearML Task、artifact 和终态
- [x] 创建独立 evidence archive Task：`91a4d6e502d446ecb18be516a83055b7`
- [x] 用户人工验收 Web UI 中的指标、artifact、文档和 Debug Sample（2026-08-26，用户确认通过）

## P4：训练期诊断与后续独立阶段

### 2026-08-26 当前主线：UrbanNav 原始 Stage-II CFM（不含 DF-OPD）

本阶段先收敛到现有 `run_stage_ii_cfm_v2_4b.sh` →
`swift.sidewalk_nav.cli.train` 训练入口，不调用 `train_df_opd.py`，不加载 Teacher，
不使用 `df_opd_diagnostics_only`。目标是把训练中间信号接入现有 pipeline，并在 ClearML
和 Research Hub 中完成最小可验收展示。

- [x] 用不带 DF-OPD 的 Stage-II CFM 小样本运行验证 `traj_collapse`、`flow_time` 和
  选定层 `traj_layer_activation`；远端真实运行根目录为
  `/mnt/volumes/mind-eb-bd-ga/suh/UrbanNavigation/runs/urbannav_viz_training_smoke_20260826_viz`，
  1 step 已完成并写出三类诊断、16 个 TRAJ token norm、JSONL 与 checkpoint-1。
- [x] 已有一次 100-step diagnostics-off/on 对照，记录 overall runtime、GPU memory、吞吐和 loss；
  历史结果为 off=`354.8700 s / 0.282 steps/s / 15.17 GiB`、on=`383.0495 s / 0.261 steps/s /
  15.17 GiB`，整体 runtime 增加 `7.94%`。当前 JSONL 没有独立的逐 step wall-clock 字段，因此只报告
  整体 runtime/吞吐。
- [x] 在 lixiang 正确当前源码 overlay 上重新完成非 OPD 100-step diagnostics-on：off=
  `428.6986 s / 0.233 steps/s / 15.17 GiB`、on=`456.9306 s / 0.219 steps/s / 15.17 GiB`，
  方向性 runtime 增加 `6.5852%`、吞吐变化 `-6.0086%`、峰值显存变化 `0 GiB`。on 运行的 102 条
  JSONL 含 `cfm_flow`、`layer_0023`、`traj_collapse`、`traj_query_source`、`traj_tokens` 五类键，
  并保存 `checkpoint-100`。off 使用 production checkout launcher，on 使用当前 overlay launcher
  以传递插件参数，因此该比较不是完全相同 shell 命令，不能做严格逐项因果归因；完整证据为
  `runs/urbannav_viz_perf_current_20260826.json`。
- [x] 补跑同一当前源码 overlay launcher 的 diagnostics-off 100-step 臂，完成严格 launcher 对照：
  off=`420.9 s / 0.238 steps/s / 15.17 GiB / loss 0.3675`，on=`456.9306 s / 0.219 steps/s /
  15.17 GiB / loss 0.3783374`；整体 runtime 增加 `8.5604%`、吞吐变化 `-7.8854%`、峰值显存变化
  `0 GiB`。两臂均完成 `checkpoint-100`，不创建新的 ClearML Task；receipt 为
  `runs/urbannav_viz_perf_strict_ab_20260826.json`。该结果仍只覆盖 2 rows/100 steps 的工程开销。
- [x] 在上述非 OPD Task 中核验 ClearML Scalars、lifecycle manifest/index/linkage、checkpoint
  layout/input snapshot 和 Research Hub 入口；Task
  `960eaa714ca44912aefa97b336a5b240` 已由本地 API 核验为 `completed`，并含诊断 Scalars、生命周期
  Artifact、checkpoint layout、input snapshot 和 unified UI 页面入口
- [x] 完成用户对 ClearML 与 Research Hub 的人工校阅，确认图表、artifact、Markdown/HTML 和媒体
  入口可用
- [x] 在 lixiang `31041` 路由的 UrbanNav production checkout
  `/mnt/volumes/mind-eb-bd-ga/suh/UrbanNavigation/runs/cosmos3_production_checkout_20260826/ms-swift`
  使用 `urbannav_ms_swift_v31`（Python 3.10.18、Torch `2.8.0+cu128`、CUDA 可用）完成一次插件导入与
  最小信号计算 smoke；未创建新的 ClearML Task。lixiang 顶层旧 checkout 缺少 `diagnostics.py`，不计入
  当前插件证据。
- [x] checkpoint 上传策略已在 UrbanNav adapter 和可复用 ClearML template 对齐：`link_only` 只记录
  路径，`upload_selected/upload_all` 上传显式选择的 checkpoint 目录；未解析
  `artifacts.output_uri` 时在创建 Task 前直接失败。
- [x] 可复用 adapter 提供 checkpoint 目录 manifest 与 ClearML artifact 下载接口；恢复目录可按
  相对路径、字节数和 SHA-256 做 parity 比对；本机小型 artifact smoke 与 lixiang 真实 UrbanNav
  checkpoint parity 均已通过。真实 Task 为 `da607102e5434cee926e86a2bb232685`，19 个文件、
  `11027294887` bytes，SHA-256 为 `a23509340cb5957d17291f1fecfa1b2236f1abab6011639d443f022ccc1040f9`。
- [x] 在 lixiang 既有非 OPD Task `960eaa714ca44912aefa97b336a5b240` 上核验真实 ClearML
  artifact URI：API 位于 `http://127.0.0.1:18180`，Fileserver/output URI 为
  `http://127.0.0.1:18181`；下载 `diagnostic_token_layout_step_0` 共 `176318` bytes，下载
  SHA-256 与服务器记录均为
  `f7d2e4fe274159533fdda9162a56ea6a531ee547062451e4acd45da46de688f4`。这证明单主机
  artifact 上传/下载通道可用，不等同于 checkpoint 上传或恢复 parity。
- [x] 在同一 lixiang 环境使用源 checkpoint 与 ClearML 恢复 checkpoint 跑固定单条非 OPD
  `control.jsonl` 推理；两者的 checkpoint CLI digest 均为
  `12c889dcb9bacf280392a9de6b6c7aa2049b254966e80655f5d950a610ca1d72`，trajectory 输出摘要一致，
  `condition_digest` 一致。证据为
  `runs/urbannav_checkpoint_restore_inference_parity_lixiang_20260826.json`；运行时延字段不参与
  parity，因为它由每次进程测量产生。
- [x] 在 lixiang 两个独立 GPU 主机（路由 `31041` 与 `32011`）确认同一 GPFS 挂载和同一
  `file:///mnt/volumes/ad-rl-trans-bd-ga/suh/clearml-artifacts` artifact 可见，checkpoint ZIP
  两端大小均为 `8716311498` bytes；证据为
  `runs/urbannav_shared_artifact_uri_lixiang_20260826.json`。该项证明共享文件系统可见性，
  不扩展为公网对象存储或 ClearML 服务公网可达性。
- [x] 使用训练 callback 生成的真实 `diagnostic_inputs.pt` 与
  `diagnostic_token_layout.json`，在 lixiang `32011` 对 canonical `traj_00..traj_15`
  运行 dense layer `23` attention replay；生成 121 个有限标量、HTML、JSON 和 receipt，
  产物保存在共享 evidence URI，详见
  `runs/urbannav_canonical_attention_lixiang_20260826.json`。该项只覆盖单样本/单 dense 层，
  不把 Qwen3.5 linear-attention 层假设为同类 attention map。
- [x] 提供 `scripts/run_clearml_pipeline.py`，按 `train command → train reporter → eval command →
  evaluation reporter` 顺序执行；评测 reporter 在取得 eval Task ID 后写入最终 `eval_report`，
  再将最终 `pipeline_receipt.json` 上传并绑定到同一评测 Task。训练或评测失败时写出带
  `failed_stage` 的失败 receipt。已有训练 callback 时可用
  `--skip-train-report` 避免重复创建训练 Task。该入口是无 Agent 的本地编排，不声称 ClearML-native
  Pipeline 或远程队列已完成。
- [x] 提供 `scripts/publish_clearml_history_import.py` 的计划/显式发布入口；默认只生成受限
  manifest，`--publish` 才会为选定 review root 创建 `historical_import` 标签的 review Task，
  且只上传 manifest 选出的 evidence 和媒体。
- [ ] 如果“原始训练”指 Stage-I `run_stage_i_joint_4b_full.sh` 的 LM-only 路径，单独增加
  LM-only 训练信号适配；当前 `SidewalkSftArguments` 会要求 action head 和正 action loss，不能
  直接把现有 action diagnostics 插进去
- [x] 用固定代表性数据集跑一次非 OPD baseline，并绑定评测 JSON、scorecard 和实验报告；冻结
  `test_eval_v2` control view 前 2 行已完成 inference/evaluator，输出根目录为
  `/mnt/volumes/mind-eb-bd-ga/suh/UrbanNavigation/runs/urbannav_viz_baseline_eval_20260826`，
  ClearML Task `19be4c14be584f03a55bf410b66e8250` 状态为 `completed`，含 JSON/CSV scorecard、
  receipt、Markdown、MathJax HTML、manifest/index 和 task linkage。该结果是 pipeline smoke，不是全量 benchmark。
- [x] 在 lixiang 同一非 OPD checkpoint 上扩大到冻结 `test_eval_v2` control view 的 8 行切片；
  prediction/reference 均为 8 行且按 `sample_id` 对齐，parse/strict success=1、NaN/Inf=0，
  evaluator summary 与三个输出哈希见 `runs/urbannav_non_opd_baseline8_lixiang_20260826.json`。
- [x] 继续扩大到冻结 `test_eval_v2` control view 的 32 行代表性切片；prediction/reference 均为
  32 行且按 `sample_id` 对齐，parse/strict success=1、NaN/Inf=0，ADE/FDE=`1.4330284/0.9765120`，
  结果和 hash 见 `runs/urbannav_non_opd_baseline32_lixiang_20260826.json`。该结果仍不替代完整
  test view benchmark。
- [x] UrbanNav Stage-I LM-only launcher 复用 `sidewalk_clearml` 生命周期 callback；该路径只记录通用
  训练 Scalars、生命周期 artifact 和 checkpoint，不伪造 CFM/TRAJ 诊断信号。Stage-I 专属的 hidden-state
  插件适配仍保持延期，直到定义对应的语言 loss 信号合同。

### 校阅通过后的当前待做顺序

组合层校验更新（2026-08-26）：`portfolio_doctor.py` 当前 `validation_errors=0`；剩余
`snapshot_drift` 只反映本轮两个责任仓和组合层仍有未提交改动，以及快照尚未重新生成，
不表示本轮 run receipt 结构错误。

1. 将 32 行切片扩展为预注册的完整 test view；当前 32 行只验证代表性绑定和数值门禁，不支持全量 benchmark 结论。
2. 将 FWTW/其他责任仓的 ClearML profile、训练 Task、评测 Task 和报告 bundle 统一接入同一 Research Hub 索引约定。
3. 当前本地 `train → eval → report` 编排已经可用；证据齐全后再决定是否接入 ClearML-native
  Pipeline、GPU Agent 和 Queue。

以下能力继续延期，不属于当前非 OPD 原始训练可视化验收：GPU Agent/Queue、ClearML-native Pipeline、Teacher certification、正式 DF-OPD Student 训练，以及 Decision/Flow OPD 专项层分析。

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
- [x] 使用 lixiang `/mnt/volumes/ad-rl-trans-bd-ga/suh/UrbanNavigation` 的非 OPD checkpoint，
  通过 `/mnt/volumes/ad-rl-trans-bd-ga/suh/clearml-artifacts` 完成真实 artifact 上传、下载和文件级
  parity；Task `da607102e5434cee926e86a2bb232685`，receipt 见
  `runs/urbannav_checkpoint_parity_lixiang_20260826.json`
- [x] 使用 `validate_stage_ii_checkpoint` 对源目录和恢复目录执行 sidecar 运行时合同校验；两者
  完全一致，合同为 `stage_ii_cfm_v2`、16 queries、`flow_action`。
- [x] 在远端 `/tmp` 绕开持久盘 quota 执行带 checkpoint/layout/input snapshot 的真实 Task：Task
  `2a4c4954a4024c3687cf0bdd97373dbe` 已完成，并在同一任务中上传两个诊断 Artifact 和三个生命周期 Artifact；本轮真实 checkpoint 使用独立的 GPFS-backed `ad-rl-trans-bd-ga` 共享空间
- [x] 使用 r13 的 checkpoint、layout 和 input snapshot 重新执行 attention CLI：CUDA/bfloat16 dense layer `23` 返回成功，生成 HTML/JSON/receipt
- [x] DF-OPD 精确 `_df_opd_decision_value_token_mask` 已绑定到 `TokenLayout.key_groups["decision_value"]`；远端正确 Torch 环境 focused smoke 输出 `REMOTE_DECISION_LAYOUT_OK`，未从序列位置推断语义
- [x] 修复单查询 `[B]` 与 TokenLayout `[B,Q]` 的轴契约；远端 post-encode smoke 输出 `REMOTE_POST_ENCODE_DECISION_LAYOUT_OK`，16-query 路径保持 `[B,16]`
- [x] 修复 Qwen BPE 标点/value 边界 token 的过度拒绝；真实 `checkpoint-6079` tokenizer 输出 `REMOTE_REAL_TOKENIZER_DECISION_OK`，每个 canonical value 保留完整 token 覆盖
- [x] 定位 DF-OPD 远端通用 `GKDTrainer` 误分派根因：远端 `swift/pipelines/train/sft.py` 未同步当前 `self._get_trainer_cls()` 入口；r20 已确认 `SidewalkDFOPDTrainer` 实例化，r31 已在正确远端环境完成真实 optimizer step 并产出 DF-OPD/层/TRAJ/CFM 诊断指标
- [x] 修复 DF-OPD replay 的 Qwen 模板对齐：FullCoT 使用既有 Stage-I `\\n\\n` payload suffix，Decision value mask 使用当前 template 的真实 `<|im_end|>\\n` suffix；r31 8 行/1-step 运行通过
- [ ] 通过晋级门禁的 Teacher 后重新执行 DF-OPD diagnostics Task
- [x] 完整 checkpoint 的模型加载/推理恢复 parity（固定单条非 OPD 输入）；长运行实时吞吐证据仍待补充
- [x] 提供 `ms-swift/scripts/sidewalk_nav/clearml_report_train.py` 的手动训练收尾入口；checkpoint 默认 link-only
- [x] 历史 review_outputs 选择性本地导入清单，标记 `historical_import`
- [x] 执行一次历史清单中的选定目录，创建真实 ClearML `historical_import` Task：Task
  `6b59d9cc78f94f6aaa18c38d45f4df20`，只上传 `scorecard.html` 和 `scorecard.json`
- [x] 在本机 ClearML Server 以 `upload_selected` 完成两个小型 checkpoint 文件的上传、下载和
  manifest parity；Task `01ea6565e9b54097902194512ead8fab`，receipt 见
  `runs/clearml_checkpoint_parity_smoke_20260826.json`
- [x] 本地 train → eval → report contract 与编排入口
- [x] 提供 `scripts/register_clearml_pipeline.py` 原生 Pipeline 注册入口：显式 train/eval/report
  基础 Task、Queue、父子 DAG 和参数覆盖；默认只生成计划，不创建 Task。
- [ ] ClearML-native Pipeline 设计、GPU Agent/Queue 调度与远程执行
- [ ] GPU Agent/Queue 评估；不作为第一阶段前置条件
