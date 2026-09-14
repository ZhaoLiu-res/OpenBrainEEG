# Validation / 验证记录

The standalone edition has 21 automated tests in scripts/test_local.py covering
local access guards, settings persistence, upload limits, report previews and
path boundaries, dataset mapping, API key preservation/redaction, locale fallback,
Ollama/Chat Completions/Anthropic protocols, model discovery and conversation
consent/history/retry/locking. AI protocol tests use local HTTP fixtures and do
not need external API keys.

The development environment also completed a real EDF cleaning/export pipeline,
report downloads/previews and a real DeepSeek multi-turn connection test. No
credentials, user reports or conversation histories are included in this repo.

Known limits: local Ollama/LM Studio inference and all other live cloud accounts
have not been individually verified; PDF depends on optional system libraries.
Windows Edge browser screenshots and interactions were verified for the guide and copyright pages at 1980x1280, 2560x1440 and 390x844 in both languages.
Mac desktop interactions require independent runtime verification. CI results, when
available, are visible in GitHub Actions and do not imply scientific validation.

Run tests after installing backend/requirements-dev.txt:

Windows: backend/.venv/Scripts/python.exe scripts/test_local.py
macOS: backend/.venv/bin/python scripts/test_local.py
Frontend: python start.py build

The workflow executes the tests and frontend build on Windows and macOS with
Python 3.11 and Node 22. This first publication is a source preview, not a
medical product or completed license audit.

## Documentation and noncommercial license — 2026-09-14

Added User guide and Copyright navigation, a searchable bilingual illustrated guide, offline HTML/Markdown ZIP, a personal noncommercial license and separate third-party notices. Fourteen screenshots come from a real isolated workspace using S001R01.edf; no private jobs, keys or real AI exchanges were used. The sample ran the default ASR/ICA pipeline and generated HTML and data exports. Settings screenshots show an unsaved preset.

Verified: 17 backend tests, frontend production build, real report rendering, 12 guide/copyright language and viewport combinations, search and section focus, screenshot loading, five download endpoints, all offline HTML local links and ZIP integrity (20 files). No browser JavaScript errors or HTTP failures in the final acceptance run.

Screenshot generation used a separate local port and an isolated runtime directory; the extra test origin was allowed in memory only, without changing production access guards. No scientific code changed. Company identity has since been supplied; commercial contact remains to be supplied. A tailored license draft is not a completed professional legal/provenance review.

To regenerate exports after editing guide.json, license text or images, run `python scripts/export_user_guide.py`, then `python start.py build`.

## PDF and research exports — 2026-09-14

Added post-completion, queued PDF and figure exports with persisted state, deduplication, retry, interruption recovery, confined input/output paths and atomic publication. Rendering uses the existing scientific plotting factory; no cleaning algorithm was changed. PDF uses ReportLab, with CJK text and English figure labels. Research ZIP has three styles and PNG/SVG/PDF formats, plus warnings/manifest and saved metadata.

The public S001R01 history fixture exported a 12-page Chinese PDF and a ZIP with 63 images (7 figures × 3 styles × 3 formats) plus 6 metadata files. Saved parameters, metrics, steps and job count remained unchanged. Browser downloads, zh/en layouts at 1980x1280, 2560x1440 and 390x844 passed. Backend suite now includes export guards/deduplication and failure/path-boundary cases.

PDF verification: all 12 pages rendered with PDFium and visually inspected (Poppler was downloaded but its executable failed to start on this Windows environment). Chinese headings, report tables, seven figure pages and parameter/log appendices were readable with no clipped content. Actual PNG/SVG/PDF bundle downloads and ZIP integrity passed.

The new-job automatic PDF path also completed on a real English-language EDF sample with ASR/ICA disabled for this additional check: HTML, PDF and data files were registered with no warnings. The current local service was restarted with the export API after confirming there were no active cleaning jobs. Backend suite: 21 tests passed.
