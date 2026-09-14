"""
Step 2: 坏导检测与插值
"""
import numpy as np
import mne
from loguru import logger

from .base import BaseStep
from config import BadChannelConfig


class BadChannelStep(BaseStep):
    name = "bad_channels"

    def __init__(self, config: BadChannelConfig | None = None):
        self.config = config or BadChannelConfig()

    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        raw = raw.copy()
        language = "en" if str(context.get("report_language") or "zh").strip().lower() == "en" else "zh"

        eeg_picks = mne.pick_types(raw.info, eeg=True)
        if len(eeg_picks) == 0:
            return raw, {"language": language, "method": "skipped", "reason": "No EEG channels" if language == "en" else "无 EEG 通道"}

        # 标准化通道名 → 设置 montage
        self._standardize_channel_names(raw)

        # ★ 先处理数据中的 NaN/Inf（GDF 格式常见）
        nan_channels = self._fix_nan_data(raw)

        # 检测坏导
        if self.config.method == "pyprep":
            bad_chs = self._detect_pyprep(raw)
        else:
            bad_chs = self._detect_threshold(raw)

        # 合并 NaN 通道和统计检测到的坏导
        all_bads = list(set(nan_channels + bad_chs))

        # 标记并尝试插值
        interpolated = False
        if all_bads:
            raw.info["bads"] = list(set(raw.info["bads"] + all_bads))
            logger.info(f"检测到 {len(all_bads)} 个坏导: {all_bads}")

            # 设置 montage 用于插值
            self._try_set_montage(raw)

            if raw.get_montage() is not None:
                try:
                    raw.interpolate_bads(reset_bads=True, verbose=False)
                    interpolated = True
                    logger.info("坏导插值完成")
                except Exception as e:
                    logger.warning(f"插值失败 ({e})，仅标记坏导不插值")
                    # 插值失败就只标记，不影响后续流程
            else:
                logger.warning("无电极位置信息，跳过插值")
        else:
            logger.info("未检测到坏导")

        metrics = {
            "language": language,
            "method": self.config.method,
            "n_bad_channels": len(all_bads),
            "bad_channels": all_bads,
            "nan_channels": nan_channels,
            "n_total_channels": len(eeg_picks),
            "bad_ratio_pct": round(len(all_bads) / len(eeg_picks) * 100, 1),
            "interpolated": interpolated,
        }

        return raw, metrics

    @staticmethod
    def _fix_nan_data(raw: mne.io.Raw) -> list[str]:
        """
        检测并修复数据中的 NaN/Inf 值
        GDF 文件中未记录的时段常被填充为 NaN
        返回包含 NaN 的通道列表
        """
        data = raw.get_data()
        nan_mask = ~np.isfinite(data)

        if not nan_mask.any():
            return []

        nan_channels = []
        for i in range(data.shape[0]):
            nan_ratio = nan_mask[i].sum() / data.shape[1]
            if nan_ratio > 0:
                if nan_ratio > 0.5:
                    # 超过50% 是 NaN 的通道标记为坏导
                    nan_channels.append(raw.ch_names[i])
                # 将 NaN 替换为 0（防止后续计算崩溃）
                data[i, nan_mask[i]] = 0.0

        # 写回修复后的数据
        raw_data = raw.get_data()
        raw_data[~np.isfinite(raw_data)] = 0.0
        # 直接修改底层数据
        raw._data = raw_data

        if nan_channels:
            logger.info(f"发现 {len(nan_channels)} 个通道含大量 NaN 数据: {nan_channels}")
        else:
            n_nan = nan_mask.sum()
            logger.debug(f"修复了 {n_nan} 个 NaN/Inf 数据点")

        return nan_channels

    @staticmethod
    def _standardize_channel_names(raw: mne.io.Raw):
        """
        标准化通道名以匹配标准 montage

        PhysioNet: "Fc5." → "Fc5"
        BCI Competition: "EEG-Fz" → "Fz"
        """
        rename_map = {}
        for ch_name in raw.ch_names:
            new_name = ch_name

            # 去掉 "EEG-" 前缀
            if new_name.upper().startswith("EEG-"):
                new_name = new_name[4:]

            # 去掉末尾的点号
            new_name = new_name.rstrip(".")

            if new_name != ch_name:
                rename_map[ch_name] = new_name

        if rename_map:
            new_names = [rename_map.get(ch, ch) for ch in raw.ch_names]
            if len(new_names) == len(set(new_names)):
                raw.rename_channels(rename_map)
                logger.debug(f"标准化了 {len(rename_map)} 个通道名")
            else:
                logger.debug("通道名标准化后存在重复，跳过重命名")

    @staticmethod
    def _try_set_montage(raw: mne.io.Raw):
        """尝试自动设置标准 montage"""
        if raw.get_montage() is not None:
            return

        for montage_name in ["standard_1005", "standard_1020"]:
            try:
                montage = mne.channels.make_standard_montage(montage_name)
                # 计算能匹配多少通道
                eeg_chs = [raw.ch_names[i] for i in mne.pick_types(raw.info, eeg=True)]
                matched = [ch for ch in eeg_chs if ch in montage.ch_names]

                if len(matched) >= 3:
                    raw.set_montage(montage, on_missing="ignore", verbose=False)
                    logger.debug(f"Montage {montage_name}: 匹配 {len(matched)}/{len(eeg_chs)} EEG通道")
                    return
            except Exception:
                continue

        logger.debug("无法匹配任何标准 montage")

    def _detect_pyprep(self, raw: mne.io.Raw) -> list[str]:
        try:
            from pyprep.find_noisy_channels import NoisyChannels
            nd = NoisyChannels(raw, random_state=42)
            nd.find_all_bads(ransac=False)
            return nd.get_bads()
        except ImportError:
            logger.warning("pyprep 未安装，回退到阈值法")
            return self._detect_threshold(raw)
        except Exception as e:
            logger.warning(f"PyPREP 失败 ({e})，回退到阈值法")
            return self._detect_threshold(raw)

    def _detect_threshold(self, raw: mne.io.Raw) -> list[str]:
        """基于统计阈值的坏导检测（已处理 NaN 安全）"""
        data = raw.get_data(picks="eeg")
        ch_names = [raw.ch_names[i] for i in mne.pick_types(raw.info, eeg=True)]

        # ★ NaN 安全的统计计算
        stds = np.nanstd(data, axis=1)
        stds = np.where(np.isfinite(stds), stds, 0.0)

        median_std = np.median(stds[stds > 0]) if np.any(stds > 0) else 1.0
        mad = np.median(np.abs(stds - median_std))
        if mad == 0:
            mad = median_std * 0.1  # 防止除零

        threshold = self.config.threshold_std
        bad_mask = np.abs(stds - median_std) > threshold * mad * 1.4826
        flat_mask = stds < median_std * 0.01

        combined = bad_mask | flat_mask
        return [ch_names[i] for i in np.where(combined)[0]]

    def _build_description(self, metrics: dict) -> str:
        if metrics.get("reason"):
            return str(metrics["reason"])
        n = metrics["n_bad_channels"]
        if n == 0:
            return "Bad-channel scan finished. No bad channels found." if metrics.get("language") == "en" else "坏导检测完成，未发现坏导"
        if metrics.get("language") == "en":
            action = "and interpolated" if metrics.get("interpolated") else "(not interpolated)"
            return f"Detected {n} bad channels ({metrics['bad_ratio_pct']}%) {action}: {metrics['bad_channels']}"
        action = "并已插值修复" if metrics.get("interpolated") else "（未插值）"
        return f"检测到 {n} 个坏导 ({metrics['bad_ratio_pct']}%) {action}: {metrics['bad_channels']}"
