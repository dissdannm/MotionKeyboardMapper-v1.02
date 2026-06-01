"""
平台级基础角度计算器 —— 计算 10 个关节角度。
定位: 平台能力层，不关心具体动作规则。
"""

from __future__ import annotations

from pose.estimator import PoseResult
from analysis.math_utils import calculate_angle, point_from_landmark_xy


class AngleCalculator:
    """计算全部 10 个基础关节角度。"""

    def calculate_all(self, pose: PoseResult) -> dict[str, float]:
        values: dict[str, float] = {}

        self._try_add(values, "left_elbow", pose,
                      ("left_shoulder", "left_elbow", "left_wrist"))
        self._try_add(values, "right_elbow", pose,
                      ("right_shoulder", "right_elbow", "right_wrist"))

        self._try_add(values, "left_shoulder", pose,
                      ("left_elbow", "left_shoulder", "left_hip"))
        self._try_add(values, "right_shoulder", pose,
                      ("right_elbow", "right_shoulder", "right_hip"))

        self._try_add(values, "left_hip", pose,
                      ("left_shoulder", "left_hip", "left_knee"))
        self._try_add(values, "right_hip", pose,
                      ("right_shoulder", "right_hip", "right_knee"))

        self._try_add(values, "left_knee", pose,
                      ("left_hip", "left_knee", "left_ankle"))
        self._try_add(values, "right_knee", pose,
                      ("right_hip", "right_knee", "right_ankle"))

        self._try_add(values, "left_ankle", pose,
                      ("left_knee", "left_ankle", "left_foot_index"))
        self._try_add(values, "right_ankle", pose,
                      ("right_knee", "right_ankle", "right_foot_index"))

        return values

    def _try_add(self, values: dict, metric_id: str, pose: PoseResult,
                 point_names: tuple[str, str, str]) -> None:
        p1 = point_from_landmark_xy(pose.get(point_names[0]))
        vx = point_from_landmark_xy(pose.get(point_names[1]))
        p3 = point_from_landmark_xy(pose.get(point_names[2]))
        if p1 is None or vx is None or p3 is None:
            return
        values[metric_id] = calculate_angle(p1, vx, p3)
