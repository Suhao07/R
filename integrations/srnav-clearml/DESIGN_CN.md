# SR-Nav ClearML 设计文档

## 1. 设计目标

本系统不是重新实现训练框架，也不是替换实验 Markdown 或本地人工校阅页。
它把已有的实验结果、文档、指标和媒体映射到 ClearML 的可视化对象，同时保留
责任仓中的 canonical evidence。

核心原则：

```text
实验/评测代码与文档          责任仓 canonical
        │
        ├── scorecard / receipt / visualization index
        ├── Markdown experiment record
        └── review_outputs/index.html 与选定媒体
                         │
                 ClearML post-run adapter
                         │
       Task / Scalars / Debug Samples / Artifacts / Reports
```

ClearML Task 是运行索引和可视化层，不是实验结论的唯一证据。实验结论必须仍能
通过 Markdown、receipt、scorecard、visualization index 和人工校阅材料追溯。

## 2. 内容到 ClearML 对象的映射

| 研究内容 | ClearML 对象 | 设计理由 |
| --- | --- | --- |
| 中文实验方案、setting、原因分析、下一实验 | Reports + responsibility-repo Markdown | Report 便于在线编辑和嵌入；Markdown 保留 Git 历史 |
| loss、学习率、评测指标、覆盖率 | Scalars | 支持按 iteration 绘制曲线和跨 Task 比较 |
| HTML 校阅页、图片、FPV/BEV 视频 | Debug Samples | 适合交互查看、按 series/iteration 浏览 |
| scorecard、CSV、JSON、receipt、manifest | Artifacts | 可下载、可追踪、可供后续 Task 使用 |
| 全量本地校阅目录 | `review_outputs/index.html` | 保留现有批量人工校阅和相对路径上下文 |
| Task 与 canonical evidence 的对应关系 | evidence binding sidecar | 记录 ID、路径、大小和 hash，不复制正文 |

ClearML 官方将日志、标量、plots 和 debug samples 作为 Task 结果类型，并将
artifact 作为独立的结果资产；Reports 支持 Markdown 和嵌入 Task 可视化。

## 3. 仓库责任边界

```text
ResearchWorkflow/
├── schemas/                         profile 与 artifact contract
├── policies/                        上传、隐私、证据策略
├── templates/clearml/               可复用模板和示例
├── integrations/srnav-clearml/     SR-Nav profile、Server、操作文档
├── scripts/                         validator、manifest、preflight、binding
└── workstreams/clearml-*/           状态、设计和决策记录

ms-swift/
├── docs/Experiments/                实验 Markdown canonical
├── swift/sidewalk_nav/observability/clearml.py
└── scripts/sidewalk_nav/clearml_report_eval.py

review_outputs/
├── index.html                       本地中文校阅总览
└── <run-root>/                      scorecard、receipt、HTML、媒体
```

`Urban-Nav-SR` 继续拥有 RouteServer、数据 contract 和 benchmark/evaluation 语义；
`ms-swift` 拥有训练、推理和评测入口；`ResearchWorkflow` 只保存组合层模板、策略
和小型证据索引。

## 4. 运行数据流

### 4.1 评测结果

```text
原有 evaluator
    ↓
scorecard.json + receipt + visualization_index + review.html/media
    ↓
clearml_report_eval.py
    ├── 读取 profile.metric_sources
    ├── 提取有限 numeric metrics
    ├── 创建一个 evaluation Task
    ├── report_mapped_values → SCALARS
    ├── upload_artifact → ARTIFACTS
    ├── report_media → DEBUG SAMPLES
    └── 写出 clearml_task_linkage.json
    ↓
render_clearml_evidence_binding.py
    ↓
clearml_evidence_binding.json + archive Task
```

### 4.2 文档和 Report

实验 Markdown 不由 ClearML 自动改写。操作者在 Reports 页面创建中文 Report，
从 Task 的 Scalars、Plots、Debug Samples 生成嵌入内容；Report 作为浏览和汇报
版本，原 Markdown 继续作为 Git 中的长期记录。

### 4.3 本地校阅

`review_outputs/index.html` 不迁移到 ClearML，也不因上传而改变。它继续提供本地
批量筛选、相对路径媒体和人工标注上下文。ClearML 只接收 operator 明确选择的
代表性 HTML、图片和视频。

## 5. 配置和安全边界

当前本地通道：

```text
Web UI       http://127.0.0.1:8080
API          http://127.0.0.1:8008
Fileserver   http://127.0.0.1:8081
artifact URI http://127.0.0.1:8081
```

`docker-compose.yml` 只启动核心 Server、Fileserver、MongoDB、Redis 和
Elasticsearch，不启动 Agent 服务。`local.env`、固定用户配置和 `state/` 均不
进入 Git。

上传策略由 `project-profile.yaml` 固定：

- `raw_data_policy: never_upload`
- `checkpoint_policy: link_only`
- `review_bundle_policy: upload_selected`
- review media 必须位于 `documents.review_root`
- 每个 media series 有数量上限
- Task configuration 只保存 provenance、fingerprint 和 bounded evidence hash

## 6. 已实现部分

### 模板和治理

- `clearml-project-profile.schema.json`
- `clearml-artifact-manifest.schema.json`
- 可复用 `clearml_adapter.py.template`
- 可复用 `report_payload.py.template`
- rank-zero `train_hook.py.template`
- ClearML observability policy

### SR-Nav 接入

- `project-profile.yaml` 路径、任务、指标和媒体策略
- `ClearMLRun`：Task、配置、scalar、artifact、media、linkage、terminal state
- `clearml_report_eval.py`：不改 evaluator 的 post-run 评测上报
- `clearml_report_train.py`：手动训练收尾入口，checkpoint 默认 link-only

### 证据和验证

- profile validator
- payload manifest dry-run
- server preflight
- evidence binding sidecar
- historical review import manifest
- 本地 loopback ClearML Server compose
- 无 GPU evaluation Task smoke
- evidence archive Task
- ResearchWorkflow 和 ms-swift focused tests

### 当前真实验证对象

- evaluation Task：`d205590a475b483ebd8b256980e8aa71`
- evidence archive Task：`91a4d6e502d446ecb18be516a83055b7`
- 归档记录：`review_outputs/citywalker_zeroshot_stage_ii_cfm_validation_20260808_01/clearml_archive_record.json`

该验证证明的是本地 ClearML 结果可视化和证据归档链路，不代表 GPU 训练收敛、
benchmark validation 或论文结论。

## 7. 尚未实现部分

### 明确延期

- 真实训练循环内的 step/loss/lr 实时埋点
- TensorBoard/DeepSpeed 日志自动接入
- GPU Agent、Queue、暂停/重跑和优先级调度
- train → eval → report Pipeline/DAG

### 仍需产品化

- 多机器共享 artifact URI（NAS/MinIO/S3）
- 远程主机的真实 SSH tunnel 配置和验收
- 更严格的 Web 登录、用户管理和外部访问安全配置
- ClearML Reports 的自动生成 API/脚本
- 从 `review_outputs` 选择媒体的图形化上传界面
- ClearML Web UI 菜单中文化；当前只保证中文实验内容和 Report

### 当前行为限制

- Task 进入 `completed` 后不能追加 artifact；补充归档必须创建 archive Task。
- HTML 若引用本地相对路径，单独上传后不保证媒体可见；应将媒体单独作为
  Debug Sample，或生成 self-contained HTML。
- 本地 Fileserver URI 只适合当前主机；远程机器不能直接使用另一台主机的
  `127.0.0.1`。
- ClearML Report 是可读呈现层，不替代 canonical Markdown、receipt 或
  benchmark contract。

## 8. 阶段计划

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| P0 | 已完成 | 责任边界、旧静态 Hub 降级、ClearML workstream |
| P1 | 已完成 | schema、profile、manifest、上传策略 |
| P2 | 已完成 | adapter、评测 reporter、证据 binding |
| P3 | 已完成 | 本地 Server、no-GPU Task、artifact/media、归档 |
| P3验收 | 当前 | 用户验收 Web UI 的 Scalars、Debug Samples、Artifacts、Reports |
| P4 | 未开始 | 实时训练、共享存储、Pipeline、Agent/Queue |

## 9. 参考文档

- [ClearML Server](https://clear.ml/docs/latest/docs/deploying_clearml/clearml_server/)
- [Media Reporting](https://clear.ml/docs/latest/docs/guides/reporting/media_reporting/)
- [Artifacts Reporting](https://clear.ml/docs/latest/docs/guides/reporting/artifacts/)
- [Task visualization](https://clear.ml/docs/latest/docs/webapp/webapp_exp_track_visual/)
- [ClearML Reports](https://clear.ml/docs/latest/docs/webapp/webapp_reports/)
