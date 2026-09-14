"""
Step 5: ICA + ICLabel 自动伪迹去除

核心流程:
1. 运行 ICA 分解，将多通道 EEG 分解为独立成分
2. 使用 ICLabel 自动分类每个成分（脑/眼/肌肉/心脏/线噪/通道噪声/其他）
3. 将伪迹概率超过阈值的成分排除
4. 用剩余成分重构信号

这是 EEG 清洗中最关键的一步，对眼电和心电伪迹效果极佳。
"""
import warnings

import numpy as np
import mne
from mne.preprocessing import ICA
from loguru import logger

from .base import BaseStep
from config import ICAConfig


# ICLabel 的类别标签
ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other",
]


class ICAStep(BaseStep):
    name = "ica"

    def __init__(self, config: ICAConfig | None = None):
        self.config = config or ICAConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"
        if not self.config.enabled:
            return raw, {"language": language, "enabled": False, "reason": "ICA disabled" if language == "en" else "ICA 已禁用"}

        raw = raw.copy()
        cfg = self.config

        eeg_picks = mne.pick_types(raw.info, eeg=True)
        n_channels = len(eeg_picks)

        if n_channels < 3:
            return raw, {"language": language, "enabled": False, "reason": "At least 3 EEG channels are required" if language == "en" else "EEG 通道不足，需至少 3 个"}

        # ICLabel 强烈推荐 infomax extended=True，fastica 会导致分类质量下降
        ica_method = "infomax"
        fit_params = {"extended": True}

        # ICLabel 需要 1-100Hz 带通，统一做临时滤波副本（不影响主 raw）
        raw_for_ica = raw.copy()
        # h_freq 不能超过奈奎斯特频率，动态取安全上限
        nyquist = raw_for_ica.info['sfreq'] / 2
        h_freq_ica = min(100.0, nyquist - 1.0)
        raw_for_ica.filter(l_freq=1.0, h_freq=h_freq_ica, verbose=False)

        # ICLabel 需要通道位置信息，自动修复 montage（容忍大小写不一致）
        # rename_map 同步应用到主 raw，保证 ica.apply(raw) 时通道名一致
        rename_map = self._ensure_montage(raw_for_ica)
        if rename_map:
            raw.rename_channels({k: v for k, v in rename_map.items() if k in raw.ch_names})

        # 确定成分数量: 默认为通道数-1 或 min(通道数-1, 数据实际秩)
        n_components = cfg.n_components
        if n_components is None:
            try:
                rank = mne.compute_rank(raw_for_ica, verbose=False)
                eeg_rank = rank.get("eeg", n_channels)
            except Exception:
                rank = mne.compute_rank(raw_for_ica, rank="info", verbose=False)
                eeg_rank = rank.get("eeg", n_channels)
            n_components = min(int(eeg_rank) - 1, n_channels - 1, 50)
            n_components = max(n_components, 2)

        logger.debug(f"ICA: method={ica_method} (extended=True), n_components={n_components}")

        # 运行 ICA
        ica = ICA(
            n_components=n_components,
            method=ica_method,
            fit_params=fit_params,
            random_state=42,
            max_iter="auto",
            verbose=False,
        )

        ica.fit(raw_for_ica, picks="eeg", verbose=False)

        # ICLabel 自动分类
        ic_labels, exclude_idx, component_probs = self._classify_components(ica, raw_for_ica)

        if cfg.manual_exclude is not None:
            exclude_idx = sorted({idx for idx in cfg.manual_exclude if 0 <= idx < n_components})
            logger.info(f"使用手动 ICA 排除列表: {exclude_idx}")

        # 排除伪迹成分
        ica.exclude = exclude_idx
        raw = ica.apply(raw, verbose=False)

        # 汇总统计
        label_counts = {}
        for label in ic_labels:
            label_counts[label] = label_counts.get(label, 0) + 1

        metrics = {
            "language": language,
            "enabled": True,
            "method": cfg.method,
            "n_components": n_components,
            "n_excluded": len(exclude_idx),
            "excluded_indices": exclude_idx,
            "component_labels": ic_labels,
            "label_distribution": label_counts,
            "threshold": cfg.ic_reject_threshold,
            "component_probs": component_probs,  # {idx: {label: prob}}
            "manual_override": cfg.manual_exclude is not None,
        }

        # 把 ICA 对象放入 context，报告模块需要画成分图
        context["ica"] = ica
        context["ic_labels"] = ic_labels
        context["component_probs"] = component_probs

        return raw, metrics

    def _ensure_montage(self, raw: mne.io.Raw) -> dict:
        """
        确保 raw 有完整的通道位置信息，供 ICLabel 使用。
        返回 rename_map，调用方可用于同步修正其他 raw 实例的通道名。

        策略：
        1. 将通道名统一映射到标准 10-20 大小写（如 Fc5→FC5、Cpz→CPz）
        2. 设置 standard_1020 montage，找不到的通道用 on_missing="ignore" 跳过
        """
        montage = mne.channels.make_standard_montage("standard_1020")
        montage_lookup = {ch.upper(): ch for ch in montage.ch_names}

        rename_map = {}
        for ch in raw.ch_names:
            # EDF 通道名常有尾部点号/空格补位，先 strip 再查标准表
            ch_clean = ch.strip(". ").upper()
            std = montage_lookup.get(ch_clean)
            if std and std != ch:
                rename_map[ch] = std

        if rename_map:
            raw.rename_channels(rename_map)
            logger.info(
                f"自动修正通道名大小写 ({len(rename_map)} 个): "
                f"{list(rename_map.items())[:5]}{'...' if len(rename_map) > 5 else ''}"
            )

        raw.set_montage(montage, on_missing="ignore", verbose=False)
        logger.info("已自动设置 standard_1020 montage")
        return rename_map

    def _classify_components(
        self, ica: ICA, raw: mne.io.Raw
    ) -> tuple[list[str], list[int], dict]:
        """
        用 ICLabel 对 ICA 成分分类

        Returns:
            (各成分的标签列表, 需要排除的成分索引列表)
        """
        try:
            from mne_icalabel import label_components

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The provided Raw instance is not filtered between 1 and 100 Hz.*",
                    category=RuntimeWarning,
                )
                ic_result = label_components(raw, ica, method="iclabel")

            labels = list(ic_result["labels"])
            probs = self._extract_label_confidences(labels, ic_result.get("y_pred_proba"))
            reject_categories = set(self.config.reject_categories or [])

            # 排除非脑成分：置信度超过阈值则排除
            exclude = []
            for i, label in enumerate(labels):
                if label in reject_categories and float(probs[i]) >= self.config.ic_reject_threshold:
                    exclude.append(i)

            # component_probs: {idx: {"label": str, "confidence": float}}
            component_probs = {
                i: {"label": labels[i], "confidence": round(float(probs[i]), 3)}
                for i in range(len(labels))
            }

            logger.info(
                f"ICLabel 分类: {len(labels)} 个成分，"
                f"排除 {len(exclude)} 个伪迹成分"
            )
            return labels, exclude, component_probs

        except ImportError as exc:
            logger.warning(f"ICLabel 依赖不可用，回退为启发式方法: {exc}")
            return self._heuristic_classify(ica, raw)
        except Exception as exc:
            logger.warning(f"ICLabel 自动分类失败，回退为启发式方法: {exc}")
            return self._heuristic_classify(ica, raw)

    @staticmethod
    def _extract_label_confidences(labels: list[str], probabilities) -> np.ndarray:
        probs = np.asarray(probabilities, dtype=float)
        if probs.ndim == 1:
            return probs

        if probs.ndim == 2 and probs.shape[0] == len(labels):
            label_to_index = {label: index for index, label in enumerate(ICLABEL_CLASSES)}
            confidences = []
            for idx, label in enumerate(labels):
                class_index = label_to_index.get(label)
                if class_index is None or class_index >= probs.shape[1]:
                    confidences.append(float(np.nanmax(probs[idx])))
                else:
                    confidences.append(float(probs[idx, class_index]))
            return np.asarray(confidences, dtype=float)

        raise ValueError(f"无法解析 ICLabel 概率输出，shape={probs.shape}")

    def _heuristic_classify(
        self, ica: ICA, raw: mne.io.Raw
    ) -> tuple[list[str], list[int], dict]:
        """
        ICLabel 不可用时的简易启发式分类（基于 EOG/ECG 相关性）
        注意：raw 必须是传给 ica.fit() 的同一个副本（通道数/名称须一致）
        """
        labels = ["brain"] * ica.n_components_
        exclude = []

        try:
            eog_picks = mne.pick_types(raw.info, eog=True)
            if len(eog_picks) > 0:
                eog_indices, _ = ica.find_bads_eog(raw, verbose=False)
                for idx in eog_indices:
                    labels[idx] = "eye blink"
                    exclude.append(idx)
        except Exception as e:
            logger.warning(f"EOG 检测失败（跳过）: {e}")

        try:
            ecg_picks = mne.pick_types(raw.info, ecg=True)
            if len(ecg_picks) > 0:
                ecg_indices, _ = ica.find_bads_ecg(raw, verbose=False)
                for idx in ecg_indices:
                    if idx not in exclude:
                        labels[idx] = "heart beat"
                        exclude.append(idx)
        except Exception as e:
            logger.warning(f"ECG 检测失败（跳过）: {e}")

        component_probs = {
            idx: {"label": label, "confidence": 1.0 if idx in exclude else 0.0}
            for idx, label in enumerate(labels)
        }
        return labels, exclude, component_probs

    def _build_description(self, metrics: dict) -> str:
        if not metrics.get("enabled"):
            return f"ICA skipped: {metrics.get('reason', '')}" if metrics.get("language") == "en" else f"ICA 跳过: {metrics.get('reason', '')}"
        dist = metrics.get("label_distribution", {})
        dist_str = ", ".join(f"{k}={v}" for k, v in dist.items())
        if metrics.get("language") == "en":
            return (
                f"ICA decomposed {metrics['n_components']} components, "
                f"removed {metrics['n_excluded']} artifact components "
                f"(threshold={metrics['threshold']}). "
                f"Distribution: {dist_str}"
            )
        return (
            f"ICA 分解 {metrics['n_components']} 个成分，"
            f"排除 {metrics['n_excluded']} 个伪迹 "
            f"(阈值={metrics['threshold']})。"
            f"分布: {dist_str}"
        )
