# Research Review Hub

`research_hub` 是 `/SR/Code` 的本地科研管理与校阅控制面。它扫描既有产物，
但不改变 `review_outputs` 下的历史 HTML、JSON、JSONL 或媒体。

```bash
cd /home/ubuntu/WorkSpace/project/SR/Code/ResearchWorkflow
python -m research_hub scan
python -m research_hub export
python -m research_hub serve --host 127.0.0.1 --port 8765
python -m research_hub gateway --host 127.0.0.1 --port 8080 --hub-port 8765 --clearml-port 8082
python -m research_hub doctor
```

`scan` 写入可重建的 `_research_hub/catalog.{json,sqlite}`，`export` 生成可直接打开的
`../review_outputs/index.html`，以及 `_research_hub/rendered_documents/` 下的 Markdown
预览页。静态首页会内嵌预览 HTML、图片、视频、音频和 PDF；实验 Markdown 的表格、代码块、
相对本地媒体链接会被渲染为 HTML。

要在线编辑 canonical Markdown，使用 `serve` 打印的带 token URL：

```bash
python -m research_hub serve --host 127.0.0.1 --port 8765
```

live 页面会把生成的 Markdown 预览和 HTML artifact 通过 loopback API 提供给 iframe，
所以不要把 ClearML Artifacts 面板或 `file://` 页面当作在线文件编辑器。ClearML 的
Artifacts 用于只读保存/下载，HTML 的交互查看应放在 Debug Samples；Research Hub 才
负责 Markdown 校验、diff、原子保存和备份。

使用 `gateway` 后，`http://127.0.0.1:8080/` 仍然打开 ClearML Web，
`http://127.0.0.1:8080/research/` 打开同一端口下的 Research Hub。统一 gateway
在服务端注入 Hub session token，浏览器端不需要复制或填写 token；
通过该 gateway 打开的、已绑定的 ClearML Task 详情 URL 会显示同一页面的
“ClearML 原生任务 / 实验校阅工作台”切换按钮，兼容 `/tasks/<task_id>/general` 和
`/experiments/<task_id>/...` 两种 ClearML 路径；原生 ClearML 页面可通过 `native=1`
查询参数单独打开，统一页面也会嵌入该原生视图；
`/research/experiments/<run_id>` 是一个实验的完整校阅工作台，聚合 canonical
Markdown、完整 `report.html`、scorecard、章节图片/视频/HTML 和 ClearML Task。
媒体通过带 HTTP Range 的 `/research/api/experiments/<id>/files/...` 提供，视频可拖动。
实验媒体按 report manifest 的章节分组显示；attention/paired-trace 采用统一宽度的
响应式网格、章节筛选和文件名搜索，点击图片可放大查看。JSON/NPZ 保持在“证据文件”
中作为下载型 Artifact，不会被当作图片媒体渲染。

在 Chrome/Edge 中，静态页面的 canonical 实验记录可点击“选择工作区目录”，选择包含
`ResearchWorkflow` 与 `review_outputs` 的 `Code` 目录后写回。该路径先备份到
`review_outputs/_research_hub/history/browser-static/` 并做全文冲突检查，但浏览器 File System
Access API 无法保证操作系统级原子替换；保存时会同步 `index.html` 内的静态 catalog，因而可以
继续只打开该页面编辑。运行 `python -m research_hub export` 仅在需要重新扫描新产物或重新生成
Markdown HTML 预览页时使用。Firefox/Safari 或需要原子保存时使用下方服务路径。

本地服务的写接口要求启动时打印的 session token；服务只绑定 loopback，远程查看应使用受信
SSH 隧道。

实验 Markdown 的保存必须经过现有 `validate_experiment_record.py`、base SHA-256、diff 预览和
原子替换。审核事件单独追加到 `_research_hub/review_events/`，并可导出派生的 review view；
不会改写原始 annotation 或 diagnosis JSONL。
