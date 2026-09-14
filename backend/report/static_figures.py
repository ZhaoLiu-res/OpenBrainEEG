from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mne
import numpy as np
from loguru import logger


STATIC_STYLE_DEFINITIONS = {
    "academic_bw": {
        "label": "Academic B/W",
        "font_family": "DejaVu Serif",
        "font_size": 11,
        "title_size": 16,
        "palette": ["#111111", "#4B5563", "#9CA3AF", "#1F2937", "#6B7280"],
        "background": "#FFFFFF",
        "grid": "#D1D5DB",
        "accent": "#111111",
        "topomap_cmap": "Greys",
        "delta_cmap": "gray",
    },
    "standard_color": {
        "label": "Standard Color",
        "font_family": "DejaVu Sans",
        "font_size": 11,
        "title_size": 16,
        "palette": ["#1F77B4", "#D62728", "#2CA02C", "#9467BD", "#FF7F0E"],
        "background": "#FFFFFF",
        "grid": "#E5E7EB",
        "accent": "#1F4B7A",
        "topomap_cmap": "viridis",
        "delta_cmap": "RdBu_r",
    },
    "presentation": {
        "label": "Presentation",
        "font_family": "DejaVu Sans",
        "font_size": 12,
        "title_size": 18,
        "palette": ["#0A6CF5", "#FF7A59", "#2FBF71", "#8B5CF6", "#F5B700"],
        "background": "#FFFFFF",
        "grid": "#DCE6F2",
        "accent": "#0A6CF5",
        "topomap_cmap": "plasma",
        "delta_cmap": "coolwarm",
    },
}


class MatplotlibFigureFactory:
    def __init__(self, raw_before, raw_after, step_results, context, metrics):
        self.raw_before = raw_before
        self.raw_after = raw_after
        self.step_results = step_results
        self.context = context
        self.metrics = metrics

    @staticmethod
    def _safe_style(style_code: str) -> dict:
        return STATIC_STYLE_DEFINITIONS.get(style_code, STATIC_STYLE_DEFINITIONS["standard_color"])

    @staticmethod
    def _sanitize_channel_name(name: str) -> str:
        clean = name.replace(".", "").replace(" ", "").strip()
        if clean.upper().startswith("EEG-"):
            clean = clean[4:]
        return clean or name

    def _prepare_topomap_raw(self, raw: mne.io.BaseRaw) -> mne.io.BaseRaw | None:
        picks = mne.pick_types(raw.info, eeg=True, exclude=[])
        if len(picks) < 4:
            return None

        eeg = raw.copy().pick(picks)
        rename_map: dict[str, str] = {}
        used_names = set(eeg.ch_names)
        for ch_name in list(eeg.ch_names):
            clean = self._sanitize_channel_name(ch_name)
            if clean != ch_name and clean not in used_names:
                rename_map[ch_name] = clean
                used_names.add(clean)
        if rename_map:
            eeg.rename_channels(rename_map)

        locs = np.array([channel["loc"][:3] for channel in eeg.info["chs"]], dtype=float)
        has_positions = np.isfinite(locs).all(axis=1) & ~np.all(np.isclose(locs, 0.0), axis=1)
        if has_positions.sum() < 4:
            try:
                eeg.set_montage("standard_1020", match_case=False, on_missing="ignore", verbose=False)
            except Exception as exc:
                logger.debug("标准 montage 应用失败: {}", exc)

        locs = np.array([channel["loc"][:3] for channel in eeg.info["chs"]], dtype=float)
        valid = np.isfinite(locs).all(axis=1) & ~np.all(np.isclose(locs, 0.0), axis=1)
        if valid.sum() < 4:
            return None
        return eeg.copy().pick(np.where(valid)[0].tolist())

    @staticmethod
    def _band_channel_power(raw: mne.io.BaseRaw, fmin: float, fmax: float) -> np.ndarray:
        raw_for_psd = raw.copy()
        raw_for_psd.info["bads"] = []
        psd = raw_for_psd.compute_psd(
            fmin=fmin,
            fmax=fmax,
            picks=np.arange(raw_for_psd.info["nchan"]),
            exclude=(),
            verbose=False,
        )
        values = np.asarray(psd.get_data(), dtype=float)
        return np.nan_to_num(values.mean(axis=1) * 1e12, nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _channel_std(raw: mne.io.BaseRaw) -> np.ndarray:
        data = np.asarray(raw.get_data(), dtype=float) * 1e6
        return np.nan_to_num(np.nanstd(data, axis=1), nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _placeholder(title: str, message: str, style: dict, *, width: float = 10, height: float = 4):
        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        ax.axis("off")
        ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=style["title_size"], color=style["accent"], fontweight="bold")
        ax.text(0.5, 0.40, message, ha="center", va="center", fontsize=style["font_size"], color="#6B7280", wrap=True)
        return fig

    def quality_gauge(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        score = float(getattr(self.metrics, "quality_score", 0.0) or 0.0)
        grade = getattr(self.metrics, "quality_grade", "N/A")
        color = "#1F6D3D" if score >= 85 else "#1D4E89" if score >= 70 else "#B45309" if score >= 55 else "#B42318"

        fig, ax = plt.subplots(figsize=(9, 2.8))
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        ax.barh([0], [100], color="#E5E7EB", height=0.36)
        ax.barh([0], [score], color=color, height=0.36)
        ax.set_xlim(0, 100)
        ax.set_yticks([])
        ax.set_xlabel("Quality score / 100", fontsize=style["font_size"], fontname=style["font_family"])
        ax.set_title("Overall EEG Quality Score", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"], pad=12)
        ax.grid(axis="x", color=style["grid"], linewidth=0.8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(min(score + 2, 96), 0, f"{score:.0f} ({grade})", va="center", ha="left", fontsize=style["font_size"] + 1, color=color, fontweight="bold")
        fig.tight_layout()
        return fig

    def psd_comparison(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        psd_before = self.raw_before.compute_psd(fmin=0.5, fmax=45, verbose=False)
        psd_after = self.raw_after.compute_psd(fmin=0.5, fmax=45, verbose=False)
        freqs = np.asarray(psd_before.freqs, dtype=float)
        db_before = 10 * np.log10(np.nanmean(psd_before.get_data(), axis=0) + 1e-20)
        db_after = 10 * np.log10(np.nanmean(psd_after.get_data(), axis=0) + 1e-20)

        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        ax.plot(freqs, db_before, label="Before cleaning", color=style["palette"][1], linewidth=2.0, linestyle="--")
        ax.plot(freqs, db_after, label="After cleaning", color=style["palette"][2], linewidth=2.4)

        band_spans = [
            ("delta", 0.5, 4, "#EDE9FE"),
            ("theta", 4, 8, "#DBEAFE"),
            ("alpha", 8, 13, "#DCFCE7"),
            ("beta", 13, 30, "#FEF3C7"),
            ("gamma", 30, 45, "#FDE68A"),
        ]
        y_top = float(max(np.nanmax(db_before), np.nanmax(db_after))) if len(freqs) else 0.0
        for label, start, stop, fill in band_spans:
            ax.axvspan(start, stop, color=fill, alpha=0.35, zorder=0)
            ax.text((start + stop) / 2, y_top, label, ha="center", va="bottom", fontsize=style["font_size"] - 1, color="#4B5563")

        ax.set_title("Power Spectral Density Comparison", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"], pad=12)
        ax.set_xlabel("Frequency (Hz)", fontsize=style["font_size"], fontname=style["font_family"])
        ax.set_ylabel("Power (dB)", fontsize=style["font_size"], fontname=style["font_family"])
        ax.grid(color=style["grid"], linewidth=0.8)
        ax.legend(frameon=False)
        fig.tight_layout()
        return fig

    def waveform_comparison(self, style_code: str = "standard_color", duration: float = 5.0, start: float = 10.0):
        style = self._safe_style(style_code)
        n_ch = min(4, len(self.raw_before.ch_names))
        if n_ch == 0:
            return self._placeholder("Time-domain Waveform Comparison", "No channels available for waveform preview.", style, width=12, height=5)

        picks = list(range(n_ch))
        sfreq = float(self.raw_before.info["sfreq"])
        start_sample = int(start * sfreq)
        stop_sample = min(int((start + duration) * sfreq), self.raw_before.n_times, self.raw_after.n_times)
        if start_sample >= stop_sample:
            start_sample = 0
            stop_sample = min(int(duration * sfreq), self.raw_before.n_times, self.raw_after.n_times)
        times = np.arange(start_sample, stop_sample) / sfreq
        data_before = self.raw_before.get_data(picks=picks, start=start_sample, stop=stop_sample) * 1e6
        data_after = self.raw_after.get_data(picks=picks, start=start_sample, stop=stop_sample) * 1e6

        fig, axes = plt.subplots(n_ch, 2, figsize=(12, max(4.5, n_ch * 2.1)), sharex=True, constrained_layout=True)
        fig.patch.set_facecolor(style["background"])
        if n_ch == 1:
            axes = np.array([axes])

        for row in range(n_ch):
            ax_before = axes[row, 0]
            ax_after = axes[row, 1]
            ax_before.plot(times, data_before[row], color=style["palette"][1], linewidth=1.0)
            ax_after.plot(times, data_after[row], color=style["palette"][2], linewidth=1.0)
            ax_before.set_ylabel(self.raw_before.ch_names[picks[row]], fontsize=style["font_size"] - 1)
            for ax in (ax_before, ax_after):
                ax.grid(color=style["grid"], linewidth=0.7)
                ax.set_facecolor(style["background"])
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
            if row == 0:
                ax_before.set_title("Before cleaning", fontsize=style["font_size"] + 1, color=style["accent"])
                ax_after.set_title("After cleaning", fontsize=style["font_size"] + 1, color=style["accent"])

        axes[-1, 0].set_xlabel("Time (s)", fontsize=style["font_size"])
        axes[-1, 1].set_xlabel("Time (s)", fontsize=style["font_size"])
        fig.suptitle("Time-domain Waveform Comparison", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"])
        return fig

    def channel_std_comparison(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        eeg_picks = mne.pick_types(self.raw_before.info, eeg=True, exclude=[])
        if len(eeg_picks) == 0:
            eeg_picks = list(range(min(20, len(self.raw_before.ch_names))))
        ch_names = [self.raw_before.ch_names[index] for index in eeg_picks]
        std_before = np.nanstd(self.raw_before.get_data(picks=eeg_picks), axis=1) * 1e6
        std_after = np.nanstd(self.raw_after.get_data(picks=eeg_picks), axis=1) * 1e6

        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        positions = np.arange(len(ch_names))
        width = 0.42
        ax.bar(positions - width / 2, std_before, width=width, color=style["palette"][1], alpha=0.7, label="Before cleaning")
        ax.bar(positions + width / 2, std_after, width=width, color=style["palette"][2], alpha=0.85, label="After cleaning")
        ax.set_xticks(positions)
        ax.set_xticklabels(ch_names, rotation=45, ha="right", fontsize=style["font_size"] - 1)
        ax.set_ylabel("Standard deviation (uV)", fontsize=style["font_size"])
        ax.set_title("Channel Variability Comparison", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"], pad=12)
        ax.grid(axis="y", color=style["grid"], linewidth=0.8)
        ax.legend(frameon=False)
        fig.tight_layout()
        return fig

    def band_power_comparison(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        bands = list(self.metrics.power_bands_before.keys())
        if not bands:
            return self._placeholder("Band Power Distribution", "Band power metrics are not available for this recording.", style, width=8, height=8)

        theta = np.linspace(0, 2 * np.pi, len(bands), endpoint=False)
        theta = np.concatenate([theta, [theta[0]]])
        before = [float(self.metrics.power_bands_before.get(band, 0.0)) for band in bands]
        after = [float(self.metrics.power_bands_after.get(band, 0.0)) for band in bands]
        before.append(before[0])
        after.append(after[0])

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        ax.plot(theta, before, color=style["palette"][1], linewidth=2.0, linestyle="--", label="Before cleaning")
        ax.fill(theta, before, color=style["palette"][1], alpha=0.12)
        ax.plot(theta, after, color=style["palette"][2], linewidth=2.2, label="After cleaning")
        ax.fill(theta, after, color=style["palette"][2], alpha=0.14)
        ax.set_xticks(theta[:-1])
        ax.set_xticklabels(bands, fontsize=style["font_size"])
        ax.grid(color=style["grid"], linewidth=0.8)
        ax.set_title("Band Power Distribution", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"], pad=20)
        ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), frameon=False)
        fig.tight_layout()
        return fig

    def step_timeline(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        steps = [result.step_name for result in self.step_results]
        durations = [float(result.duration) for result in self.step_results]
        colors = [style["palette"][3] if result.warnings else style["palette"][2] for result in self.step_results]

        if not steps:
            return self._placeholder("Pipeline Step Duration", "No step execution records were captured.", style, width=10, height=4)

        fig, ax = plt.subplots(figsize=(10, max(3.5, len(steps) * 0.7 + 1.5)))
        fig.patch.set_facecolor(style["background"])
        ax.set_facecolor(style["background"])
        positions = np.arange(len(steps))
        ax.barh(positions, durations, color=colors, alpha=0.9)
        ax.set_yticks(positions)
        ax.set_yticklabels(steps, fontsize=style["font_size"])
        ax.invert_yaxis()
        ax.set_xlabel("Duration (s)", fontsize=style["font_size"])
        ax.set_title("Pipeline Step Duration", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"], pad=12)
        ax.grid(axis="x", color=style["grid"], linewidth=0.8)
        for idx, duration in enumerate(durations):
            ax.text(duration + max(max(durations) * 0.015, 0.05), idx, f"{duration:.1f}s", va="center", fontsize=style["font_size"] - 1, color="#374151")
        fig.tight_layout()
        return fig

    def topomap_comparison(self, style_code: str = "standard_color"):
        style = self._safe_style(style_code)
        before = self._prepare_topomap_raw(self.raw_before)
        after = self._prepare_topomap_raw(self.raw_after)
        if before is None or after is None:
            return self._placeholder(
                "Spatial Topomap Comparison",
                "Insufficient EEG channel locations were available for topographic mapping.",
                style,
                width=12,
                height=4.5,
            )

        common_channels = [name for name in before.ch_names if name in set(after.ch_names)]
        if len(common_channels) < 4:
            return self._placeholder(
                "Spatial Topomap Comparison",
                "Topographic mapping requires at least four channels with valid scalp coordinates.",
                style,
                width=12,
                height=4.5,
            )

        before = before.copy().pick(common_channels)
        after = after.copy().pick(common_channels)
        if before.info["nchan"] != after.info["nchan"]:
            common_channels = [name for name in before.ch_names if name in set(after.ch_names)]
            before = before.copy().pick(common_channels)
            after = after.copy().pick(common_channels)
        before.info["bads"] = []
        after.info["bads"] = []
        before_alpha = self._band_channel_power(before, 8.0, 13.0)
        after_alpha = self._band_channel_power(after, 8.0, 13.0)
        delta_alpha = after_alpha - before_alpha

        vmax = float(max(np.nanmax(before_alpha), np.nanmax(after_alpha), 1e-6))
        delta_vmax = float(max(np.nanmax(np.abs(delta_alpha)), 1e-6))

        fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), constrained_layout=True)
        fig.patch.set_facecolor(style["background"])

        image_before, _ = mne.viz.plot_topomap(
            before_alpha,
            before.info,
            axes=axes[0],
            show=False,
            sensors=True,
            contours=6,
            cmap=style["topomap_cmap"],
            vlim=(0.0, vmax),
        )
        image_after, _ = mne.viz.plot_topomap(
            after_alpha,
            after.info,
            axes=axes[1],
            show=False,
            sensors=True,
            contours=6,
            cmap=style["topomap_cmap"],
            vlim=(0.0, vmax),
        )
        image_delta, _ = mne.viz.plot_topomap(
            delta_alpha,
            after.info,
            axes=axes[2],
            show=False,
            sensors=True,
            contours=6,
            cmap=style["delta_cmap"],
            vlim=(-delta_vmax, delta_vmax),
        )

        axes[0].set_title("Alpha power before", fontsize=style["font_size"] + 1, color=style["accent"])
        axes[1].set_title("Alpha power after", fontsize=style["font_size"] + 1, color=style["accent"])
        axes[2].set_title("Alpha power change", fontsize=style["font_size"] + 1, color=style["accent"])
        fig.suptitle("Spatial Topomap Comparison", fontsize=style["title_size"], fontname=style["font_family"], color=style["accent"])
        fig.colorbar(image_before, ax=axes[:2], shrink=0.78, location="right", label="Alpha power (uV^2)")
        fig.colorbar(image_delta, ax=axes[2], shrink=0.78, location="right", label="After - before")
        return fig

    def generate_all(self, style_code: str = "standard_color") -> dict[str, plt.Figure]:
        figures: dict[str, plt.Figure] = {}
        generators = [
            ("quality_gauge", self.quality_gauge),
            ("psd_comparison", self.psd_comparison),
            ("waveform_comparison", self.waveform_comparison),
            ("channel_std", self.channel_std_comparison),
            ("band_power", self.band_power_comparison),
            ("topomap_comparison", self.topomap_comparison),
            ("step_timeline", self.step_timeline),
        ]
        for name, generator in generators:
            try:
                figures[name] = generator(style_code=style_code)
            except Exception as exc:
                logger.warning("静态图表 {} 生成失败: {}", name, exc)
        return figures
