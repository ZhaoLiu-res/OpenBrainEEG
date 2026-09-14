"""
Step 6: Epoch 分段 + Autoreject 质量控制 (可选)

对连续数据做固定长度分段，然后用 Autoreject 自动确定
各通道的 rejection 阈值，剔除质量不达标的 epoch。

注意: 对于 BCI 数据，用户可能希望基于事件标记 (event markers) 来做 epoch，
      而不是固定分段。这种情况在配置中设置 epoch.enabled = False 即可。
"""
import numpy as np
import mne
from loguru import logger

from .base import BaseStep
from config import EpochConfig


class EpochStep(BaseStep):
    name = "epochs"

    def __init__(self, config: EpochConfig | None = None):
        self.config = config or EpochConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"
        if not self.config.enabled:
            return raw, {"language": language, "enabled": False, "reason": "Epoch step disabled (continuous-mode workflow)" if language == "en" else "Epoch 步骤未启用（连续数据模式）"}

        cfg = self.config

        # 创建等间隔事件用于分段
        events = mne.make_fixed_length_events(
            raw,
            duration=cfg.duration,
            overlap=cfg.overlap,
        )

        epochs = mne.Epochs(
            raw,
            events,
            tmin=0,
            tmax=cfg.duration,
            baseline=None,
            preload=True,
            verbose=False,
        )

        n_epochs_before = len(epochs)
        logger.debug(f"创建 {n_epochs_before} 个 epoch (时长={cfg.duration}s)")

        # Autoreject 自动阈值
        n_rejected = 0
        reject_log = None
        if cfg.autoreject and n_epochs_before > 0:
            n_rejected, reject_log = self._run_autoreject(epochs)

        n_epochs_after = len(epochs)

        metrics = {
            "language": language,
            "enabled": True,
            "duration": cfg.duration,
            "overlap": cfg.overlap,
            "n_epochs_before": n_epochs_before,
            "n_epochs_after": n_epochs_after,
            "n_rejected": n_rejected,
            "reject_ratio_pct": round(n_rejected / n_epochs_before * 100, 1) if n_epochs_before > 0 else 0,
            "autoreject_used": cfg.autoreject,
        }

        # 保存 epochs 到 context，后续报告可能需要
        context["epochs"] = epochs
        context["reject_log"] = reject_log

        return raw, metrics

    def _run_autoreject(self, epochs: mne.Epochs) -> tuple[int, object]:
        """运行 Autoreject"""
        try:
            from autoreject import AutoReject

            ar = AutoReject(random_state=42, verbose=False)
            epochs_clean = ar.fit_transform(epochs)

            n_rejected = len(epochs) - len(epochs_clean)
            reject_log = ar.get_reject_log(epochs)

            # 用清洗后的 epochs 替换原来的
            epochs.drop(reject_log.bad_epochs)

            logger.info(f"Autoreject: 剔除 {n_rejected} 个 epoch")
            return n_rejected, reject_log

        except ImportError:
            logger.warning("autoreject 未安装，使用简易振幅阈值")
            return self._simple_reject(epochs)

    def _simple_reject(self, epochs: mne.Epochs) -> tuple[int, None]:
        """简易振幅阈值剔除"""
        # 剔除峰值超过 150µV 的 epoch
        reject = dict(eeg=150e-6)
        epochs.drop_bad(reject=reject, verbose=False)
        n_rejected = epochs.drop_log_stats()
        return int(n_rejected), None

    def _build_description(self, metrics: dict) -> str:
        if not metrics.get("enabled"):
            return metrics.get("reason", "Epoch step disabled" if metrics.get("language") == "en" else "Epoch 步骤未启用")
        if metrics.get("language") == "en":
            return (
                f"Created {metrics['n_epochs_before']} epochs "
                f"(duration={metrics['duration']}s), "
                f"rejected {metrics['n_rejected']} ({metrics['reject_ratio_pct']}%)"
            )
        return (
            f"分段 {metrics['n_epochs_before']} 个 epoch "
            f"(时长={metrics['duration']}s)，"
            f"剔除 {metrics['n_rejected']} 个 ({metrics['reject_ratio_pct']}%)"
        )
