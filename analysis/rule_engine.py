"""
动作规则引擎 —— 对照 JSON 阈值判定激活/非激活。

设计:
  1. 读取 ActionDefinition 中的 metric_rules (normal_lo / normal_hi)
  2. 对每个启用的指标检查 filtered 值是否在正常范围内
  3. 全部指标通过 → 动作激活
  4. 任一指标超出 → 动作不激活
"""

from __future__ import annotations

from models.action_definition import ActionDefinition


class RuleEngine:
    """
    动作规则评判器。
    返回 (activated: bool, confidence: float)
    """

    def evaluate(self, action_def: ActionDefinition,
                 filtered_selected: dict[str, float]) -> tuple[bool, float]:
        """评估所有启用的指标是否都在正常范围内。"""
        if not action_def.enabled_metrics:
            return False, 0.0

        total_conf = 0.0
        count = 0

        for metric_id in action_def.enabled_metrics:
            rule = action_def.metric_rules.get(metric_id)
            if rule is None:
                continue
            value = filtered_selected.get(metric_id)
            if value is None:
                return False, 0.0

            lo = rule.get("normal_lo", 0) if isinstance(rule, dict) else rule.normal_lo
            hi = rule.get("normal_hi", 0) if isinstance(rule, dict) else rule.normal_hi

            if value < lo or value > hi:
                return False, 0.0

            # 区间内归一化置信度: 越接近中点越高
            mid = (lo + hi) / 2
            half_range = (hi - lo) / 2
            if half_range > 0:
                conf = 1.0 - min(abs(value - mid) / half_range, 1.0) * 0.4
            else:
                conf = 1.0
            total_conf += conf
            count += 1

        if count == 0:
            return False, 0.0

        return True, total_conf / count
