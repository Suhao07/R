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
| 中文实验方案、setting、原因分析、下一实验 | 一实验一 bundle：原始 Markdown artifact + 自动生成 HTML artifact/Debug Sample | Markdown 保留 Git 历史；HTML 负责网页排版、表格、公式和章节媒体 |
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
└── <experiment_id>/                 一实验一 report bundle
    ├── report.md                    可编辑正文
    ├── report.html                  自动派生 HTML
    ├── report_manifest.json         章节到媒体映射
    ├── scorecard.json / receipt.json
    ├── charts/ images/ videos/      结果媒体
    └── clearml_task_linkage.json
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
    ├── render Markdown → experiment_record_html
    ├── report rendered HTML → DEBUG SAMPLES
    ├── report_media → DEBUG SAMPLES
    └── 写出 clearml_task_linkage.json
    ↓
render_clearml_evidence_binding.py
    ↓
clearml_evidence_binding.json + archive Task
```

### 4.2 文档和 Report

实验 Markdown 不被替换或覆盖。post-run reporter 在保留原始
`experiment_record` artifact 的同时，生成一个 `experiment_record_html` 派生
artifact，并把它作为 `实验文档 / markdown_rendered` Debug Sample 上传。这样
Artifacts 负责证据保存，Debug Samples 负责网页阅读：ClearML 的 Markdown
artifact 预览器不会自动把 `.md` 转成排版页面，所以不能把 Artifacts 面板当成
Markdown 阅读器。

派生 HTML 使用 Python-Markdown 处理标题、表格、代码块和目录，并加载 MathJax
处理 `$...$`、`$$...$$`、`\(...\)` 与 `\[...\]`；小型本地图片内嵌为 data URI，
视频和大型媒体通过独立 Debug Sample 绑定。Reports 页面仍可把该 Debug Sample、
Scalars 和 Plots 组合成更适合汇报的中文页面；原 Markdown 继续作为 Git 中的
长期记录。

每个实验使用一个 `review_outputs/<experiment_id>/` bundle。reporter 接收
`--experiment-root` 后自动发现约定文件：`report.md`、`report.html`、
`report_manifest.json`、scorecard、receipt、charts、images 和 videos。manifest
会将“主要指标”“成功案例”“失败案例与人工校阅”等章节绑定到图表、图片和视频；
这些文件分别保存为 Artifact 或 Debug Sample。旧的 `--artifact`/`--media` 参数
仍可用于补充特殊证据。

### 4.3 本地校阅

`review_outputs/index.html` 不迁移到 ClearML，也不因上传而改变。它继续提供本地
批量筛选、相对路径媒体和人工标注上下文。新增的 Research Hub unified gateway
则在同一个 `8080` 网址下提供按 `run_id` 聚合的单实验校阅页；ClearML 只接收
operator 明确选择的代表性 HTML、图片和视频。

### 4.4 在线编辑与 HTML 查看边界

在线编辑不是 ClearML Task artifact 的能力。两类页面的职责必须分开：

| 页面 | 能力 | 是否可编辑 |
| --- | --- | --- |
| ClearML `Reports` | 在线编写中文总结、嵌入 Task 图表和媒体 | 可以编辑 Report 草稿 |
| ClearML `Task → ARTIFACTS` | 保存原始 Markdown、JSON、CSV、HTML 和 receipt | 只读/下载，不是文件编辑器 |
| ClearML `Task → DEBUG SAMPLES` | 在浏览器中查看 HTML、图片、视频 | 只读查看 |
| Research Hub live page | 编辑责任仓 Markdown、校验、diff、原子保存、备份 | 可以编辑 canonical Markdown |

### 4.5 单实验统一工作台

`research_hub.catalog` 以 `clearml_task_linkage.json`、任意
`clearml_*linkage*.json`、`report_manifest.json` 或
`report.md` 为边界发现 bundle，并把 `report.html`、scorecard、receipt、章节媒体
和 canonical 文档 ID 聚合为一个 `experiment` 对象。工作台页面为：

```text
http://127.0.0.1:8080/research/experiments/<run_id>
```

页面左侧编辑责任仓 Markdown，中间显示完整 `report.html` 和编辑后源文档预览，
右侧显示 ClearML 状态、指标和文件，下方按 manifest 展示图片、视频和嵌套 HTML。
媒体经过 `/api/experiments/<id>/files/<path>` 提供，路径限制在 bundle 内并支持
HTTP Range；不允许访问 checkpoint、压缩包或目录外文件。保存仍走已有
`DocumentStore` 的校验、冲突检查和备份，发布则明确创建新的 ClearML 快照。

因此本系统的“Web 实时编辑文件”入口是 Research Hub，而不是 ClearML 的
Artifacts 面板。使用统一 gateway 时，浏览器直接打开无 token 的入口；gateway
仅在本机上游请求中注入临时 session token：

```bash
cd /home/ubuntu/WorkSpace/project/SR/Code/ResearchWorkflow/integrations/srnav-clearml/clearml-server
./start_unified_ui.sh
```

然后访问 `http://127.0.0.1:8080/research/`。统一 gateway 还会在 ClearML 原生
Task 详情 URL 自动读取当前 Task ID 与本地 bundle 下所有
`clearml_*linkage*.json` 的映射，并返回同一 8080 的统一切换页面。页面顶部提供
“ClearML 原生任务”和“实验校阅工作台”按钮，下面分别加载两个 iframe；不依赖浮动
按钮、旧 Task Description，也不要求修改 ClearML Docker 镜像。原生 iframe 使用
`native=1`；一个 bundle 可以因此绑定多个 report、v2、UI acceptance Task。
单实验页面还嵌入 ClearML 原生 Task
视图，因此可以在同一校阅页查看 Task 状态、日志、Scalars 和 Debug Samples；
ClearML 的完成 Task/Artifact 仍保持只读，Markdown 编辑、媒体插入和新快照发布由
本工作台完成。直接运行 `python -m research_hub serve` 仅用于调试，此时才需要使用
命令打印的 token URL。

在 `实验文档` 中点击“编辑”即可修改 Markdown；“检查并预览 diff”会运行模板
校验并生成公式/表格预览，“确认保存”会做 base SHA-256 冲突检查、原子替换和
gzip 备份。`产物` 页面中的 `.html` 会通过 loopback `/api/artifacts/<id>` 以
iframe 打开，因而不需要把它当作 Markdown 文本阅读。

`file:///.../review_outputs/index.html` 仍是静态降级入口：可预览，但要么在
Chrome/Edge 显式授权工作区目录，要么使用上面的 live 服务，才能稳定写回和加载
由 Hub 生成的 Markdown 预览页。

## 5. 配置和安全边界

当前本地通道：

```text
Web UI       http://127.0.0.1:8080
ClearML Web upstream http://127.0.0.1:8082
Research Hub upstream http://127.0.0.1:8765/research/
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
- `--experiment-root` 一实验一目录自动发现：Markdown、HTML、scorecard、receipt、
  manifest 和章节媒体；可生成持久化 `report.html`
- `clearml_report_train.py`：手动训练收尾入口，checkpoint 默认 link-only

### 证据和验证

- profile validator
- payload manifest dry-run
- server preflight
- evidence binding sidecar
- historical review import manifest
- 本地 loopback ClearML Server compose
- loopback unified gateway：`8080/` → ClearML Web，`8080/research/` → Research Hub
- 一实验一页面：bundle 聚合、Range 媒体路由、canonical Markdown 编辑、显式快照发布
- 无 GPU evaluation Task smoke
- evidence archive Task
- ResearchWorkflow 和 ms-swift focused tests

### 当前真实验证对象

- evaluation Task：`d205590a475b483ebd8b256980e8aa71`
- evidence archive Task：`91a4d6e502d446ecb18be516a83055b7`
- Markdown/HTML acceptance Task：`82c5f91031c04b20b61db7878f078869`
  （`citywalker-markdown-report-acceptance-v2-20260812`，8 artifacts、3 Debug Samples）
- 归档记录：`review_outputs/citywalker_zeroshot_stage_ii_cfm_validation_20260808_01/clearml_archive_record.json`

该验证证明的是本地 ClearML 结果可视化、Markdown → HTML、公式/表格呈现和证据
归档链路，不代表 GPU 训练收敛、benchmark validation 或论文结论。

## 7. 尚未实现部分

统一工作台的本地页面、bundle 聚合、媒体 Range 路由和显式发布入口已经实现；当前
尚未完成的是对真实浏览器/容器启动环境的长期运行验收，以及跨主机共享 URI。发布
按钮依赖责任仓 Python 环境和 ClearML 凭据，未提供凭据时会安全返回失败，不会伪造
Task 成功。

### P4-1～P4-3 实施方案（已完成设计，尚未声称生产验证）

这三个阶段可以实施，但必须按下面的边界逐步接入，不能把 no-GPU smoke 或已有
post-run 结果误报为实时训练验证：

#### P4-1 训练实时 ClearML 埋点

1. 在 `ms-swift` 训练入口创建一个 `train` Task；只由 rank 0 创建 Task 和写
   ClearML 事件。
2. 在现有训练循环的日志回调位置调用可复用
   `ResearchWorkflow/templates/clearml/train_hook.py.template`：上报
   `iteration`、有限的 `loss`、`learning_rate`、`throughput`，不改变 optimizer、
   DeepSpeed、checkpoint 或数据语义。
3. 训练启动时写 provenance/config，结束时上传 receipt、TensorBoard/日志摘要和
   checkpoint link；checkpoint 默认仍是 `link_only`。
4. 先用 CPU/合成 logger 验证“Task 创建→标量序列→失败/成功收尾”，再接真实
   GPU 训练；只有出现最终 step、receipt 和 eval 结果才可称为训练证据。

#### P4-2 远程结果同步与共享 artifact URI

1. 将 `artifacts.output_uri` 从当前本机 Fileserver 改为 NAS、MinIO 或 S3 URI，
   通过运行环境变量注入，绝不把凭据写入 profile 或 Markdown。
2. 每个训练机只上传选定的 scorecard、HTML、媒体和 receipt；原始数据、完整预测
   和 checkpoint 继续按策略禁止或只记录 URI。
3. 通过 `ssh_tunnel.sh` 暴露 Web/API/Fileserver，验收“远程启动页面可读、artifact
   URI 可下载、不同主机不依赖另一台主机的 `127.0.0.1`”。
4. 记录 URI、大小、SHA-256 和上传时间，归档 sidecar 仍由责任仓保存。

#### P4-3 自动 `train → eval → report` Pipeline

1. 使用 ClearML Pipeline/DAG（最终执行仍需要 Agent/Queue）或等价的受控调度器，
   将同一个 `run_id` 作为参数贯穿 train、eval、report 三个 Task。
2. `train` 成功且 receipt 完整才触发 `eval`；`eval` 通过 metric/coverage gate
   才触发 `report`；任何失败都停止后继步骤并留下失败 Task。
3. 每一步只消费上一步声明的 artifact URI，生成新的 linkage、证据绑定和报告，
   不通过共享工作目录隐式传参。
4. 第一版只实现单 Pipeline、单 Queue、手动触发和失败重跑；多队列、优先级和
   自动扩缩容另列阶段。

### 明确延期

- 真实训练循环内的 step/loss/lr 实时埋点
- TensorBoard/DeepSpeed 日志自动接入
- GPU Agent、Queue、暂停/重跑和优先级调度
- train → eval → report Pipeline/DAG

### 仍需产品化

- 多机器共享 artifact URI（NAS/MinIO/S3）
- 远程主机的真实 SSH tunnel 配置和验收
- 更严格的 Web 登录、用户管理和外部访问安全配置
- ClearML Reports 的自动生成 API/脚本（当前已实现 Markdown → HTML Debug Sample；
  复杂 Report 页面仍需在 Web UI 中组合）
- 从 `review_outputs` 选择媒体的图形化上传界面
- ClearML Web UI 菜单中文化；当前只保证中文实验内容和 Report

### 当前行为限制

- Task 进入 `completed` 后不能追加 artifact；补充归档必须创建 archive Task。
- Markdown artifact 不保证在 Artifacts 面板内按 Markdown 排版；应打开自动生成的
  `markdown_rendered` Debug Sample。
- HTML 若引用本地相对路径，单独上传后不保证媒体可见；小型图片由 Markdown
  renderer 内嵌；report bundle 的本地 `report.html` 会按 manifest 插入视频和
  iframe，但 ClearML 远端 HTML Debug Sample 不会自动携带同目录的大型视频，
  因此视频仍以独立 Debug Sample 作为远端查看权威。
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
| P4-1 | 设计/模板已完成，未接真实训练 | rank-zero 实时 step/loss/lr 埋点与训练收尾 |
| P4-2 | 设计已完成，当前仍是本机 URI | NAS/MinIO/S3 artifact URI 与 SSH tunnel 验收 |
| P4-3 | 未实现 | train → eval → report DAG；需要 Agent/Queue |

## 9. 参考文档

- [ClearML Server](https://clear.ml/docs/latest/docs/deploying_clearml/clearml_server/)
- [Media Reporting](https://clear.ml/docs/latest/docs/guides/reporting/media_reporting/)
- [Artifacts Reporting](https://clear.ml/docs/latest/docs/guides/reporting/artifacts/)
- [Task visualization](https://clear.ml/docs/latest/docs/webapp/webapp_exp_track_visual/)
- [ClearML Reports](https://clear.ml/docs/latest/docs/webapp/webapp_reports/)
