"""
Step 1: 带通滤波 + 陷波滤波

- 带通: 去除基线漂移 (低频) 和高频噪声
- 陷波: 去除工频干扰 (50Hz 中国 / 60Hz 美国) 及其谐波
"""
import numpy as np
import mne
from loguru import logger

from .base import BaseStep
from config import FilterConfig


class FilteringStep(BaseStep):
    name = "filtering"

    def __init__(self, config: FilterConfig | None = None):
        self.config = config or FilterConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        raw = raw.copy()
        cfg = self.config
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"

        # 记录滤波前的功率谱特征
        psd_before = raw.compute_psd(fmin=0.5, fmax=cfg.h_freq + 20, verbose=False)
        power_before = psd_before.get_data().mean()

        # 带通滤波
        logger.debug(f"带通滤波: {cfg.l_freq}-{cfg.h_freq} Hz")
        raw.filter(
            l_freq=cfg.l_freq,
            h_freq=cfg.h_freq,
            fir_design="firwin",
            verbose=False,
        )

        # 陷波滤波: 基频 + 谐波
        notch_freqs = [
            cfg.notch_freq * i
            for i in range(1, cfg.notch_harmonics + 1)
            if cfg.notch_freq * i < raw.info["sfreq"] / 2  # 不超过奈奎斯特频率
        ]
        if notch_freqs:
            logger.debug(f"陷波滤波: {notch_freqs} Hz")
            raw.notch_filter(
                freqs=notch_freqs,
                verbose=False,
            )

        # 滤波后功率
        psd_after = raw.compute_psd(fmin=0.5, fmax=cfg.h_freq + 20, verbose=False)
        power_after = psd_after.get_data().mean()

        metrics = {
            "language": language,
            "bandpass": f"{cfg.l_freq}-{cfg.h_freq} Hz",
            "notch_freqs": notch_freqs,
            "power_reduction_pct": round((1 - power_after / power_before) * 100, 1) if power_before > 0 else 0,
        }

        return raw, metrics

    def _build_description(self, metrics: dict) -> str:
        if metrics.get("language") == "en":
            return (
                f"Band-pass {metrics['bandpass']}, "
                f"notch {metrics['notch_freqs']} Hz, "
                f"power reduced by {metrics['power_reduction_pct']}%"
            )
        return (
            f"带通滤波 {metrics['bandpass']}，"
            f"陷波 {metrics['notch_freqs']} Hz，"
            f"功率降低 {metrics['power_reduction_pct']}%"
        )
