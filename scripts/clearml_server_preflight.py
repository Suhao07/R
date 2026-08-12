#!/usr/bin/env python3
"""Read-only preflight for a local ClearML Server/SSH-tunnel setup.

The command never starts containers, pulls images, installs packages, reads
ClearML credentials, or uploads artifacts. It only checks declared local
configuration and endpoint reachability.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from validate_clearml_project_profile import load_profile, validate_profile


def parse_endpoint(spec: str) -> tuple[str, str]:
    """Parse ``name=url`` without accepting an unnamed endpoint."""

    name, separator, url = spec.partition('=')
    if not separator or not name or not url:
        raise ValueError(f'Invalid endpoint {spec!r}; expected name=url')
    if not url.startswith(('http://', 'https://')):
        raise ValueError(f'Endpoint must use http:// or https://: {url}')
    return name, url


def check_endpoint(url: str, *, timeout: float) -> dict[str, Any]:
    """Perform a safe GET and report reachability without returning content."""

    request = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                'url': url,
                'reachable': True,
                'status': int(response.status)
            }
    except urllib.error.HTTPError as exc:
        # 401/403/404 still prove that the HTTP service is reachable. The body
        # is deliberately not read because it may contain private data.
        return {
            'url': url,
            'reachable': True,
            'status': int(exc.code),
            'http_error': True,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {'url': url, 'reachable': False, 'error': type(exc).__name__}


def check_command(command: Sequence[str]) -> dict[str, Any]:
    """Run a bounded version/status command and retain no command output."""

    executable = shutil.which(command[0])
    if executable is None:
        return {
            'available': False,
            'command': list(command),
            'reason': 'not_found'
        }
    try:
        completed = subprocess.run(
            list(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            'available': False,
            'command': list(command),
            'reason': type(exc).__name__,
        }
    return {
        'available': completed.returncode == 0,
        'command': list(command),
        'returncode': completed.returncode,
    }


def check_local_config(path: Path | None) -> dict[str, Any]:
    """Report config presence only; never inspect its contents."""

    if path is None:
        return {'configured': False, 'path': None}
    resolved = path.expanduser().resolve(strict=False)
    return {
        'configured':
        resolved.is_file(),
        'path':
        str(resolved),
        'mode':
        oct(resolved.stat().st_mode & 0o777) if resolved.is_file() else None,
    }


def run_preflight(
    *,
    profile_path: Path | None = None,
    workspace_root: Path | None = None,
    allow_missing_profile_paths: bool = False,
    endpoints: Sequence[str] = (),
    clearml_config: Path | None = None,
    require_docker: bool = False,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Build a no-side-effect preflight report."""

    report: dict[str, Any] = {
        'schema_version': 'clearml_server_preflight_v1',
        'docker': check_command(('docker', 'ps', '--format', '{{.Names}}')),
        'docker_compose': check_command(('docker', 'compose', 'version')),
        'clearml_config': check_local_config(clearml_config),
        'endpoints': {},
        'profile': None,
        'ready': True,
        'errors': [],
    }
    if require_docker and not report['docker']['available']:
        report['ready'] = False
        report['errors'].append(
            'Docker is required but docker ps is unavailable')

    if profile_path is not None:
        resolved_profile = profile_path.expanduser().resolve()
        try:
            profile = load_profile(resolved_profile)
            errors = validate_profile(
                profile,
                resolved_profile,
                workspace_root=workspace_root,
                require_paths=not allow_missing_profile_paths,
            )
        except (OSError, ValueError) as exc:
            errors = [str(exc)]
        report['profile'] = {
            'path': str(resolved_profile),
            'valid': not errors,
            'errors': errors,
        }
        if errors:
            report['ready'] = False
            report['errors'].extend(f'profile: {error}' for error in errors)

    for spec in endpoints:
        try:
            name, url = parse_endpoint(spec)
            result = check_endpoint(url, timeout=timeout)
        except ValueError as exc:
            name = spec.split('=', 1)[0] or spec
            result = {'url': None, 'reachable': False, 'error': str(exc)}
        report['endpoints'][name] = result
        if not result.get('reachable', False):
            report['ready'] = False
            report['errors'].append(f'endpoint {name} is unreachable')

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--allow-missing-profile-paths', action='store_true')
    parser.add_argument('--endpoint',
                        action='append',
                        default=[],
                        help='name=http(s)://host:port')
    parser.add_argument('--clearml-config', type=Path)
    parser.add_argument('--require-docker', action='store_true')
    parser.add_argument('--timeout', type=float, default=2.0)
    parser.add_argument('--json', action='store_true', help='emit JSON only')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout <= 0:
        raise SystemExit('--timeout must be positive')
    report = run_preflight(
        profile_path=args.profile,
        workspace_root=args.workspace_root,
        allow_missing_profile_paths=args.allow_missing_profile_paths,
        endpoints=args.endpoint,
        clearml_config=args.clearml_config,
        require_docker=args.require_docker,
        timeout=args.timeout,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
