"""Persisted local runtime preferences. Applied to new tasks."""
from pathlib import Path
from threading import Lock
from typing import Literal
from pydantic import BaseModel, Field


class SystemSettings(BaseModel):
    max_upload_mb: int = Field(default=512, ge=1, le=8192)
    max_active_jobs: int = Field(default=4, ge=1, le=16)
    report_language: Literal["auto", "zh", "en"] = "auto"
    default_pdf: bool = False
    auto_open_report: bool = True


class SettingsStore:
    def __init__(self, root: Path):
        self.path = root / "system-settings.json"
        self.lock = Lock()

    def read(self):
        return SystemSettings.model_validate_json(self.path.read_text(encoding="utf-8")) if self.path.exists() else SystemSettings()

    def save(self, settings):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
            temp.replace(self.path)
        return settings
