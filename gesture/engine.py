"""
手势识别引擎 —— 实时评估姿态数据，判定当前激活的手势。

工作原理:
  1. 加载 gesture/definitions/*.json 中的手势定义
  2. 每一帧对所有启用的手势规则进行打分
  3. 分数超过阈值的手势被视为 "激活"
  4. 冲突组 (conflict_group) 内只保留得分最高的一个
  5. 连续 hold_frames 帧激活后，手势正式触发
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from pose.estimator import PoseResult, Landmark


# ---------------------------------------------------------------------------
# 规则评估器 —— 每种 rule.type 对应一个静态方法
# ---------------------------------------------------------------------------

class RuleEvaluator:
    """对所有规则类型执行评估，返回 0.0~1.0 的匹配度。"""

    @staticmethod
    def angle_range(lm: Dict[str, Landmark], rule: dict) -> float:
        """三点连线夹角是否在 [min, max] 范围内"""
        pa, pb, pc = rule["points"]
        a = lm.get(pa)
        b = lm.get(pb)
        c = lm.get(pc)
        if not (a and b and c):
            return 0.0
        angle = _angle_between(a, b, c)
        lo, hi = rule["min"], rule["max"]
        if lo <= angle <= hi:
            mid = (lo + hi) / 2
            spread = (hi - lo) / 2
            return 1.0 - min(abs(angle - mid) / spread, 1.0) * 0.5
        # 越界惩罚
        dist = min(abs(angle - lo), abs(angle - hi))
        return max(0.0, 1.0 - dist / 30.0)

    @staticmethod
    def relative_height(lm: Dict[str, Landmark], rule: dict) -> float:
        """point_a 的 y 坐标是否在 point_b 的 threshold 范围内"""
        a = lm.get(rule["point_a"])
        b = lm.get(rule["point_b"])
        if not (a and b):
            return 0.0
        diff = b.y - a.y
        t = rule["threshold"]
        if rule.get("operator", "above") == "above":
            return _sigmoid_score(diff, t, 0.03)
        else:
            return _sigmoid_score(t - diff, 0, 0.03)

    @staticmethod
    def relative_position(lm: Dict[str, Landmark], rule: dict) -> float:
        """两点在指定轴上的位置比较"""
        a = lm.get(rule["point_a"])
        b = lm.get(rule["point_b"])
        if not (a and b):
            return 0.0
        axis = rule.get("axis", "x")
        val_a = getattr(a, axis)
        val_b = getattr(b, axis)
        diff = val_a - val_b
        t = rule["threshold"]
        op = rule.get("operator", "lt")
        if op in ("lt", "less_than"):
            return _sigmoid_score(-diff, -t, 0.02)
        else:
            return _sigmoid_score(diff, t, 0.02)

    @staticmethod
    def distance_ratio(lm: Dict[str, Landmark], rule: dict) -> float:
        """两组点对的欧氏距离比值"""
        a1 = lm.get(rule["point_a"])
        b1 = lm.get(rule["point_b"])
        a2 = lm.get(rule["ref_a"])
        b2 = lm.get(rule["ref_b"])
        if not all([a1, b1, a2, b2]):
            return 0.0
        d1 = _euclidean(a1, b1)
        d2 = _euclidean(a2, b2)
        if d2 < 0.001:
            return 0.0
        ratio = d1 / d2
        min_r = rule.get("min_ratio", 0.0)
        return _sigmoid_score(ratio, min_r, 0.1)


def _angle_between(a: Landmark, b: Landmark, c: Landmark) -> float:
    """计算 ABC 夹角 (B 为顶点)，返回角度制。"""
    ba = (a.x - b.x, a.y - b.y)
    bc = (c.x - b.x, c.y - b.y)
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag = math.hypot(*ba) * math.hypot(*bc)
    if mag < 1e-9:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))


def _euclidean(a: Landmark, b: Landmark) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _sigmoid_score(value: float, threshold: float, smooth: float = 0.02) -> float:
    """Sigmoid 平滑打分: value 超过 threshold 越多分越高。"""
    if smooth <= 0:
        smooth = 0.01
    return 1.0 / (1.0 + math.exp(-(value - threshold) / smooth))


# ---------------------------------------------------------------------------
# 手势引擎核心
# ---------------------------------------------------------------------------

@dataclass
class GestureState:
    """单个手势的运行时状态"""
    gesture_id: str
    active: bool = False
    score: float = 0.0
    hold_count: int = 0
    triggered: bool = False   # 当满足 hold_frames 后变为 True


class GestureEngine:
    """
    手势识别引擎。
    使用方式:
        engine = GestureEngine("path/to/standard.json")
        engine.update(pose_result)  # 每帧调用
        active = engine.active_gestures  # 获取当前激活手势 ID 集合
    """

    def __init__(self, definitions_path: str, score_threshold: float = 0.55) -> None:
        self.definitions_path = Path(definitions_path)
        self.score_threshold = score_threshold
        self.gestures: Dict[str, dict] = {}
        self.states: Dict[str, GestureState] = {}
        self.active_gestures: Set[str] = set()
        self._load()

    def _load(self) -> None:
        with open(self.definitions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("gestures", {})
        self.gestures = raw
        self.states = {gid: GestureState(gesture_id=gid) for gid in raw}
        print(f"[Gesture] 已加载 {len(self.gestures)} 个手势定义")

    def update(self, pose: PoseResult) -> None:
        """处理一帧数据，更新所有手势状态。"""
        if not pose:
            self._reset_all()
            return

        lm = pose.landmarks
        scores: Dict[str, float] = {}

        for gid, gdef in self.gestures.items():
            rules = gdef.get("rules", [])
            if not rules:
                scores[gid] = 0.0
                continue
            total = 0.0
            weight_sum = 0.0
            for rule in rules:
                evaluator = getattr(RuleEvaluator, rule["type"], None)
                if evaluator is None:
                    continue
                w = float(rule.get("weight", 1.0))
                s = evaluator(lm, rule)
                total += s * w
                weight_sum += w
            scores[gid] = total / weight_sum if weight_sum > 0 else 0.0

        # 冲突组解决: 同组只留最高分
        resolved: Dict[str, float] = dict(scores)
        groups: Dict[str, List[str]] = {}
        for gid, gdef in self.gestures.items():
            cg = gdef.get("conflict_group", "")
            groups.setdefault(cg, []).append(gid)

        for cg, members in groups.items():
            if not cg or len(members) <= 1:
                continue
            best = max(members, key=lambda g: scores.get(g, 0.0))
            for g in members:
                if g != best:
                    resolved[g] = 0.0

        # 更新状态
        self.active_gestures = set()
        for gid, gdef in self.gestures.items():
            state = self.states[gid]
            score = resolved.get(gid, 0.0)
            state.score = score
            hold = int(gdef.get("hold_frames", 1))

            if score >= self.score_threshold:
                state.hold_count += 1
            else:
                state.hold_count = 0
                state.triggered = False
                state.active = False

            if state.hold_count >= hold:
                state.triggered = True
                state.active = True
                self.active_gestures.add(gid)

    def _reset_all(self) -> None:
        self.active_gestures.clear()
        for st in self.states.values():
            st.active = False
            st.score = 0.0
            st.hold_count = 0
            st.triggered = False

    def get_state(self, gesture_id: str) -> Optional[GestureState]:
        return self.states.get(gesture_id)

    def reload(self) -> None:
        """热加载手势定义（不重启进程）"""
        self._load()
