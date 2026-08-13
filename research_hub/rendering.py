"""Static Markdown rendering for the file-first research review Hub."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import HubConfig, atomic_write_text


_MARKDOWN_LINK_RE = re.compile(r"(!?\[[^\]]*\]\()([^\s)]+)([^)]*\))")
_VENDOR_ROOT = Path(__file__).parent / "vendor"


def render_document_pages(config: HubConfig, catalog: dict[str, Any]) -> None:
    """Render catalogued Markdown documents into safe local HTML previews.

    The generated pages live under Hub-owned state.  Source Markdown remains
    untouched; canonical records also retain their source text in the catalog
    so Chromium's File System Access API can write a reviewed version back only
    after the user explicitly chooses the workspace directory.

    Args:
        config: Resolved Hub configuration.
        catalog: Mutable catalog returned by the scanner.
    """

    config.ensure_state_root()
    _sync_vendor_assets(config)
    output_root = config.state_root / "rendered_documents"
    output_root.mkdir(exist_ok=True)
    for document in catalog.get("documents", []):
        path = Path(str(document["path"]))
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            document["render_error"] = "unable_to_read_utf8_markdown"
            continue
        document["rendered_href"] = _relative_to_artifact_root(
            config, output_root / f"{document['id']}.html"
        )
        if document.get("writable"):
            document["static_content"] = source
        rendered = _render_markdown(source, path.parent)
        atomic_write_text(
            output_root / f"{document['id']}.html",
            _page(
                str(document.get("title") or path.stem),
                rendered,
                str(path),
                state_root=config.state_root,
                state_route_prefix=config.state_root.relative_to(config.artifact_root).as_posix(),
            ),
        )


def _relative_to_artifact_root(config: HubConfig, path: Path) -> str:
    """Return a URL-safe link from the static homepage to one Hub state file."""

    return quote(path.relative_to(config.artifact_root).as_posix(), safe="/")


def _sync_vendor_assets(config: HubConfig) -> None:
    """Copy pinned browser-only dependencies into generated Hub state.

    Generated pages must work from ``file://`` without a CDN or a running
    server.  KaTeX is therefore vendored in the control repository and copied
    to the same Hub-owned state tree as the rendered HTML.  Only package
    distribution files needed at runtime are present under ``vendor/katex``.
    """

    source = _VENDOR_ROOT / "katex"
    target = config.state_root / "vendor" / "katex"
    if not source.is_dir():
        raise RuntimeError(f"missing vendored KaTeX assets: {source}")
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or destination.read_bytes() != path.read_bytes():
            shutil.copy2(path, destination)


def _render_markdown(source: str, source_parent: Path) -> str:
    """Convert Markdown after making local links independent of preview location."""

    try:
        import markdown
    except ImportError:
        return "<pre>" + html.escape(source) + "</pre>"
    rewritten = _MARKDOWN_LINK_RE.sub(
        lambda match: match.group(1) + _local_target(match.group(2), source_parent) + match.group(3),
        source,
    )
    return markdown.markdown(
        rewritten,
        extensions=["extra", "sane_lists", "toc"],
        output_format="html5",
    )


def _local_target(target: str, source_parent: Path) -> str:
    """Convert a local Markdown link target to a portable file URI.

    Absolute web URLs, anchors, mail links, and already-URI targets retain
    their original meaning.  The leading ``<``/``>`` syntax is accepted by
    CommonMark and preserved around the rewritten file URI.
    """

    prefix = "<" if target.startswith("<") else ""
    suffix = ">" if target.endswith(">") else ""
    value = target[1:-1] if prefix else target
    lowered = value.casefold()
    if not value or value.startswith("#") or "://" in value or lowered.startswith(("mailto:", "data:")):
        return target
    path_part, marker, fragment = value.partition("#")
    candidate = Path(path_part)
    resolved = candidate if candidate.is_absolute() else source_parent / candidate
    uri = resolved.resolve().as_uri()
    if marker:
        uri += "#" + quote(fragment, safe="/:?&=+-._~")
    return prefix + uri + suffix


def _page(
    title: str,
    body: str,
    source_path: str,
    *,
    state_root: Path | None = None,
    state_route_prefix: str = "",
) -> str:
    """Wrap rendered Markdown in a readable no-network local HTML document."""

    safe_title = html.escape(title)
    safe_path = html.escape(source_path)
    state_uri = state_root.resolve().as_uri().rstrip("/") + "/" if state_root else ""
    state_uri_json = json.dumps(state_uri, ensure_ascii=False)
    state_route_json = json.dumps(state_route_prefix.strip("/"), ensure_ascii=False)
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{safe_title}</title><link rel=\"stylesheet\" href=\"../vendor/katex/katex.min.css\"><style>
:root{{--bg:#f4f7fb;--card:#fff;--ink:#172033;--muted:#60708a;--line:#d5deeb;--link:#275dad}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif}}main{{max-width:1100px;margin:0 auto;padding:28px}}article{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:28px;box-shadow:0 3px 18px #21345a0b}}h1,h2,h3,h4{{line-height:1.25;margin:1.35em 0 .55em}}h1{{margin-top:0}}a{{color:var(--link)}}img,video{{max-width:100%;height:auto;border:1px solid var(--line);border-radius:7px}}table{{width:100%;border-collapse:collapse;overflow:auto;display:block}}th,td{{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}}th{{background:#f6f9fd}}pre{{overflow:auto;background:#101820;color:#eaf1f9;padding:14px;border-radius:8px}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.source{{color:var(--muted);font-size:12px;overflow-wrap:anywhere}}
</style></head><body><main><p class=\"source\">源文件：{safe_path}</p><article>{body}</article></main><script defer src=\"../vendor/katex/katex.min.js\"></script><script defer src=\"../vendor/katex/contrib/auto-render.min.js\"></script><script>window.addEventListener("DOMContentLoaded",function(){{if(typeof renderMathInElement==="function"){{renderMathInElement(document.body,{{delimiters:[{{left:"$$",right:"$$",display:true}},{{left:"\\\\[",right:"\\\\]",display:true}},{{left:"$",right:"$",display:false}},{{left:"\\\\(",right:"\\\\)",display:false}}],throwOnError:false}})}}const stateRoot={state_uri_json},stateRoute={state_route_json};if(location.protocol!=="file:"&&stateRoot){{const prefix=location.pathname.startsWith("/research/")||location.pathname==="/research"?"/research":"";document.querySelectorAll("img[src],video[src],audio[src],iframe[src],a[href]").forEach(function(node){{["src","href"].forEach(function(attribute){{const value=node.getAttribute(attribute);if(value&&value.startsWith(stateRoot))node.setAttribute(attribute,prefix+"/api/hub-state/"+(stateRoute?stateRoute+"/":"")+value.slice(stateRoot.length));}});}});}}}});</script></body></html>
"""
