# Research Review Hub

`research_hub` 是 `/SR/Code` 的本地科研管理与校阅控制面。它扫描既有产物，
但不改变 `review_outputs` 下的历史 HTML、JSON、JSONL 或媒体。

```bash
cd /home/ubuntu/WorkSpace/project/SR/Code/ResearchWorkflow
python -m research_hub scan
python -m research_hub export
python -m research_hub serve --host 127.0.0.1 --port 8765
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
