"""
平台级力线/偏移分析器 —— 计算 10 个对齐指标。
定位: 平台能力层，不关心具体动作规则。
"""

from __future__ import annotations

from dataclasses import dataclass

from pose.estimator import PoseResult
from analysis.math_utils import (
    calculate_angle, midpoint, point_from_landmark_xy,
    safe_ratio, angle_with_horizontal, line_midpoint_vertical_gap,
)


@dataclass
class AlignmentResult:
    trunk_tilt:          float = 0.0
    pelvis_tilt:         float = 0.0
    neck_forward_offset: float = 0.0
    center_offset:       float = 0.0
    knee_offset_left:    float = 0.0
    knee_offset_right:   float = 0.0
    body_line_angle:     float = 0.0
    trunk_ground_angle:  float = 0.0
    neck_flexion_angle:  float = 0.0
    lumbar_gap_distance: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.__dict__.items()}


class AlignmentAnalyzer:
    """计算全部 10 个力线/偏移指标。"""

    def calculate_all(self, pose: PoseResult) -> AlignmentResult:
        r = AlignmentResult()
        self._calc_trunk_tilt_center(pose, r)
        self._calc_pelvis_tilt(pose, r)
        self._calc_neck_forward(pose, r)
        self._calc_knee_offsets(pose, r)
        self._calc_body_line_angle(pose, r)
        self._calc_trunk_ground_angle(pose, r)
        self._calc_neck_flexion(pose, r)
        self._calc_lumbar_gap(pose, r)
        return r

    def _calc_trunk_tilt_center(self, pose, r: AlignmentResult) -> None:
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        la = point_from_landmark_xy(pose.get("left_ankle"))
        ra = point_from_landmark_xy(pose.get("right_ankle"))
        if not all([ls, rs, lh, rh]):
            return
        sm = midpoint(ls, rs)
        hm = midpoint(lh, rh)
        dx = sm[0] - hm[0]
        dy = sm[1] - hm[1]
        r.trunk_tilt = safe_ratio(dx, abs(dy), default=0.0)
        if la and ra:
            am = midpoint(la, ra)
            r.center_offset = hm[0] - am[0]

    def _calc_pelvis_tilt(self, pose, r: AlignmentResult) -> None:
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        if lh and rh:
            r.pelvis_tilt = lh[1] - rh[1]

    def _calc_neck_forward(self, pose, r: AlignmentResult) -> None:
        nose = point_from_landmark_xy(pose.get("nose"))
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        if nose and ls and rs:
            sm = midpoint(ls, rs)
            r.neck_forward_offset = nose[0] - sm[0]

    def _calc_knee_offsets(self, pose, r: AlignmentResult) -> None:
        lh = point_from_landmark_xy(pose.get("left_hip"))
        lk = point_from_landmark_xy(pose.get("left_knee"))
        la = point_from_landmark_xy(pose.get("left_ankle"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        rk = point_from_landmark_xy(pose.get("right_knee"))
        ra = point_from_landmark_xy(pose.get("right_ankle"))
        if lh and lk and la:
            ref_x = (lh[0] + la[0]) / 2.0
            r.knee_offset_left = lk[0] - ref_x
        if rh and rk and ra:
            ref_x = (rh[0] + ra[0]) / 2.0
            r.knee_offset_right = rk[0] - ref_x

    def _calc_body_line_angle(self, pose, r: AlignmentResult) -> None:
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        la = point_from_landmark_xy(pose.get("left_ankle"))
        ra = point_from_landmark_xy(pose.get("right_ankle"))
        if all([ls, rs, lh, rh, la, ra]):
            r.body_line_angle = calculate_angle(
                midpoint(ls, rs), midpoint(lh, rh), midpoint(la, ra))

    def _calc_trunk_ground_angle(self, pose, r: AlignmentResult) -> None:
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        if all([ls, rs, lh, rh]):
            r.trunk_ground_angle = angle_with_horizontal(
                midpoint(lh, rh), midpoint(ls, rs))

    def _calc_neck_flexion(self, pose, r: AlignmentResult) -> None:
        nose = point_from_landmark_xy(pose.get("nose"))
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        if all([nose, ls, rs, lh, rh]):
            r.neck_flexion_angle = calculate_angle(
                nose, midpoint(ls, rs), midpoint(lh, rh))

    def _calc_lumbar_gap(self, pose, r: AlignmentResult) -> None:
        ls = point_from_landmark_xy(pose.get("left_shoulder"))
        rs = point_from_landmark_xy(pose.get("right_shoulder"))
        lh = point_from_landmark_xy(pose.get("left_hip"))
        rh = point_from_landmark_xy(pose.get("right_hip"))
        if all([ls, rs, lh, rh]):
            r.lumbar_gap_distance = line_midpoint_vertical_gap(
                midpoint(ls, rs), midpoint(lh, rh), midpoint(lh, rh))
