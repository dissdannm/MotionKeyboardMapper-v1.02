"""
动作识别引擎 —— 基于 metric_catalog 的分层 Pipeline。

流程: PoseResult → AngleCalc → AlignAnalyzer → TemporalAnalyzer
         → merge → filter → NoiseFilter → RuleEngine → Action判定

与旧 GestureEngine 的区别:
  - 旧: 手势=直接对关键点写规则, 无分层的指标计算
  - 新: 动作=先算26个通用指标, 再基于指标阈值判定
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional

from pose.estimator import PoseResult
from models.action_definition import ActionDefinition, MetricRule
from analysis.angle_calculator import AngleCalculator
from analysis.alignment_analyzer import AlignmentAnalyzer
from analysis.temporal_analyzer import TemporalAnalyzer
from analysis.noise_filter import NoiseFilter
from analysis.rule_engine import RuleEngine
from analysis.motion_analyzer import MotionAnalyzer


@dataclass
class ActionState:
    """单个动作的运行时状态"""
    action_id: str
    active: bool = False
    confidence: float = 0.0
    hold_count: int = 0
    triggered: bool = False


class ActionEngine:
    """
    动作识别引擎 —— 基于指标目录的分层 Pipeline。
    """

    def __init__(self, definitions_path: str,
                 catalog_path: str | None = None) -> None:
        self.definitions: Dict[str, ActionDefinition] = {}
        self.states: Dict[str, ActionState] = {}
        self.active_actions: Set[str] = set()

        # 构建分析链
        angle_calc = AngleCalculator()
        align_analyzer = AlignmentAnalyzer()
        temporal_analyzer = TemporalAnalyzer()
        noise_filter = NoiseFilter(window_size=5)
        rule_engine = RuleEngine()

        self._analyzer = MotionAnalyzer(
            angle_calc, align_analyzer, temporal_analyzer,
            noise_filter, rule_engine)

        self._load_definitions(definitions_path)

    def _load_definitions(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw = data.get("actions", {})
        for aid, adef in raw.items():
            rules: Dict[str, dict] = {}
            for mid, mr in adef.get("metric_rules", {}).items():
                rules[mid] = {
                    "normal_lo": mr.get("normal_lo", 0),
                    "normal_hi": mr.get("normal_hi", 0),
                }

            action_def = ActionDefinition(
                action_id=adef["action_id"],
                name=adef.get("name", aid),
                action_type=adef.get("action_type", "pose"),
                description=adef.get("description", ""),
                hold_frames=int(adef.get("hold_frames", 1)),
                enabled_metrics=list(adef.get("enabled_metrics", [])),
                metric_rules=rules,
                conflict_group=adef.get("conflict_group", ""),
            )
            self.definitions[aid] = action_def
            self.states[aid] = ActionState(action_id=aid)

        print(f"[Action] 已加载 {len(self.definitions)} 个动作定义 "
              f"(来自: {Path(path).name})")

    def update(self, pose: PoseResult, timestamp_ms: int = 0) -> None:
        """处理一帧，更新所有动作状态。"""
        if not pose:
            self._reset_all()
            return

        # 对每个动作跑完整 Pipeline
        results: Dict[str, tuple[bool, float]] = {}
        for aid, adef in self.definitions.items():
            activated, confidence, _ = self._analyzer.analyze(
                pose, adef, timestamp_ms)
            results[aid] = (activated, confidence)

        # 冲突组解决
        groups: Dict[str, List[str]] = {}
        for aid, adef in self.definitions.items():
            cg = adef.conflict_group
            if cg:
                groups.setdefault(cg, []).append(aid)

        resolved: Dict[str, bool] = {}
        for aid, (activated, conf) in results.items():
            resolved[aid] = activated

        for cg, members in groups.items():
            best = max(members,
                       key=lambda g: results.get(g, (False, 0.0))[1])
            for g in members:
                if g != best:
                    resolved[g] = False

        # 更新状态
        self.active_actions = set()
        for aid, adef in self.definitions.items():
            st = self.states[aid]
            activated = resolved.get(aid, False)
            conf = results.get(aid, (False, 0.0))[1]
            st.confidence = conf
            hold = adef.hold_frames

            if activated:
                st.hold_count += 1
            else:
                st.hold_count = 0
                st.triggered = False
                st.active = False

            if st.hold_count >= hold:
                st.triggered = True
                st.active = True
                self.active_actions.add(aid)

    def _reset_all(self) -> None:
        self.active_actions.clear()
        for st in self.states.values():
            st.active = False
            st.confidence = 0.0
            st.hold_count = 0
            st.triggered = False

    def get_state(self, action_id: str) -> Optional[ActionState]:
        return self.states.get(action_id)

    def reload(self) -> None:
        pass  # 留给后续热加载
