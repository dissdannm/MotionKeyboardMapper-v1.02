"""
噪声滤波器 —— 滑动窗口移动平均。
对角度、偏移、启用的指标分别做逐指标平滑。
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy

from analysis.alignment_analyzer import AlignmentResult


class NoiseFilter:
    """简单移动平均滤波器，window_size=5 表示最近 5 帧平均。"""

    def __init__(self, window_size: int = 5) -> None:
        self.window_size = window_size
        self._angle_history: dict[str, deque[float]] = {}
        self._align_history: dict[str, deque[float]] = {}
        self._selected_history: dict[str, deque[float]] = {}

    def apply(self, angle_values: dict[str, float],
              alignment: AlignmentResult,
              selected: dict[str, float]) -> tuple[dict[str, float],
                                                    AlignmentResult,
                                                    dict[str, float]]:
        """平滑所有指标，返回新对象。"""
        filtered_angles = self._filter_dict(angle_values, self._angle_history)
        filtered_align = self._filter_alignment(alignment)
        filtered_selected = self._filter_dict(selected, self._selected_history)
        return filtered_angles, filtered_align, filtered_selected

    def _filter_dict(self, values: dict[str, float],
                     history_map: dict[str, deque[float]]) -> dict[str, float]:
        result: dict[str, float] = {}
        for k, v in values.items():
            h = history_map.setdefault(k, deque(maxlen=self.window_size))
            h.append(v)
            result[k] = sum(h) / len(h) if h else 0.0
        return result

    def _filter_alignment(self, a: AlignmentResult) -> AlignmentResult:
        fields = [
            "trunk_tilt", "pelvis_tilt", "neck_forward_offset",
            "center_offset", "knee_offset_left", "knee_offset_right",
            "body_line_angle", "trunk_ground_angle", "neck_flexion_angle",
            "lumbar_gap_distance",
        ]
        result = deepcopy(a)
        for fname in fields:
            val = getattr(a, fname, 0.0)
            h = self._align_history.setdefault(fname, deque(maxlen=self.window_size))
            h.append(val)
            setattr(result, fname, sum(h) / len(h) if h else 0.0)
        return result
