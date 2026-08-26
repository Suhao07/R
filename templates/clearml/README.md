# Reusable ClearML observability template

This template adds ClearML tracking to an existing training/evaluation
project. It does not replace the project's trainer, evaluator, benchmark,
experiment Markdown, or receipt contract.

## Onboard a project

1. Copy `project-profile.example.yaml` and set the document/review roots,
   task owners and metric mapping.
2. Keep credentials outside the profile in the operator's local
   `clearml.conf` or environment variables.
3. Run `python ResearchWorkflow/scripts/validate_clearml_project_profile.py`
   against the profile.
4. Copy `clearml_adapter.py.template` into the responsibility repository and
   call it only from the existing train/eval entrypoint. For live training,
   also copy `train_hook.py.template`: call `start_training_observer` once,
   `report_training_step` from the existing logging callback, and
   `report_training_checkpoint` from the existing checkpoint callback, then
   finalize on normal or failed exit.
5. Copy `report_payload.py.template` beside the adapter. Set optional
   `metric_sources` dotted paths in the profile instead of writing a new
   project-specific uploader.
6. Put each run under the convention in `experiment_bundle/` and run the
   copied reporter with `--experiment-root <run-root>`. It automatically
   discovers `report.md`, `report.html`, `scorecard.json`, receipts,
   visualization manifests, the section media manifest and configured media
   directories. The generated HTML is reported as a Debug Sample and the same
   files are uploaded as artifacts. `--summary-json`, `--artifact` and
   `--media` remain available for exceptional files. The bundle reporter does
   not sweep raw data, predictions or checkpoints.
7. Start the original command manually through SSH/tmux, or use
   `ResearchWorkflow/scripts/run_clearml_pipeline.py` to order an existing
   train command, eval command and the two post-run reporters. When base
   ClearML Tasks and a queue already exist, use
   `ResearchWorkflow/scripts/register_clearml_pipeline.py` to register the
   native train → eval → report DAG; it accepts project-owned parameter
   overrides and does not install or start an Agent.

The generic reporter accepts the same evidence paths and `--media
title=series=path` selections. Use `--dry-run` first. A real invocation
creates one Task, connects provenance-only configuration (Git identity,
dirty-state, command with obvious credential values redacted, fingerprints and
evidence hashes), uploads only the convention-based bundle plus explicit
overrides, and reports at most `media.max_debug_samples_per_series` samples per
series.

After the reporter writes `clearml_task_linkage.json`, render the separate
evidence binding sidecar:

```bash
python ResearchWorkflow/scripts/render_clearml_evidence_binding.py \
  --linkage <run-root>/clearml_task_linkage.json \
  --evidence experiment_record=<experiment.md> \
  --evidence receipt=<finished_receipt.json> \
  --evidence scorecard=<scorecard.json> \
  --evidence visualization_index=<visualization_index.json> \
  --out <run-root>/clearml_evidence_binding.json
```

For historical review folders, use
`render_clearml_history_import.py --root <one-selected-folder>` first. The
manifest labels folders without a started receipt as
`historical_index_only`; it never invents a start-time provenance claim.

## Evidence policy

- Markdown records remain canonical in the responsibility repository.
- Receipts and visualization manifests remain the lifecycle gate.
- Small receipts, scorecards, manifests and selected review HTML/media may be
  uploaded as artifacts/debug samples.
- Checkpoints and full datasets are normally link-only.
- `upload_selected`/`upload_all` require a resolved `artifacts.output_uri`; the
  adapter uploads an explicitly selected checkpoint directory as one ClearML
  artifact instead of falling back to an implicit destination.
- `download_clearml_artifact(task_id, artifact_name, destination)` restores one
  uploaded artifact and returns a deterministic file-tree manifest.
  `compare_checkpoint_manifests(source_checkpoint, restored_checkpoint)`
  compares kind, file count, bytes and full SHA-256, including a single large
  checkpoint file; the
  `clearml_checkpoint_parity.py` command fails before model use when a field
  differs.
- Raw/private data and credentials are never uploaded by this template.

The template deliberately does not scan or modify a project at runtime beyond
the paths explicitly declared in the profile.
