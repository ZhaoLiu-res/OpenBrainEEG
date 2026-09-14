from __future__ import annotations

import csv
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import mne
import numpy as np

from config import InputAdapterConfig


OPENBCI_HEADER_PREFIX = "%OpenBCI Raw EXG Data"
OPENBCI_CHANNELS_RE = re.compile(r"%Number of channels\s*=\s*(\d+)", re.IGNORECASE)
OPENBCI_SAMPLE_RATE_RE = re.compile(r"%Sample Rate\s*=\s*([0-9.]+)\s*Hz", re.IGNORECASE)
OPENBCI_BOARD_RE = re.compile(r"%Board\s*=\s*(.+)", re.IGNORECASE)


def looks_like_openbci_text(filepath: str | Path) -> bool:
    path = Path(filepath)
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                return line.startswith(OPENBCI_HEADER_PREFIX)
    except OSError:
        return False
    return False


def looks_like_brainflow_csv(filepath: str | Path, adapter: InputAdapterConfig | None = None) -> bool:
    path = Path(filepath)
    config = adapter or InputAdapterConfig()
    try:
        rows, delimiter = _read_numeric_rows(path, expected_rows=6)
    except ValueError:
        return False
    if not rows:
        return False
    total_columns = len(rows[0])
    exg_count = _infer_brainflow_exg_count(total_columns, config)
    if exg_count is None:
        return False
    if delimiter not in {",", "\t"}:
        return False
    timestamps = [row[-2] for row in rows if len(row) == total_columns]
    return _looks_like_timestamp_series(timestamps)


def load_raw(filepath: str | Path, adapter: InputAdapterConfig | None = None) -> mne.io.Raw:
    path = Path(filepath)
    config = adapter or InputAdapterConfig()
    suffix = path.suffix.lower()
    if config.source_format == "openbci_txt" or (suffix == ".txt" and looks_like_openbci_text(path)):
        return _load_openbci_text(path, config)
    if config.source_format == "brainflow_csv" or (suffix == ".csv" and looks_like_brainflow_csv(path, config)):
        return _load_brainflow_csv(path, config)
    raise ValueError(f"当前文件不是可识别的 OpenBCI / BrainFlow 原始格式: {path.name}")


def _load_openbci_text(filepath: Path, adapter: InputAdapterConfig) -> mne.io.Raw:
    metadata_lines: list[str] = []
    header_row: list[str] | None = None
    data_rows: list[list[float]] = []

    with filepath.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("%"):
                metadata_lines.append(line)
                continue
            header_row = [item.strip() for item in line.split(",")]
            break

        if not header_row:
            raise ValueError("OpenBCI TXT 缺少列头，无法识别 EXG 通道")

        reader = csv.reader(handle, delimiter=",", skipinitialspace=True)
        for row in reader:
            if not row or not any(str(item).strip() for item in row):
                continue
            if len(row) < len(header_row):
                continue
            data_rows.append([_parse_float_or_nan(item) for item in row[: len(header_row)]])

    if not data_rows:
        raise ValueError("OpenBCI TXT 不包含有效数据行")

    data = np.asarray(data_rows, dtype=float)
    exg_indices = [index for index, name in enumerate(header_row) if name.lower().startswith("exg channel")]
    if not exg_indices:
        raise ValueError("OpenBCI TXT 中未找到 EXG 通道列")

    fallback_sfreq = _header_sample_rate(metadata_lines)
    timestamps = _extract_named_column(data, header_row, "Timestamp")
    marker_values = _extract_named_column(data, header_row, "Marker Channel")
    raw = _build_raw_from_exg(
        data[:, exg_indices],
        timestamps=timestamps,
        marker_values=marker_values,
        fallback_sfreq=fallback_sfreq,
        adapter=adapter,
    )
    board = _header_board(metadata_lines)
    if board:
        raw.info["description"] = f"OpenBCI raw import ({board})"
    return raw


def _load_brainflow_csv(filepath: Path, adapter: InputAdapterConfig) -> mne.io.Raw:
    rows, _delimiter = _read_numeric_rows(filepath)
    if not rows:
        raise ValueError("BrainFlow CSV 不包含有效数据行")

    total_columns = len(rows[0])
    exg_count = _infer_brainflow_exg_count(total_columns, adapter)
    if exg_count is None:
        raise ValueError(
            f"BrainFlow CSV 列数 {total_columns} 无法自动判断 EEG 通道数，请在高级配置中补充通道映射"
        )

    data = np.asarray(rows, dtype=float)
    timestamps = data[:, -2]
    marker_values = data[:, -1]
    exg = data[:, 1 : 1 + exg_count]
    raw = _build_raw_from_exg(
        exg,
        timestamps=timestamps,
        marker_values=marker_values,
        fallback_sfreq=None,
        adapter=adapter,
    )
    raw.info["description"] = "BrainFlow raw import"
    return raw


def _build_raw_from_exg(
    exg_data: np.ndarray,
    *,
    timestamps: np.ndarray | None,
    marker_values: np.ndarray | None,
    fallback_sfreq: float | None,
    adapter: InputAdapterConfig,
) -> mne.io.Raw:
    if exg_data.ndim != 2 or exg_data.shape[0] == 0 or exg_data.shape[1] == 0:
        raise ValueError("未解析到有效 EEG 通道数据")

    n_samples, n_channels = exg_data.shape
    sfreq = _estimate_sampling_rate(timestamps, fallback=fallback_sfreq or 250.0)
    channel_names = _build_channel_names(adapter, n_channels)
    channel_types = _build_channel_types(channel_names)
    scale = 1e-6 if str(adapter.signal_unit or "uV").lower() in {"uv", "microvolt", "microvolts"} else 1.0

    raw = mne.io.RawArray(
        (exg_data.T * scale).astype(float),
        mne.create_info(channel_names, sfreq, ch_types=channel_types),
        verbose=False,
    )

    _apply_meas_date(raw, timestamps)
    _apply_marker_annotations(raw, timestamps, marker_values, sfreq)
    _apply_montage(raw, adapter)

    if n_samples < 10:
        raise ValueError("EEG 采样点数量过少，无法进入清洗流程")
    return raw


def _read_numeric_rows(filepath: Path, *, expected_rows: int | None = None) -> tuple[list[list[float]], str]:
    with filepath.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        first_line = ""
        for raw_line in handle:
            if raw_line.strip():
                first_line = raw_line
                break
        if not first_line:
            raise ValueError("文件为空")
        delimiter = "\t" if first_line.count("\t") >= first_line.count(",") else ","
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        rows: list[list[float]] = []
        for row in reader:
            if not row or not any(str(item).strip() for item in row):
                continue
            try:
                parsed = [_parse_float(item) for item in row]
            except ValueError as exc:
                raise ValueError("文件存在非数值列，无法按 BrainFlow 原始 CSV 解析") from exc
            rows.append(parsed)
            if expected_rows is not None and len(rows) >= expected_rows:
                break
    _ensure_uniform_columns(rows)
    return rows, delimiter


def _ensure_uniform_columns(rows: list[list[float]]) -> None:
    if not rows:
        return
    column_count = len(rows[0])
    if column_count == 0:
        raise ValueError("数据列为空")
    if any(len(row) != column_count for row in rows):
        raise ValueError("文件列数不一致，无法解析")


def _parse_float(value: object) -> float:
    text = str(value).strip()
    if not text:
        return math.nan
    return float(text)


def _parse_float_or_nan(value: object) -> float:
    try:
        return _parse_float(value)
    except ValueError:
        return math.nan


def _infer_brainflow_exg_count(total_columns: int, adapter: InputAdapterConfig) -> int | None:
    if adapter.exg_channel_count:
        return int(adapter.exg_channel_count)
    candidate = total_columns - 16
    if candidate in {4, 8, 16}:
        return candidate
    return None


def _looks_like_timestamp_series(values: list[float]) -> bool:
    finite = [value for value in values if math.isfinite(value)]
    if len(finite) < 4:
        return False
    if max(finite) < 1_000:
        return False
    diffs = [current - previous for previous, current in zip(finite, finite[1:]) if current > previous]
    if len(diffs) < 3:
        return False
    median_diff = float(np.median(diffs))
    return median_diff > 0


def _estimate_sampling_rate(timestamps: np.ndarray | None, *, fallback: float) -> float:
    if timestamps is None:
        return fallback
    finite = np.asarray([item for item in timestamps if math.isfinite(float(item))], dtype=float)
    if finite.size < 4:
        return fallback
    diffs = np.diff(finite)
    diffs = diffs[diffs > 0]
    if diffs.size < 3:
        return fallback
    median_diff = float(np.median(diffs))
    if median_diff <= 0:
        return fallback
    estimated = 1.0 / median_diff if median_diff < 1 else 1000.0 / median_diff
    if not math.isfinite(estimated) or estimated < 10 or estimated > 5_000:
        return fallback
    return round(float(estimated), 3)


def _build_channel_names(adapter: InputAdapterConfig, n_channels: int) -> list[str]:
    if adapter.channel_names:
        cleaned = [str(item).strip() for item in adapter.channel_names if str(item).strip()]
        if len(cleaned) != n_channels:
            raise ValueError(f"通道映射数量与数据通道数不一致：需要 {n_channels} 个，当前提供 {len(cleaned)} 个")
        return cleaned
    return [f"EXG{index + 1}" for index in range(n_channels)]


def _build_channel_types(channel_names: list[str]) -> list[str]:
    channel_types: list[str] = []
    for name in channel_names:
        upper_name = name.upper()
        if upper_name.startswith("EOG"):
            channel_types.append("eog")
        elif upper_name.startswith("ECG"):
            channel_types.append("ecg")
        elif upper_name.startswith("EMG"):
            channel_types.append("emg")
        elif upper_name.startswith("STIM") or upper_name.startswith("TRIG"):
            channel_types.append("stim")
        else:
            channel_types.append("eeg")
    return channel_types


def _apply_meas_date(raw: mne.io.Raw, timestamps: np.ndarray | None) -> None:
    if timestamps is None:
        return
    finite = [float(item) for item in timestamps if math.isfinite(float(item))]
    if not finite:
        return
    first = finite[0]
    try:
        raw.set_meas_date(datetime.fromtimestamp(first, tz=timezone.utc))
    except Exception:
        return


def _apply_marker_annotations(
    raw: mne.io.Raw,
    timestamps: np.ndarray | None,
    marker_values: np.ndarray | None,
    sfreq: float,
) -> None:
    if marker_values is None:
        return
    events: list[tuple[float, str]] = []
    marker_array = np.asarray(marker_values, dtype=float)
    if timestamps is not None:
        finite_timestamps = np.asarray(timestamps, dtype=float)
        if finite_timestamps.size:
            base_time = float(finite_timestamps[0])
        else:
            base_time = 0.0
    else:
        finite_timestamps = np.array([], dtype=float)
        base_time = 0.0

    for index, marker in enumerate(marker_array):
        if not math.isfinite(float(marker)) or abs(float(marker)) < 1e-9:
            continue
        if finite_timestamps.size > index and math.isfinite(float(finite_timestamps[index])):
            onset = max(float(finite_timestamps[index]) - base_time, 0.0)
        else:
            onset = index / sfreq
        label = str(int(marker)) if float(marker).is_integer() else f"{marker:.3f}"
        events.append((onset, label))

    if not events:
        return

    raw.set_annotations(
        mne.Annotations(
            onset=[item[0] for item in events],
            duration=[0.0] * len(events),
            description=[f"marker:{item[1]}" for item in events],
        )
    )


def _apply_montage(raw: mne.io.Raw, adapter: InputAdapterConfig) -> None:
    montage_name = str(adapter.montage_name or "").strip()
    if not montage_name:
        return
    montage = mne.channels.make_standard_montage(montage_name)
    raw.set_montage(montage, on_missing="ignore", verbose=False)


def _extract_named_column(data: np.ndarray, column_names: list[str], expected_name: str) -> np.ndarray | None:
    try:
        index = next(
            idx for idx, name in enumerate(column_names) if name.strip().lower() == expected_name.strip().lower()
        )
    except StopIteration:
        return None
    return data[:, index]


def _header_sample_rate(metadata_lines: list[str]) -> float | None:
    for line in metadata_lines:
        match = OPENBCI_SAMPLE_RATE_RE.search(line)
        if match:
            return float(match.group(1))
    return None


def _header_board(metadata_lines: list[str]) -> str | None:
    for line in metadata_lines:
        match = OPENBCI_BOARD_RE.search(line)
        if match:
            return match.group(1).strip()
    return None
