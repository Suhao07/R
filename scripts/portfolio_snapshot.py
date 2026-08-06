#!/usr/bin/env python3
"""Generate a mechanical snapshot of the research repository portfolio."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PORTFOLIO_ROOT = SCRIPT_DIR.parent
DEFAULT_MATRIX = PORTFOLIO_ROOT / "repos.json"
DEFAULT_OUTPUT = PORTFOLIO_ROOT / "snapshots" / "repo_snapshot_current.json"


def _run_git(path: Path, *args: str, check: bool = True) -> str:
    """Run a read-only Git command and return stripped stdout."""

    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed in {path}: {detail}")
    return result.stdout.strip()


def _is_git_repository(path: Path) -> bool:
    """Return whether path is a Git worktree."""

    if not path.is_dir():
        return False
    return _run_git(path, "rev-parse", "--is-inside-work-tree", check=False) == "true"


def _remotes(path: Path) -> dict[str, dict[str, str]]:
    """Return fetch and push URLs without performing network access."""

    result: dict[str, dict[str, str]] = {}
    for line in _run_git(path, "remote", "-v", check=False).splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        name, url, kind = parts
        result.setdefault(name, {})[kind.strip("()")] = url
    return result


def _git_state(path: Path) -> dict[str, Any]:
    """Collect reproducibility-relevant Git state."""

    if not _is_git_repository(path):
        return {
            "git_repository": False,
            "branch": None,
            "commit": None,
            "describe": None,
            "dirty": None,
            "dirty_path_count": None,
            "dirty_paths": [],
            "dirty_paths_truncated": False,
            "status_branch": None,
            "remotes": {},
        }
    status_lines = _run_git(path, "status", "--porcelain=v1").splitlines()
    status_branch = _run_git(path, "status", "--short", "--branch").splitlines()
    dirty_limit = 200
    commit = _run_git(path, "rev-parse", "--verify", "HEAD", check=False) or None
    return {
        "git_repository": True,
        "branch": _run_git(path, "branch", "--show-current"),
        "commit": commit,
        "describe": _run_git(
            path, "describe", "--always", "--dirty", "--broken", check=False
        ),
        "dirty": bool(status_lines),
        "dirty_path_count": len(status_lines),
        "dirty_paths": status_lines[:dirty_limit],
        "dirty_paths_truncated": len(status_lines) > dirty_limit,
        "status_branch": status_branch[0] if status_branch else "",
        "remotes": _remotes(path),
    }


def collect_snapshot(matrix_path: Path = DEFAULT_MATRIX) -> dict[str, Any]:
    """Collect the portfolio and repository state described by the matrix."""

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    portfolio_path = Path(matrix["portfolio_root"])
    portfolio_state = _git_state(portfolio_path)
    repositories: list[dict[str, Any]] = []
    for repo in matrix["repositories"]:
        path = Path(repo["path"])
        agent_relative = repo.get("agent_instructions")
        agent_path = path / agent_relative if agent_relative else None
        state = {
            "id": repo["id"],
            "name": repo["name"],
            "path": str(path),
            "role": repo["role"],
            "required": bool(repo["required"]),
            "mutation_policy": repo["mutation_policy"],
            "policy_profile": repo["policy_profile"],
            "exists": path.is_dir(),
            "agent_instructions": (
                str(agent_path) if agent_path is not None else None
            ),
            "agent_instructions_exist": (
                agent_path.is_file() if agent_path is not None else None
            ),
        }
        state.update(_git_state(path))
        repositories.append(state)
    return {
        "schema_version": "research_portfolio_repo_snapshot_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matrix": str(matrix_path.resolve()),
        "workspace_root": matrix["workspace_root"],
        "portfolio": {
            "path": str(portfolio_path),
            **portfolio_state,
        },
        "repositories": repositories,
    }


def main() -> int:
    """Generate and write the current snapshot."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    snapshot = collect_snapshot(args.matrix.resolve())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    for repo in snapshot["repositories"]:
        commit = repo["commit"][:12] if repo["commit"] else "not-git"
        print(
            f"- {repo['id']}: role={repo['role']} {commit} "
            f"dirty={repo['dirty']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
