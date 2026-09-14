"""
清洗数据导出器

将清洗后的 MNE Raw 数据导出为不同格式:
- FIF: MNE 原生格式，无损，推荐用于后续 Python 分析
- EDF: 通用格式，兼容性最好，可在 EEGLAB/BrainVision 等工具中打开
- CSV: 便于进入 R / MATLAB / Excel / 自定义统计流水线继续分析
"""
import csv
from pathlib import Path

import mne
from loguru import logger


class DataExporter:
    """清洗数据导出器"""

    @staticmethod
    def export_fif(raw: mne.io.Raw, output_path: str | Path) -> Path:
        """导出为 FIF 格式 (无损)"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ★ 修复: 使用 MNE 规范命名 xxx_raw.fif
        stem = output_path.stem
        if not any(stem.endswith(s) for s in ("_raw", "_eeg", "_meg")):
            output_path = output_path.parent / f"{stem}_raw.fif"

        raw.save(output_path, overwrite=True, verbose=False)
        size_mb = output_path.stat().st_size / 1024 / 1024
        logger.info(f"已导出 FIF: {output_path.name} ({size_mb:.1f} MB)")
        return output_path

    @staticmethod
    def export_edf(raw: mne.io.Raw, output_path: str | Path) -> Path:
        """导出为 EDF 格式 (通用)"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not str(output_path).endswith(".edf"):
            output_path = output_path.with_suffix(".edf")

        mne.export.export_raw(output_path, raw, fmt="edf", overwrite=True, verbose=False)
        size_mb = output_path.stat().st_size / 1024 / 1024
        logger.info(f"已导出 EDF: {output_path.name} ({size_mb:.1f} MB)")
        return output_path

    @staticmethod
    def export_csv(raw: mne.io.Raw, output_path: str | Path) -> Path:
        """导出为宽表 CSV: time_s + 每个通道 1 列，数值单位为 µV"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not str(output_path).endswith(".csv"):
            output_path = output_path.with_suffix(".csv")

        data_uv = (raw.get_data() * 1e6).T
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time_s", *raw.ch_names])
            for time_value, row in zip(raw.times, data_uv):
                writer.writerow([f"{float(time_value):.6f}", *[f"{float(value):.6f}" for value in row]])

        size_mb = output_path.stat().st_size / 1024 / 1024
        logger.info(f"已导出 CSV: {output_path.name} ({size_mb:.1f} MB)")
        return output_path

    @staticmethod
    def export(
        raw: mne.io.Raw,
        output_dir: str | Path,
        basename: str,
        formats: list[str],
    ) -> tuple[dict[str, Path], dict[str, str]]:
        """
        批量导出多种格式

        Args:
            raw: 清洗后的数据
            output_dir: 输出目录
            basename: 文件基础名 (不含扩展名)
            formats: 要导出的格式列表 ["fif", "edf", "csv"]

        Returns:
            ({格式: 文件路径}, {格式: 错误信息}) 元组
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = {}
        errors = {}

        for fmt in formats:
            try:
                if fmt == "fif":
                    output_path = output_dir / f"{basename}_cleaned_raw.fif"
                    results["fif"] = DataExporter.export_fif(raw, output_path)
                elif fmt == "edf":
                    output_path = output_dir / f"{basename}_cleaned.edf"
                    results["edf"] = DataExporter.export_edf(raw, output_path)
                elif fmt == "csv":
                    output_path = output_dir / f"{basename}_cleaned.csv"
                    results["csv"] = DataExporter.export_csv(raw, output_path)
                else:
                    logger.warning(f"不支持的导出格式: {fmt}")
                    errors[fmt] = f"不支持的导出格式: {fmt}"
            except Exception as exc:  # pragma: no cover - runtime dependent
                errors[fmt] = str(exc)
                logger.warning(f"导出 {fmt} 失败，已跳过: {exc}")

        return results, errors
