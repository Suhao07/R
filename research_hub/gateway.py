"""Loopback gateway combining ClearML Web and Research Hub on one port."""

from __future__ import annotations

import http.client
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from html import escape
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .config import HubConfig
from .server import make_server


HUB_PREFIX = "/research"
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
_TASK_PATH_RE = re.compile(r"/projects/[^/]+/(?:experiments|tasks)/([0-9a-fA-F]{32})(?:/|$)")
_WORKBENCH_SCRIPT = r'''<script data-srnav-workbench="1">
(function () {
  if (window.top !== window.self || window.__srnavWorkbenchLoaded) return;
  window.__srnavWorkbenchLoaded = true;
  var id = "srnav-workbench-link";
  function remove() { var node = document.getElementById(id); if (node) node.remove(); }
  function add(href, text) {
    var old = document.getElementById(id);
    if (old) { old.href = href; old.textContent = text; return; }
    var link = document.createElement("a");
    link.id = id; link.href = href; link.target = "_self"; link.textContent = text;
    link.style.cssText = "position:fixed;top:58px;right:24px;z-index:2147483647;display:block;padding:12px 18px;border-radius:8px;background:#d9480f;color:#fff;font:700 15px system-ui,sans-serif;text-decoration:none;box-shadow:0 3px 14px #17203355;border:2px solid #fff";
    document.body.appendChild(link);
  }
  function update() {
    var match = location.pathname.match(/\/projects\/[^/]+\/(?:experiments|tasks)\/([0-9a-fA-F]{32})(?:\/|$)/);
    if (!match) { remove(); return; }
    fetch("/research/api/task-links/" + match[1]).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (data) {
      if (data && data.ok && data.href) add(data.href, "打开本实验校阅工作台"); else remove();
    }).catch(remove);
  }
  window.addEventListener("popstate", update);
  new MutationObserver(update).observe(document.documentElement, {childList:true, subtree:true});
  setTimeout(update, 300); setTimeout(update, 1500);
}());
</script>'''


def _task_id_from_path(path: str) -> str | None:
    """Extract a ClearML Task ID from either supported detail URL shape."""

    match = _TASK_PATH_RE.search(path.split("?", 1)[0])
    return match.group(1) if match else None


def _fallback_workbench_link(task_id: str) -> bytes:
    """Return a visible non-JavaScript link for the injected Task page UI."""

    return (
        '<a id="srnav-workbench-link" href="/research/task/'
        + task_id
        + '" target="_self"'
        ' style="position:fixed;top:58px;right:24px;z-index:2147483647;display:block;'
        'padding:12px 18px;border-radius:8px;background:#d9480f;color:#fff;'
        'font:700 15px system-ui,sans-serif;text-decoration:none;box-shadow:0 3px 14px #17203355;border:2px solid #fff">'
        '打开本实验校阅工作台</a>'
    ).encode("utf-8")


def _render_task_switcher(task_id: str, native_href: str, review_href: str) -> bytes:
    """Render one same-origin shell with explicit ClearML/review tabs."""

    safe_task = escape(task_id, quote=True)
    safe_native = escape(native_href, quote=True)
    safe_review = escape(review_href, quote=True)
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SR-Nav 实验校阅工作台</title>
<style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;font:14px system-ui,-apple-system,"Segoe UI",sans-serif;background:#eef3f9;color:#172033}}
.bar{{height:54px;display:flex;align-items:center;gap:10px;padding:0 16px;box-sizing:border-box;background:#172b4d;color:#fff;box-shadow:0 2px 8px #17203355;position:relative;z-index:2}}
.brand{{font-weight:700;margin-right:10px;white-space:nowrap}}.task{{font:12px ui-monospace,monospace;opacity:.8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}}
button,.open{{font:600 14px system-ui,sans-serif;border:1px solid #b9c8df;border-radius:7px;padding:8px 13px;background:#fff;color:#17345f;cursor:pointer;text-decoration:none;white-space:nowrap}}
button.active{{background:#2f80ed;border-color:#2f80ed;color:#fff}}.open{{background:#f3a712;border-color:#f3a712;color:#172033}}
.view{{width:100%;height:calc(100% - 54px);border:0;background:#fff;display:none}}.view.active{{display:block}}
</style></head><body>
<nav class="bar"><span class="brand">SR-Nav 实验管理</span><span class="task">Task {safe_task}</span>
<button id="nativeButton" class="active" type="button">ClearML 原生任务</button>
<button id="reviewButton" type="button">实验校阅工作台</button>
<a class="open" href="{safe_review}" target="_blank" rel="noopener">新窗口打开校阅</a></nav>
<iframe id="nativeView" class="view active" src="{safe_native}" title="ClearML 原生任务"></iframe>
<iframe id="reviewView" class="view" src="{safe_review}" title="实验校阅工作台"></iframe>
<script>(function(){{var n=document.getElementById('nativeView'),r=document.getElementById('reviewView'),nb=document.getElementById('nativeButton'),rb=document.getElementById('reviewButton');function show(which){{var native=which==='native';n.classList.toggle('active',native);r.classList.toggle('active',!native);nb.classList.toggle('active',native);rb.classList.toggle('active',!native)}}nb.onclick=function(){{show('native')}};rb.onclick=function(){{show('review')}}}})();</script>
</body></html>'''
    return html.encode("utf-8")


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """Proxy `/research` to Hub and all other paths to ClearML Web.

    The gateway keeps the Hub session token server-side.  Therefore the
    browser uses one tokenless 8080 URL while write requests still carry the
    Hub token on the private upstream hop.
    """

    hub_host = "127.0.0.1"
    hub_port = 8765
    hub_token = ""
    clearml_host = "127.0.0.1"
    clearml_port = 8082

    def do_GET(self) -> None:  # noqa: N802
        self._proxy()

    def do_HEAD(self) -> None:  # noqa: N802
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def _proxy(self) -> None:
        if self._serve_task_switcher():
            return
        target_host, target_port = self._target()
        connection = http.client.HTTPConnection(target_host, target_port, timeout=120)
        body = b""
        raw_length = self.headers.get("Content-Length")
        if raw_length:
            try:
                body = self.rfile.read(max(0, min(int(raw_length), 64 * 1024 * 1024)))
            except ValueError:
                self.send_error(400, "invalid Content-Length")
                return
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP and key.lower() != "host"
        }
        headers["Host"] = f"{target_host}:{target_port}"
        headers["X-Forwarded-Host"] = self.headers.get("Host", "127.0.0.1:8080")
        headers["X-Forwarded-Proto"] = "http"
        if target_port == self.hub_port and self.hub_token:
            # The gateway is loopback-only, so it can keep the Hub session token
            # server-side and present a tokenless editing URL to the user.
            headers["X-Research-Hub-Token"] = self.hub_token
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_headers = response.getheaders()
            content_type = response.getheader("Content-Type", "")
            should_inject = (
                target_port == self.clearml_port
                and self.command != "HEAD"
                and response.status == 200
                and content_type.lower().startswith("text/html")
                and not response.getheader("Content-Encoding")
                and not self._native_requested()
            )
            body = response.read() if should_inject else None
            if body is not None:
                marker = b"</body>"
                if marker in body.lower():
                    lower = body.lower()
                    index = lower.rfind(marker)
                    task_id = _task_id_from_path(self.path)
                    injection = _WORKBENCH_SCRIPT.encode("utf-8")
                    if task_id:
                        injection = _fallback_workbench_link(task_id) + injection
                    body = body[:index] + injection + body[index:]
            self.send_response(response.status, response.reason)
            for key, value in response_headers:
                lowered = key.lower()
                if lowered in _HOP_BY_HOP or (body is not None and lowered in {"content-length", "etag", "last-modified"}):
                    continue
                self.send_header(key, value)
            if body is not None:
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body is not None:
                self.wfile.write(body)
            elif self.command != "HEAD":
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (OSError, http.client.HTTPException) as exc:
            self.send_error(502, f"upstream unavailable: {type(exc).__name__}")
        finally:
            connection.close()

    def _native_requested(self) -> bool:
        """Return whether the native ClearML iframe escape hatch is active."""

        return parse_qs(urlparse(self.path).query).get("native", [""])[0] in {"1", "true", "yes"}

    def _serve_task_switcher(self) -> bool:
        """Serve a visible same-URL switcher for a mapped Task detail route."""

        if self.command not in {"GET", "HEAD"}:
            return False
        task_id = _task_id_from_path(self.path)
        if not task_id:
            return False
        if self._native_requested():
            return False
        location = self._review_location(task_id)
        if not location:
            return False
        query = parse_qs(urlparse(self.path).query)
        native_query = [(key, value) for key, values in query.items() for value in values if key != "native"]
        native_query.append(("native", "1"))
        parsed = urlparse(self.path)
        native_location = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(native_query), parsed.fragment))
        body = _render_task_switcher(task_id, native_location, location)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return True

    def _review_location(self, task_id: str) -> str | None:
        """Resolve one Task ID through the Hub without exposing its token."""

        connection = http.client.HTTPConnection(self.hub_host, self.hub_port, timeout=10)
        try:
            headers = {"Host": f"{self.hub_host}:{self.hub_port}"}
            if self.hub_token:
                headers["X-Research-Hub-Token"] = self.hub_token
            connection.request("GET", f"{HUB_PREFIX}/api/task-links/{task_id}", headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                response.read()
                return None
            value = json.loads(response.read().decode("utf-8"))
            href = value.get("href") if isinstance(value, dict) and value.get("ok") else None
            return str(href) if href else None
        except (OSError, http.client.HTTPException, UnicodeDecodeError, json.JSONDecodeError):
            return None
        finally:
            connection.close()

    def _target(self) -> tuple[str, int]:
        """Select the upstream based on the request prefix."""

        return (self.hub_host, self.hub_port) if self.path.split("?", 1)[0].rstrip("/") in {HUB_PREFIX} or self.path.startswith(HUB_PREFIX + "/") else (self.clearml_host, self.clearml_port)

    def log_message(self, format: str, *args: Any) -> None:
        safe = format.replace("?token=", "?token=redacted")
        super().log_message(safe, *args)


def serve_gateway(
    config: HubConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    hub_port: int = 8765,
    clearml_host: str = "127.0.0.1",
    clearml_port: int = 8082,
) -> None:
    """Start Hub and a loopback gateway until interrupted."""

    hub = make_server(config, "127.0.0.1", hub_port, base_path=HUB_PREFIX)
    hub_thread = Thread(target=hub.serve_forever, name="research-hub", daemon=True)
    hub_thread.start()
    bound_hub_port = int(hub.server_address[1])
    hub_token = hub.RequestHandlerClass.context.token
    gateway = make_gateway_server(
        host=host,
        port=port,
        hub_port=bound_hub_port,
        hub_token=hub_token,
        clearml_host=clearml_host,
        clearml_port=clearml_port,
    )
    print(f"Unified Research UI: http://{host}:{gateway.server_address[1]}/")
    print(f"Research Hub (可编辑入口): http://{host}:{gateway.server_address[1]}{HUB_PREFIX}/")
    try:
        gateway.serve_forever()
    except KeyboardInterrupt:
        print("\nUnified Research UI stopped.")
    finally:
        gateway.server_close()
        hub.shutdown()
        hub.server_close()
        hub_thread.join(timeout=3)


def make_gateway_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    hub_port: int = 8765,
    hub_token: str = "",
    clearml_host: str = "127.0.0.1",
    clearml_port: int = 8082,
) -> ThreadingHTTPServer:
    """Create a gateway server without starting its request loop."""

    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("unified gateway may bind only loopback")
    handler = type(
        "BoundGatewayRequestHandler",
        (GatewayRequestHandler,),
        {
            "hub_port": hub_port,
            "hub_token": hub_token,
            "clearml_host": clearml_host,
            "clearml_port": clearml_port,
        },
    )
    return ThreadingHTTPServer((host, port), handler)
