"""
清洗步骤基类

所有清洗步骤继承 BaseStep，实现统一的 run() 接口。
这样 Pipeline 可以用相同的方式调用任何步骤，也方便后续新增步骤。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import time

import mne
from loguru import logger


@dataclass
class StepResult:
    """单个清洗步骤的执行结果"""
    step_name: str
    description: str              # 人类可读的处理描述
    duration: float               # 执行耗时 (秒)
    metrics: dict = field(default_factory=dict)  # 该步骤的质量指标
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"[{self.step_name}] {self.description} ({self.duration:.1f}s)"]
        for k, v in self.metrics.items():
            lines.append(f"  {k}: {v}")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


class BaseStep(ABC):
    """清洗步骤抽象基类"""

    name: str = "unnamed_step"

    @abstractmethod
    def process(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, dict]:
        """
        执行清洗处理

        Args:
            raw: 输入的 MNE Raw 数据
            context: 上下文信息 (前置步骤的结果、全局配置等)

        Returns:
            (处理后的 Raw, 该步骤的 metrics 字典)
        """
        ...

    def run(self, raw: mne.io.Raw, context: dict) -> tuple[mne.io.Raw, StepResult]:
        """
        统一执行入口：计时 + 日志 + 异常处理

        不要覆写此方法，覆写 process() 即可。
        """
        logger.info(f"▶ 开始: {self.name}")
        t0 = time()

        try:
            raw_out, metrics = self.process(raw, context)
            duration = time() - t0

            result = StepResult(
                step_name=self.name,
                description=self._build_description(metrics),
                duration=duration,
                metrics=metrics,
            )
            logger.info(f"✓ 完成: {self.name} ({duration:.1f}s)")
            return raw_out, result

        except Exception as e:
            duration = time() - t0
            logger.error(f"✗ 失败: {self.name} - {e}")
            result = StepResult(
                step_name=self.name,
                description=f"执行失败: {str(e)}",
                duration=duration,
                warnings=[str(e)],
            )
            # 失败时返回原始数据，不中断流水线
            return raw, result

    def _build_description(self, metrics: dict) -> str:
        """子类可覆写，生成步骤描述"""
        return f"{self.name} 处理完成"
