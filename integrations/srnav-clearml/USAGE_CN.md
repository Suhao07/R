# SR-Nav ClearML 使用文档

本文是当前无 GPU Agent 阶段的操作手册。目标是把一次实验的内容分配到
ClearML 最适合的展示位置：

| 内容 | 归属 | 在哪里查看 |
| --- | --- | --- |
| 中文实验文档 | ClearML Report；原始 Markdown 仍在责任仓 | Reports，或 Task 的 Artifacts |
| loss、准确率、L2、角度等曲线 | Task Scalars | Task → SCALARS |
| HTML、图片、视频、音频 | Debug Samples | Task → DEBUG SAMPLES |
| JSON、CSV、Markdown、receipt、manifest | Artifacts | Task → ARTIFACTS |
| 本地中文总览和批量校阅 | `review_outputs/index.html` | 浏览器直接打开 |

ClearML Web UI 当前主要是英文；本系统的中文化重点放在实验名称、标签、
描述、Reports、Markdown 和本地校阅页面。不要把 API key 或密码写进实验
文档、Task 描述或 Git 文件。

## 1. 启动本地服务

在 `/home/ubuntu/WorkSpace/project/SR/Code` 下执行：

```bash
cd ResearchWorkflow/integrations/srnav-clearml/clearml-server
./start_local_server.sh
```

访问地址：

```text
Web UI:     http://127.0.0.1:8080
REST API:   http://127.0.0.1:8008
Fileserver: http://127.0.0.1:8081
```

当前 compose 明确不包含 `clearml-agent-services`，因此不会自动排队或启动
GPU 任务。服务只监听回环地址；远程访问使用：

```bash
./ssh_tunnel.sh user@remote-host
```

然后在本地浏览器打开 `http://127.0.0.1:8080`。

## 2. 每次实验的目录约定

实验执行仓保持原有目录，不把 ClearML 文件复制成第二份 canonical record：

```text
ms-swift/docs/Experiments/<experiment>.md       # 中文实验记录，canonical
review_outputs/<run-root>/scorecard.json       # 指标汇总
review_outputs/<run-root>/scorecard.csv        # 表格结果
review_outputs/<run-root>/finished_receipt.json
review_outputs/<run-root>/visualization_index.json
review_outputs/<run-root>/review.html          # 可人工校阅的 HTML
review_outputs/<run-root>/media/*.png|*.jpg|*.mp4
```

`review_outputs/index.html` 继续作为本地总览入口；ClearML 只接收明确选择的
结果和媒体，不扫描并上传整个目录。

## 3. 先做本地 dry-run

评测结果生成后，先检查 profile 和上传计划：

```bash
cd /home/ubuntu/WorkSpace/project/SR/Code

python ResearchWorkflow/scripts/validate_clearml_project_profile.py \
  ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --workspace-root /home/ubuntu/WorkSpace/project/SR/Code

python ResearchWorkflow/scripts/render_clearml_payload_manifest.py \
  --profile ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id <stable-run-id> \
  --workspace-root /home/ubuntu/WorkSpace/project/SR/Code \
  --experiment-record <experiment.md> \
  --receipt <finished_receipt.json> \
  --scorecard <scorecard.json> \
  --visualization-index <visualization_index.json> \
  --out /tmp/<stable-run-id>-clearml-manifest.json
```

这个步骤只读取文件并生成清单，不连接 ClearML、不上传任何数据。

## 4. 上传一次评测结果

原有 evaluator 不需要改动。使用 ms-swift 责任仓的 post-run reporter：

```bash
set -a
source ResearchWorkflow/integrations/srnav-clearml/clearml-server/local.env
set +a

PYTHONPATH=/home/ubuntu/WorkSpace/project/SR/Code/ms-swift \
conda run -n UrbanNav python \
  ms-swift/scripts/sidewalk_nav/clearml_report_eval.py \
  --profile ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id <stable-run-id> \
  --summary-json <run-root>/scorecard.json \
  --artifact scorecard_csv=<run-root>/scorecard.csv \
  --experiment-record <experiment.md> \
  --receipt <run-root>/finished_receipt.json \
  --visualization-index <run-root>/visualization_index.json \
  --linkage-out <run-root>/clearml_task_linkage.json \
  --task-name "中文评测/<stable-run-id>" \
  --description "中文实验记录、评测分数和选择性可视化媒体"
```

`scorecard.json` 会自动作为 `scorecard` artifact。额外的 JSON、CSV、Markdown
或 HTML 文件使用重复的 `--artifact name=path` 参数：

```bash
  --artifact rows=<run-root>/rows.jsonl \
  --artifact report_html=<run-root>/review.html \
  --artifact config=<run-root>/config.json
```

只在 Task 仍处于运行/创建阶段时上传。Task 完成后不能追加 artifact；如果
需要补充归档文件，创建一个新的 `evidence-archive` Task，并在配置中记录
原 Task ID。

## 5. 上传 HTML、图片和视频到 Debug Samples

使用 `--media "标题=系列=路径"`：

```bash
  --media "HTML=实验报告=<run-root>/review.html" \
  --media "图片=成功案例=<run-root>/media/success_001.png" \
  --media "图片=失败案例=<run-root>/media/failure_001.jpg" \
  --media "视频=FPV案例=<run-root>/media/fpv_001.mp4"
```

这些内容出现在 Task → `DEBUG SAMPLES`。视频可以在全屏查看器中播放；图片
可以按 title/series/iteration 浏览。当前 profile 默认每个 series 最多 30
个样本，并且 `selected_review_only` 要求媒体位于 `review_outputs` 下。

HTML 中如果引用相对路径：

```html
<img src="./media/example.png">
<video src="./media/fpv.mp4"></video>
```

单独上传 HTML 后相对路径不一定能在 ClearML 中解析。推荐两种方式：

1. HTML 作为 artifact 保存原始报告，同时图片/视频分别作为 Debug Samples 上传；
2. 生成 self-contained HTML，把小图片转成 data URI，把视频改为独立 Debug
   Sample 或可访问 URL。

不要把完整数据集、原始预测全集和 checkpoint 作为 Debug Sample 上传。

## 6. 创建中文 ClearML Report

Task 负责运行结果，Report 负责可读的中文研究总结：

1. 打开 ClearML Web UI 的 `Reports` 页面；
2. 新建一个中文标题，例如“Stage II CityWalker 评测报告”；
3. 写入中文 Markdown：实验目的、setting、结果表、正负案例和结论；
4. 在 Task 的 `SCALARS` 或 `DEBUG SAMPLES` 中选择需要嵌入的图表/媒体；
5. 使用资源菜单的嵌入功能复制代码，粘贴到 Report；
6. 草稿阶段持续编辑，确认后再发布。发布后的 Report 应视为锁定版本。

建议的 Report 结构：

```markdown
# 实验名称

## 目的
## Setting 与版本
## 数据和评测范围
## 主要指标
## 成功案例
## 失败案例与人工校阅
## 原因分析
## 结论
## 下一实验
```

原始 Markdown 仍保存于 `ms-swift/docs/Experiments`，Report 是面向浏览和汇报
的呈现层，不替代实验记录、receipt 或 benchmark contract。

## 7. 证据绑定和归档

真实 Task 完成后生成绑定 sidecar：

```bash
python ResearchWorkflow/scripts/render_clearml_evidence_binding.py \
  --linkage <run-root>/clearml_task_linkage.json \
  --evidence experiment_record=<experiment.md> \
  --evidence receipt=<run-root>/finished_receipt.json \
  --evidence scorecard=<run-root>/scorecard.json \
  --evidence visualization_index=<run-root>/visualization_index.json \
  --out <run-root>/clearml_evidence_binding.json
```

绑定文件记录 Task ID、Task URL、证据路径、文件大小和 bounded SHA256；它不复制
实验正文。重要归档应同时保留本地 sidecar 和 ClearML archive Task。

## 8. UI 验收清单

- [ ] Projects 中能找到中文 Task 名称和 `SR-Nav` 项目。
- [ ] `SCALARS` 能看到 `eval/*` 指标。
- [ ] `DEBUG SAMPLES` 能打开 HTML、图片并播放视频。
- [ ] `ARTIFACTS` 能下载 scorecard、CSV、Markdown、receipt 和 manifest。
- [ ] Task description 中有 validation scope 和 provenance。
- [ ] Reports 页面能创建、编辑并嵌入 Task 可视化。
- [ ] 本地 `review_outputs/index.html` 仍能打开并链接到原始校阅材料。

## 9. 当前限制

- Web UI 菜单暂不提供中文 locale；中文内容和中文 Report 可以正常使用。
- 本阶段没有实时训练 step/loss 埋点；训练过程仍需从原有日志和后续 train
  reporter 接入。
- 没有 GPU Agent、Queue 或 Pipeline。
- 当前 artifact URI 是本机 Fileserver；多机使用前应改为 NAS/MinIO/S3 等共享
  URI。
- 当前 SSH tunnel 只提供模板，真实远程主机需要由操作者填写。
