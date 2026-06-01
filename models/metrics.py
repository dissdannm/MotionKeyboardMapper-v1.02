"""
指标数据模型 —— 分层姿态分析的结果容器。
对齐参考项目 models/metrics.py 的结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.alignment_analyzer import AlignmentResult


@dataclass
class AngleMetrics:
    """角度类指标集合（10个关节角度 + 其他）"""
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class MotionMetrics:
    """动作级指标结果 —— 合并角度+偏移+时序"""
    angles: dict[str, float] = field(default_factory=dict)
    alignment: AlignmentResult | None = None
    selected: dict[str, float] = field(default_factory=dict)
