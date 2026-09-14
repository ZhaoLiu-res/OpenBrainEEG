"""
Step 4: ASR (Artifact Subspace Reconstruction)

去除非平稳的瞬态大幅值伪迹（如头动、电极接触不良等）。
ASR 通过滑动窗口 + PCA 分解，利用干净数据段建立阈值，
自动检测并重构伪迹段。

推荐在 ICA 之前运行 ASR，可以显著提升 ICA 分解质量。

依赖: meegkit 库 (pip install meegkit)
"""
import numpy as np
import mne
from loguru import logger

from .base import BaseStep
from config import ASRConfig


class ASRStep(BaseStep):
    name = "asr"

    def __init__(self, config: ASRConfig | None = None):
        self.config = config or ASRConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"
        if not self.config.enabled:
            return raw, {"language": language, "enabled": False, "reason": "ASR disabled" if language == "en" else "ASR 已禁用"}

        raw = raw.copy()

        try:
            from meegkit.asr import ASR
        except ImportError:
            logger.warning("meegkit 未安装，跳过 ASR 步骤。安装: pip install meegkit")
            return raw, {"language": language, "enabled": False, "reason": "meegkit is not installed" if language == "en" else "meegkit 未安装"}

        patch_applied = self._patch_meegkit_fit_distribution()

        eeg_picks = mne.pick_types(raw.info, eeg=True)
        if len(eeg_picks) < 2:
            return raw, {"language": language, "enabled": False, "reason": "Not enough EEG channels" if language == "en" else "EEG 通道不足"}

        sfreq = raw.info["sfreq"]
        data = np.ascontiguousarray(raw.get_data(picks=eeg_picks), dtype=np.float64)

        cal_samples = min(int(60 * sfreq), data.shape[1] // 2)
        if cal_samples < max(int(5 * sfreq), 32):
            return raw, {"language": language, "enabled": False, "reason": "The calibration segment is too short for ASR" if language == "en" else "可用于 ASR 标定的数据太短"}

        # 记录处理前的统计量
        rms_before = np.sqrt(np.mean(data ** 2))
        max_amp_before = np.max(np.abs(data))

        # 运行 ASR
        logger.debug(f"ASR 参数: cutoff={self.config.cutoff}")
        asr = ASR(sfreq=sfreq, cutoff=self.config.cutoff)

        # 用前段数据做 calibration（取前 60 秒或全部数据的一半，取较小值）
        asr.fit(data[:, :cal_samples])

        # 对全部数据做 ASR 变换
        cleaned_data = asr.transform(data)

        # 将清洗后的数据写回
        raw._data[eeg_picks] = cleaned_data

        # 统计修复程度
        rms_after = np.sqrt(np.mean(cleaned_data ** 2))
        max_amp_after = np.max(np.abs(cleaned_data))
        diff = np.abs(data - cleaned_data)
        modified_ratio = np.mean(diff > np.std(data) * 0.01)  # 被修改的数据点比例

        metrics = {
            "language": language,
            "enabled": True,
            "cutoff": self.config.cutoff,
            "calibration_seconds": round(cal_samples / sfreq, 1),
            "rms_before": round(float(rms_before * 1e6), 2),  # 转 µV
            "rms_after": round(float(rms_after * 1e6), 2),
            "max_amplitude_before_uv": round(float(max_amp_before * 1e6), 1),
            "max_amplitude_after_uv": round(float(max_amp_after * 1e6), 1),
            "modified_data_pct": round(float(modified_ratio * 100), 1),
            "library_patch_applied": patch_applied,
        }

        return raw, metrics

    def _build_description(self, metrics: dict) -> str:
        if not metrics.get("enabled"):
            return f"ASR skipped: {metrics.get('reason', '')}" if metrics.get("language") == "en" else f"ASR 跳过: {metrics.get('reason', '')}"
        if metrics.get("language") == "en":
            return (
                f"ASR completed (cutoff={metrics['cutoff']}), "
                f"modified {metrics['modified_data_pct']}% of data points, "
                f"max amplitude {metrics['max_amplitude_before_uv']}→{metrics['max_amplitude_after_uv']} µV"
            )
        return (
            f"ASR 清洗完成 (cutoff={metrics['cutoff']})，"
            f"修改了 {metrics['modified_data_pct']}% 的数据点，"
            f"最大振幅 {metrics['max_amplitude_before_uv']}→{metrics['max_amplitude_after_uv']} µV"
        )

    @staticmethod
    def _patch_meegkit_fit_distribution() -> bool:
        """
        meegkit 0.1.x 在较新的 NumPy 下会把长度为 1 的数组返回给 asr_calibrate，
        随后触发 “setting an array element with a sequence”。
        这里把返回值压成 Python float，避免整步失败。
        """
        import meegkit.asr as meegkit_asr
        from meegkit.utils import asr as meegkit_asr_utils

        if getattr(meegkit_asr, "_neuroclean_fit_patch", False):
            return False

        original_fit = meegkit_asr.fit_eeg_distribution

        def _safe_fit_eeg_distribution(*args, **kwargs):
            mu, sig, alpha, beta = original_fit(*args, **kwargs)
            return tuple(float(np.squeeze(item)) for item in (mu, sig, alpha, beta))

        meegkit_asr.fit_eeg_distribution = _safe_fit_eeg_distribution
        meegkit_asr_utils.fit_eeg_distribution = _safe_fit_eeg_distribution
        meegkit_asr._neuroclean_fit_patch = True
        logger.info("已应用 meegkit ASR 标定兼容补丁")
        return True
