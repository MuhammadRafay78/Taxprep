# Taxprep on Cloudflare Workers

A full port of the Python/FastAPI app in `../backend` and `../frontend` to a
single Cloudflare Worker — same behavior, same UI, no separate server to run.

## Why a port, not just a deploy

Cloudflare Workers doesn't run arbitrary Python with native extensions. The
Python backend's PDF parsing (`pdfplumber`) depends on `pdfminer.six`, which
depends on `cryptography` — a Rust-backed native extension that can't execute
in the Workers Python runtime (Pyodide, WASM-sandboxed, curated pure-Python
packages only). So this isn't the same code redeployed; it's the same logic
rewritten in TypeScript:

| Python (`../backend`) | Worker (`src/`) | Notes |
|---|---|---|
| `parser.py` | `parser.ts` | Same line definitions, phrase matching, and per-schedule-page number fallback. |
| `explain.py` | `explain.ts` | Same flags and money-flow logic. |
| `tax_data.py` | `taxData.ts` | Same reference brackets/deductions/EIC limits. |
| `pdfplumber` (`layout=True` text) | `pdfText.ts` + [`unpdf`](https://github.com/unjs/unpdf) | `unpdf` ships PDF.js built specifically for edge runtimes (worker thread inlined, no separate `pdf.worker.js` to load). It hands back individual positioned text runs (`extractTextItems`) rather than pre-assembled lines, so `pdfText.ts` groups runs sharing a y-coordinate into rows and sorts them left-to-right — reconstructing the same "label ... amount" row shape `parser.ts` expects. |
| FastAPI routes + `StaticFiles` | `index.ts` fetch handler + Workers Assets | `/api/extract` and `/api/analyze` are handled in the Worker; everything else falls through to the static `public/` directory. |

`public/index.html` is **not** a byte-for-byte copy of `../frontend/index.html`
— it's copied over, then several spots are deliberately changed to reflect
this deployment having no OCR (see "No OCR" below):
1. **No PDF upload at all.** The Python frontend's `<div class="dropzone">`,
   its file `<input>`, and the `<p id="status">` next to it are removed
   entirely — most real-world returns include at least one scanned page,
   and with no OCR fallback there's no benefit to offering upload here. In
   their place, `<div id="upload-panel">` keeps only an explainer paragraph
   and `<div id="sample-scenarios"></div>` (the two built-in sample-return
   buttons, which work entirely client-side and need no upload). The shared
   `<script>` guards every `dropzone`/`fileInput` reference with
   `if (dropzone && fileInput) { ... }` specifically so it still runs fine
   with those elements absent — don't remove that guard when porting
   changes, and don't reintroduce the dropzone markup from a plain copy.
2. The header subtitle (`Upload a Form 1040 PDF...` becomes `See a sample
   tax return...`).

When porting a UI change from `../frontend/index.html`, copy it over first,
then re-apply all of the above — they should never make it back verbatim
from a plain copy.

Verified to produce byte-identical extraction results against the same test
PDFs used for the Python backend's test suite (see the parent repo's
`tests/test_parser.py` fixtures) via manual comparison; see the parent
README for the underlying design rationale (why no OCR, what the anomaly
checks do, etc.) — all of that carries over unchanged.

## Running it locally

```bash
cd worker
npm install
npm run dev
```

This starts `wrangler dev`, which runs the real Workers runtime locally
(no Cloudflare account needed for local dev). Open the printed
`http://localhost:8787/`.

## Deploying

```bash
cd worker
npx wrangler login   # one-time OAuth to your Cloudflare account
npm run deploy
```

`wrangler deploy` reads `wrangler.toml` (Worker name `taxprep`, assets served
from `./public`) and publishes to your account — this step needs your own
Cloudflare credentials, which this repo/session doesn't have.

## What's not ported (yet)

- No automated test suite in TypeScript — correctness here was verified
  manually (API calls + a real headless-browser run) against the same
  fixtures the Python `pytest` suite uses, but there's no `vitest` +
  `@cloudflare/vitest-pool-workers` setup checked in. Worth adding if this
  becomes the primary deployment target.
