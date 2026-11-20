# U–Pb, derived

Static documentation for the supported 535 reduction model. Open `index.html`
directly or serve this directory with Python's HTTP server. No npm installation,
build, network connection, analytics, or external fonts are required.

- `chapters.js`: derivations, complete partial derivative tables, paper comparisons.
- `app.js`: rendering, chapter navigation, covariance illustration, printing.
- `source-map.js`: generated source excerpts with revision-pinned GitHub links.
- `vendor/katex`: KaTeX 0.16.11, including its MIT license and local fonts.

From the repository root, refresh source excerpts with
`python3 tools/build_derivation_sources.py` and verify the analytical rows with
`python3 tools/verify_derivation.py`. All source changes should be committed before
regenerating links for a published site so that the linked revision exists on
GitHub. The generator records the current HEAD, while snippets use the local
files. Review the mathematical prose when the model changes; source regeneration
does not rewrite the derivation.

For GitHub Pages, publish the branch's `/docs` folder. `.nojekyll` permits direct
static serving. All asset paths are relative, so a repository subpath works.

The reference PDF is deliberately not copied into this site. The paper's DOI,
equation numbers, verified algebraic corrections, and model differences are
recorded in the walkthrough. The ellipse is an illustrative unit Mahalanobis
contour, not a grain covariance result or a 68% joint confidence contour.
