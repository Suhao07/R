# ClearML observability policy

This policy defines the reusable, no-Agent first phase for projects in the
research workspace.

## Ownership

- The responsibility repository owns training, inference, evaluation,
  annotation semantics, benchmark contracts, checkpoints and experiment
  Markdown.
- `ResearchWorkflow` owns the profile schema, evidence policy, validators and
  small payload manifests.
- ClearML owns runtime visibility: Task metadata, logs, metrics, plots, debug
  samples, artifact references and later queue/pipeline state.

ClearML Task descriptions and plots are indexes into evidence; they do not
replace experiment records, receipts, manifests or human analysis.

## First-phase constraints

- Start existing commands manually through SSH/tmux.
- Do not install or run a GPU Agent as part of this phase.
- Do not change DeepSpeed, torchrun, checkpoint or evaluator semantics.
- Only rank zero creates and writes the Task in distributed execution.
- Use a unique run ID and `reuse_last_task_id=False`.
- Never put API keys, cloud credentials, private tokens or raw private data in
  profiles, Task config, descriptions or portfolio control files.
- Keep services loopback-only and use trusted SSH forwarding for UI/API access.
- Connect only provenance metadata and explicitly selected evidence paths; the
  adapter records commit/branch/dirty-state, bounded evidence hashes and an
  operator-provided validation scope without copying file contents into Task
  configuration.

## Artifact classes

`required_upload` is limited to receipts, manifests, scorecards, summaries and
selected rendered reports. `debug_sample` is limited to representative media
and interactive review HTML. Large checkpoints, full predictions and full
video collections are `link_only`; raw/private data is `never_upload`.

Every formal run must still satisfy the existing experiment-documentation
requirements: a started visualization manifest and a finished visualization
index bound by lifecycle receipts.

The generic payload manifest may inventory all declared review files, but an
actual reporter uploads only the scorecard plus paths explicitly supplied by
the operator. Selected debug media must obey the profile's per-series limit;
`selected_review_only` media must remain below `documents.review_root`.
