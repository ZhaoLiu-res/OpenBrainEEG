from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParadigmPreset:
    code: str
    name: str
    summary: str
    description: str
    recommended_for: str
    badges: tuple[str, ...]
    defaults: dict[str, Any]


DEFAULT_PIPELINE_PAYLOAD: dict[str, Any] = {
    "report_language": "zh",
    "filter": {"l_freq": 0.5, "h_freq": 40.0, "notch_freq": 50.0},
    "asr": {"enabled": True, "cutoff": 20.0},
    "ica": {"enabled": True, "n_components": None, "ic_reject_threshold": 0.8},
    "epoch": {"enabled": False, "duration": 2.0, "overlap": 0.0, "autoreject": True},
    "input_adapter": {},
    "export_formats": ["fif", "edf", "csv"],
    "report_formats": ["html", "pdf"],
    "generate_report": True,
}


PRESETS: tuple[ParadigmPreset, ...] = (
    ParadigmPreset(
        code="custom",
        name="自定义",
        summary="保留通用默认参数，适合熟悉 EEG 预处理的用户自行调参。",
        description="不会额外偏向某一类实验范式，适合作为全局通用起点。",
        recommended_for="已经清楚自己实验参数范围，或需要手动复刻既有流程。",
        badges=("通用", "手动调参"),
        defaults=deepcopy(DEFAULT_PIPELINE_PAYLOAD),
    ),
    ParadigmPreset(
        code="resting_state",
        name="静息态",
        summary="强调稳定的低频保留和全局质量评估，适合 eyes-open / eyes-closed 数据。",
        description="保留 0.5-40 Hz 常用频段，启用 ASR 与 ICA，默认不切 epoch。",
        recommended_for="静息态谱分析、功能连接、脑网络与一般质量评估。",
        badges=("Resting", "谱分析"),
        defaults={
            **deepcopy(DEFAULT_PIPELINE_PAYLOAD),
            "filter": {"l_freq": 0.5, "h_freq": 40.0, "notch_freq": 50.0},
            "epoch": {"enabled": False, "duration": 2.0, "overlap": 0.0, "autoreject": True},
        },
    ),
    ParadigmPreset(
        code="motor_imagery",
        name="运动想象 MI",
        summary="偏向保留 mu/beta 节律，适合运动想象与 SMR 类任务。",
        description="建议 1-40 Hz、启用 ASR/ICA，并切成 4 秒 epoch 便于后续特征提取。",
        recommended_for="CSP、FBCSP、时频功率分析与在线 BCI 原型数据。",
        badges=("MI", "mu/beta"),
        defaults={
            **deepcopy(DEFAULT_PIPELINE_PAYLOAD),
            "filter": {"l_freq": 1.0, "h_freq": 40.0, "notch_freq": 50.0},
            "asr": {"enabled": True, "cutoff": 20.0},
            "ica": {"enabled": True, "n_components": None, "ic_reject_threshold": 0.8},
            "epoch": {"enabled": True, "duration": 4.0, "overlap": 0.0, "autoreject": True},
        },
    ),
    ParadigmPreset(
        code="p300",
        name="P300 / ERP",
        summary="保留更低频的 ERP 成分，默认缩短低通并切成短 epoch。",
        description="建议 0.1-30 Hz，适合刺激锁定 ERP 波形分析与平均。",
        recommended_for="Oddball、P300、N200/N400 等事件相关电位研究。",
        badges=("ERP", "P300"),
        defaults={
            **deepcopy(DEFAULT_PIPELINE_PAYLOAD),
            "filter": {"l_freq": 0.1, "h_freq": 30.0, "notch_freq": 50.0},
            "asr": {"enabled": True, "cutoff": 25.0},
            "ica": {"enabled": True, "n_components": None, "ic_reject_threshold": 0.75},
            "epoch": {"enabled": True, "duration": 1.0, "overlap": 0.0, "autoreject": True},
        },
    ),
    ParadigmPreset(
        code="ssvep",
        name="SSVEP",
        summary="偏向保留刺激频率及其谐波，适合稳态视觉诱发电位。",
        description="建议 1-45 Hz，保留较高频信息，epoch 长度默认为 2 秒。",
        recommended_for="频率编码 SSVEP、谐波分析与频域分类。",
        badges=("SSVEP", "频域"),
        defaults={
            **deepcopy(DEFAULT_PIPELINE_PAYLOAD),
            "filter": {"l_freq": 1.0, "h_freq": 45.0, "notch_freq": 50.0},
            "asr": {"enabled": True, "cutoff": 20.0},
            "ica": {"enabled": True, "n_components": None, "ic_reject_threshold": 0.85},
            "epoch": {"enabled": True, "duration": 2.0, "overlap": 0.0, "autoreject": True},
        },
    ),
)


def list_paradigm_presets() -> list[dict[str, Any]]:
    return [
        {
            "code": preset.code,
            "name": preset.name,
            "summary": preset.summary,
            "description": preset.description,
            "recommended_for": preset.recommended_for,
            "badges": list(preset.badges),
            "defaults": deepcopy(preset.defaults),
        }
        for preset in PRESETS
    ]


def get_paradigm_preset(code: str | None) -> ParadigmPreset:
    normalized = (code or "custom").strip().lower()
    for preset in PRESETS:
        if preset.code == normalized:
            return preset
    raise ValueError(f"未知范式 preset: {code}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_pipeline_config(payload: dict[str, Any] | None = None):
    from config import PipelineConfig

    raw = deepcopy(payload or {})
    preset = get_paradigm_preset(str(raw.get("preset_code") or "custom"))
    merged = _deep_merge(preset.defaults, raw)
    merged["preset_code"] = preset.code
    merged["preset_name"] = preset.name
    return PipelineConfig.model_validate(merged)
