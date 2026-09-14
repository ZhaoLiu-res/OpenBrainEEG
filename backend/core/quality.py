"""
数据质量指标计算

计算清洗前后的各种质量指标，用于报告生成。
"""
import numpy as np
import mne
from dataclasses import dataclass, field


@dataclass
class QualityMetrics:
    """数据质量指标汇总"""

    # 基本信息
    n_channels: int = 0
    sfreq: float = 0.0
    duration: float = 0.0

    # 信噪比
    snr_before: float = 0.0
    snr_after: float = 0.0
    snr_improvement_db: float = 0.0

    # 通道质量
    n_bad_channels: int = 0
    bad_channel_ratio: float = 0.0

    # 伪迹统计
    n_ica_components: int = 0
    n_ica_excluded: int = 0
    ica_artifact_ratio: float = 0.0

    # 频段功率
    power_bands_before: dict = field(default_factory=dict)
    power_bands_after: dict = field(default_factory=dict)

    # 整体质量评分 (0-100)
    quality_score: int = 0
    quality_grade: str = "N/A"   # A/B/C/D

    def compute_grade(self):
        """根据各项指标计算综合质量评分"""
        score = 100

        # 坏导扣分: 每个坏导扣 3 分
        score -= self.n_bad_channels * 3

        # 伪迹成分扣分: 超过 30% 的成分是伪迹则扣分
        if self.n_ica_components > 0:
            artifact_pct = self.n_ica_excluded / self.n_ica_components
            if artifact_pct > 0.5:
                score -= 20
            elif artifact_pct > 0.3:
                score -= 10

        # SNR 加分
        if self.snr_improvement_db > 5:
            score += 5
        elif self.snr_improvement_db > 2:
            score += 2

        self.quality_score = max(0, min(100, score))

        if self.quality_score >= 85:
            self.quality_grade = "A"
        elif self.quality_score >= 70:
            self.quality_grade = "B"
        elif self.quality_score >= 55:
            self.quality_grade = "C"
        else:
            self.quality_grade = "D"


# 标准频段定义
FREQUENCY_BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta": (13, 30),
    "gamma": (30, 45),
}


def compute_band_powers(raw: mne.io.Raw) -> dict[str, float]:
    """计算各频段的平均功率 (µV²)"""
    psd = raw.compute_psd(fmin=0.5, fmax=45, verbose=False)
    freqs = psd.freqs
    psds = psd.get_data()  # (n_channels, n_freqs)

    powers = {}
    for band_name, (fmin, fmax) in FREQUENCY_BANDS.items():
        mask = (freqs >= fmin) & (freqs < fmax)
        if mask.any():
            # 平均功率转 µV²
            band_power = psds[:, mask].mean() * 1e12
            powers[band_name] = round(band_power, 4)

    return powers


def compute_snr(raw: mne.io.Raw) -> float:
    """
    估算全局信噪比 (dB)

    简易方法: 信号功率 (alpha+beta) / 噪声功率 (高频 30-45Hz)
    """
    psd = raw.compute_psd(fmin=0.5, fmax=45, verbose=False)
    freqs = psd.freqs
    psds = psd.get_data().mean(axis=0)  # 通道平均

    # 信号: alpha + beta 频段
    signal_mask = (freqs >= 8) & (freqs < 30)
    signal_power = psds[signal_mask].mean() if signal_mask.any() else 1e-20

    # 噪声: gamma 高频段
    noise_mask = (freqs >= 30) & (freqs < 45)
    noise_power = psds[noise_mask].mean() if noise_mask.any() else 1e-20

    snr_db = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else 0
    return round(float(snr_db), 2)


def compute_quality_metrics(
    raw_before: mne.io.Raw,
    raw_after: mne.io.Raw,
    step_results: list,
) -> QualityMetrics:
    """根据清洗前后数据和步骤结果计算综合质量指标"""

    metrics = QualityMetrics(
        n_channels=raw_after.info["nchan"],
        sfreq=raw_after.info["sfreq"],
        duration=raw_after.times[-1],
    )

    # SNR
    metrics.snr_before = compute_snr(raw_before)
    metrics.snr_after = compute_snr(raw_after)
    metrics.snr_improvement_db = round(metrics.snr_after - metrics.snr_before, 2)

    # 频段功率
    metrics.power_bands_before = compute_band_powers(raw_before)
    metrics.power_bands_after = compute_band_powers(raw_after)

    # 从步骤结果中提取统计信息
    for result in step_results:
        m = result.metrics
        if result.step_name == "bad_channels":
            metrics.n_bad_channels = m.get("n_bad_channels", 0)
            metrics.bad_channel_ratio = m.get("bad_ratio_pct", 0) / 100

        elif result.step_name == "ica":
            metrics.n_ica_components = m.get("n_components", 0)
            metrics.n_ica_excluded = m.get("n_excluded", 0)
            if metrics.n_ica_components > 0:
                metrics.ica_artifact_ratio = metrics.n_ica_excluded / metrics.n_ica_components

    # 计算综合评分
    metrics.compute_grade()

    return metrics
