"""
Brainifly 清洗流水线编排器

核心职责:
1. 按顺序串联各清洗步骤
2. 记录每步的处理日志和指标
3. 保存清洗前后的数据
4. 计算综合质量指标
5. 支持自定义步骤和参数

默认流水线:
  滤波 → 坏导检测 → 重参考 → ASR → ICA → (Epoch)
"""
from pathlib import Path
from dataclasses import dataclass, field
from time import time
from typing import Callable

import mne
from loguru import logger
from rich.console import Console
from rich.table import Table

from config import PipelineConfig
from core.loader import EEGLoader, DatasetInfo
from core.steps.base import BaseStep, StepResult
from core.steps import (
    FilteringStep,
    BadChannelStep,
    ReferenceStep,
    ASRStep,
    ICAStep,
    EpochStep,
)
from core.quality import compute_quality_metrics, QualityMetrics
from core.exporter import DataExporter

console = Console()


@dataclass
class PipelineResult:
    """流水线执行结果"""
    # 数据
    raw_before: mne.io.Raw         # 原始数据
    raw_after: mne.io.Raw          # 清洗后数据
    dataset_info: DatasetInfo      # 数据集元信息

    # 步骤结果
    step_results: list[StepResult] = field(default_factory=list)

    # 质量指标
    metrics: QualityMetrics | None = None

    # 导出路径
    exported_files: dict = field(default_factory=dict)  # {"fif": Path, "edf": Path, ...}
    export_errors: dict = field(default_factory=dict)   # {"edf": "error message"}

    # 总耗时
    total_duration: float = 0.0

    # 上下文 (ICA 对象等，报告模块需要)
    context: dict = field(default_factory=dict)

    # 配置
    config: PipelineConfig | None = None

    def print_summary(self):
        """在终端打印漂亮的结果摘要"""
        console.print("\n" + "=" * 60, style="blue")
        console.print("  Brainifly 清洗报告摘要", style="bold cyan")
        console.print("=" * 60, style="blue")

        # 数据集信息
        console.print(f"\n📁 {self.dataset_info.summary()}\n")

        # 步骤表格
        table = Table(title="清洗步骤", show_header=True, header_style="bold magenta")
        table.add_column("步骤", style="cyan", width=16)
        table.add_column("描述", width=50)
        table.add_column("耗时", justify="right", style="green", width=8)

        for r in self.step_results:
            status = "✓" if not r.warnings else "⚠"
            table.add_row(
                f"{status} {r.step_name}",
                r.description[:50],
                f"{r.duration:.1f}s",
            )

        console.print(table)

        # 质量评分
        if self.metrics:
            m = self.metrics
            grade_colors = {"A": "green", "B": "blue", "C": "yellow", "D": "red"}
            color = grade_colors.get(m.quality_grade, "white")

            console.print(f"\n📊 质量评分: [{color} bold]{m.quality_score}/100 ({m.quality_grade})[/]")
            console.print(f"   SNR: {m.snr_before} → {m.snr_after} dB (改善 {m.snr_improvement_db} dB)")
            console.print(f"   坏导: {m.n_bad_channels} 个 | ICA 排除: {m.n_ica_excluded}/{m.n_ica_components} 个成分")

        # 导出文件
        if self.exported_files:
            console.print("\n📦 导出文件:")
            for fmt, path in self.exported_files.items():
                console.print(f"   {fmt}: {path}")

        console.print(f"\n⏱ 总耗时: {self.total_duration:.1f}s")
        console.print("=" * 60 + "\n", style="blue")


class CleaningPipeline:
    """EEG 清洗流水线"""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.steps: list[BaseStep] = []
        self._progress_callback: Callable | None = None

    def add_step(self, step: BaseStep) -> "CleaningPipeline":
        """链式添加清洗步骤"""
        self.steps.append(step)
        return self

    def on_progress(self, callback: Callable) -> "CleaningPipeline":
        """
        注册进度回调 (用于 Web 端实时推送)

        callback 签名:
        (step_index, total_steps, step_name, status, step_result=None, dataset_info=None) -> None
        """
        self._progress_callback = callback
        return self

    def run(self, raw: mne.io.Raw, filepath: str | Path | None = None) -> PipelineResult:
        """
        执行完整清洗流水线

        Args:
            raw: 输入的 MNE Raw 数据 (会被 copy，不修改原始数据)
            filepath: 原始文件路径 (用于元信息)

        Returns:
            PipelineResult 包含清洗前后数据、步骤结果、质量指标
        """
        t0 = time()

        # 保留原始数据副本
        raw_before = raw.copy()
        raw_current = raw.copy()

        # 提取元信息
        dataset_info = EEGLoader.extract_metadata(raw_before, filepath)

        logger.info(f"开始清洗: {dataset_info.filename}")
        logger.info(f"  {dataset_info.n_channels} 通道, {dataset_info.sfreq} Hz, {dataset_info.duration_str}")
        logger.info(f"  清洗步骤: {' → '.join(s.name for s in self.steps)}")

        # 逐步执行
        step_results = []
        context = {"report_language": self.config.report_language}
        total_steps = len(self.steps)

        if self._progress_callback:
            self._progress_callback(
                -1,
                total_steps,
                "metadata",
                "ready",
                dataset_info=dataset_info,
                step_result=None,
            )

        for i, step in enumerate(self.steps):
            # 进度回调
            if self._progress_callback:
                self._progress_callback(
                    i,
                    total_steps,
                    step.name,
                    "running",
                    dataset_info=dataset_info,
                    step_result=None,
                )

            raw_current, result = step.run(raw_current, context)
            step_results.append(result)

            if self._progress_callback:
                status = "done" if not result.warnings else "warning"
                self._progress_callback(
                    i,
                    total_steps,
                    step.name,
                    status,
                    dataset_info=dataset_info,
                    step_result=result,
                )

        # 计算质量指标
        logger.info("计算质量指标...")
        metrics = compute_quality_metrics(raw_before, raw_current, step_results)

        total_duration = time() - t0

        result = PipelineResult(
            raw_before=raw_before,
            raw_after=raw_current,
            dataset_info=dataset_info,
            step_results=step_results,
            metrics=metrics,
            total_duration=total_duration,
            context=context,
            config=self.config,
        )

        logger.info(f"清洗完成! 质量评分: {metrics.quality_score}/100 ({metrics.quality_grade})")
        return result

    def run_and_export(
        self,
        raw: mne.io.Raw,
        filepath: str | Path,
        output_dir: str | Path,
        export_basename: str | None = None,
    ) -> PipelineResult:
        """
        执行清洗并自动导出结果

        这是最常用的一站式方法:
        加载 → 清洗 → 导出清洗数据 → (后续可生成报告)
        """
        result = self.run(raw, filepath)

        # 导出清洗后的数据
        basename = export_basename or Path(filepath).stem
        result.exported_files, result.export_errors = DataExporter.export(
            raw=result.raw_after,
            output_dir=output_dir,
            basename=basename,
            formats=self.config.export_formats,
        )

        return result

    @staticmethod
    def build_default(config: PipelineConfig | None = None) -> "CleaningPipeline":
        """
        构建默认清洗流水线

        滤波 → 坏导检测 → 重参考 → ASR → ICA → (Epoch)
        """
        config = config or PipelineConfig()

        pipeline = CleaningPipeline(config)
        pipeline.add_step(FilteringStep(config.filter))
        pipeline.add_step(BadChannelStep(config.bad_channel))
        pipeline.add_step(ReferenceStep(config.reference))
        pipeline.add_step(ASRStep(config.asr))
        pipeline.add_step(ICAStep(config.ica))

        if config.epoch.enabled:
            pipeline.add_step(EpochStep(config.epoch))

        return pipeline


# ==================== 便捷函数 ====================

def clean_file(
    filepath: str | Path,
    output_dir: str | Path | None = None,
    config: PipelineConfig | None = None,
    print_summary: bool = True,
) -> PipelineResult:
    """
    一站式清洗函数: 加载文件 → 清洗 → 导出 → 打印结果

    最简使用方式:
        from core.pipeline import clean_file
        result = clean_file("S001R01.edf")

    Args:
        filepath: EEG 文件路径
        output_dir: 输出目录 (默认: 同目录/cleaned/)
        config: 清洗配置 (默认: 标准参数)
        print_summary: 是否在终端打印结果

    Returns:
        PipelineResult
    """
    filepath = Path(filepath)

    if output_dir is None:
        output_dir = filepath.parent / "cleaned"

    effective_config = config or PipelineConfig()

    # 加载
    raw = EEGLoader.load(filepath, input_adapter=effective_config.input_adapter)

    # 构建并执行流水线
    pipeline = CleaningPipeline.build_default(effective_config)
    result = pipeline.run_and_export(raw, filepath, output_dir)

    if print_summary:
        result.print_summary()

    return result
