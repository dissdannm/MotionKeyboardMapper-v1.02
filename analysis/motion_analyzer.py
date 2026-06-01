"""
动作指标合并器 —— 协调角度、偏移、时序三层指标。
等价于参考项目的 MotionAnalyzer。
"""

from __future__ import annotations

from pose.estimator import PoseResult
from models.action_definition import ActionDefinition
from analysis.angle_calculator import AngleCalculator
from analysis.alignment_analyzer import AlignmentAnalyzer, AlignmentResult
from analysis.temporal_analyzer import TemporalAnalyzer
from analysis.noise_filter import NoiseFilter
from analysis.rule_engine import RuleEngine


class MotionAnalyzer:
    """
    合并所有指标并输出 Pipeline 结果。
    工作流: Angle + Alignment → merge → filter by enabled → noise → rule
    """

    def __init__(self,
                 angle_calc: AngleCalculator,
                 alignment_analyzer: AlignmentAnalyzer,
                 temporal_analyzer: TemporalAnalyzer,
                 noise_filter: NoiseFilter,
                 rule_engine: RuleEngine) -> None:
        self.angle_calc = angle_calc
        self.alignment_analyzer = alignment_analyzer
        self.temporal_analyzer = temporal_analyzer
        self.noise_filter = noise_filter
        self.rule_engine = rule_engine

    def analyze(self, pose: PoseResult, action_def: ActionDefinition,
                timestamp_ms: int) -> tuple[bool, float, AlignmentResult]:
        """
        分析一帧，返回 (activated, confidence, alignment)。
        """
        # Layer 1: 角度 + 偏移
        angle_values = self.angle_calc.calculate_all(pose)
        alignment = self.alignment_analyzer.calculate_all(pose)

        # Layer 2: 合并所有基础指标
        all_base = dict(angle_values)
        all_base.update(alignment.to_dict())

        # Layer 3: 时序指标
        temporal = self.temporal_analyzer.calculate(action_def, alignment, timestamp_ms)
        all_base.update(temporal.values)

        # Layer 4: 过滤到启用的指标
        selected = {mid: all_base[mid] for mid in action_def.enabled_metrics
                    if mid in all_base}

        # Layer 5: 噪声平滑
        _, filt_align, filt_selected = self.noise_filter.apply(
            angle_values, alignment, selected)

        # Layer 6: 规则评判
        activated, confidence = self.rule_engine.evaluate(action_def, filt_selected)

        return activated, confidence, filt_align
