from __future__ import annotations

from typing import Any

import mne
import numpy as np


def build_signal_preview(
    raw: mne.io.BaseRaw,
    *,
    duration_seconds: float = 8.0,
    max_points: int = 180,
) -> dict[str, Any]:
    eeg_picks = mne.pick_types(raw.info, eeg=True, exclude=[])
    if len(eeg_picks):
        preview_pick = int(eeg_picks[0])
    elif raw.info["nchan"] > 0:
        preview_pick = 0
    else:
        return {
            "preview_signal": [],
            "preview_channel": None,
            "preview_duration_seconds": 0.0,
        }

    sfreq = float(raw.info.get("sfreq") or 0.0)
    if sfreq <= 0 or raw.n_times <= 0:
        return {
            "preview_signal": [],
            "preview_channel": raw.ch_names[preview_pick] if raw.ch_names else None,
            "preview_duration_seconds": 0.0,
        }

    stop = min(raw.n_times, max(1, int(round(sfreq * duration_seconds))))
    data = raw.get_data(picks=[preview_pick], start=0, stop=stop)[0]
    if data.size == 0:
        return {
            "preview_signal": [],
            "preview_channel": raw.ch_names[preview_pick] if raw.ch_names else None,
            "preview_duration_seconds": 0.0,
        }

    if data.size > max_points:
        indices = np.linspace(0, data.size - 1, max_points).astype(int)
        data = data[indices]

    centered = data - float(np.mean(data))
    scale = float(np.max(np.abs(centered))) or 1.0
    normalized = np.clip(centered / scale, -1.0, 1.0)
    preview_duration = min(raw.n_times / sfreq, duration_seconds)

    return {
        "preview_signal": normalized.round(4).tolist(),
        "preview_channel": raw.ch_names[preview_pick] if raw.ch_names else None,
        "preview_duration_seconds": round(float(preview_duration), 3),
    }


def merge_signal_preview(dataset_info: dict[str, Any], raw: mne.io.BaseRaw) -> dict[str, Any]:
    merged = dict(dataset_info)
    merged.update(build_signal_preview(raw))
    return merged
