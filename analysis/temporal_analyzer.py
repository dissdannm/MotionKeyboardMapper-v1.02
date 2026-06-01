"""
时序分析器 —— 追踪跨帧的身体运动指标。
用于: 跳跃检测(垂直速度)、侧移检测(水平速度)、稳定性评估。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque

from models.action_definition import ActionDefinition
from analysis.alignment_analyzer import AlignmentResult


@dataclass
class TemporalResult:
    """时序指标结果"""
    values: dict[str, float] = field(default_factory=dict)


class TemporalAnalyzer:
    """追踪跨帧运动状态，计算速度、稳定性等指标。"""

    def __init__(self) -> None:
        self._prev_center: tuple[float, float] | None = None
        self._prev_timestamp_ms: int | None = None
        self._center_history: deque[tuple[float, float]] = deque(maxlen=10)

    def reset(self) -> None:
        self._prev_center = None
        self._prev_timestamp_ms = None
        self._center_history.clear()

    def calculate(self, action_def: ActionDefinition,
                  alignment: AlignmentResult,
                  timestamp_ms: int) -> TemporalResult:
        values: dict[str, float] = {}

        center_y = abs(alignment.center_offset)
        center_x = alignment.center_offset

        if self._prev_center is not None and self._prev_timestamp_ms is not None:
            dt = max((timestamp_ms - self._prev_timestamp_ms) / 1000.0, 1e-6)
            dy = abs(center_y - self._prev_center[1])
            dx = abs(center_x - self._prev_center[0])
            values["vertical_velocity"] = dy / dt
            values["lateral_velocity"] = dx / dt
        else:
            values["vertical_velocity"] = 0.0
            values["lateral_velocity"] = 0.0

        self._center_history.append((center_x, center_y))
        if len(self._center_history) >= 2:
            diffs = [
                ((self._center_history[i][0] - self._center_history[i - 1][0]) ** 2 +
                 (self._center_history[i][1] - self._center_history[i - 1][1]) ** 2) ** 0.5
                for i in range(1, len(self._center_history))
            ]
            avg_disp = sum(diffs) / len(diffs)
            var = sum((d - avg_disp) ** 2 for d in diffs) / len(diffs)
            values["body_stability"] = 1.0 / (1.0 + var * 100)
        else:
            values["body_stability"] = 1.0

        self._prev_center = (center_x, center_y)
        self._prev_timestamp_ms = timestamp_ms

        return TemporalResult(values=values)
