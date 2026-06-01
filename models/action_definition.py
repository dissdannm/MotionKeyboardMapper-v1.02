"""
动作定义数据模型 —— 从 JSON 加载。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SeverityRule:
    """分级阈值规则"""
    level: str          # "severe" | "moderate" | "mild"
    threshold: float    # 偏差阈值
    operator: str = "gt"  # "gt" = 大于阈值触发, "lt" = 小于阈值触发


@dataclass
class MetricRule:
    """单个指标规则"""
    metric_id: str
    normal_lo: float = 0.0
    normal_hi: float = 0.0
    severity_rules: List[SeverityRule] = field(default_factory=list)
    voice_prompt: str = ""


@dataclass
class ActionDefinition:
    """完整的动作定义（对应一个身体动作）"""
    action_id: str
    name: str = ""
    action_type: str = "pose"                 # "pose" | "motion"
    description: str = ""
    hold_frames: int = 2
    enabled_metrics: List[str] = field(default_factory=list)   # 关注的指标ID列表
    metric_rules: Dict[str, MetricRule] = field(default_factory=dict)  # metric_id → 规则
    conflict_group: str = ""


@dataclass
class MetricCatalogEntry:
    """指标目录条目（描述元数据——从 metric_catalog.json 加载）"""
    metric_id: str
    display_name: str = ""
    category: str = ""       # "angle" | "alignment" | "temporal"
    unit: str = "°"
    description: str = ""
