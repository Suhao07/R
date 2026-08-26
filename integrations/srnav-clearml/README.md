# SR-Nav ClearML profile

中文使用入口：

- [使用文档](USAGE_CN.md)：启动服务、上传实验结果、嵌入 HTML/图片/视频、创建中文 Report。
- [设计文档](DESIGN_CN.md)：架构、责任边界、数据流、已实现和未实现部分。

This is the first concrete project profile for the reusable ClearML template.
It covers both `ms-swift/docs/Experiments` and the RouteServer documentation
root, while using the existing `review_outputs` tree as a read-only source.

FWTW uses the project-specific companion profile
`fwtw-project-profile.yaml`. It keeps the same review root but maps FWTW's
native `metrics.ADE/FDE/yaw_MAE` evaluation schema and task ownership.

Validate it from the `/SR/Code` workspace:

```bash
python ResearchWorkflow/scripts/validate_clearml_project_profile.py \
  ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --workspace-root /home/ubuntu/WorkSpace/project/SR/Code
```

Build a local-only payload plan:

```bash
python ResearchWorkflow/scripts/render_clearml_payload_manifest.py \
  --profile ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id srnav-review-inventory-20260811 \
  --out /tmp/srnav-clearml-payload-manifest.json \
  --workspace-root /home/ubuntu/WorkSpace/project/SR/Code \
  --experiment-record <experiment.md> \
  --receipt <finished_receipt.json> \
  --scorecard <scorecard.json> \
  --visualization-index <visualization_index.json>
```

The output is an inventory and upload plan. It does not upload files or start
an experiment.

Run the read-only local preflight before asking for a real Server smoke:

```bash
python ResearchWorkflow/scripts/clearml_server_preflight.py \
  --profile ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --workspace-root /home/ubuntu/WorkSpace/project/SR/Code \
  --clearml-config ~/.clearml.conf
```

After an SSH tunnel is available, add an endpoint such as
`--endpoint api=http://127.0.0.1:8008`. The command never starts Docker,
reads credential contents, or uploads artifacts; a non-zero result means that
the declared profile or endpoint is not ready.

## Manual evaluation reporting

Existing evaluator commands remain unchanged. After an evaluation has produced
its scorecard, place the outputs in `review_outputs/<experiment_id>/` and run
the responsibility-repo reporter with the directory:

```bash
PYTHONPATH=/home/ubuntu/WorkSpace/project/SR/Code/ms-swift \
python /home/ubuntu/WorkSpace/project/SR/Code/ms-swift/scripts/sidewalk_nav/clearml_report_eval.py \
  --profile /home/ubuntu/WorkSpace/project/SR/Code/ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id <stable-run-id> \
  --experiment-root <run-root>
```

This automatically reads `report.md`, `report.html`, `report_manifest.json`,
`scorecard.json`, receipt files, charts, images and videos. Use explicit
`--artifact`/`--media` only for files outside the convention.

Use `--dry-run` first. It reads the scorecard and writes only a local linkage
with `task_id: null`; the normal mode requires the operator's local ClearML
configuration and creates one testing Task.

For a train run, keep the original tmux command and invoke the responsibility
repo's post-run bridge after the summary/receipt exists:

```bash
PYTHONPATH=/home/ubuntu/WorkSpace/project/SR/Code/ms-swift \
python /home/ubuntu/WorkSpace/project/SR/Code/ms-swift/scripts/sidewalk_nav/clearml_report_train.py \
  --profile /home/ubuntu/WorkSpace/project/SR/Code/ResearchWorkflow/integrations/srnav-clearml/project-profile.yaml \
  --run-id <stable-run-id> \
  --summary-json <run-root>/train_summary.json \
  --receipt <run-root>/finished_receipt.json \
  --experiment-record <experiment.md> \
  --checkpoint-link /data/checkpoints/<run-id> \
  --linkage-out <run-root>/clearml_task_linkage.json
```

Use `--dry-run` first. `checkpoint_policy: link_only` rejects checkpoint
uploads and records only the URI plus optional checkpoint metadata.
