# Third-party browser assets

## KaTeX 0.17.0

- Upstream: https://github.com/KaTeX/KaTeX
- License: MIT; full text in `katex/LICENSE`.
- Source: `npm pack katex@0.17.0`, fetched on 2026-08-11.
- Included runtime subset: `katex.min.js`, `katex.min.css`, auto-render
  extension, and the referenced WOFF2 fonts.

The Hub copies this pinned runtime subset into the generated
`review_outputs/_research_hub/vendor/katex/` tree, so generated pages work
offline through `file://` and make no CDN request.
