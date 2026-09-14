"""
Step 3: 重参考

将 EEG 数据重新参考到指定参考点。
默认使用平均参考 (Average Reference)，这是 BCI 研究中最常用的方案。
"""
import mne
from loguru import logger

from .base import BaseStep
from config import ReferenceConfig


class ReferenceStep(BaseStep):
    name = "reference"

    def __init__(self, config: ReferenceConfig | None = None):
        self.config = config or ReferenceConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        raw = raw.copy()
        method = self.config.method
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"

        if method == "average":
            raw.set_eeg_reference("average", projection=False, verbose=False)
            ref_desc = "Average reference" if language == "en" else "平均参考 (Average Reference)"

        elif method == "REST":
            # REST 参考需要 forward model，暂用近似实现
            raw.set_eeg_reference("average", projection=False, verbose=False)
            ref_desc = "REST reference (approximation)" if language == "en" else "REST 参考 (近似实现)"
            logger.info("REST 参考需要前向模型，当前使用平均参考近似")

        elif method == "mastoid":
            # 查找乳突电极
            mastoid_chs = [ch for ch in raw.ch_names if ch.upper() in ("M1", "M2", "A1", "A2", "TP9", "TP10")]
            if len(mastoid_chs) >= 2:
                raw.set_eeg_reference(mastoid_chs[:2], verbose=False)
                ref_desc = f"Mastoid reference: {mastoid_chs[:2]}" if language == "en" else f"乳突参考: {mastoid_chs[:2]}"
            elif len(mastoid_chs) == 1:
                raw.set_eeg_reference(mastoid_chs, verbose=False)
                ref_desc = f"Single mastoid reference: {mastoid_chs}" if language == "en" else f"单乳突参考: {mastoid_chs}"
            else:
                logger.warning("未找到乳突电极，回退到平均参考")
                raw.set_eeg_reference("average", projection=False, verbose=False)
                ref_desc = "Average reference (mastoids unavailable)" if language == "en" else "平均参考 (乳突不可用)"
        else:
            raise ValueError(f"不支持的参考方法: {method}")

        metrics = {
            "language": language,
            "method": method,
            "description": ref_desc,
        }

        return raw, metrics

    def _build_description(self, metrics: dict) -> str:
        return f"Re-referenced: {metrics['description']}" if metrics.get("language") == "en" else f"重参考: {metrics['description']}"
