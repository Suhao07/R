# 一实验一报告目录

复制此目录作为：

```text
review_outputs/<experiment_id>/
```

目录约定：

```text
<experiment_id>/
├── report.md                 # 人工编辑的实验报告正文
├── report.html               # 自动生成并上传的 HTML
├── report_manifest.json      # 章节 → 图表/图片/视频映射
├── scorecard.json            # 必需的定量结果
├── receipt.json              # 或 finished_receipt.json
├── charts/                   # 主要指标和分析图表
├── images/                   # 图片案例
└── videos/                   # FPV/BEV/失败案例视频
```

`report.md` 使用以下章节名，系统会把 manifest 中的媒体插入对应章节：

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

上传时不需要逐个列出文件：

```bash
python ms-swift/scripts/sidewalk_nav/clearml_report_eval.py \
  --profile ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id <experiment_id> \
  --experiment-root review_outputs/<experiment_id>
```

系统自动发现并上传：

- `report.md`：原始 Markdown Artifact；
- `report.html`：渲染后 HTML Artifact 和 Debug Sample；
- `scorecard.json`、receipt、manifest、visualization index：Artifacts；
- `charts/`、`images/`、`videos/`、`media/`：按 manifest 章节或目录默认分类为 Debug Samples。

原始 Markdown 是长期可编辑证据；HTML 是由 Markdown 和 manifest 派生的网页报告。
在 Research Hub 中编辑 `report.md`，重新运行上传命令即可刷新同一个实验目录的 HTML。
ClearML 已完成的 Task 不能追加文件，因此修改后应使用新的 run ID 或 archive Task。
