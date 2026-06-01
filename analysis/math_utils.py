"""数学工具 —— 角度、中点、向量计算。"""

from __future__ import annotations

import math
from typing import Optional, Tuple

Point2D = Tuple[float, float]
Vector2D = Tuple[float, float]


def vector_from_points(start: Point2D, end: Point2D) -> Vector2D:
    return end[0] - start[0], end[1] - start[1]


def vector_length(vector: Vector2D) -> float:
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def dot_product(v1: Vector2D, v2: Vector2D) -> float:
    return v1[0] * v2[0] + v1[1] * v2[1]


def calculate_angle(p1: Point2D, vertex: Point2D, p3: Point2D) -> float:
    """三点夹角 (vertex为顶点)，返回角度制。"""
    v1 = vector_from_points(vertex, p1)
    v2 = vector_from_points(vertex, p3)
    len1 = vector_length(v1)
    len2 = vector_length(v2)
    if len1 == 0 or len2 == 0:
        return 0.0
    cosine = dot_product(v1, v2) / (len1 * len2)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def midpoint(p1: Point2D, p2: Point2D) -> Point2D:
    return (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0


def safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den != 0 else default


def point_from_landmark_xy(landmark) -> Optional[Point2D]:
    """从 Landmark 对象提取 (x, y) 坐标。"""
    if landmark is None:
        return None
    return landmark.x, landmark.y


def angle_with_horizontal(start: Point2D, end: Point2D) -> float:
    """线段与水平线的夹角 (0~180度)。"""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return math.degrees(math.atan2(abs(dy), abs(dx)))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def line_midpoint_vertical_gap(a: Point2D, b: Point2D, ref: Point2D) -> float:
    mid_y = (a[1] + b[1]) / 2.0
    return abs(mid_y - ref[1])
