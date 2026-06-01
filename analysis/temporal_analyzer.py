"""
时序分析器 —— 追踪跨帧的身体运动指标。
v1.02-final fix: vertical_velocity 改用 hip_vertical (y轴)，
                 lateral_velocity 使用 center_offset (x轴)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque

from models.action_definition import ActionDefinition
from analysis.alignment_analyzer import AlignmentResult


@dataclass
class TemporalResult:
    values: dict[str, float] = field(default_factory=dict)


class TemporalAnalyzer:

    def __init__(self) -> None:
        self._prev_hip_y: float | None = None
        self._prev_center_x: float | None = None
        self._prev_timestamp_ms: int | None = None
        self._center_history: deque[tuple[float, float]] = deque(maxlen=10)

    def reset(self) -> None:
        self._prev_hip_y = None
        self._prev_center_x = None
        self._prev_timestamp_ms = None
        self._center_history.clear()

    def calculate(self, _action_def: ActionDefinition,
                  alignment: AlignmentResult,
                  timestamp_ms: int) -> TemporalResult:
        values: dict[str, float] = {}

        hip_y = alignment.hip_vertical
        center_x = alignment.center_offset

        if (self._prev_hip_y is not None and
                self._prev_center_x is not None and
                self._prev_timestamp_ms is not None):
            dt = max((timestamp_ms - self._prev_timestamp_ms) / 1000.0, 1e-6)

            # 垂直速度: hip_vertical 的变化 (y 轴 — true vertical)
            dy = abs(hip_y - self._prev_hip_y)
            values["vertical_velocity"] = dy / dt

            # 水平速度: center_offset 的变化 (x 轴 — lateral)
            dx = abs(center_x - self._prev_center_x)
            values["lateral_velocity"] = dx / dt
        else:
            values["vertical_velocity"] = 0.0
            values["lateral_velocity"] = 0.0

        self._center_history.append((center_x, hip_y))
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

        self._prev_hip_y = hip_y
        self._prev_center_x = center_x
        self._prev_timestamp_ms = timestamp_ms

        return TemporalResult(values=values)
