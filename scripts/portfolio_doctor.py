#!/usr/bin/env python3
"""Compare portfolio structure and the saved repository snapshot with live state."""

from __future__ import annotations

import json

from portfolio_snapshot import DEFAULT_MATRIX, DEFAULT_OUTPUT, collect_snapshot
from portfolio_validate import PORTFOLIO_ROOT, validate_portfolio


def main() -> int:
    """Report validation errors, snapshot drift, blockers and reference warnings."""

    errors = validate_portfolio(PORTFOLIO_ROOT)
    drift: list[str] = []
    release_blockers: list[str] = []
    reference_warnings: list[str] = []
    if DEFAULT_OUTPUT.is_file():
        saved = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        live = collect_snapshot(DEFAULT_MATRIX)
        for field_name in ("commit", "branch", "dirty", "dirty_paths"):
            if saved["portfolio"].get(field_name) != live["portfolio"].get(
                field_name
            ):
                drift.append(
                    f"portfolio {field_name}: "
                    f"saved={saved['portfolio'].get(field_name)!r} "
                    f"live={live['portfolio'].get(field_name)!r}"
                )
        saved_by_id = {repo["id"]: repo for repo in saved["repositories"]}
        for current in live["repositories"]:
            prior = saved_by_id.get(current["id"])
            if prior is None:
                drift.append(f"{current['id']}: missing from snapshot")
                continue
            for field_name in (
                "commit",
                "branch",
                "dirty",
                "dirty_paths",
                "agent_instructions_exist",
            ):
                if prior.get(field_name) != current.get(field_name):
                    drift.append(
                        f"{current['id']} {field_name}: "
                        f"saved={prior.get(field_name)!r} "
                        f"live={current.get(field_name)!r}"
                    )
    else:
        drift.append(f"missing snapshot: {DEFAULT_OUTPUT}")
    if errors or drift:
        print(
            "portfolio doctor: FAIL "
            f"(validation_errors={len(errors)}, snapshot_drift={len(drift)})"
        )
        for error in errors:
            print(f"- validation: {error}")
        for item in drift:
            print(f"- drift: {item}")
        return 1
    snapshot = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    if snapshot["portfolio"].get("dirty"):
        release_blockers.append("ResearchWorkflow repository is dirty")
    for repo in snapshot["repositories"]:
        if not repo.get("dirty"):
            continue
        if repo["role"] == "primary_framework":
            release_blockers.append(f"{repo['id']} primary framework is dirty")
        elif repo["role"] == "integration_control":
            release_blockers.append(f"{repo['id']} integration repository is dirty")
        else:
            reference_warnings.append(
                f"{repo['id']} reference dirty state is preserved"
            )
    print(
        "portfolio doctor: PASS "
        f"(release_blockers={len(release_blockers)}, "
        f"reference_warnings={len(reference_warnings)})"
    )
    print(
        f"- portfolio: {snapshot['portfolio'].get('commit') or 'uncommitted'} "
        f"dirty={snapshot['portfolio'].get('dirty')}"
    )
    for repo in snapshot["repositories"]:
        commit = repo["commit"][:12] if repo.get("commit") else "not-git"
        print(
            f"- {repo['id']}: role={repo['role']} {commit} "
            f"dirty={repo['dirty']}"
        )
    for blocker in release_blockers:
        print(f"- release-blocker: {blocker}")
    for warning in reference_warnings:
        print(f"- reference-warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
