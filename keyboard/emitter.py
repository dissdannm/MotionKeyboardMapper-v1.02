"""
键盘事件发射器 —— 基于 pynput 模拟键盘输入。

关键特性:
  - 支持按住 (hold) 和单次点击 (tap) 两种模式
  - 冷却机制避免同键连发 (spam prevention)
  - 自动管理按键状态转换 (idle → pressed → held → released)
  - 支持双人模式的独立键位
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set

from pynput.keyboard import Key, Controller, KeyCode


class KeyState(Enum):
    IDLE = 0
    PRESSED = 1
    HELD = 2


@dataclass
class _KeySlot:
    """单个按键槽位的运行时状态"""
    key: str
    state: KeyState = KeyState.IDLE
    last_press_time: float = 0.0
    hold: bool = True      # 是否保持按住


class KeyboardEmitter:
    """
    键盘事件发射器。

    用法:
        emitter = KeyboardEmitter(cooldown_ms=300)
        emitter.load_profile("config/profiles/naruto_fighting.json")
        # 每帧调用
        emitter.update({"walk_forward", "right_punch"})
    """

    def __init__(self, cooldown_ms: int = 300) -> None:
        self.cooldown_ms = cooldown_ms / 1000.0
        self._kb = Controller()
        self._slots: Dict[str, _KeySlot] = {}        # action_id → slot
        self._mapping: Dict[str, dict] = {}           # action_id → {key, hold}
        self._active_keys: Set[str] = set()
        self._action_to_key: Dict[str, str] = {}      # action_id → key_name

    def load_profile(self, profile_path: str) -> None:
        """加载映射配置 (JSON)"""
        import json
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._mapping.clear()
        self._slots.clear()
        self._action_to_key.clear()

        for m in data.get("mappings", []):
            gid = m["action_id"]
            key = m["key"]
            hold = m.get("hold", False)
            self._mapping[gid] = {"key": key, "hold": hold}
            self._action_to_key[gid] = key
            if gid not in self._slots:
                self._slots[key] = _KeySlot(key=key, hold=hold)

        print(f"[Keyboard] 已加载 {len(self._mapping)} 条映射 (profile={data.get('profile_id')})")

    def update(self, active_actions: Set[str]) -> None:
        """
        根据当前激活的手势更新键盘状态。
        active_actions: 当前帧激活的手势 ID 集合。
        """
        now = time.time()

        # 确定哪些按键应该被按下
        desired_keys: Dict[str, bool] = {}   # key_name → hold_mode
        for gid in active_actions:
            m = self._mapping.get(gid)
            if m is None:
                continue
            key = m["key"]
            # 如果多个手势映射到同一个键，取第一个
            if key not in desired_keys:
                desired_keys[key] = m["hold"]

        # 释放不再激活的按键
        for key in list(self._active_keys - set(desired_keys)):
            self._release_key(key)
            self._active_keys.discard(key)

        # 按下新激活的按键
        for key, hold in desired_keys.items():
            slot = self._slots.setdefault(key, _KeySlot(key=key, hold=hold))
            slot.hold = hold
            self._press_key(key, hold, now)

        self._active_keys = set(desired_keys)

    def _press_key(self, key: str, hold: bool, now: float) -> None:
        """根据 hold 模式执行按键"""
        slot = self._slots.get(key)
        if slot is None:
            return

        if slot.state == KeyState.IDLE:
            # 新按下
            self._tap(key)
            slot.state = KeyState.PRESSED if not hold else KeyState.HELD
            slot.last_press_time = now

        elif slot.state == KeyState.PRESSED:
            # 已点过，如果是 hold 模式则转为持续按住（无操作，pynput 自动维持）
            if hold:
                slot.state = KeyState.HELD

        elif slot.state == KeyState.HELD:
            # 非 hold 模式下检查冷却，允许多次触发
            if not hold and (now - slot.last_press_time) >= self.cooldown_ms:
                self._tap(key)
                slot.last_press_time = now

    def _release_key(self, key: str) -> None:
        """释放按键"""
        slot = self._slots.get(key)
        if slot is None:
            return

        if slot.state in (KeyState.PRESSED, KeyState.HELD):
            if slot.hold:
                # hold 模式需要主动释放
                self._release(key)
            # 非 hold 模式无需释放（tap 已完成）
        slot.state = KeyState.IDLE

    def _tap(self, key: str) -> None:
        """单次点击"""
        parsed = self._parse_key(key)
        self._kb.tap(parsed)

    def _release(self, key: str) -> None:
        """释放按键"""
        parsed = self._parse_key(key)
        self._kb.release(parsed)

    @staticmethod
    def _parse_key(key: str):
        """将字符串键名转换为 pynput Key 或 KeyCode"""
        special = {
            "space": Key.space,
            "enter": Key.enter,
            "esc": Key.esc,
            "tab": Key.tab,
            "shift": Key.shift,
            "ctrl": Key.ctrl,
            "alt": Key.alt,
            "up": Key.up,
            "down": Key.down,
            "left": Key.left,
            "right": Key.right,
            "backspace": Key.backspace,
            "delete": Key.delete,
            "caps_lock": Key.caps_lock,
            "cmd": Key.cmd,
            "f1": Key.f1, "f2": Key.f2, "f3": Key.f3,
            "f4": Key.f4, "f5": Key.f5, "f6": Key.f6,
            "f7": Key.f7, "f8": Key.f8, "f9": Key.f9,
            "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
        }
        key_lower = key.lower()
        if key_lower in special:
            return special[key_lower]
        return KeyCode.from_char(key_lower)

    def release_all(self) -> None:
        """释放所有当前按下的按键"""
        for key in list(self._active_keys):
            self._release_key(key)
        self._active_keys.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release_all()
