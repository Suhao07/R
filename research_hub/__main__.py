"""Command-line entry points for the local research review hub."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import build_catalog, load_catalog, scan_and_write, write_catalog
from .config import HubConfig, load_config
from .frontend import render_index
from .server import make_server


def main(argv: list[str] | None = None) -> int:
    """Run the Hub CLI.

    Args:
        argv: Optional command-line arguments, primarily for focused tests.

    Returns:
        Zero for a completed command and non-zero for an actionable failure.
    """

    parser = argparse.ArgumentParser(description="Local file-first research management and review hub")
    parser.add_argument("--portfolio-root", type=Path, help="alternate ResearchWorkflow root for isolated tests")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scan", help="rebuild derived JSON and SQLite catalog")
    subparsers.add_parser("export", help="rebuild catalog and static review_outputs/index.html")
    serve = subparsers.add_parser("serve", help="start token-protected loopback UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--base-path", default="")
    gateway = subparsers.add_parser("gateway", help="start one loopback port for ClearML Web and Research Hub")
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8080)
    gateway.add_argument("--hub-port", type=int, default=8765)
    gateway.add_argument("--clearml-host", default="127.0.0.1")
    gateway.add_argument("--clearml-port", type=int, default=8082)
    subparsers.add_parser("doctor", help="check Hub configuration and generated catalog state")
    args = parser.parse_args(argv)
    config = load_config(args.portfolio_root)
    if args.command == "scan":
        catalog = scan_and_write(config)
        print(json.dumps({"catalog": str(config.catalog_json), "summary": catalog["summary"]}, ensure_ascii=False))
        return 0
    if args.command == "export":
        catalog = scan_and_write(config)
        _write_static(config, catalog)
        print(f"WROTE {config.static_index}")
        return 0
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "serve":
        catalog = scan_and_write(config)
        _write_static(config, catalog)
        server = make_server(config, args.host, args.port, base_path=args.base_path)
        token = server.RequestHandlerClass.context.token
        host, bound_port = server.server_address[:2]
        route = args.base_path.rstrip("/")
        print(f"Research Hub: http://{host}:{bound_port}{route or ''}/?token={token}")
        print("Static homepage: " + str(config.static_index))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nResearch Hub stopped.")
        finally:
            server.server_close()
        return 0
    if args.command == "gateway":
        from .gateway import serve_gateway

        catalog = scan_and_write(config)
        _write_static(config, catalog)
        serve_gateway(
            config,
            host=args.host,
            port=args.port,
            hub_port=args.hub_port,
            clearml_host=args.clearml_host,
            clearml_port=args.clearml_port,
        )
        return 0
    raise AssertionError(f"unsupported command {args.command}")


def _write_static(config: HubConfig, catalog: dict[str, object]) -> None:
    """Render local document previews then write the no-server homepage."""

    from .config import atomic_write_text
    from .rendering import render_document_pages

    render_document_pages(config, catalog)
    write_catalog(config, catalog)
    atomic_write_text(config.static_index, render_index(catalog, live=False))


def _doctor(config: HubConfig) -> int:
    """Check Hub-owned state and source roots without modifying canonical evidence."""

    errors: list[str] = []
    for source in config.sources:
        if not source.path.exists():
            errors.append(f"missing source root: {source.id}: {source.path}")
    if not config.catalog_json.is_file():
        errors.append("catalog.json is missing; run `python -m research_hub scan`")
    else:
        try:
            catalog = load_catalog(config)
            if catalog.get("schema_version") != "research_review_hub_catalog_v1":
                errors.append("catalog.json has an unexpected schema version")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"catalog.json unreadable: {type(exc).__name__}")
    if not config.static_index.is_file():
        errors.append("static index.html is missing; run `python -m research_hub export`")
    if errors:
        print("research hub doctor: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("research hub doctor: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
