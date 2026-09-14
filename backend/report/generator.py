"""
Brainifly 报告生成器

将 PipelineResult 转化为专业的数据质量报告。
支持 HTML（交互式）和 PDF（静态）两种输出。
"""
import base64
import io
import json
from html import escape
from pathlib import Path
from datetime import datetime

import numpy as np
from loguru import logger

from .figures import FigureFactory
from .static_figures import MatplotlibFigureFactory

try:
    import plotly.graph_objects as go
    from plotly.offline import get_plotlyjs_version, get_plotlyjs
    HAS_PLOTLY = True
    PLOTLY_JS_URL = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"
except ImportError:
    HAS_PLOTLY = False
    PLOTLY_JS_URL = None


class ReportGenerator:
    """数据质量报告生成器"""

    def __init__(self, pipeline_result):
        self.result = pipeline_result
        self.language = "en" if str(getattr(pipeline_result.config, "report_language", "zh") or "zh").strip().lower() == "en" else "zh"
        self.is_english = self.language == "en"
        self.figures = {}
        self.static_figures = {}
        self._generated = False

    def generate_figures(self):
        factory = FigureFactory(
            raw_before=self.result.raw_before,
            raw_after=self.result.raw_after,
            step_results=self.result.step_results,
            context=self.result.context,
        )
        self.figures = factory.generate_all(self.result.metrics)
        static_factory = MatplotlibFigureFactory(
            raw_before=self.result.raw_before,
            raw_after=self.result.raw_after,
            step_results=self.result.step_results,
            context=self.result.context,
            metrics=self.result.metrics,
        )
        self.static_figures = static_factory.generate_all("standard_color")
        self._generated = True

    def _static_figure_html(self, name: str) -> str:
        figure = self.static_figures.get(name)
        if figure is None:
            return ""
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f'<img src="data:image/png;base64,{encoded}" alt="{escape(name)}" style="width:100%;height:auto;border-radius:8px">'

    def generate_html(self, output_path):
        if not self._generated:
            self.generate_figures()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html = self._build_html()
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML 报告: {output_path.name} ({output_path.stat().st_size/1024:.0f} KB)")
        return output_path

    def generate_pdf(self, output_path):
        if not self._generated:
            self.generate_figures()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from weasyprint import HTML as WeasyHTML
            html = self._build_pdf_html()
            WeasyHTML(string=html).write_pdf(str(output_path))
            logger.info(f"PDF 报告: {output_path.name}")
            return output_path
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning(f"PDF 生成失败，回退为 HTML: {exc}")
            html_path = output_path.with_suffix(".html")
            return self.generate_html(html_path)

    @staticmethod
    def _grade_color(grade: str) -> str:
        return {"A": "#1f6d3d", "B": "#1d4e89", "C": "#9a6700", "D": "#a61b1b"}.get(grade, "#374151")

    def _grade_description(self, grade: str) -> str:
        labels = {
            "A": (
                "数据质量优秀，可直接进入后续分析流程。",
                "Data quality is excellent and ready for downstream analysis.",
            ),
            "B": (
                "数据质量良好，满足常规分析要求，建议复核少量残余伪迹。",
                "Data quality is good for standard analysis, with only a small amount of residual artifact to review.",
            ),
            "C": (
                "数据质量一般，存在较明显伪迹或坏导，建议人工复核后再分析。",
                "Data quality is moderate. Visible artifacts or bad channels should be reviewed before analysis.",
            ),
            "D": (
                "数据质量较差，建议重新采集或采用更严格的人工清洗策略。",
                "Data quality is poor. Re-acquisition or a stricter manual cleaning strategy is recommended.",
            ),
        }
        zh, en = labels.get(grade, ("未定义的质量等级。", "Undefined quality grade."))
        return en if self.is_english else zh

    def _step_title(self, step_name: str) -> str:
        labels = {
            "filtering": ("滤波", "Filtering"),
            "bad_channels": ("坏导检测与插值", "Bad-channel detection & interpolation"),
            "reference": ("重参考", "Re-referencing"),
            "asr": ("瞬态伪迹去除（ASR）", "Transient artifact removal (ASR)"),
            "ica": ("独立成分分析（ICA）", "Independent component analysis (ICA)"),
            "epochs": ("分段与剔除", "Epoching & rejection"),
        }
        if step_name not in labels:
            return step_name
        zh, en = labels[step_name]
        return en if self.is_english else zh

    def _format_scalar(self, value, digits: int = 2) -> str:
        if value is None or value == "":
            return "-"
        if isinstance(value, bool):
            if self.is_english:
                return "Yes" if value else "No"
            return "是" if value else "否"
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value) if value else "-"
        if isinstance(value, dict):
            return ", ".join(f"{key}: {val}" for key, val in value.items()) if value else "-"
        return str(value)

    def _esc(self, value, digits: int = 2) -> str:
        return escape(self._format_scalar(value, digits=digits))

    def _find_step(self, step_name: str):
        return next((step for step in self.result.step_results if step.step_name == step_name), None)

    def _render_table(self, headers: list[str], rows: list[list[str]], table_class: str = "report-table") -> str:
        if not rows:
            return '<p class="empty-note">Nothing to display.</p>' if self.is_english else '<p class="empty-note">无可展示内容。</p>'

        head_html = "".join(f"<th>{header}</th>" for header in headers)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in rows
        )
        return (
            f'<table class="{table_class}">'
            f"<thead><tr>{head_html}</tr></thead>"
            f"<tbody>{body_html}</tbody>"
            "</table>"
        )

    def _flatten_config(self, value, prefix: str = "") -> list[tuple[str, str]]:
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        elif hasattr(value, "dict"):
            value = value.dict()

        rows: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, item in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                rows.extend(self._flatten_config(item, next_prefix))
            return rows

        if isinstance(value, list):
            joined = ", ".join(self._format_scalar(item) for item in value) if value else "-"
            return [(prefix, joined)]

        return [(prefix, self._format_scalar(value))]

    def _channel_stat_rows(self, limit: int = 15) -> list[list[str]]:
        try:
            import mne

            eeg_picks = mne.pick_types(self.result.raw_before.info, eeg=True)
            if len(eeg_picks) == 0:
                eeg_picks = list(range(min(limit, len(self.result.raw_before.ch_names))))

            ch_names = [self.result.raw_before.ch_names[index] for index in eeg_picks]
            std_before = np.nanstd(self.result.raw_before.get_data(picks=eeg_picks), axis=1) * 1e6
            std_after = np.nanstd(self.result.raw_after.get_data(picks=eeg_picks), axis=1) * 1e6
            order = np.argsort(std_after)[::-1][:limit]

            rows = []
            for order_index in order:
                before = float(std_before[order_index])
                after = float(std_after[order_index])
                delta = after - before
                delta_pct = "-" if abs(before) < 1e-12 else f"{(delta / before) * 100:+.1f}%"
                rows.append([
                    escape(ch_names[order_index]),
                    f"{before:.2f}",
                    f"{after:.2f}",
                    f"{delta:+.2f}",
                    delta_pct,
                ])
            return rows
        except Exception as exc:
            logger.warning(f"PDF 通道统计表生成失败: {exc}")
            return []

    def _build_step_metric_summary(self, step_result) -> str:
        metrics = step_result.metrics or {}
        parts: list[str] = []
        label = (lambda zh, en: en if self.is_english else zh)

        if step_result.step_name == "filtering":
            parts.extend(
                [
                    f"{label('带通', 'Band-pass')}: {self._esc(metrics.get('bandpass'))}",
                    f"{label('陷波', 'Notch')}: {self._esc(metrics.get('notch_freqs'))} Hz",
                    f"{label('功率变化', 'Power change')}: {self._esc(metrics.get('power_reduction_pct'))}%",
                ]
            )
        elif step_result.step_name == "bad_channels":
            parts.extend(
                [
                    f"{label('坏导数', 'Bad channels')}: {self._esc(metrics.get('n_bad_channels'), digits=0)}",
                    f"{label('坏导占比', 'Bad-channel ratio')}: {self._esc(metrics.get('bad_ratio_pct'))}%",
                    f"{label('是否插值', 'Interpolated')}: {self._esc(metrics.get('interpolated'))}",
                    f"{label('坏导列表', 'Channel list')}: {self._esc(metrics.get('bad_channels'))}",
                ]
            )
        elif step_result.step_name == "reference":
            parts.append(f"{label('参考方式', 'Reference')}: {self._esc(metrics.get('description'))}")
        elif step_result.step_name == "asr":
            if metrics.get("enabled") is False:
                parts.append(f"{label('状态', 'Status')}: {label('跳过', 'Skipped')} ({self._esc(metrics.get('reason'))})")
            else:
                parts.extend(
                    [
                        f"cutoff: {self._esc(metrics.get('cutoff'))}",
                        f"{label('修改数据点', 'Modified points')}: {self._esc(metrics.get('modified_data_pct'))}%",
                        f"{label('最大振幅', 'Max amplitude')}: {self._esc(metrics.get('max_amplitude_before_uv'))} → {self._esc(metrics.get('max_amplitude_after_uv'))} µV",
                    ]
                )
        elif step_result.step_name == "ica":
            distribution = metrics.get("label_distribution") or {}
            dist_text = ", ".join(f"{label}: {count}" for label, count in sorted(distribution.items(), key=lambda item: (-item[1], item[0])))
            parts.extend(
                [
                    f"{label('成分数', 'Components')}: {self._esc(metrics.get('n_components'), digits=0)}",
                    f"{label('排除成分', 'Excluded')}: {self._esc(metrics.get('n_excluded'), digits=0)}",
                    f"{label('阈值', 'Threshold')}: {self._esc(metrics.get('threshold'))}",
                    f"{label('类别分布', 'Label distribution')}: {escape(dist_text) if dist_text else '-'}",
                ]
            )
        elif step_result.step_name == "epochs":
            parts.extend(
                [
                    f"{label('原始 epoch', 'Epochs before')}: {self._esc(metrics.get('n_epochs_before'), digits=0)}",
                    f"{label('剔除 epoch', 'Rejected epochs')}: {self._esc(metrics.get('n_rejected'), digits=0)}",
                    f"{label('剔除比例', 'Reject ratio')}: {self._esc(metrics.get('reject_ratio_pct'))}%",
                ]
            )

        if step_result.warnings:
            parts.append(f"{label('警告', 'Warnings')}: " + "<br>".join(escape(message) for message in step_result.warnings))

        return "<br>".join(parts) if parts else "-"

    def _build_quality_recommendations(self) -> list[str]:
        metrics = self.result.metrics
        notes = [self._grade_description(metrics.quality_grade)]

        if metrics.bad_channel_ratio >= 0.1:
            notes.append(
                "A relatively high bad-channel ratio was detected. Please review electrode contact quality and interpolated regions."
                if self.is_english
                else "坏导占比较高，建议复核电极接触质量与插值区域。"
            )
        elif metrics.n_bad_channels > 0:
            notes.append(
                "A small number of bad channels remain. Review those channels before final analysis."
                if self.is_english
                else "存在少量坏导，建议在正式统计前复核相关通道。"
            )

        if metrics.snr_improvement_db < 0:
            notes.append(
                "SNR did not improve after cleaning. Recheck filtering and artifact-rejection settings."
                if self.is_english
                else "清洗后信噪比未提升，建议人工复核滤波与伪迹剔除策略。"
            )

        asr_step = self._find_step("asr")
        if asr_step and asr_step.warnings:
            notes.append(
                "The ASR step reported warnings. Review transient high-amplitude artifact segments."
                if self.is_english
                else "ASR 步骤存在警告，建议重点检查瞬态大幅伪迹区段。"
            )

        if metrics.n_ica_components > 0 and metrics.ica_artifact_ratio > 0.3:
            notes.append(
                "A large share of ICA components were classified as artifacts, suggesting a heavy artifact burden in the raw recording."
                if self.is_english
                else "ICA 伪迹成分占比较高，提示原始记录中伪迹负荷较重。"
            )

        if len(notes) == 1:
            notes.append(
                "This result is suitable for downstream feature extraction, statistical analysis, or modeling."
                if self.is_english
                else "当前结果适合进入后续特征提取、统计分析或建模流程。"
            )

        return notes

    def _build_pdf_html(self) -> str:
        result = self.result
        metrics = result.metrics
        info = result.dataset_info
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.is_english:
            return self._build_pdf_html_en(generated_at)
        grade_color = self._grade_color(metrics.quality_grade)
        channel_type_text = ", ".join(
            f"{escape(str(name))}: {count}" for name, count in sorted((info.channel_types or {}).items())
        ) or "-"
        meas_date = info.meas_date.strftime("%Y-%m-%d %H:%M:%S") if info.meas_date else "-"

        summary_rows = [
            ['<span class="label-cell">文件名</span>', escape(info.filename), '<span class="label-cell">文件格式</span>', escape(info.file_format)],
            ['<span class="label-cell">采样率</span>', f"{info.sfreq:.2f} Hz", '<span class="label-cell">时长</span>', escape(info.duration_str)],
            ['<span class="label-cell">通道数</span>', str(info.n_channels), '<span class="label-cell">通道类型</span>', channel_type_text],
            ['<span class="label-cell">样本点数</span>', str(info.n_samples), '<span class="label-cell">文件大小</span>', f"{info.file_size_mb:.2f} MB"],
            ['<span class="label-cell">硬件高通 / 低通</span>', f"{info.highpass:.2f} / {info.lowpass:.2f} Hz", '<span class="label-cell">采集时间</span>', escape(meas_date)],
            ['<span class="label-cell">质量评分</span>', f"{metrics.quality_score}/100", '<span class="label-cell">质量等级</span>', f'<span class="grade-badge" style="color:{grade_color};border-color:{grade_color}">{escape(metrics.quality_grade)}</span>'],
            ['<span class="label-cell">SNR（前 / 后）</span>', f"{metrics.snr_before:.2f} / {metrics.snr_after:.2f} dB", '<span class="label-cell">SNR 改善</span>', f"{metrics.snr_improvement_db:+.2f} dB"],
            ['<span class="label-cell">坏导数 / 占比</span>', f"{metrics.n_bad_channels} / {metrics.bad_channel_ratio * 100:.1f}%", '<span class="label-cell">ICA 排除 / 总成分</span>', f"{metrics.n_ica_excluded} / {metrics.n_ica_components}"],
            ['<span class="label-cell">总处理耗时</span>', f"{result.total_duration:.2f} s", '<span class="label-cell">报告生成时间</span>', escape(generated_at)],
        ]

        recommendation_items = "".join(
            f"<li>{escape(item)}</li>" for item in self._build_quality_recommendations()
        )

        band_rows = []
        band_order = ["delta", "theta", "alpha", "beta", "gamma"]
        for band in band_order:
            before = float(metrics.power_bands_before.get(band, 0.0))
            after = float(metrics.power_bands_after.get(band, 0.0))
            delta = after - before
            rel_change = "-" if abs(before) < 1e-12 else f"{(delta / before) * 100:+.1f}%"
            band_rows.append([
                escape(band),
                f"{before:.4f}",
                f"{after:.4f}",
                f"{delta:+.4f}",
                rel_change,
            ])

        step_rows = []
        for step in result.step_results:
            if step.warnings:
                status = '<span class="status-badge status-warning">警告</span>'
            elif isinstance(step.metrics, dict) and step.metrics.get("enabled") is False:
                status = '<span class="status-badge status-muted">跳过</span>'
            else:
                status = '<span class="status-badge status-success">完成</span>'
            step_rows.append([
                escape(self._step_title(step.step_name)),
                status,
                f"{step.duration:.2f}",
                escape(step.description),
                self._build_step_metric_summary(step),
            ])

        bad_step = self._find_step("bad_channels")
        bad_metrics = bad_step.metrics if bad_step else {}
        bad_rows = [[
            self._esc(bad_metrics.get("n_bad_channels"), digits=0),
            self._esc(bad_metrics.get("bad_ratio_pct")),
            self._esc(bad_metrics.get("interpolated")),
            self._esc(bad_metrics.get("bad_channels")),
        ]] if bad_step else []

        channel_rows = self._channel_stat_rows(limit=15)

        asr_step = self._find_step("asr")
        asr_rows = []
        if asr_step:
            asr_metrics = asr_step.metrics or {}
            asr_status = "跳过" if asr_metrics.get("enabled") is False else ("警告" if asr_step.warnings else "完成")
            asr_rows.append([
                escape(asr_status),
                self._esc(asr_metrics.get("cutoff")),
                self._esc(asr_metrics.get("modified_data_pct")),
                f"{self._esc(asr_metrics.get('max_amplitude_before_uv'))} → {self._esc(asr_metrics.get('max_amplitude_after_uv'))}",
                "<br>".join(escape(message) for message in asr_step.warnings) if asr_step.warnings else "-",
            ])

        ica_step = self._find_step("ica")
        ica_summary_rows: list[list[str]] = []
        ica_component_rows: list[list[str]] = []
        if ica_step and ica_step.metrics.get("enabled"):
            ica_metrics = ica_step.metrics
            label_distribution = ica_metrics.get("label_distribution") or {}
            distribution_text = ", ".join(
                f"{label}: {count}" for label, count in sorted(label_distribution.items(), key=lambda item: (-item[1], item[0]))
            ) or "-"
            ica_summary_rows = [[
                self._esc(ica_metrics.get("n_components"), digits=0),
                self._esc(ica_metrics.get("n_excluded"), digits=0),
                self._esc(ica_metrics.get("threshold")),
                escape(distribution_text),
            ]]

            excluded_indices = {int(index) for index in (ica_metrics.get("excluded_indices") or [])}
            component_probs = ica_metrics.get("component_probs") or {}
            for component_index, entry in sorted(component_probs.items(), key=lambda item: int(item[0])):
                idx = int(component_index)
                label = escape(str(entry.get("label", "-")))
                confidence = float(entry.get("confidence", 0.0)) * 100
                action = (
                    '<span class="status-badge status-danger">排除</span>'
                    if idx in excluded_indices
                    else '<span class="status-badge status-success">保留</span>'
                )
                ica_component_rows.append([
                    f"IC {idx:02d}",
                    label,
                    f"{confidence:.1f}%",
                    action,
                ])

        config_rows = [
            [escape(path), escape(value)]
            for path, value in self._flatten_config(result.config)
        ]

        summary_table = self._render_table(["字段", "数值", "字段", "数值"], summary_rows, "report-table summary-table")
        band_table = self._render_table(["频段", "清洗前 (µV²)", "清洗后 (µV²)", "变化量", "相对变化"], band_rows)
        step_table = self._render_table(["步骤", "状态", "耗时 (s)", "处理说明", "关键指标"], step_rows)
        bad_table = self._render_table(["坏导数", "坏导占比 (%)", "是否插值", "坏导列表"], bad_rows)
        channel_table = self._render_table(["通道", "清洗前标准差 (µV)", "清洗后标准差 (µV)", "变化量", "相对变化"], channel_rows)
        asr_table = self._render_table(["状态", "ASR cutoff", "修改数据点 (%)", "最大振幅前后 (µV)", "备注"], asr_rows)
        ica_summary_table = self._render_table(["总成分数", "排除成分数", "阈值", "类别分布"], ica_summary_rows)
        ica_component_table = self._render_table(["成分", "判定类别", "置信度", "处理结果"], ica_component_rows, "report-table compact-table")
        config_table = self._render_table(["参数路径", "参数值"], config_rows, "report-table compact-table")

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Brainifly PDF Report — {escape(info.filename)}</title>
<style>
@page {{
  size: A4;
  margin: 15mm 12mm 16mm 12mm;
  @bottom-right {{
    content: "Page " counter(page) " / " counter(pages);
    font-size: 9px;
    color: #6b7280;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  color: #111827;
  font-size: 11px;
  line-height: 1.55;
}}
h1, h2, h3, p {{ margin: 0; }}
.report-shell {{ width: 100%; }}
.cover {{
  border-bottom: 2px solid #1f4b7a;
  padding-bottom: 10px;
  margin-bottom: 16px;
}}
.cover-kicker {{
  font-size: 10px;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: #4b5563;
  margin-bottom: 6px;
}}
.cover h1 {{
  font-size: 22px;
  color: #0f2740;
  margin-bottom: 6px;
}}
.cover-meta {{
  font-size: 10px;
  color: #4b5563;
}}
.quality-box {{
  margin-top: 12px;
  border: 1px solid #cbd5e1;
  border-left: 5px solid {grade_color};
  padding: 10px 12px;
  background: #f8fafc;
}}
.quality-line {{
  margin-top: 4px;
  color: #334155;
}}
.section {{
  margin-top: 16px;
}}
.section h2 {{
  font-size: 13px;
  color: #0f2740;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #cbd5e1;
}}
.section-note {{
  color: #475569;
  margin-bottom: 8px;
}}
.report-table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}}
.report-table thead {{
  display: table-header-group;
}}
.report-table tr {{
  page-break-inside: avoid;
}}
.report-table th,
.report-table td {{
  border: 1px solid #cbd5e1;
  padding: 6px 7px;
  vertical-align: top;
  word-wrap: break-word;
}}
.report-table th {{
  background: #e2e8f0;
  color: #0f2740;
  font-weight: 700;
}}
.summary-table td:nth-child(1),
.summary-table td:nth-child(3) {{
  background: #f8fafc;
  font-weight: 600;
  width: 18%;
}}
.label-cell {{
  color: #334155;
}}
.grade-badge {{
  display: inline-block;
  padding: 2px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-weight: 700;
}}
.status-badge {{
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid transparent;
}}
.status-success {{
  color: #166534;
  background: #dcfce7;
  border-color: #86efac;
}}
.status-warning {{
  color: #92400e;
  background: #fef3c7;
  border-color: #fcd34d;
}}
.status-danger {{
  color: #991b1b;
  background: #fee2e2;
  border-color: #fca5a5;
}}
.status-muted {{
  color: #475569;
  background: #e2e8f0;
  border-color: #cbd5e1;
}}
.compact-table td,
.compact-table th {{
  padding: 5px 6px;
  font-size: 10px;
}}
.finding-list {{
  margin: 0;
  padding-left: 18px;
}}
.finding-list li {{
  margin: 4px 0;
}}
.empty-note {{
  color: #64748b;
  font-style: italic;
}}
.page-break {{
  page-break-before: always;
}}
.footer-note {{
  margin-top: 16px;
  font-size: 9px;
  color: #6b7280;
  text-align: right;
}}
</style>
</head>
<body>
<div class="report-shell">
  <div class="cover">
    <div class="cover-kicker">Brainifly EEG Cleaning Report</div>
    <h1>脑电数据清洗质量报告</h1>
    <div class="cover-meta">文件: {escape(info.filename)} | 生成时间: {escape(generated_at)} | 系统: Brainifly</div>
    <div class="quality-box">
      <div><strong>综合结论</strong>: 质量等级 {escape(metrics.quality_grade)}，评分 {metrics.quality_score}/100</div>
      <div class="quality-line">{escape(self._grade_description(metrics.quality_grade))}</div>
    </div>
  </div>

  <div class="section">
    <h2>1. 数据与质量摘要</h2>
    {summary_table}
  </div>

  <div class="section">
    <h2>2. 结论与建议</h2>
    <ul class="finding-list">{recommendation_items}</ul>
  </div>

  <div class="section">
    <h2>3. 频段功率统计</h2>
    <p class="section-note">表中列出清洗前后各标准频段平均功率以及相对变化，可用于快速判断高频噪声和低频漂移的变化趋势。</p>
    {band_table}
  </div>

  <div class="section">
    <h2>4. 处理步骤执行记录</h2>
    <p class="section-note">以下记录保留每一步的状态、耗时、自动判定结果和关键指标，便于审计与复现。</p>
    {step_table}
  </div>

  <div class="section">
    <h2>5. 通道质量统计</h2>
    <p class="section-note">先给出坏导检测汇总，再列出清洗后标准差最高的前 15 个 EEG 通道，便于定位仍需人工关注的通道。</p>
    {bad_table}
    <div style="height:8px"></div>
    {channel_table}
  </div>

  <div class="section">
    <h2>6. ASR 结果</h2>
    {asr_table}
  </div>

  <div class="section page-break">
    <h2>7. ICA 结果汇总</h2>
    <p class="section-note">先展示 ICA 总体统计，再给出每个成分的自动分类、置信度和处理结果。</p>
    {ica_summary_table}
  </div>

  <div class="section">
    <h2>8. ICA 成分明细</h2>
    {ica_component_table}
  </div>

  <div class="section page-break">
    <h2>9. 参数记录</h2>
    <p class="section-note">以下参数来自本次任务实际执行配置，可直接用于复现实验与审计留档。</p>
    {config_table}
  </div>

  <div class="footer-note">PDF 版为静态归档文档；交互式图表与页面导航请查看 HTML 报告。</div>
</div>
</body>
</html>"""

    def _build_html(self, static_images=False):
        r = self.result
        m = r.metrics
        info = r.dataset_info

        chart_htmls = {}
        for name, fig in self.figures.items():
            if static_images:
                try:
                    import base64
                    img = fig.to_image(format="png", width=900, height=400, scale=2)
                    chart_htmls[name] = f'<img src="data:image/png;base64,{base64.b64encode(img).decode()}" style="width:100%">'
                except Exception:
                    chart_htmls[name] = fig.to_html(include_plotlyjs=False, full_html=False, config={"responsive": True})
            else:
                chart_htmls[name] = fig.to_html(include_plotlyjs=False, full_html=False, config={"responsive": True})
        for name in self.static_figures:
            chart_htmls.setdefault(name, self._static_figure_html(name))
        if self.is_english:
            return self._build_html_en(chart_htmls)
        STEP_EXPLANATIONS = {
    "filtering": {
        "cn_name": "信号滤波",
        "what": "就像给脑电信号戴上一个「频率过滤器」，只保留我们关心的脑电频率范围（通常 0.5-40Hz），同时去掉电网干扰（中国为 50Hz 交流电噪声）。",
        "why": "原始脑电信号中混杂着很多与大脑活动无关的噪声，比如电源线的嗡嗡声（50Hz工频干扰）、身体缓慢移动造成的基线漂移（极低频）。滤波是所有后续处理的基础。",
        "analogy": "类比：就像你在嘈杂的教室里戴上降噪耳机，过滤掉背景噪音，只听到老师讲课的声音。",
    },
    "bad_channels": {
        "cn_name": "坏导检测与修复",
        "what": "自动检测哪些电极记录的信号质量很差（称为「坏导」），然后用周围好的电极信号来估算和修复它。",
        "why": "在脑电采集过程中，某些电极可能因为接触不良、导电膏干燥或被试者头动等原因，记录到异常数据。如果不处理，这些坏导会污染后续分析结果。",
        "analogy": "类比：就像考试中有几道题的答题卡涂错了位置，我们需要先找出这些错误，然后根据前后文推测正确答案来修正。",
    },
    "reference": {
        "cn_name": "重参考",
        "what": "将所有电极的信号重新设定一个统一的「基准点」（参考电极），最常用的是所有电极的平均值作为参考。",
        "why": "脑电信号测量的是两点之间的电位差。不同设备、不同实验室使用的参考电极可能不同，重参考可以消除这种差异，让不同来源的数据具有可比性。",
        "analogy": "类比：就像测量身高时，有人从地面量，有人从台阶上量——重参考就是把所有人都统一到从地面量，这样才能公平比较。",
    },
    "asr": {
        "cn_name": "瞬态伪迹去除 (ASR)",
        "what": "ASR（伪迹子空间重构）是一种智能算法，能自动发现并修复数据中的瞬间大幅度异常信号，比如突然的头部运动或电极晃动产生的尖锐波形。",
        "why": "被试者在实验中难免会有偶尔的头动、吞咽、打哈欠等动作，这些会在脑电中产生短暂但幅度很大的异常信号。ASR 利用数据中相对干净的部分来学习「正常」的模式，然后自动修复异常段。",
        "analogy": "类比：就像照片修复软件，自动检测照片中的划痕或污点，然后用周围正常的画面来智能填补。",
    },
    "ica": {
        "cn_name": "独立成分分析 (ICA)",
        "what": "ICA 将混合在一起的脑电信号「拆解」成多个独立的来源，其中有的来自真正的大脑活动，有的来自眨眼、肌肉活动、心跳等非脑源信号。系统会自动识别并去除这些伪迹来源，只保留纯净的脑信号。",
        "why": "这是 EEG 清洗中最核心的一步。人在采集脑电时，眨眼会产生很大的眼电伪迹（尤其影响前额区域），面部肌肉紧张会产生高频肌电噪声，心跳也会产生周期性干扰。ICA 可以精准地将这些伪迹从脑信号中分离出来。",
        "analogy": "类比：想象在一个房间里有 3 个人同时说话，录音设备录下了混合声音。ICA 就像一个超级聪明的「声音分离器」，能把每个人的声音单独分离出来，让你选择只听其中一个人的声音（脑活动），把其他人（伪迹）静音。",
    },
    "epochs": {
        "cn_name": "数据分段",
        "what": "将连续的脑电记录按固定时间窗口切分成一个个小片段（epoch），然后检查每个片段的质量，剔除质量不达标的片段。",
        "why": "后续的统计分析（如事件相关电位 ERP）通常需要对多个相同条件的数据段进行平均，因此需要先将数据切分为等长的片段。",
        "analogy": "类比：就像把一整卷电影胶片剪成一个个场景片段，然后检查每个片段是否清晰，丢弃模糊不清的画面。",
    },
}

        ICA_LABEL_COLORS = {
            "brain":           {"bg": "#EDF7F1", "border": "#4A9E72", "text": "#1E6644", "icon": ""},
            "eye blink":       {"bg": "#EEF4FB", "border": "#4A7FB5", "text": "#1A4F80", "icon": ""},
            "muscle artifact": {"bg": "#F2EEF8", "border": "#7B5EA7", "text": "#4A2F80", "icon": ""},
            "heart beat":      {"bg": "#EEF7F5", "border": "#3D9E8A", "text": "#1A5E52", "icon": ""},
            "line noise":      {"bg": "#FEF6E6", "border": "#B8872A", "text": "#7A5200", "icon": ""},
            "channel noise":   {"bg": "#F0F3F5", "border": "#607D8B", "text": "#37474F", "icon": ""},
            "other":           {"bg": "#F3F3F3", "border": "#8E9BAA", "text": "#4A5568", "icon": ""},
        }

        def _build_ica_detail(m_ica):
            dist = m_ica.get("label_distribution", {})
            component_probs = m_ica.get("component_probs", {})
            n_total = m_ica.get("n_components", 0)
            n_excluded = m_ica.get("n_excluded", 0)
            excluded_idx = set(m_ica.get("excluded_indices", []))
            component_labels = m_ica.get("component_labels", [])

            # 色块卡片：只显示类别统计，不显示排除/保留（因为排除是按概率阈值算的，和类别不完全对应）
            cards = []
            for label, count in sorted(dist.items(), key=lambda x: -x[1]):
                c = ICA_LABEL_COLORS.get(label, ICA_LABEL_COLORS["other"])
                cards.append(
                    "<div style='background:{bg};border:1px solid {border};border-radius:8px;"
                    "padding:7px 14px;display:inline-flex;align-items:center;gap:0;margin:3px'>"
                    "<div>"
                    "<div style='font-weight:600;color:{text};font-size:12px'>{label}</div>"
                    "<div style='color:#888;font-size:11px'>{count} 个成分</div>"
                    "</div></div>".format(
                        bg=c["bg"], border=c["border"], text=c["text"],
                        label=label, count=count)
                )

            # 明细表：每行显示判定类别、置信度、是否被排除
            prob_rows = []
            threshold = m_ica.get("threshold", 0.8)
            for idx in sorted(component_probs.keys()):
                entry = component_probs[idx]
                label = entry.get("label", component_labels[idx] if idx < len(component_labels) else "?")
                confidence = entry.get("confidence", 0.0)
                c = ICA_LABEL_COLORS.get(label, ICA_LABEL_COLORS["other"])
                is_excl = idx in excluded_idx
                row_bg = "#F5F3FA" if is_excl else ""

                conf_w = max(int(confidence * 120), 2)
                over_thresh = confidence >= threshold and label != "brain"
                thresh_note = (
                    "<span style='font-size:10px;color:#7B52AB;margin-left:4px'>≥ {:.0%} 阈值，已排除</span>".format(threshold)
                    if over_thresh else ""
                )
                conf_bar = (
                    "<div style='display:flex;align-items:center;gap:6px'>"
                    "<div style='width:{w}px;height:6px;background:{col};border-radius:3px'></div>"
                    "<span style='font-size:11px;color:#444'>{pct}</span>{note}"
                    "</div>".format(w=conf_w, col=c["border"], pct="{:.0%}".format(confidence), note=thresh_note)
                )

                status = (
                    "<span style='color:#7B52AB;font-size:11px;font-weight:500'>已排除</span>"
                    if is_excl else
                    "<span style='color:#888;font-size:11px'>保留</span>"
                )

                prob_rows.append(
                    "<tr style='background:{rb}'>"
                    "<td style='padding:5px 10px;font-size:11px;color:#888'>IC {idx:02d}</td>"
                    "<td style='padding:5px 10px'><span style='background:{bg};color:{text};"
                    "border:1px solid {border};border-radius:4px;padding:2px 7px;font-size:11px'>"
                    "{label}</span></td>"
                    "<td style='padding:5px 10px'>{conf}</td>"
                    "<td style='padding:5px 10px'>{status}</td>"
                    "</tr>".format(
                        rb=row_bg, idx=idx,
                        bg=c["bg"], text=c["text"], border=c["border"],
                        label=label, conf=conf_bar, status=status)
                )

            expand = ""
            if prob_rows:
                tbl = (
                    "<table style='width:100%;border-collapse:collapse;margin-top:4px'><thead><tr>"
                    "<th style='padding:5px 10px;font-size:11px;color:#aaa;font-weight:500;text-align:left'>成分</th>"
                    "<th style='padding:5px 10px;font-size:11px;color:#aaa;font-weight:500;text-align:left'>判定类别</th>"
                    "<th style='padding:5px 10px;font-size:11px;color:#aaa;font-weight:500;text-align:left'>置信度（超过阈值则排除）</th>"
                    "<th style='padding:5px 10px;font-size:11px;color:#aaa;font-weight:500;text-align:left'>处理结果</th>"
                    "</tr></thead><tbody>" + "".join(prob_rows) + "</tbody></table>"
                )
                expand = (
                    "<button class='step-detail-toggle' onclick='toggleStepDetail(this)' type='button' style='margin-top:4px'>"
                    "<span class='toggle-arrow'>▶</span><span class='toggle-label'>查看每个成分的详细判定</span></button>"
                    "<div class='step-detail-body'>" + tbl + "</div>"
                )

            summary = (
                "<div style='font-size:12px;color:#555;margin-bottom:8px'>共 <b>{t}</b> 个成分 &nbsp;·&nbsp; "
                "系统排除 <b style='color:#7B52AB'>{e}</b> 个伪迹成分 &nbsp;·&nbsp; "
                "保留 <b style='color:#2E7D5E'>{k}</b> 个脑信号成分</div>"
            ).format(t=n_total, e=n_excluded, k=n_total - n_excluded)

            return (
                "<div style='margin-top:10px'>" + summary +
                "<div style='display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px'>" + "".join(cards) + "</div>" +
                expand + "</div>"
            )

        steps_html = ""
        for sr in r.step_results:
            icon = "⚠️" if sr.warnings else "✅"
            exp = STEP_EXPLANATIONS.get(sr.step_name, {})
            cn_name = exp.get("cn_name", sr.step_name)
            what = exp.get("what", "")
            why = exp.get("why", "")
            analogy = exp.get("analogy", "")

            ica_detail_html = ""
            if sr.step_name == "ica" and isinstance(sr.metrics, dict) and sr.metrics.get("enabled"):
                ica_detail_html = _build_ica_detail(sr.metrics)

            explain_html = ""
            if what:
                explain_html = (
                    "<button class='step-detail-toggle' onclick='toggleStepDetail(this)' type='button'>"
                    "<span class='toggle-arrow'>▶</span><span class='toggle-label'>了解这一步在做什么</span></button>"
                    "<div class='step-detail-body'>"
                    "<div class='step-detail-item'><span class='step-detail-label'>📖 这一步在做什么？</span>" + what + "</div>"
                    "<div class='step-detail-item'><span class='step-detail-label'>❓ 为什么需要这一步？</span>" + why + "</div>"
                    "<div class='step-detail-item step-detail-analogy'><span class='step-detail-label'>💡 通俗理解</span>" + analogy + "</div>"
                    "</div>"
                )

            steps_html += (
                "<tr><td>" + icon + " <strong>" + cn_name + "</strong><br>"
                "<span style='color:#999;font-size:11px'>" + sr.step_name + "</span></td>"
                "<td>" + sr.description + ica_detail_html + explain_html + "</td>"
                "<td>" + f"{sr.duration:.1f}" + "s</td></tr>"
            )
        # steps_html = ""
        # for sr in r.step_results:
        #     icon = "⚠️" if sr.warnings else "✅"
        #     steps_html += f"<tr><td>{icon} {sr.step_name}</td><td>{sr.description}</td><td>{sr.duration:.1f}s</td></tr>"
        
        gc = {"A": "#27AE60", "B": "#2E75B6", "C": "#F39C12", "D": "#E74C3C"}.get(m.quality_grade, "#999")
        gd = {"A": "数据质量优秀，可直接用于后续分析。",
              "B": "数据质量良好，存在少量伪迹残留，建议检查坏导区段。",
              "C": "数据质量一般，存在较多伪迹或坏导，建议手动检查。",
              "D": "数据质量较差，建议重新采集或深度手动清洗。"}.get(m.quality_grade, "")

        # config_json = json.dumps(r.config.model_dump(), indent=2, ensure_ascii=False) if r.config else "{}"
        try:
            config_json = json.dumps(r.config.model_dump(), indent=2, ensure_ascii=False) if r.config else "{}"
        except AttributeError:
            config_json = json.dumps(r.config.dict(), indent=2, ensure_ascii=False) if r.config else "{}"
        plotly_script = f"<script>{get_plotlyjs()}</script>" if HAS_PLOTLY else ""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brainifly 报告 — {info.filename}</title>
{plotly_script}
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',-apple-system,sans-serif;background:#F4F6F9;color:#2C3E50;line-height:1.6}}
.container{{max-width:1100px;margin:0 auto;padding:40px 20px}}
.header{{background:linear-gradient(135deg,#1B3A5C,#2E75B6);color:#fff;padding:40px;border-radius:16px;margin-bottom:30px;box-shadow:0 4px 20px rgba(27,58,92,0.3)}}
.header h1{{font-size:28px;font-weight:700;margin-bottom:6px}}
.header .sub{{font-size:14px;opacity:0.8}}
.meta{{display:flex;gap:20px;margin-top:20px;flex-wrap:wrap}}
.meta-item{{background:rgba(255,255,255,0.15);padding:10px 16px;border-radius:8px;font-size:13px}}
.meta-item .label{{opacity:0.7;font-size:11px;display:block}}
.meta-item .val{{font-weight:600;font-size:16px}}
.banner{{display:flex;align-items:center;gap:30px;background:#fff;padding:30px;border-radius:12px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.grade{{width:80px;height:80px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:36px;font-weight:700;color:#fff;background:{gc};flex-shrink:0}}
.metrics{{display:flex;gap:16px;margin-top:12px;flex-wrap:wrap}}
.metric{{background:#F8F9FA;padding:8px 14px;border-radius:6px;font-size:13px}}
.metric b{{color:#1B3A5C}}
.section{{background:#fff;padding:30px;border-radius:12px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.section h2{{font-size:18px;color:#1B3A5C;margin-bottom:20px;padding-bottom:10px;border-bottom:2px solid #E8ECF1}}
.note{{color:#666;font-size:13px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#F0F4F8;padding:10px 14px;text-align:left;font-weight:600;color:#1B3A5C}}
td{{padding:10px 14px;border-bottom:1px solid #E8ECF1}}
tr:hover td{{background:#F8FAFE}}
pre{{background:#F8F9FA;padding:16px;border-radius:8px;font-size:12px;overflow-x:auto}}
.footer{{text-align:center;padding:30px;color:#999;font-size:12px}}
.nav{{position:fixed;right:20px;top:50%;transform:translateY(-50%);background:#fff;border-radius:10px;padding:12px;box-shadow:0 2px 12px rgba(0,0,0,0.1);z-index:100}}
.nav a{{display:block;padding:6px 10px;color:#666;text-decoration:none;font-size:12px;border-radius:4px}}
.nav a:hover{{background:#F0F4F8;color:#1B3A5C}}
@media(max-width:1300px){{.nav{{display:none}}}}
.step-detail-toggle{{
  display:inline-flex;align-items:center;gap:5px;
  margin-top:8px;padding:4px 12px;
  background:#EEF5FD;border:1px solid #C5D9F1;border-radius:20px;
  font-size:11px;color:#2E75B6;cursor:pointer;
  font-family:inherit;transition:background 0.15s;
}}
.step-detail-toggle:hover{{background:#D9EAFC}}
.toggle-arrow{{transition:transform 0.2s;display:inline-block;font-size:10px}}
.step-detail-toggle.open .toggle-arrow{{transform:rotate(90deg)}}
.step-detail-body{{
  display:none;
  background:#F0F7FF;border-left:3px solid #2E75B6;
  padding:12px 16px;margin:6px 0 4px;
  border-radius:0 6px 6px 0;font-size:12px;line-height:1.8;
}}
.step-detail-body.open{{display:block}}
.step-detail-item{{margin-bottom:6px;color:#333}}
.step-detail-item:last-child{{margin-bottom:0}}
.step-detail-analogy{{color:#555;font-style:italic}}
.step-detail-label{{display:block;color:#1B3A5C;font-weight:600;margin-bottom:2px}}
</style>
</head>
<body>
<nav class="nav">
<a href="#summary">📊 摘要</a>
<a href="#psd">📈 PSD</a>
<a href="#waveform">〰️ 波形</a>
<a href="#channels">📡 通道</a>
<a href="#bands">🎯 频段</a>
<a href="#topomap">🧠 Topomap</a>
<a href="#steps">⚙️ 步骤</a>
<a href="#params">📋 参数</a>
</nav>
<div class="container">

<div class="header">
<h1>Brainifly 数据质量报告</h1>
<p class="sub">Brainifly EEG Data Cleaning &amp; Assessment Report</p>
<div class="meta">
<div class="meta-item"><span class="label">文件</span><span class="val">{info.filename}</span></div>
<div class="meta-item"><span class="label">通道</span><span class="val">{info.n_channels}</span></div>
<div class="meta-item"><span class="label">采样率</span><span class="val">{info.sfreq} Hz</span></div>
<div class="meta-item"><span class="label">时长</span><span class="val">{info.duration_str}</span></div>
<div class="meta-item"><span class="label">格式</span><span class="val">{info.file_format}</span></div>
<div class="meta-item"><span class="label">生成时间</span><span class="val">{datetime.now().strftime("%Y-%m-%d %H:%M")}</span></div>
</div>
</div>

<div class="banner" id="summary">
<div class="grade">{m.quality_grade}</div>
<div>
<h2 style="font-size:22px">质量评分: {m.quality_score}/100</h2>
<p style="color:#666;font-size:14px">{gd}</p>
<div class="metrics">
<div class="metric">SNR 改善: <b>{m.snr_improvement_db:+.1f} dB</b></div>
<div class="metric">坏导: <b>{m.n_bad_channels}</b> 个</div>
<div class="metric">ICA 排除: <b>{m.n_ica_excluded}/{m.n_ica_components}</b> 成分</div>
<div class="metric">耗时: <b>{r.total_duration:.1f}s</b></div>
</div>
</div>
</div>

<div class="section">{chart_htmls.get("quality_gauge", "")}</div>

<div class="section" id="psd">
<h2>📈 功率谱密度 (PSD) 对比</h2>
<p class="note">红色虚线为清洗前，绿色实线为清洗后。清洗后高频噪声和工频干扰应显著降低。</p>
{chart_htmls.get("psd_comparison", "<p>图表不可用</p>")}
</div>

<div class="section" id="waveform">
<h2>〰️ 时域波形对比</h2>
<p class="note">展示部分通道的原始波形和清洗后波形，清洗后应可见伪迹减少、信号更平稳。</p>
{chart_htmls.get("waveform_comparison", "<p>图表不可用</p>")}
</div>

<div class="section" id="channels">
<h2>📡 通道质量分析</h2>
{chart_htmls.get("channel_std", "<p>图表不可用</p>")}
</div>

<div class="section" id="bands">
<h2>🎯 频段功率分布</h2>
<p class="note">δ(0.5-4Hz) θ(4-8Hz) α(8-13Hz) β(13-30Hz) γ(30-45Hz) 各频段功率对比。</p>
{chart_htmls.get("band_power", "<p>图表不可用</p>")}
</div>

<div class="section" id="topomap">
<h2>🧠 空间 Topomap 对比</h2>
<p class="note">展示 α 频段在头皮空间上的分布变化。左侧为清洗前，中间为清洗后，右侧为清洗后相对清洗前的变化。</p>
{chart_htmls.get("topomap_comparison", "<p>图表不可用</p>")}
</div>

<div class="section" id="steps">
<h2>⚙️ 清洗步骤详情</h2>
{chart_htmls.get("step_timeline", "")}
<table><thead><tr><th>步骤</th><th>描述</th><th>耗时</th></tr></thead>
<tbody>{steps_html}</tbody></table>
</div>

<div class="section" id="params">
<h2>📋 处理参数记录</h2>
<p class="note">完整的处理参数，可用于复现清洗流程。</p>
<pre>{config_json}</pre>
</div>

<div class="footer">
<p>Generated by <strong>Brainifly</strong> v1.0 — EEG Data Cleaning &amp; Assessment System</p>
<p>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</div>

</div>
</body>
<script>
function toggleStepDetail(btn) {{
  var body = btn.nextElementSibling;
  var isOpen = body.classList.contains('open');
  body.classList.toggle('open');
  btn.classList.toggle('open');
  btn.querySelector('.toggle-label').textContent = isOpen ? '了解这一步在做什么' : '收起详情';
}}
</script>
</html>"""

    def _build_pdf_html_en(self, generated_at: str) -> str:
        result = self.result
        metrics = result.metrics
        info = result.dataset_info
        grade_color = self._grade_color(metrics.quality_grade)
        channel_type_text = ", ".join(
            f"{escape(str(name))}: {count}" for name, count in sorted((info.channel_types or {}).items())
        ) or "-"
        meas_date = info.meas_date.strftime("%Y-%m-%d %H:%M:%S") if info.meas_date else "-"

        summary_rows = [
            ['<span class="label-cell">Filename</span>', escape(info.filename), '<span class="label-cell">Format</span>', escape(info.file_format)],
            ['<span class="label-cell">Sampling rate</span>', f"{info.sfreq:.2f} Hz", '<span class="label-cell">Duration</span>', escape(info.duration_str)],
            ['<span class="label-cell">Channels</span>', str(info.n_channels), '<span class="label-cell">Channel types</span>', channel_type_text],
            ['<span class="label-cell">Samples</span>', str(info.n_samples), '<span class="label-cell">File size</span>', f"{info.file_size_mb:.2f} MB"],
            ['<span class="label-cell">Hardware high-pass / low-pass</span>', f"{info.highpass:.2f} / {info.lowpass:.2f} Hz", '<span class="label-cell">Acquisition time</span>', escape(meas_date)],
            ['<span class="label-cell">Quality score</span>', f"{metrics.quality_score}/100", '<span class="label-cell">Quality grade</span>', f'<span class="grade-badge" style="color:{grade_color};border-color:{grade_color}">{escape(metrics.quality_grade)}</span>'],
            ['<span class="label-cell">SNR (before / after)</span>', f"{metrics.snr_before:.2f} / {metrics.snr_after:.2f} dB", '<span class="label-cell">SNR improvement</span>', f"{metrics.snr_improvement_db:+.2f} dB"],
            ['<span class="label-cell">Bad channels / ratio</span>', f"{metrics.n_bad_channels} / {metrics.bad_channel_ratio * 100:.1f}%", '<span class="label-cell">ICA excluded / total</span>', f"{metrics.n_ica_excluded} / {metrics.n_ica_components}"],
            ['<span class="label-cell">Processing time</span>', f"{result.total_duration:.2f} s", '<span class="label-cell">Generated at</span>', escape(generated_at)],
        ]

        recommendation_items = "".join(f"<li>{escape(item)}</li>" for item in self._build_quality_recommendations())

        band_rows = []
        for band in ["delta", "theta", "alpha", "beta", "gamma"]:
            before = float(metrics.power_bands_before.get(band, 0.0))
            after = float(metrics.power_bands_after.get(band, 0.0))
            delta = after - before
            rel_change = "-" if abs(before) < 1e-12 else f"{(delta / before) * 100:+.1f}%"
            band_rows.append([escape(band), f"{before:.4f}", f"{after:.4f}", f"{delta:+.4f}", rel_change])

        step_rows = []
        for step in result.step_results:
            if step.warnings:
                status = '<span class="status-badge status-warning">Warning</span>'
            elif isinstance(step.metrics, dict) and step.metrics.get("enabled") is False:
                status = '<span class="status-badge status-muted">Skipped</span>'
            else:
                status = '<span class="status-badge status-success">Done</span>'
            step_rows.append([
                escape(self._step_title(step.step_name)),
                status,
                f"{step.duration:.2f}",
                escape(step.description),
                self._build_step_metric_summary(step),
            ])

        bad_step = self._find_step("bad_channels")
        bad_metrics = bad_step.metrics if bad_step else {}
        bad_rows = [[
            self._esc(bad_metrics.get("n_bad_channels"), digits=0),
            self._esc(bad_metrics.get("bad_ratio_pct")),
            self._esc(bad_metrics.get("interpolated")),
            self._esc(bad_metrics.get("bad_channels")),
        ]] if bad_step else []

        channel_rows = self._channel_stat_rows(limit=15)

        asr_step = self._find_step("asr")
        asr_rows = []
        if asr_step:
            asr_metrics = asr_step.metrics or {}
            asr_status = "Skipped" if asr_metrics.get("enabled") is False else ("Warning" if asr_step.warnings else "Done")
            asr_rows.append([
                escape(asr_status),
                self._esc(asr_metrics.get("cutoff")),
                self._esc(asr_metrics.get("modified_data_pct")),
                f"{self._esc(asr_metrics.get('max_amplitude_before_uv'))} → {self._esc(asr_metrics.get('max_amplitude_after_uv'))}",
                "<br>".join(escape(message) for message in asr_step.warnings) if asr_step.warnings else "-",
            ])

        ica_step = self._find_step("ica")
        ica_summary_rows: list[list[str]] = []
        ica_component_rows: list[list[str]] = []
        if ica_step and ica_step.metrics.get("enabled"):
            ica_metrics = ica_step.metrics
            label_distribution = ica_metrics.get("label_distribution") or {}
            distribution_text = ", ".join(
                f"{label}: {count}" for label, count in sorted(label_distribution.items(), key=lambda item: (-item[1], item[0]))
            ) or "-"
            ica_summary_rows = [[
                self._esc(ica_metrics.get("n_components"), digits=0),
                self._esc(ica_metrics.get("n_excluded"), digits=0),
                self._esc(ica_metrics.get("threshold")),
                escape(distribution_text),
            ]]

            excluded_indices = {int(index) for index in (ica_metrics.get("excluded_indices") or [])}
            component_probs = ica_metrics.get("component_probs") or {}
            for component_index, entry in sorted(component_probs.items(), key=lambda item: int(item[0])):
                idx = int(component_index)
                label = escape(str(entry.get("label", "-")))
                confidence = float(entry.get("confidence", 0.0)) * 100
                action = (
                    '<span class="status-badge status-danger">Excluded</span>'
                    if idx in excluded_indices
                    else '<span class="status-badge status-success">Kept</span>'
                )
                ica_component_rows.append([f"IC {idx:02d}", label, f"{confidence:.1f}%", action])

        config_rows = [[escape(path), escape(value)] for path, value in self._flatten_config(result.config)]

        summary_table = self._render_table(["Field", "Value", "Field", "Value"], summary_rows, "report-table summary-table")
        band_table = self._render_table(["Band", "Before (µV²)", "After (µV²)", "Delta", "Relative change"], band_rows)
        step_table = self._render_table(["Step", "Status", "Duration (s)", "Description", "Key metrics"], step_rows)
        bad_table = self._render_table(["Bad channels", "Bad-channel ratio (%)", "Interpolated", "Channel list"], bad_rows)
        channel_table = self._render_table(["Channel", "Std before (µV)", "Std after (µV)", "Delta", "Relative change"], channel_rows)
        asr_table = self._render_table(["Status", "ASR cutoff", "Modified points (%)", "Max amplitude before/after (µV)", "Notes"], asr_rows)
        ica_summary_table = self._render_table(["Total components", "Excluded", "Threshold", "Label distribution"], ica_summary_rows)
        ica_component_table = self._render_table(["Component", "Predicted label", "Confidence", "Action"], ica_component_rows, "report-table compact-table")
        config_table = self._render_table(["Parameter path", "Value"], config_rows, "report-table compact-table")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Brainifly PDF Report — {escape(info.filename)}</title>
<style>
@page {{
  size: A4;
  margin: 15mm 12mm 16mm 12mm;
  @bottom-right {{
    content: "Page " counter(page) " / " counter(pages);
    font-size: 9px;
    color: #6b7280;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
  color: #111827;
  font-size: 11px;
  line-height: 1.55;
}}
h1, h2, h3, p {{ margin: 0; }}
.report-shell {{ width: 100%; }}
.cover {{
  border-bottom: 2px solid #1f4b7a;
  padding-bottom: 10px;
  margin-bottom: 16px;
}}
.cover-kicker {{
  font-size: 10px;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: #4b5563;
  margin-bottom: 6px;
}}
.cover h1 {{
  font-size: 22px;
  color: #0f2740;
  margin-bottom: 6px;
}}
.cover-meta {{
  font-size: 10px;
  color: #4b5563;
}}
.quality-box {{
  margin-top: 12px;
  border: 1px solid #cbd5e1;
  border-left: 5px solid {grade_color};
  padding: 10px 12px;
  background: #f8fafc;
}}
.quality-line {{
  margin-top: 4px;
  color: #334155;
}}
.section {{
  margin-top: 16px;
}}
.section h2 {{
  font-size: 13px;
  color: #0f2740;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #cbd5e1;
}}
.section-note {{
  color: #475569;
  margin-bottom: 8px;
}}
.report-table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}}
.report-table thead {{
  display: table-header-group;
}}
.report-table tr {{
  page-break-inside: avoid;
}}
.report-table th,
.report-table td {{
  border: 1px solid #cbd5e1;
  padding: 6px 7px;
  vertical-align: top;
  word-wrap: break-word;
}}
.report-table th {{
  background: #e2e8f0;
  color: #0f2740;
  font-weight: 700;
}}
.summary-table td:nth-child(1),
.summary-table td:nth-child(3) {{
  background: #f8fafc;
  font-weight: 600;
  width: 18%;
}}
.label-cell {{
  color: #334155;
}}
.grade-badge {{
  display: inline-block;
  padding: 2px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-weight: 700;
}}
.status-badge {{
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid transparent;
}}
.status-success {{ color: #166534; background: #dcfce7; border-color: #86efac; }}
.status-warning {{ color: #92400e; background: #fef3c7; border-color: #fcd34d; }}
.status-danger {{ color: #991b1b; background: #fee2e2; border-color: #fca5a5; }}
.status-muted {{ color: #475569; background: #e2e8f0; border-color: #cbd5e1; }}
.compact-table td,
.compact-table th {{ padding: 5px 6px; font-size: 10px; }}
.finding-list {{ margin: 0; padding-left: 18px; }}
.finding-list li {{ margin: 4px 0; }}
.empty-note {{ color: #64748b; font-style: italic; }}
.page-break {{ page-break-before: always; }}
.footer-note {{ margin-top: 16px; font-size: 9px; color: #6b7280; text-align: right; }}
</style>
</head>
<body>
<div class="report-shell">
  <div class="cover">
    <div class="cover-kicker">Brainifly EEG Cleaning Report</div>
    <h1>EEG Cleaning Quality Report</h1>
    <div class="cover-meta">File: {escape(info.filename)} | Generated: {escape(generated_at)} | System: Brainifly</div>
    <div class="quality-box">
      <div><strong>Overall conclusion</strong>: Grade {escape(metrics.quality_grade)}, score {metrics.quality_score}/100</div>
      <div class="quality-line">{escape(self._grade_description(metrics.quality_grade))}</div>
    </div>
  </div>

  <div class="section"><h2>1. Data and quality summary</h2>{summary_table}</div>
  <div class="section"><h2>2. Recommendations</h2><ul class="finding-list">{recommendation_items}</ul></div>
  <div class="section"><h2>3. Band power statistics</h2><p class="section-note">The table below compares standard EEG bands before and after cleaning.</p>{band_table}</div>
  <div class="section"><h2>4. Processing steps</h2><p class="section-note">This section records status, duration, automatic decisions, and key metrics for each processing step.</p>{step_table}</div>
  <div class="section"><h2>5. Channel quality</h2><p class="section-note">Bad-channel detection is summarized first, followed by the 15 channels with the highest post-cleaning standard deviation.</p>{bad_table}<div style="height:8px"></div>{channel_table}</div>
  <div class="section"><h2>6. ASR outcome</h2>{asr_table}</div>
  <div class="section page-break"><h2>7. ICA summary</h2><p class="section-note">Overall ICA statistics followed by per-component automatic labels and actions.</p>{ica_summary_table}</div>
  <div class="section"><h2>8. ICA component details</h2>{ica_component_table}</div>
  <div class="section page-break"><h2>9. Parameter record</h2><p class="section-note">The following parameters come from the actual execution config and can be used for reproducibility and audit.</p>{config_table}</div>

  <div class="footer-note">The PDF version is a static archive. Please open the HTML report for interactive charts and in-page navigation.</div>
</div>
</body>
</html>"""

    def _build_html_en(self, chart_htmls: dict[str, str]) -> str:
        r = self.result
        m = r.metrics
        info = r.dataset_info
        grade_color = {"A": "#27AE60", "B": "#2E75B6", "C": "#F39C12", "D": "#E74C3C"}.get(m.quality_grade, "#999")
        grade_description = self._grade_description(m.quality_grade)
        try:
            config_json = json.dumps(r.config.model_dump(), indent=2, ensure_ascii=False) if r.config else "{}"
        except AttributeError:
            config_json = json.dumps(r.config.dict(), indent=2, ensure_ascii=False) if r.config else "{}"
        plotly_script = f"<script>{get_plotlyjs()}</script>" if HAS_PLOTLY else ""

        step_rows = []
        for step in r.step_results:
            icon = "⚠️" if step.warnings else "✅"
            step_rows.append(
                "<tr><td>"
                + icon
                + " <strong>"
                + escape(self._step_title(step.step_name))
                + "</strong><br><span style='color:#999;font-size:11px'>"
                + escape(step.step_name)
                + "</span></td><td>"
                + escape(step.description)
                + "</td><td>"
                + f"{step.duration:.1f}s"
                + "</td></tr>"
            )

        nav_items = [
            ("summary", "Summary"),
            ("psd", "PSD"),
            ("waveform", "Waveform"),
            ("channels", "Channels"),
            ("bands", "Bands"),
            ("topomap", "Topomap"),
            ("steps", "Steps"),
            ("params", "Parameters"),
        ]

        nav_html = "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in nav_items)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brainifly Report — {info.filename}</title>
{plotly_script}
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',-apple-system,sans-serif;background:#F4F6F9;color:#2C3E50;line-height:1.6}}
.container{{max-width:1100px;margin:0 auto;padding:40px 20px}}
.header{{background:linear-gradient(135deg,#1B3A5C,#2E75B6);color:#fff;padding:40px;border-radius:16px;margin-bottom:30px;box-shadow:0 4px 20px rgba(27,58,92,0.3)}}
.header h1{{font-size:28px;font-weight:700;margin-bottom:6px}}
.header .sub{{font-size:14px;opacity:0.82}}
.meta{{display:flex;gap:20px;margin-top:20px;flex-wrap:wrap}}
.meta-item{{background:rgba(255,255,255,0.15);padding:10px 16px;border-radius:8px;font-size:13px}}
.meta-item .label{{opacity:0.7;font-size:11px;display:block}}
.meta-item .val{{font-weight:600;font-size:16px}}
.banner{{display:flex;align-items:center;gap:30px;background:#fff;padding:30px;border-radius:12px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.grade{{width:80px;height:80px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:36px;font-weight:700;color:#fff;background:{grade_color};flex-shrink:0}}
.metrics{{display:flex;gap:16px;margin-top:12px;flex-wrap:wrap}}
.metric{{background:#F8F9FA;padding:8px 14px;border-radius:6px;font-size:13px}}
.metric b{{color:#1B3A5C}}
.section{{background:#fff;padding:30px;border-radius:12px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.section h2{{font-size:18px;color:#1B3A5C;margin-bottom:20px;padding-bottom:10px;border-bottom:2px solid #E8ECF1}}
.note{{color:#666;font-size:13px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#F0F4F8;padding:10px 14px;text-align:left;font-weight:600;color:#1B3A5C}}
td{{padding:10px 14px;border-bottom:1px solid #E8ECF1}}
tr:hover td{{background:#F8FAFE}}
pre{{background:#F8F9FA;padding:16px;border-radius:8px;font-size:12px;overflow-x:auto}}
.footer{{text-align:center;padding:30px;color:#999;font-size:12px}}
.nav{{position:fixed;right:20px;top:50%;transform:translateY(-50%);background:#fff;border-radius:10px;padding:12px;box-shadow:0 2px 12px rgba(0,0,0,0.1);z-index:100}}
.nav a{{display:block;padding:6px 10px;color:#666;text-decoration:none;font-size:12px;border-radius:4px}}
.nav a:hover{{background:#F0F4F8;color:#1B3A5C}}
@media(max-width:1300px){{.nav{{display:none}}}}
</style>
</head>
<body>
<nav class="nav">{nav_html}</nav>
<div class="container">

<div class="header">
<h1>Brainifly EEG Quality Report</h1>
<p class="sub">Brainifly EEG Data Cleaning &amp; Assessment Report</p>
<div class="meta">
<div class="meta-item"><span class="label">File</span><span class="val">{info.filename}</span></div>
<div class="meta-item"><span class="label">Channels</span><span class="val">{info.n_channels}</span></div>
<div class="meta-item"><span class="label">Sampling rate</span><span class="val">{info.sfreq} Hz</span></div>
<div class="meta-item"><span class="label">Duration</span><span class="val">{info.duration_str}</span></div>
<div class="meta-item"><span class="label">Format</span><span class="val">{info.file_format}</span></div>
<div class="meta-item"><span class="label">Generated</span><span class="val">{datetime.now().strftime("%Y-%m-%d %H:%M")}</span></div>
</div>
</div>

<div class="banner" id="summary">
<div class="grade">{m.quality_grade}</div>
<div>
<h2 style="font-size:22px">Quality score: {m.quality_score}/100</h2>
<p style="color:#666;font-size:14px">{grade_description}</p>
<div class="metrics">
<div class="metric">SNR improvement: <b>{m.snr_improvement_db:+.1f} dB</b></div>
<div class="metric">Bad channels: <b>{m.n_bad_channels}</b></div>
<div class="metric">ICA excluded: <b>{m.n_ica_excluded}/{m.n_ica_components}</b></div>
<div class="metric">Runtime: <b>{r.total_duration:.1f}s</b></div>
</div>
</div>
</div>

<div class="section">{chart_htmls.get("quality_gauge", "")}</div>

<div class="section" id="psd">
<h2>PSD comparison</h2>
<p class="note">The dotted line shows the recording before cleaning and the solid line shows the cleaned result.</p>
{chart_htmls.get("psd_comparison", "<p>Chart unavailable</p>")}
</div>

<div class="section" id="waveform">
<h2>Waveform comparison</h2>
<p class="note">Selected channels are shown before and after cleaning to visualize artifact reduction and waveform stabilization.</p>
{chart_htmls.get("waveform_comparison", "<p>Chart unavailable</p>")}
</div>

<div class="section" id="channels">
<h2>Channel quality analysis</h2>
{chart_htmls.get("channel_std", "<p>Chart unavailable</p>")}
</div>

<div class="section" id="bands">
<h2>Band power distribution</h2>
<p class="note">Comparison across delta, theta, alpha, beta, and gamma bands.</p>
{chart_htmls.get("band_power", "<p>Chart unavailable</p>")}
</div>

<div class="section" id="topomap">
<h2>Spatial topomap comparison</h2>
<p class="note">Alpha-band topographies before and after cleaning, plus the relative change map.</p>
{chart_htmls.get("topomap_comparison", "<p>Chart unavailable</p>")}
</div>

<div class="section" id="steps">
<h2>Processing steps</h2>
{chart_htmls.get("step_timeline", "")}
<table><thead><tr><th>Step</th><th>Description</th><th>Duration</th></tr></thead>
<tbody>{''.join(step_rows)}</tbody></table>
</div>

<div class="section" id="params">
<h2>Processing parameters</h2>
<p class="note">The full execution config is recorded here for reproducibility.</p>
<pre>{config_json}</pre>
</div>

<div class="footer">
<p>Generated by <strong>Brainifly</strong> v1.0 — EEG Data Cleaning &amp; Assessment System</p>
<p>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</div>

</div>
</body>
</html>"""


def generate_report(pipeline_result, output_dir, formats=None):
    if formats is None:
        formats = ["html"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = pipeline_result.dataset_info.filename.rsplit(".", 1)[0]
    gen = ReportGenerator(pipeline_result)
    gen.generate_figures()
    results = {}
    if "html" in formats:
        results["html"] = gen.generate_html(output_dir / f"{basename}_report.html")
    if "pdf" in formats:
        results["pdf"] = gen.generate_pdf(output_dir / f"{basename}_report.pdf")
    return results
