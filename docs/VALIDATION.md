# Validation / 验证记录

The standalone edition has 17 automated tests in scripts/test_local.py covering
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
Browser screenshot/click acceptance at 1980x1280 and 2560x1440 is pending. The
Mac instructions require independent runtime verification. CI results, when
available, are visible in GitHub Actions and do not imply scientific validation.

Run tests after installing backend/requirements-dev.txt:

Windows: backend/.venv/Scripts/python.exe scripts/test_local.py
macOS: backend/.venv/bin/python scripts/test_local.py
Frontend: python start.py build

The workflow executes the tests and frontend build on Windows and macOS with
Python 3.11 and Node 22. This first publication is a source preview, not a
medical product or completed license audit.
