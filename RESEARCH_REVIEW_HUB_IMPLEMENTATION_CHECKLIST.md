# 本地科研管理与校阅系统 V1：实施 Checklist

> 责任边界：本清单与 Hub 源码归 `ResearchWorkflow`；`review_outputs` 中的既有
> HTML、JSON、JSONL 和媒体保持只读。实验 Markdown 仍由 `ms-swift` 与
> `Urban-Nav-SR` 责任仓拥有。

## V1 纠偏：必须完成后才可交付

- [x] 将 KaTeX 0.17.0（MIT）作为本地 vendored 资源；`file://` 不依赖 CDN，
  支持 `$...$`、`$$...$$`、`\\(...\\)` 和 `\\[...\\]` 数学公式。
- [x] 用真实实验 Markdown 的 Chrome 渲染 smoke 确认生成 49 个 KaTeX 数学节点。
- [ ] 增加可视化 / 媒体、实验记录、审核输入目录的可视化设置页，而不是只要求手改 JSON。
- [ ] 将设置保存、目录合法性校验、重新索引与前端状态刷新收敛为一个可验证工作流。
- [ ] 基于开源工具调研写入明确的复用 / 不复用决策及 license、数据归属边界。

## 0. 治理与可恢复性

- [x] 确认本地优先、单用户、仅 loopback 的运行模式。
- [x] 确认历史产物只读，审核结论写 append-only sidecar。
- [x] 确认实验 Markdown 采用 SHA 冲突检测、diff 预览和原子写回。
- [x] 创建 `research-review-hub` workstream；不改变现有 `core-framework` 状态。
- [x] 记录首次真实语料 scan 的基线计数、时间和已知限制。

## 1. Catalog 与静态主页

- [x] 建立 allowlisted source registry：`review_outputs`、主仓实验 Markdown、
  `ResearchWorkflow` run/workstream evidence。
- [x] 实现 manifest-first 扫描，读取实验记录、run manifest、visualization index、
  scorecard、review HTML 和 JSONL schema。
- [x] 建立可删除重建的 SQLite FTS5 索引与 JSON catalog；大 JSONL/weights 只索引元数据。
- [x] 生成 `review_outputs/index.html`；`file://` 下可搜索、打开并内嵌预览既有产物。
- [x] 将实验 Markdown 预渲染为 Hub-owned HTML 页面，保留表格、代码块、相对图片/媒体链接和文档内锚点。
- [x] 显示验证四轴、待审核数、文档校验、远端缺失与责任仓 dirty 状态。

## 2. 本地服务与实验文档

- [x] 实现 `scan`、`export`、`serve`、`doctor` CLI；服务只接受 loopback 地址。
- [x] 实现 catalog/search/artifact/document 只读 API 与 HTTP Range 媒体响应。
- [x] 实现 Markdown 预览、现有实验记录校验、三方 SHA 冲突检测、备份和原子保存。
- [x] 在服务页提供讨论决定/下一实验的一键表格追加、完整 Markdown 编辑、diff 和 Git 状态提示。
- [x] 在静态页提供 Markdown 编辑器与渲染预览；Chrome/Edge 由用户选择工作区目录后可进行备份、内容冲突检查和原 Markdown 写回。
- [x] 静态写回同时更新 `index.html` 的内嵌 document catalog；重开同一 `file://` 页面可以继续编辑，无需先启动服务。
- [x] 明确静态浏览器写回不具备原子 replace；需要原子保存或不支持 File System Access API 时，保留 loopback `serve` 路径。

## 3. 审核与媒体

- [x] 识别 CityWalker diagnosis、Reasoning reconciliation 和 generic JSONL review queue。
- [x] 定义并写入 `research_hub_review_event_v1` append-only 审核事件。
- [x] 按最后有效事件折叠当前审核状态；导出不修改原件的 `reviewed.jsonl + summary.json`。
- [x] 支持图片、SVG、视频、音频、PDF、HTML、CSV、JSON/JSONL 的浏览器内嵌或原文件预览。
- [x] 支持新媒体上传到 Hub artifact root，并返回可插入实验文档的本地链接。

## 4. 验证与交付

- [x] 覆盖扫描、FTS、文档冲突、路径逃逸、审核幂等、导出不改原件和 HTTP smoke 的 focused tests。
- [x] 对真实 `review_outputs` 运行 scan/export/serve smoke，并检查 catalog、静态主页响应和 CityWalker queue 识别。
- [x] 用本机 Chrome 无头模式打开真实静态主页与生成的 Markdown 页，确认 JavaScript 工作台、章节和 HTML 表格实际渲染。
- [x] 运行 `git diff --check`、Hub tests 与 `ResearchWorkflow/scripts/portfolio_doctor.py`；portfolio validator 通过，doctor 仅报告历史 snapshot drift。
- [x] 报告精确修改仓、通过/跳过的 gate、既有 dirty state 与唯一下一步。

## 明确不做

- 不迁移既有 run 到 MLflow、FiftyOne 或 Label Studio。
- 不把模型、原始数据、checkpoint 或 secrets 写入 `ResearchWorkflow`。
- 不直接改写历史 annotation、diagnosis、scorecard、receipt 或 review HTML。
- 不启动训练、外部服务、上传、push、tag 或 release。
