"""
报告图表工厂

使用 Plotly 生成交互式图表（HTML报告），支持导出静态 PNG（PDF报告）。
"""
import numpy as np
import mne
from loguru import logger

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    logger.warning("plotly 未安装。安装: pip install plotly kaleido")

COLORS = {
    "primary": "#1B3A5C", "accent": "#2E75B6",
    "success": "#27AE60", "warning": "#F39C12", "danger": "#E74C3C",
    "before": "#E74C3C", "after": "#27AE60",
    "text": "#2C3E50", "bg": "#FFFFFF",
}
BAND_COLORS = {"delta": "#9B59B6", "theta": "#3498DB", "alpha": "#2ECC71", "beta": "#F1C40F", "gamma": "#E67E22"}

LAYOUT = dict(
    font=dict(family="Inter, sans-serif", color=COLORS["text"]),
    plot_bgcolor=COLORS["bg"], paper_bgcolor=COLORS["bg"],
    margin=dict(l=60, r=30, t=50, b=50),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


class FigureFactory:
    def __init__(self, raw_before, raw_after, step_results, context):
        self.raw_before = raw_before
        self.raw_after = raw_after
        self.step_results = step_results
        self.context = context
        self.language = "en" if str((context or {}).get("report_language") or "zh").strip().lower() == "en" else "zh"

    @property
    def is_english(self) -> bool:
        return self.language == "en"

    @staticmethod
    def _series(values, scale=1.0):
        array = np.asarray(values, dtype=float) * scale
        array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
        return array.tolist()

    @staticmethod
    def _scalar(value, default=0.0):
        try:
            scalar = float(np.squeeze(value))
        except Exception:
            return default
        return scalar if np.isfinite(scalar) else default

    def psd_comparison(self):
        psd_b = self.raw_before.compute_psd(fmin=0.5, fmax=45, verbose=False)
        psd_a = self.raw_after.compute_psd(fmin=0.5, fmax=45, verbose=False)
        freqs = self._series(psd_b.freqs)
        db_b = 10 * np.log10(np.nanmean(psd_b.get_data(), axis=0) + 1e-20)
        db_a = 10 * np.log10(np.nanmean(psd_a.get_data(), axis=0) + 1e-20)
        db_b = self._series(db_b)
        db_a = self._series(db_a)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=freqs, y=db_b, name="Before cleaning" if self.is_english else "清洗前", line=dict(color=COLORS["before"], width=1.5, dash="dot"), opacity=0.7))
        fig.add_trace(go.Scatter(x=freqs, y=db_a, name="After cleaning" if self.is_english else "清洗后", line=dict(color=COLORS["after"], width=2)))

        bands = {"δ": (0.5, 4), "θ": (4, 8), "α": (8, 13), "β": (13, 30), "γ": (30, 45)}
        for (label, (f1, f2)), key in zip(bands.items(), BAND_COLORS.keys()):
            fig.add_vrect(x0=f1, x1=f2, fillcolor=BAND_COLORS[key], opacity=0.06, layer="below", line_width=0,
                          annotation_text=label, annotation_position="top left", annotation_font_size=10)

        fig.update_layout(
            title="Power spectral density (PSD) comparison" if self.is_english else "功率谱密度 (PSD) 对比",
            xaxis_title="Frequency (Hz)" if self.is_english else "频率 (Hz)",
            yaxis_title="Power (dB)" if self.is_english else "功率 (dB)",
            **LAYOUT,
        )
        return fig

    def waveform_comparison(self, duration=5.0, start=10.0):
        n_ch = min(4, len(self.raw_before.ch_names))
        picks = list(range(n_ch))
        sfreq = self.raw_before.info["sfreq"]
        s0 = int(start * sfreq)
        s1 = min(int((start + duration) * sfreq), self.raw_before.n_times, self.raw_after.n_times)
        if s0 >= s1:
            s0, s1 = 0, min(int(duration * sfreq), self.raw_before.n_times)
        times = self._series(np.arange(s0, s1) / sfreq)

        fig = make_subplots(
            rows=n_ch,
            cols=2,
            shared_xaxes=True,
            shared_yaxes="rows",
            column_titles=["Before cleaning", "After cleaning"] if self.is_english else ["清洗前", "清洗后"],
            vertical_spacing=0.04,
            horizontal_spacing=0.05,
        )

        d_b = self.raw_before.get_data(picks=picks, start=s0, stop=s1) * 1e6
        d_a = self.raw_after.get_data(picks=picks, start=s0, stop=s1) * 1e6

        for i in range(n_ch):
            ch = self.raw_before.ch_names[picks[i]]
            fig.add_trace(go.Scatter(x=times, y=self._series(d_b[i]), line=dict(color=COLORS["before"], width=0.8), showlegend=False), row=i+1, col=1)
            fig.add_trace(go.Scatter(x=times, y=self._series(d_a[i]), line=dict(color=COLORS["after"], width=0.8), showlegend=False), row=i+1, col=2)
            fig.update_yaxes(title_text=ch, row=i+1, col=1, title_font_size=10)

        fig.update_layout(
            title=(f"Time-domain waveform comparison ({start:.0f}-{start+duration:.0f}s)" if self.is_english else f"时域波形对比 ({start:.0f}-{start+duration:.0f}s)"),
            height=150*n_ch+100,
            showlegend=False,
            **LAYOUT,
        )
        return fig

    def channel_std_comparison(self):
        eeg_picks = mne.pick_types(self.raw_before.info, eeg=True)
        if len(eeg_picks) == 0:
            eeg_picks = list(range(min(20, len(self.raw_before.ch_names))))
        ch_names = [self.raw_before.ch_names[i] for i in eeg_picks]
        std_b = np.nanstd(self.raw_before.get_data(picks=eeg_picks), axis=1) * 1e6
        std_a = np.nanstd(self.raw_after.get_data(picks=eeg_picks), axis=1) * 1e6

        fig = go.Figure()
        fig.add_trace(go.Bar(x=ch_names, y=self._series(std_b), name="Before cleaning" if self.is_english else "清洗前", marker_color=COLORS["before"], opacity=0.6))
        fig.add_trace(go.Bar(x=ch_names, y=self._series(std_a), name="After cleaning" if self.is_english else "清洗后", marker_color=COLORS["after"], opacity=0.8))
        fig.update_layout(
            title="Channel standard deviation comparison" if self.is_english else "各通道标准差对比",
            xaxis_title="Channel" if self.is_english else "通道",
            yaxis_title="Standard deviation (µV)" if self.is_english else "标准差 (µV)",
            barmode="group",
            **LAYOUT,
        )
        return fig

    def band_power_comparison(self, power_before, power_after):
        bands = list(power_before.keys())
        if not bands:
            return go.Figure()
        vals_b = [self._scalar(power_before.get(b, 0)) for b in bands] + [self._scalar(power_before.get(bands[0], 0))]
        vals_a = [self._scalar(power_after.get(b, 0)) for b in bands] + [self._scalar(power_after.get(bands[0], 0))]
        bands_c = bands + [bands[0]]

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=vals_b, theta=bands_c, name="Before cleaning" if self.is_english else "清洗前", fill="toself",
                                       fillcolor="rgba(231,76,60,0.1)", line=dict(color=COLORS["before"], dash="dot")))
        fig.add_trace(go.Scatterpolar(r=vals_a, theta=bands_c, name="After cleaning" if self.is_english else "清洗后", fill="toself",
                                       fillcolor="rgba(39,174,96,0.1)", line=dict(color=COLORS["after"])))
        fig.update_layout(title="Band power distribution" if self.is_english else "频段功率分布", polar=dict(radialaxis=dict(visible=True)), **LAYOUT)
        return fig

    def quality_gauge(self, score, grade):
        score = self._scalar(score, default=0.0)
        color = COLORS["success"] if score >= 85 else COLORS["accent"] if score >= 70 else COLORS["warning"] if score >= 55 else COLORS["danger"]
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            title={"text": (f"Data quality — grade {grade}" if self.is_english else f"数据质量 — {grade}级"), "font": {"size": 20}},
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": color, "thickness": 0.75},
                   "steps": [{"range": [0, 55], "color": "#FADBD8"}, {"range": [55, 70], "color": "#FCF3CF"},
                             {"range": [70, 85], "color": "#D5F5E3"}, {"range": [85, 100], "color": "#ABEBC6"}]}
        ))
        fig.update_layout(height=280, margin=dict(l=30, r=30, t=60, b=20), paper_bgcolor=COLORS["bg"])
        return fig

    def step_timeline(self):
        steps = [r.step_name for r in self.step_results]
        durations = self._series([r.duration for r in self.step_results])
        colors = [COLORS["warning"] if r.warnings else COLORS["success"] for r in self.step_results]
        fig = go.Figure(go.Bar(x=durations, y=steps, orientation="h", marker_color=colors,
                                text=[f"{d:.1f}s" for d in durations], textposition="auto"))
        fig.update_layout(title="Processing step durations" if self.is_english else "清洗步骤耗时", xaxis_title="Duration (s)" if self.is_english else "耗时 (秒)", yaxis=dict(autorange="reversed"),
                          height=max(200, 45*len(steps)+80), **LAYOUT)
        return fig

    def generate_all(self, metrics):
        if not HAS_PLOTLY:
            return {}
        figures = {}
        generators = [
            ("quality_gauge", lambda: self.quality_gauge(metrics.quality_score, metrics.quality_grade)),
            ("psd_comparison", self.psd_comparison),
            ("waveform_comparison", self.waveform_comparison),
            ("channel_std", self.channel_std_comparison),
            ("band_power", lambda: self.band_power_comparison(metrics.power_bands_before, metrics.power_bands_after)),
            ("step_timeline", self.step_timeline),
        ]
        for name, gen_fn in generators:
            try:
                figures[name] = gen_fn()
            except Exception as e:
                logger.warning(f"图表 {name} 生成失败: {e}")
        logger.info(f"生成了 {len(figures)} 个图表")
        return figures
