"""
EEG 多格式统一加载器

支持格式: EDF, BDF, GDF, FIF, SET, BrainVision
所有格式统一返回 mne.io.Raw 对象
"""
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

import mne
from loguru import logger

from config import InputAdapterConfig
from core.openbci_loader import load_raw as load_openbci_raw
from core.openbci_loader import looks_like_brainflow_csv, looks_like_openbci_text


@dataclass
class DatasetInfo:
    """数据集元信息"""
    filepath: str
    filename: str
    file_format: str
    n_channels: int
    channel_names: list[str]
    sfreq: float                 # 采样率 (Hz)
    duration: float              # 时长 (秒)
    n_samples: int
    highpass: float              # 硬件高通 (Hz)
    lowpass: float               # 硬件低通 (Hz)
    meas_date: datetime | None
    file_size_mb: float
    channel_types: dict = field(default_factory=dict)  # {"eeg": 64, "eog": 2, ...}

    @property
    def duration_str(self) -> str:
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"

    def summary(self) -> str:
        return (
            f"文件: {self.filename} ({self.file_format})\n"
            f"通道: {self.n_channels} ({', '.join(f'{v}{k}' for k, v in self.channel_types.items())})\n"
            f"采样率: {self.sfreq} Hz | 时长: {self.duration_str}\n"
            f"大小: {self.file_size_mb:.1f} MB"
        )


class EEGLoader:
    """统一 EEG 文件加载器"""

    BCI_COMPETITION_2A_CHANNEL_MAP = {
        "EEG-FZ": "Fz",
        "EEG-0": "FC3",
        "EEG-1": "FC1",
        "EEG-2": "FCz",
        "EEG-3": "FC2",
        "EEG-4": "FC4",
        "EEG-5": "C5",
        "EEG-C3": "C3",
        "EEG-6": "C1",
        "EEG-CZ": "Cz",
        "EEG-7": "C2",
        "EEG-C4": "C4",
        "EEG-8": "C6",
        "EEG-9": "CP3",
        "EEG-10": "CP1",
        "EEG-11": "CPz",
        "EEG-12": "CP2",
        "EEG-13": "CP4",
        "EEG-14": "P1",
        "EEG-PZ": "Pz",
        "EEG-15": "P2",
        "EEG-16": "POz",
    }

    # 扩展名 → 读取函数的映射
    READERS = {
        ".edf": "_read_edf",
        ".bdf": "_read_bdf",
        ".gdf": "_read_gdf",
        ".fif": "_read_fif",
        ".set": "_read_set",
        ".vhdr": "_read_brainvision",
    }

    RAW_COMPAT_FORMATS = {".txt", ".csv"}
    SUPPORTED_FORMATS = set(READERS.keys()) | RAW_COMPAT_FORMATS

    @classmethod
    def load(
        cls,
        filepath: str | Path,
        preload: bool = True,
        *,
        input_adapter: InputAdapterConfig | dict | None = None,
    ) -> mne.io.Raw:
        """
        根据文件扩展名自动选择读取器，返回 MNE Raw 对象

        Args:
            filepath: EEG 文件路径
            preload: 是否预加载数据到内存 (大文件可设 False)

        Returns:
            mne.io.Raw 对象
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")

        suffix = filepath.suffix.lower()
        adapter = cls._coerce_input_adapter(input_adapter)
        if suffix not in cls.SUPPORTED_FORMATS:
            raise ValueError(
                f"不支持的文件格式: {suffix}\n"
                f"支持的格式: {', '.join(sorted(cls.SUPPORTED_FORMATS))}"
            )

        logger.info(f"加载文件: {filepath.name} (格式: {suffix})")
        if suffix in cls.RAW_COMPAT_FORMATS:
            raw = load_openbci_raw(filepath, adapter)
        else:
            reader_name = cls.READERS[suffix]
            reader = getattr(cls, reader_name)
            raw = reader(filepath, preload=preload)
        cls._normalize_channel_metadata(raw, suffix)
        logger.info(f"加载完成: {raw.info['nchan']} 通道, {raw.info['sfreq']} Hz, {raw.times[-1]:.1f}s")

        return raw

    @classmethod
    def extract_metadata(cls, raw: mne.io.Raw, filepath: str | Path | None = None) -> DatasetInfo:
        """从 Raw 对象提取元数据"""
        filepath = Path(filepath) if filepath else Path("unknown")

        # 统计各类型通道数量
        ch_types = {}
        for ch_type in set(raw.get_channel_types()):
            count = len(mne.pick_types(raw.info, **{ch_type: True})) if ch_type in ("eeg", "eog", "ecg", "emg", "stim") \
                else len([c for c, t in zip(raw.ch_names, raw.get_channel_types()) if t == ch_type])
            if count > 0:
                ch_types[ch_type] = count

        return DatasetInfo(
            filepath=str(filepath),
            filename=filepath.name,
            file_format=filepath.suffix.lower(),
            n_channels=raw.info["nchan"],
            channel_names=raw.ch_names.copy(),
            sfreq=raw.info["sfreq"],
            duration=raw.times[-1],
            n_samples=raw.n_times,
            highpass=raw.info.get("highpass", 0.0),
            lowpass=raw.info.get("lowpass", 0.0),
            meas_date=raw.info["meas_date"],
            file_size_mb=filepath.stat().st_size / 1024 / 1024 if filepath.exists() else 0,
            channel_types=ch_types,
        )

    @classmethod
    def validate_format(
        cls,
        filepath: str | Path,
        *,
        input_adapter: InputAdapterConfig | dict | None = None,
    ) -> bool:
        """校验文件格式是否支持"""
        path = Path(filepath)
        suffix = path.suffix.lower()
        if suffix in cls.READERS:
            return True
        if suffix == ".txt":
            return looks_like_openbci_text(path)
        if suffix == ".csv":
            return looks_like_brainflow_csv(path, cls._coerce_input_adapter(input_adapter))
        return False

    @staticmethod
    def _coerce_input_adapter(value: InputAdapterConfig | dict | None) -> InputAdapterConfig:
        if isinstance(value, InputAdapterConfig):
            return value
        return InputAdapterConfig.model_validate(value or {})

    @classmethod
    def _normalize_channel_metadata(cls, raw: mne.io.Raw, suffix: str) -> None:
        cls._promote_aux_channel_types(raw)
        if suffix == ".gdf":
            cls._rename_bci_competition_channels(raw)

    @staticmethod
    def _promote_aux_channel_types(raw: mne.io.Raw) -> None:
        type_map = {}
        for ch_name in raw.ch_names:
            upper_name = ch_name.upper()
            if upper_name.startswith("EOG") and mne.channel_type(raw.info, raw.ch_names.index(ch_name)) == "eeg":
                type_map[ch_name] = "eog"
            elif upper_name.startswith("ECG") and mne.channel_type(raw.info, raw.ch_names.index(ch_name)) == "eeg":
                type_map[ch_name] = "ecg"

        if type_map:
            raw.set_channel_types(type_map, on_unit_change="ignore", verbose=False)
            logger.info(f"已修正辅助通道类型: {type_map}")

    @classmethod
    def _rename_bci_competition_channels(cls, raw: mne.io.Raw) -> None:
        rename_map = {}
        for ch_name in raw.ch_names:
            mapped = cls.BCI_COMPETITION_2A_CHANNEL_MAP.get(ch_name.upper())
            if mapped and mapped != ch_name:
                rename_map[ch_name] = mapped

        if rename_map:
            raw.rename_channels(rename_map)
            logger.info(f"已应用 BCI Competition GDF 通道映射: {rename_map}")

    # ==================== 各格式读取器 ====================

    @staticmethod
    def _read_edf(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_edf(filepath, preload=preload, verbose=False)

    @staticmethod
    def _read_bdf(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_bdf(filepath, preload=preload, verbose=False)

    @staticmethod
    def _read_gdf(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_gdf(filepath, preload=preload, verbose=False)

    @staticmethod
    def _read_fif(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_fif(filepath, preload=preload, verbose=False)

    @staticmethod
    def _read_set(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_eeglab(filepath, preload=preload, verbose=False)

    @staticmethod
    def _read_brainvision(filepath: Path, preload: bool) -> mne.io.Raw:
        return mne.io.read_raw_brainvision(filepath, preload=preload, verbose=False)
