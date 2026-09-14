"""Single-user desktop server. No users, payments, quota or database imports."""
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from uuid import uuid4

# Configure paths before importing plotting and scientific packages.
ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("BRAINIFLY_DATA_DIR", str(ROOT / ".local-data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(DATA / "matplotlib"))
os.environ.setdefault("MPLBACKEND", "Agg")
if os.name != "nt":
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib:/usr/local/lib")

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from config import PipelineConfig
from core.loader import EEGLoader
from core.pipeline import CleaningPipeline
from local_ai import AISettings, AIStore
from local_locale import LocaleResolver
from local_settings import SettingsStore, SystemSettings
from ai_catalog import PROVIDERS
from local_conversations import ConversationStore

SUPPORTED = {".edf", ".bdf", ".gdf", ".fif", ".txt", ".csv"}
MAX_BYTES = 512 * 1024 * 1024
REPORT_STYLE = """<style id="local-report-layout">
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;font-size:16px}
.container{width:100%;max-width:none;padding:28px clamp(18px,3vw,56px)}
.nav{position:sticky;top:0;right:auto;transform:none;display:flex;flex-wrap:wrap;gap:8px;border-radius:0}
.nav a{font-size:14px}.section h2{font-size:23px}.note,.metric,.meta-item,table{font-size:16px}
.meta-item .label,.header .sub{font-size:14px}.section{overflow-x:auto}
@media(min-width:1600px){.container{padding:36px 64px}.header h1{font-size:36px}}
@media(max-width:700px){.header,.section{padding:20px}.banner{flex-wrap:wrap}.nav{position:static}}
</style>"""


def report_document(path):
    html = path.read_text(encoding="utf-8")
    html = html.replace("@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');", "")
    if 'id="local-report-layout"' not in html:
        html = html.replace("</head>", REPORT_STYLE + "</head>", 1)
    return html


SAMPLES = {
    "edf_baseline": ("physionet/S001R01.edf", "睁眼静息基线", "Eyes-open baseline"),
    "edf_imagery": ("physionet/S001R04.edf", "左右手运动想象", "Left/right hand motor imagery"),
    "gdf_training": ("bci_competition/A01T.gdf", "BCI Competition 训练样例", "BCI Competition training sample"),
}


def safe(value):
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    if hasattr(value, "item"):
        return safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime, Path)):
        return str(value)
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


class Jobs:
    def __init__(self, directory):
        self.settings = SettingsStore(directory)
        self.root = directory / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.items = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="brainifly")
        for path in self.root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                self.items[job["id"]] = job
                if job["status"] in {"queued", "running"}:
                    self.update(job["id"], status="failed", error="Processing was interrupted. Submit again.")
                for kind, state in job.get("exports", {}).items():
                    if state.get("status") in {"queued", "running"}:
                        job["exports"][kind] = {"status": "failed", "error": "Export was interrupted. Please retry."}
                        self.update(job["id"], exports=job["exports"])
            except (ValueError, KeyError):
                continue

    def update(self, job_id, **values):
        with self.lock:
            self.items[job_id].update(safe(values), updated_at=now())
            target = self.root / job_id / "job.json"
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(self.items[job_id], ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(target)

    def get(self, job_id):
        with self.lock:
            if job_id not in self.items:
                raise HTTPException(404, "Job not found")
            return json.loads(json.dumps(self.items[job_id]))

    def submit(self, path, filename, config):
        if path.stat().st_size > self.settings.read().max_upload_mb * 1024 * 1024:
            raise HTTPException(413, "File exceeds the upload limit in System settings")
        # Precheck uses the same loader, without cloud billing/runtime settings.
        try:
            raw = EEGLoader.load(path, preload=False, input_adapter=config.input_adapter)
            info = safe(asdict(EEGLoader.extract_metadata(raw, path)))
            raw.close()
        except Exception:
            raise HTTPException(422, "Cannot read this recording. Check the format and required data fields.") from None
        with self.lock:
            if sum(j["status"] in {"queued", "running"} for j in self.items.values()) >= self.settings.read().max_active_jobs:
                raise HTTPException(429, "Active task limit reached. Wait or change System settings.")
            job_id = uuid4().hex
            directory = self.root / job_id
            directory.mkdir()
            stored = directory / ("input" + Path(filename).suffix.lower())
            shutil.copyfile(path, stored)
            info.pop("filepath", None)
            info["filename"] = filename
            self.items[job_id] = {"id": job_id, "filename": filename, "created_at": now(), "status": "queued", "progress": 0,
                                  "step": "queued", "dataset": info, "config": config.model_dump(), "outputs": {}, "warnings": [], "error": None}
            self.update(job_id)
            self.pool.submit(self.run, job_id, stored, config)
            return self.get(job_id)

    def run(self, job_id, path, config):
        try:
            self.update(job_id, status="running", step="loading", progress=2)
            raw = EEGLoader.load(path, input_adapter=config.input_adapter)
            pipeline = CleaningPipeline.build_default(config)
            def progress(index, total, name, state, **kwargs):
                self.update(job_id, step=name, progress=max(3, int((index + (state != "running")) / max(total, 1) * 78)))
            pipeline.on_progress(progress)
            result = pipeline.run_and_export(raw, path, path.parent / "outputs", export_basename="cleaned")
            raw.close()
            result.dataset_info.filename = self.get(job_id)["filename"]
            warnings = [w for step in result.step_results for w in step.warnings]
            warnings.extend(f"{kind}: {error}" for kind, error in result.export_errors.items())
            outputs = {kind: str(p.relative_to(path.parent)) for kind, p in result.exported_files.items()}
            self.update(job_id, progress=82, step="report")
            if config.generate_report:
                from report.generator import ReportGenerator
                generator = ReportGenerator(result)
                if "html" in config.report_formats:
                    report = generator.generate_html(path.parent / "report.html")
                    outputs["html"] = report.name
                if "pdf" in config.report_formats:
                    try:
                        from local_exports import pdf_report
                        warnings.extend(pdf_report(result, path.parent / "report.pdf", reconstructed=False))
                        outputs["pdf"] = "report.pdf"
                    except Exception as exc:
                        warnings.append(f"PDF export failed; use the report-page retry button: {type(exc).__name__}: {exc}")
            import matplotlib.pyplot as plt
            if "html" in outputs:
                html_path = path.parent / outputs["html"]
                html_path.write_text(report_document(html_path), encoding="utf-8")
            plt.close("all")
            (path.parent / "parameters.json").write_text(config.model_dump_json(indent=2), encoding="utf-8")
            outputs["parameters"] = "parameters.json"
            self.update(job_id, status="completed", progress=100, step="done", outputs=outputs, warnings=warnings,
                        metrics=asdict(result.metrics), steps=[asdict(s) for s in result.step_results])
        except Exception as exc:
            self.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}", step="failed")

    def submit_export(self, job_id, kind):
        from local_exports import saved_file
        with self.lock:
            job = self.get(job_id)
            if job["status"] != "completed":
                raise HTTPException(409, "Finish cleaning before exporting the report or figures.")
            existing = job.get("outputs", {}).get(kind)
            if existing:
                try:
                    saved_file(self.root / job_id, existing)
                    return job
                except ValueError:
                    pass  # A removed export can be regenerated.
            states = job.get("exports", {})
            if states.get(kind, {}).get("status") in {"queued", "running"}:
                return job
            pending = sum(s.get("status") in {"queued", "running"} for j in self.items.values() for s in j.get("exports", {}).values())
            if pending >= 4:
                raise HTTPException(429, "Four exports are already active or queued. Wait before submitting another.")
            states[kind] = {"status": "queued", "step": "waiting", "error": None, "warnings": []}
            self.update(job_id, exports=states)
            # Use the cleaning executor: Matplotlib and large recordings must not run concurrently.
            self.pool.submit(self.run_export, job_id, kind)
            return self.get(job_id)

    def run_export(self, job_id, kind):
        from local_exports import restore_result, pdf_report, research_bundle
        result = None
        def state(**values):
            with self.lock:
                states = self.get(job_id).get("exports", {})
                states[kind] = {**states.get(kind, {}), **values}
                self.update(job_id, exports=states)
        try:
            state(status="running", step="loading", error=None)
            job = self.get(job_id)
            directory = self.root / job_id
            result = restore_result(directory, job)
            filename = "report.pdf" if kind == "pdf" else "research_figures.zip"
            with tempfile.TemporaryDirectory(prefix="export-", dir=directory) as temporary:
                target = Path(temporary) / filename
                export = pdf_report if kind == "pdf" else research_bundle
                warnings = export(result, target, lambda step: state(step=step))
                if not target.is_file() or not target.stat().st_size:
                    raise ValueError("Export did not create a valid output file.")
                target.replace(directory / filename)
            with self.lock:
                outputs = self.get(job_id).get("outputs", {})
                outputs[kind] = filename
                self.update(job_id, outputs=outputs)
                state(status="completed", step="done", warnings=warnings)
        except Exception as exc:
            state(status="failed", error=f"{type(exc).__name__}: {exc}", step="failed")
        finally:
            if result is not None:
                result.raw_before.close()
                result.raw_after.close()
            import matplotlib.pyplot as plt
            plt.close("all")


@asynccontextmanager
async def lifespan(app):
    app.state.jobs = Jobs(DATA)
    app.state.ai = AIStore(DATA)
    app.state.locale = LocaleResolver()
    app.state.settings = SettingsStore(DATA)
    app.state.conversations = ConversationStore(DATA)
    yield
    app.state.jobs.pool.shutdown(wait=True)


app = FastAPI(title="Brainifly Local", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
ORIGINS = ["http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5174", "http://localhost:5174"]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "X-Brainifly-Local"])


@app.middleware("http")
async def local_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        if request.headers.get("X-Brainifly-Local") != "1" or (request.headers.get("origin") and request.headers["origin"] not in ORIGINS):
            return JSONResponse({"detail": "Request must originate from Brainifly Local."}, status_code=403)
    return await call_next(request)


def parse_config(value):
    try:
        config = PipelineConfig.model_validate_json(value)
        if set(config.export_formats) - {"fif", "edf", "csv"} or set(config.report_formats) - {"html", "pdf"}:
            raise ValueError("Unsupported output format")
        if config.filter.l_freq < 0 or config.filter.h_freq <= config.filter.l_freq:
            raise ValueError("Invalid frequency range")
        if config.asr.cutoff <= 0:
            raise ValueError("ASR cutoff must be positive")
        if config.report_language not in {"zh", "en"}:
            raise ValueError("Unsupported report language")
        return config
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid processing configuration") from None


@app.get("/api/health")
def health():
    return {"status": "ok", "edition": "local", "login_required": False}


@app.get("/api/demos")
def demos():
    return [{"id": key, "filename": Path(rel).name, "name": zh, "name_en": en, "available": (ROOT / "backend/test_data" / rel).is_file()} for key, (rel, zh, en) in SAMPLES.items()]


@app.get("/api/locale")
def locale(request: Request):
    return request.app.state.locale.resolve()


@app.post("/api/demos/{sample_id}", status_code=202)
def demo(sample_id: str, request: Request, config: PipelineConfig):
    if sample_id not in SAMPLES:
        raise HTTPException(404, "Sample not found")
    config = parse_config(config.model_dump_json())
    path = ROOT / "backend/test_data" / SAMPLES[sample_id][0]
    if not path.is_file():
        raise HTTPException(404, "Sample file is missing. Download it using the sample guide.")
    return request.app.state.jobs.submit(path, path.name, config)


@app.post("/api/jobs", status_code=202)
def upload(request: Request, file: UploadFile = File(...), config_json: str = Form("{}")):
    config = parse_config(config_json)
    name = Path((file.filename or "recording").replace("\\", "/")).name
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(422, "Use EDF, BDF, GDF, FIF, OpenBCI TXT or BrainFlow CSV. Multi-file formats are not supported in this edition yet.")
    max_bytes = request.app.state.settings.read().max_upload_mb * 1024 * 1024
    temp = DATA / (uuid4().hex + Path(name).suffix.lower())
    try:
        size = 0
        with temp.open("wb") as stream:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, "File exceeds the upload limit in System settings.")
                stream.write(chunk)
        return request.app.state.jobs.submit(temp, name, config)
    finally:
        temp.unlink(missing_ok=True)
        file.file.close()


@app.get("/api/jobs")
def list_jobs(request: Request):
    jobs = request.app.state.jobs
    with jobs.lock:
        return sorted((jobs.get(key) for key in jobs.items), key=lambda j: j.get("created_at", ""), reverse=True)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    return request.app.state.jobs.get(job_id)


@app.post("/api/jobs/{job_id}/exports/{kind}")
def create_export(job_id: str, kind: str, request: Request):
    if kind not in {"pdf", "research_figures"}:
        raise HTTPException(422, "Supported exports: pdf, research_figures")
    return request.app.state.jobs.submit_export(job_id, kind)


def output_path(job_id: str, kind: str, request: Request):
    jobs = request.app.state.jobs
    job = jobs.get(job_id)
    rel = job.get("outputs", {}).get(kind)
    if not rel:
        raise HTTPException(404, "Output not available")
    directory = jobs.root / job_id
    path = (directory / rel).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise HTTPException(404, "Output not found")
    return path


@app.get("/api/jobs/{job_id}/files/{kind}")
def download(job_id: str, kind: str, request: Request):
    path = output_path(job_id, kind, request)
    return FileResponse(path, filename=path.name)


@app.get("/api/jobs/{job_id}/report")
def preview_report(job_id: str, request: Request):
    path = output_path(job_id, "html", request)
    return HTMLResponse(report_document(path), headers={
        "Content-Security-Policy": "sandbox allow-scripts allow-downloads; object-src 'none'; connect-src 'none'",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-cache",
    })


@app.get("/api/settings")
def system_settings(request: Request):
    return request.app.state.settings.read()


@app.put("/api/settings")
def save_system_settings(settings: SystemSettings, request: Request):
    return request.app.state.settings.save(settings)


@app.get("/api/ai/providers")
def ai_providers():
    return PROVIDERS


@app.post("/api/ai/models")
def ai_models(request: Request, settings: AISettings | None = None):
    try:
        return {"models": request.app.state.ai.models(settings)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/api/ai/settings")
def ai_settings(request: Request):
    return request.app.state.ai.public()


@app.put("/api/ai/settings")
def save_ai(settings: AISettings, request: Request):
    return request.app.state.ai.save(settings)


@app.post("/api/ai/test")
def test_ai(request: Request, settings: AISettings | None = None):
    try:
        if settings is not None and not settings.model_fields_set:
            settings = None
        result = request.app.state.ai.ask("Reply with OK. This is a connection test; no EEG data is included.", settings=settings)
        return {"status": "ok", "model": result["model"]}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    job_id: str | None = None
    include_summary: bool = False


@app.post("/api/ai/ask")
def ask(payload: Question, request: Request):
    summary = None
    if payload.include_summary:
        if not payload.job_id:
            raise HTTPException(422, "Select a completed job to include its summary")
        job = request.app.state.jobs.get(payload.job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "The report is not ready")
        summary = {"metrics": job.get("metrics"), "parameters": job["config"], "warnings": job["warnings"]}
    try:
        return request.app.state.ai.ask(payload.question, summary)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class NewConversation(BaseModel):
    job_id: str | None = None
    title: str | None = Field(default=None, max_length=160)


class ConversationQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    include_summary: bool = False


@app.get("/api/conversations")
def conversations(request: Request):
    return request.app.state.conversations.list()


@app.post("/api/conversations", status_code=201)
def new_conversation(payload: NewConversation, request: Request):
    if payload.job_id and request.app.state.jobs.get(payload.job_id)["status"] != "completed":
        raise HTTPException(409, "Select a completed report")
    return request.app.state.conversations.create(job_id=payload.job_id, title=payload.title)


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: str, request: Request):
    try:
        return request.app.state.conversations.get(conversation_id)
    except KeyError:
        raise HTTPException(404, "Conversation not found") from None


@app.post("/api/conversations/{conversation_id}/messages")
def conversation_message(conversation_id: str, payload: ConversationQuestion, request: Request):
    store = request.app.state.conversations
    try:
        lock = store.request_lock(conversation_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is already in progress")
        try:
            conv = store.get(conversation_id)
            summary = None
            if payload.include_summary:
                if not conv.get("job_id"):
                    raise HTTPException(422, "Select a report before sending its summary")
                job = request.app.state.jobs.get(conv["job_id"])
                if job["status"] != "completed": raise HTTPException(409, "Report not ready")
                summary = {"metrics":job.get("metrics"), "parameters":job["config"], "warnings":job["warnings"]}
            result = request.app.state.ai.ask(payload.question, summary=summary, history=conv["messages"])
            return store.append_exchange(conversation_id, payload.question, result["answer"], include_summary=payload.include_summary)
        finally:
            lock.release()
    except KeyError:
        raise HTTPException(404, "Conversation not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


DIST = ROOT / "frontend/dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
