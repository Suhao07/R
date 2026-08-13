"""Explicit, operator-triggered ClearML snapshot publishing for one bundle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import HubConfig, is_within


def publish_experiment(config: HubConfig, experiment: dict[str, Any]) -> dict[str, Any]:
    """Run the responsibility-repo post-run reporter for one safe bundle.

    Publishing is intentionally never automatic.  The caller must have passed
    the Hub write token, and the command is limited to the standard reporter
    and the selected experiment root.  ClearML credentials are read from the
    operator environment or the ignored local.env file, but are never returned
    in the response.
    """

    root = Path(str(experiment.get("root", ""))).resolve()
    if not root.is_dir() or not is_within(root, config.artifact_root):
        raise ValueError("experiment root is outside the configured artifact root")
    run_id = str(experiment.get("run_id", "")).strip()
    if not run_id or any(char.isspace() for char in run_id):
        raise ValueError("experiment run_id is invalid")
    profile = config.portfolio_root / "integrations" / "srnav-clearml" / "project-profile.yaml"
    reporter = config.workspace_root / "ms-swift" / "scripts" / "sidewalk_nav" / "clearml_report_eval.py"
    if not profile.is_file() or not reporter.is_file():
        raise ValueError("ClearML profile or responsibility-repo reporter is missing")
    env = os.environ.copy()
    _load_ignored_local_env(config, env)
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(config.workspace_root / "ms-swift"), env.get("PYTHONPATH", "")) if item
    )
    python = env.get("RESEARCH_HUB_PUBLISH_PYTHON") or sys.executable
    command = [
        python,
        str(reporter),
        "--profile",
        str(profile),
        "--run-id",
        run_id,
        "--experiment-root",
        str(root),
        "--task-name",
        f"archive/{run_id}",
        "--description",
        "由 Research Hub 明确触发的完整实验校阅快照",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(config.workspace_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"ClearML publish command failed: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no reporter output").strip()
        raise RuntimeError(f"ClearML publish failed (exit {result.returncode}): {detail[-4000:]}")
    payload = _last_json_object(result.stdout)
    return {
        "ok": True,
        "mode": payload.get("mode", "clearml") if payload else "clearml",
        "run_id": run_id,
        "task_id": payload.get("task_id") if payload else None,
        "artifact_names": payload.get("artifact_names", []) if payload else [],
        "media_candidates": payload.get("media_candidates") if payload else None,
        "message": "ClearML snapshot published; refresh the experiment page to load the new linkage.",
    }


def _load_ignored_local_env(config: HubConfig, env: dict[str, str]) -> None:
    """Load simple KEY=VALUE entries from the ignored local ClearML env file."""

    path = config.portfolio_root / "integrations" / "srnav-clearml" / "clearml-server" / "local.env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum():
            env.setdefault(key, value.strip().strip("\"'"))


def _last_json_object(output: str) -> dict[str, Any] | None:
    """Extract the reporter's final JSON object without exposing command logs."""

    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
