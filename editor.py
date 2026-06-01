"""
MotionKeyboardMapper — 动作/档案自定义编辑器
从启动器 [打开编辑器] 按钮打开，独立窗口。
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from tkinter import Toplevel, Frame, Label, Button, Entry, StringVar, IntVar, \
    DoubleVar, BooleanVar, Checkbutton, OptionMenu, messagebox, \
    Listbox, Scrollbar, Canvas, DISABLED, NORMAL

if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG

# ── 样式常量 (与 launcher 保持一致) ──────────────────────────────────
BG_MAIN = "#1a1a2e"
BG_PANEL = "#16213e"
BG_BUTTON = "#0f3460"
FG_ACCENT = "#e94560"
FG_ACCENT2 = "#00d2ff"
FG_TEXT = "#eaeaea"
FG_DIM = "#8899aa"
FONT_TITLE = ("Microsoft YaHei", 13, "bold")
FONT_NORMAL = ("Microsoft YaHei", 10)
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_MONO = ("Consolas", 9)

# 按键候选列表
KEY_OPTIONS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "space", "enter", "esc", "tab", "shift", "ctrl", "alt",
    "up", "down", "left", "right",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
]

CONFLICT_GROUPS = ["movement", "arm_action", "body_action"]


class EditorWindow:
    """独立的编辑器窗口"""

    def __init__(self) -> None:
        self.win = Toplevel()
        self.win.title("动作/档案编辑器 — MotionKeyboardMapper")
        self.win.geometry("1100x700")
        self.win.configure(bg=BG_MAIN)
        self.win.minsize(900, 550)

        # 数据
        self._actions: dict = {}
        self._catalog: dict = {}
        self._profiles: dict[str, dict] = {}  # profile_id → data
        self._selected_action: str | None = None
        self._selected_profile: str | None = None

        # 指标行控件: metric_id → {check_var, lo_var, hi_var, scale_lo, scale_hi, ...}
        self._metric_widgets: dict = {}

        self._load_data()
        self._build_ui()

    # ═══════════════════════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════════════════════

    def _load_data(self) -> None:
        # 动作定义
        with open(ACTIONS_DEFS, "r", encoding="utf-8") as f:
            self._actions = json.load(f).get("actions", {})
        # 指标目录
        with open(METRIC_CATALOG, "r", encoding="utf-8") as f:
            self._catalog = json.load(f).get("metrics", {})
        # 按键档案
        for fp in PROFILES_DIR.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                pid = data.get("profile_id", fp.stem)
                self._profiles[pid] = data
            except Exception:
                pass

    def _save_actions(self) -> None:
        """写回 naruto_actions.json"""
        data = {
            "_description": "火影忍者格斗 — 全身姿态动作定义",
            "version": "1.0.0",
            "player_count": 1,
            "actions": self._actions,
        }
        with open(ACTIONS_DEFS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Editor] 动作定义已保存 → {ACTIONS_DEFS.name}")

    def _save_profiles(self, pid: str) -> None:
        fp = PROFILES_DIR / f"{pid}.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(self._profiles[pid], f, ensure_ascii=False, indent=2)
        print(f"[Editor] 档案已保存 → {fp.name}")

    # ═══════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        # 顶栏
        top = Frame(self.win, bg=BG_MAIN)
        top.pack(fill="x", padx=12, pady=(10, 0))
        Label(top, text="动作 / 档案编辑器", font=FONT_TITLE,
              fg=FG_ACCENT, bg=BG_MAIN).pack(side="left")
        Label(top, text="所有修改保存后立即生效，无需重启",
              font=FONT_SMALL, fg=FG_DIM, bg=BG_MAIN).pack(side="right")

        # 主区域
        main = Frame(self.win, bg=BG_MAIN)
        main.pack(fill="both", expand=True, padx=12, pady=8)

        # 左侧列表 (30%)
        left = Frame(main, bg=BG_PANEL, width=240)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        self._build_left_panel(left)

        # 右侧详情 (70%)
        right = Frame(main, bg=BG_PANEL)
        right.pack(side="left", fill="both", expand=True)
        self._right_frame = right

    # ── 左侧列表 ──

    def _build_left_panel(self, parent: Frame) -> None:
        # 动作分区
        Label(parent, text=" 动作定义", font=FONT_NORMAL, fg=FG_ACCENT2,
              bg=BG_PANEL, anchor="w").pack(fill="x", padx=8, pady=(8, 2))

        list_frame = Frame(parent, bg=BG_PANEL)
        list_frame.pack(fill="both", expand=True, padx=4, pady=2)

        scroll = Scrollbar(list_frame, orient="vertical")
        self._action_listbox = Listbox(
            list_frame, yscrollcommand=scroll.set,
            bg=BG_MAIN, fg=FG_TEXT, font=FONT_SMALL,
            selectbackground=FG_ACCENT, selectforeground="#fff",
            activestyle="none", borderwidth=0, highlightthickness=0,
            exportselection=False)
        scroll.config(command=self._action_listbox.yview)
        self._action_listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._action_listbox.bind("<<ListboxSelect>>", self._on_action_select)

        # 动作按钮
        abtn = Frame(parent, bg=BG_PANEL)
        abtn.pack(fill="x", padx=4, pady=(2, 6))
        Button(abtn, text="+ 新增动作", font=FONT_SMALL,
               bg=BG_BUTTON, fg=FG_TEXT, relief="flat", cursor="hand2",
               command=self._on_new_action).pack(side="left", padx=2)

        # 分隔
        Frame(parent, bg=BG_BUTTON, height=1).pack(fill="x", padx=8, pady=2)

        # 档案分区
        Label(parent, text=" 按键档案", font=FONT_NORMAL, fg=FG_ACCENT2,
              bg=BG_PANEL, anchor="w").pack(fill="x", padx=8, pady=(6, 2))

        pf_frame = Frame(parent, bg=BG_PANEL)
        pf_frame.pack(fill="both", expand=True, padx=4, pady=2)

        pscroll = Scrollbar(pf_frame, orient="vertical")
        self._profile_listbox = Listbox(
            pf_frame, yscrollcommand=pscroll.set,
            bg=BG_MAIN, fg=FG_TEXT, font=FONT_SMALL,
            selectbackground=FG_ACCENT, selectforeground="#fff",
            activestyle="none", borderwidth=0, highlightthickness=0,
            exportselection=False)
        pscroll.config(command=self._profile_listbox.yview)
        self._profile_listbox.pack(side="left", fill="both", expand=True)
        pscroll.pack(side="right", fill="y")
        self._profile_listbox.bind("<<ListboxSelect>>", self._on_profile_select)

        # 档案按钮
        pbtn = Frame(parent, bg=BG_PANEL)
        pbtn.pack(fill="x", padx=4, pady=(2, 8))
        Button(pbtn, text="+ 新增档案", font=FONT_SMALL,
               bg=BG_BUTTON, fg=FG_TEXT, relief="flat", cursor="hand2",
               command=self._on_new_profile).pack(side="left", padx=2)

        # 填充列表
        self._refresh_action_list()
        self._refresh_profile_list()

    def _refresh_action_list(self) -> None:
        self._action_listbox.delete(0, "end")
        for aid, adef in self._actions.items():
            name = adef.get("name", aid) if isinstance(adef, dict) else adef.name
            self._action_listbox.insert("end", f"  {name}")

    def _refresh_profile_list(self) -> None:
        self._profile_listbox.delete(0, "end")
        for pid, pdata in self._profiles.items():
            name = pdata.get("profile_name", pid)
            self._profile_listbox.insert("end", f"  {name}")

    # ── 右侧详情 ──

    def _build_action_detail(self) -> Frame:
        """构建动作详情编辑面板"""
        # 清除旧内容
        for w in self._right_frame.winfo_children():
            w.destroy()

        panel = Frame(self._right_frame, bg=BG_PANEL)
        panel.pack(fill="both", expand=True)
        self._metric_widgets.clear()

        aid = self._selected_action
        adef = self._actions.get(aid, {}) if isinstance(
            self._actions.get(aid, {}), dict) else {}

        # ── 顶部：基本信息 ──
        info = Frame(panel, bg=BG_PANEL)
        info.pack(fill="x", padx=10, pady=(8, 4))

        # 行1: ID + 名称
        r1 = Frame(info, bg=BG_PANEL)
        r1.pack(fill="x", pady=2)
        Label(r1, text="动作ID:", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
              width=8, anchor="w").pack(side="left")
        self._var_aid = StringVar(value=aid or "")
        Entry(r1, textvariable=self._var_aid, font=FONT_MONO, width=22,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(side="left", padx=4)
        Label(r1, text="名称:", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
              width=5, anchor="w").pack(side="left", padx=(12, 0))
        self._var_name = StringVar(value=adef.get("name", ""))
        Entry(r1, textvariable=self._var_name, font=FONT_NORMAL, width=18,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(side="left", padx=4)

        # 行2: 类型 + 冲突组 + hold帧数
        r2 = Frame(info, bg=BG_PANEL)
        r2.pack(fill="x", pady=2)
        Label(r2, text="类型:", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
              width=8, anchor="w").pack(side="left")
        self._var_type = StringVar(value=adef.get("action_type", "pose"))
        om = OptionMenu(r2, self._var_type, "pose", "motion")
        om.configure(font=FONT_SMALL, bg=BG_BUTTON, fg=FG_TEXT,
                     activebackground=BG_BUTTON, activeforeground=FG_TEXT, width=8)
        om.pack(side="left", padx=4)

        Label(r2, text="冲突组:", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
              width=7, anchor="w").pack(side="left", padx=(8, 0))
        self._var_cgroup = StringVar(value=adef.get("conflict_group", ""))
        cg_om = OptionMenu(r2, self._var_cgroup, *CONFLICT_GROUPS)
        cg_om.configure(font=FONT_SMALL, bg=BG_BUTTON, fg=FG_TEXT,
                        activebackground=BG_BUTTON, activeforeground=FG_TEXT, width=12)
        cg_om.pack(side="left", padx=4)

        Label(r2, text="hold帧:", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
              width=7, anchor="w").pack(side="left", padx=(8, 0))
        self._var_hold = IntVar(value=int(adef.get("hold_frames", 1)))
        Entry(r2, textvariable=self._var_hold, font=FONT_MONO, width=4,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(side="left", padx=4)

        # ── 分隔 ──
        Frame(panel, bg=BG_BUTTON, height=1).pack(fill="x", padx=10, pady=4)

        # ── 中部：26指标选择区 (可滚动) ──
        Label(panel, text="  指标选择与阈值", font=FONT_NORMAL, fg=FG_ACCENT2,
              bg=BG_PANEL, anchor="w").pack(fill="x", padx=10, pady=(4, 2))

        canvas = Canvas(panel, bg=BG_PANEL, highlightthickness=0, height=320)
        mscroll = Scrollbar(panel, orient="vertical", command=canvas.yview)
        metric_frame = Frame(canvas, bg=BG_PANEL)
        metric_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=metric_frame, anchor="nw")
        canvas.configure(yscrollcommand=mscroll.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=2)
        mscroll.pack(side="right", fill="y", padx=(0, 6), pady=2)

        # 鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        enabled_metrics = adef.get("enabled_metrics", [])
        metric_rules = adef.get("metric_rules", {})

        for mid in self._catalog:
            minfo = self._catalog[mid]
            enabled = mid in enabled_metrics
            rule = metric_rules.get(mid, {})
            lo = rule.get("normal_lo", 0)
            hi = rule.get("normal_hi", 100)

            self._build_metric_row(metric_frame, mid, minfo, enabled, lo, hi)

        # ── 分隔 ──
        Frame(panel, bg=BG_BUTTON, height=1).pack(fill="x", padx=10, pady=4)

        # ── 底部：按键映射 + 保存/删除 ──
        bottom = Frame(panel, bg=BG_PANEL)
        bottom.pack(fill="x", padx=10, pady=(4, 8))

        Label(bottom, text="映射按键:", font=FONT_NORMAL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left")
        self._var_key = StringVar(value="")
        key_om = OptionMenu(bottom, self._var_key, *KEY_OPTIONS)
        key_om.configure(font=FONT_MONO, bg=BG_BUTTON, fg=FG_TEXT,
                         activebackground=BG_BUTTON, activeforeground=FG_TEXT, width=6)
        key_om.pack(side="left", padx=6)

        self._var_hold_mode = BooleanVar(value=False)
        Checkbutton(bottom, text="按住模式", variable=self._var_hold_mode,
                    font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
                    selectcolor=BG_MAIN).pack(side="left", padx=8)

        # 从档案中读取当前映射
        self._load_key_mapping(aid)

        # 保存 / 删除
        Button(bottom, text="保存动作", font=("Microsoft YaHei", 10, "bold"),
               bg=FG_ACCENT, fg="#fff", activebackground="#ff5a75",
               activeforeground="#fff", relief="flat", cursor="hand2",
               command=self._on_save_action, padx=16, pady=6).pack(
            side="right", padx=4)
        Button(bottom, text="删除动作", font=FONT_NORMAL,
               bg="#aa3333", fg="#fff", activebackground="#cc5555",
               activeforeground="#fff", relief="flat", cursor="hand2",
               command=self._on_delete_action, padx=12, pady=6).pack(
            side="right", padx=4)

        return panel

    def _build_metric_row(self, parent: Frame, mid: str,
                          minfo: dict, enabled: bool,
                          lo: float, hi: float) -> None:
        """构建单行指标: 勾选框 + 名称 + 双滑块"""
        row = Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=1)

        var_enabled = BooleanVar(value=enabled)
        cb = Checkbutton(row, variable=var_enabled,
                         bg=BG_PANEL, fg=FG_TEXT,
                         selectcolor=BG_MAIN, activebackground=BG_PANEL)
        cb.pack(side="left")

        name = minfo.get("display_name", mid)
        unit = minfo.get("unit", "")
        Label(row, text=f"{name}", font=FONT_SMALL, fg=FG_TEXT,
              bg=BG_PANEL, width=16, anchor="w").pack(side="left", padx=2)
        Label(row, text=f"({unit})", font=FONT_SMALL, fg=FG_DIM,
              bg=BG_PANEL, width=8, anchor="w").pack(side="left")

        # 滑块范围根据单位决定
        if unit == "°":
            rmin, rmax, step = 0, 200, 1
        elif unit in ("ratio", "ratio/s"):
            rmin, rmax, step = -1.0, 1.0, 0.01
        elif unit == "ms":
            rmin, rmax, step = 0, 5000, 10
        elif unit == "count":
            rmin, rmax, step = 0, 100, 1
        else:
            rmin, rmax, step = 0, 200, 1

        # lo 滑块
        var_lo = DoubleVar(value=max(lo, rmin))
        var_hi = DoubleVar(value=min(hi, rmax))
        lbl_lo = Label(row, text=f"{lo:g}", font=FONT_MONO, fg=FG_ACCENT2,
                       bg=BG_PANEL, width=5, anchor="e")
        lbl_lo.pack(side="left", padx=(4, 0))

        s_lo = Scale(row, from_=rmin, to=rmax, resolution=step,
                     orient="horizontal", length=100,
                     variable=var_lo, bg=BG_PANEL, fg=FG_ACCENT2,
                     troughcolor=BG_MAIN, highlightthickness=0,
                     showvalue=False, command=lambda v, l=lbl_lo: l.configure(
                         text=f"{float(v):g}"))
        s_lo.pack(side="left", padx=2)

        Label(row, text="—", font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL).pack(side="left")

        lbl_hi = Label(row, text=f"{hi:g}", font=FONT_MONO, fg=FG_ACCENT2,
                       bg=BG_PANEL, width=5, anchor="w")
        lbl_hi.pack(side="left")

        s_hi = Scale(row, from_=rmin, to=rmax, resolution=step,
                     orient="horizontal", length=100,
                     variable=var_hi, bg=BG_PANEL, fg=FG_ACCENT2,
                     troughcolor=BG_MAIN, highlightthickness=0,
                     showvalue=False, command=lambda v, l=lbl_hi: l.configure(
                         text=f"{float(v):g}"))
        s_hi.pack(side="left", padx=2)

        self._metric_widgets[mid] = {
            "enabled": var_enabled,
            "lo": var_lo,
            "hi": var_hi,
            "lo_label": lbl_lo,
            "hi_label": lbl_hi,
        }

    def _build_profile_detail(self) -> Frame:
        """构建档案详情面板 —— 显示动作→按键映射表"""
        for w in self._right_frame.winfo_children():
            w.destroy()

        panel = Frame(self._right_frame, bg=BG_PANEL)
        panel.pack(fill="both", expand=True)

        pid = self._selected_profile
        pdata = self._profiles.get(pid, {})
        mappings = pdata.get("mappings", [])

        # 档案名称
        info = Frame(panel, bg=BG_PANEL)
        info.pack(fill="x", padx=10, pady=8)
        Label(info, text="档案ID:", font=FONT_SMALL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left")
        self._var_pid = StringVar(value=pid or "")
        Entry(info, textvariable=self._var_pid, font=FONT_MONO, width=20,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(
            side="left", padx=4)
        Label(info, text="名称:", font=FONT_SMALL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left", padx=(10, 0))
        self._var_pname = StringVar(value=pdata.get("profile_name", ""))
        Entry(info, textvariable=self._var_pname, font=FONT_NORMAL, width=18,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(
            side="left", padx=4)

        # 映射表头
        Frame(panel, bg=BG_BUTTON, height=1).pack(fill="x", padx=10, pady=4)

        hdr = Frame(panel, bg=BG_PANEL)
        hdr.pack(fill="x", padx=10, pady=2)
        for text, w in [("动作", 28), ("按键", 8), ("模式", 8), ("描述", 36)]:
            Label(hdr, text=text, font=FONT_SMALL, fg=FG_ACCENT2,
                  bg=BG_PANEL, width=w, anchor="w").pack(side="left")

        # 映射行
        map_canvas = Canvas(panel, bg=BG_PANEL, highlightthickness=0, height=280)
        map_scroll = Scrollbar(panel, orient="vertical", command=map_canvas.yview)
        self._map_frame = Frame(map_canvas, bg=BG_PANEL)
        self._map_frame.bind("<Configure>",
                             lambda e: map_canvas.configure(
                                 scrollregion=map_canvas.bbox("all")))
        map_canvas.create_window((0, 0), window=self._map_frame, anchor="nw")
        map_canvas.configure(yscrollcommand=map_scroll.set)
        map_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0))
        map_scroll.pack(side="right", fill="y", padx=(0, 6))

        self._mapping_rows: list[dict] = []
        action_ids = list(self._actions.keys())
        for m in mappings:
            self._build_mapping_row(self._map_frame, m, action_ids)

        # 按钮
        btnf = Frame(panel, bg=BG_PANEL)
        btnf.pack(fill="x", padx=10, pady=(4, 8))
        Button(btnf, text="+ 添加映射", font=FONT_SMALL,
               bg=BG_BUTTON, fg=FG_TEXT, relief="flat", cursor="hand2",
               command=lambda: self._build_mapping_row(
                   self._map_frame,
                   {"action_id": "", "key": "", "hold": False,
                    "description": ""}, action_ids)).pack(side="left")

        Button(btnf, text="保存档案", font=("Microsoft YaHei", 10, "bold"),
               bg=FG_ACCENT, fg="#fff", activebackground="#ff5a75",
               activeforeground="#fff", relief="flat", cursor="hand2",
               command=self._on_save_profile, padx=16, pady=6).pack(
            side="right", padx=4)

        return panel

    def _build_mapping_row(self, parent: Frame, m: dict,
                           action_ids: list) -> None:
        """构建一行映射"""
        row = Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=1)

        var_aid = StringVar(value=m.get("action_id", ""))
        om = OptionMenu(row, var_aid, *action_ids)
        om.configure(font=FONT_SMALL, bg=BG_BUTTON, fg=FG_TEXT,
                     activebackground=BG_BUTTON, activeforeground=FG_TEXT, width=22)
        om.pack(side="left", padx=2)

        var_key = StringVar(value=m.get("key", ""))
        kom = OptionMenu(row, var_key, *KEY_OPTIONS)
        kom.configure(font=FONT_MONO, bg=BG_BUTTON, fg=FG_TEXT,
                      activebackground=BG_BUTTON, activeforeground=FG_TEXT, width=6)
        kom.pack(side="left", padx=2)

        var_hold = BooleanVar(value=m.get("hold", False))
        cb = Checkbutton(row, variable=var_hold, text="按住" if var_hold.get() else "点击",
                         font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL,
                         selectcolor=BG_MAIN)
        cb.pack(side="left", padx=2)
        var_hold.trace("w", lambda *_, c=cb, v=var_hold:
                       c.configure(text="按住" if v.get() else "点击"))

        var_desc = StringVar(value=m.get("description", ""))
        Entry(row, textvariable=var_desc, font=FONT_SMALL, width=30,
              bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT).pack(
            side="left", padx=2)

        Button(row, text="✕", font=FONT_SMALL, fg=FG_ACCENT,
               bg=BG_PANEL, relief="flat", cursor="hand2",
               command=lambda r=row: (r.destroy(),
                                      self._mapping_rows.remove(row_data))
               ).pack(side="left")

        row_data = {"row": row, "aid": var_aid, "key": var_key,
                    "hold": var_hold, "desc": var_desc}
        self._mapping_rows.append(row_data)

    # ── 按键映射加载 ──

    def _load_key_mapping(self, aid: str) -> None:
        """从当前选中的档案加载动作的按键映射"""
        pid = self._selected_profile
        if not pid or pid not in self._profiles:
            self._var_key.set("")
            self._var_hold_mode.set(False)
            return
        for m in self._profiles[pid].get("mappings", []):
            if m.get("action_id") == aid:
                self._var_key.set(m.get("key", ""))
                self._var_hold_mode.set(m.get("hold", False))
                return
        self._var_key.set("")
        self._var_hold_mode.set(False)

    # ═══════════════════════════════════════════════════════════════
    # 事件处理
    # ═══════════════════════════════════════════════════════════════

    def _on_action_select(self, event) -> None:
        sel = self._action_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        aid = list(self._actions.keys())[idx]
        self._selected_action = aid
        self._build_action_detail()

    def _on_profile_select(self, event) -> None:
        sel = self._profile_listbox.curselection()
        if not sel:
            return
        pid = list(self._profiles.keys())[sel[0]]
        self._selected_profile = pid
        self._build_profile_detail()

    def _on_new_action(self) -> None:
        base = "custom"
        i = 1
        while f"{base}_{i}" in self._actions:
            i += 1
        new_id = f"{base}_{i}"
        self._actions[new_id] = {
            "action_id": new_id,
            "name": f"自定义动作{i}",
            "action_type": "pose",
            "description": "",
            "hold_frames": 2,
            "enabled_metrics": [],
            "metric_rules": {},
            "conflict_group": "",
        }
        self._refresh_action_list()
        # 选中新动作
        idx = list(self._actions.keys()).index(new_id)
        self._action_listbox.selection_clear(0, "end")
        self._action_listbox.selection_set(idx)
        self._action_listbox.see(idx)
        self._selected_action = new_id
        self._build_action_detail()

    def _on_new_profile(self) -> None:
        base = "new_profile"
        i = 1
        while f"{base}_{i}" in self._profiles:
            i += 1
        pid = f"{base}_{i}"
        self._profiles[pid] = {
            "profile_id": pid,
            "profile_name": f"新档案{i}",
            "description": "",
            "version": "1.0.0",
            "player_count": 1,
            "mappings": [],
        }
        self._save_profiles(pid)
        self._refresh_profile_list()
        idx = list(self._profiles.keys()).index(pid)
        self._profile_listbox.selection_clear(0, "end")
        self._profile_listbox.selection_set(idx)
        self._profile_listbox.see(idx)
        self._selected_profile = pid
        self._build_profile_detail()

    def _on_save_action(self) -> None:
        aid = self._var_aid.get().strip()
        if not aid:
            messagebox.showerror("错误", "动作ID不能为空", parent=self.win)
            return
        if aid != self._selected_action:
            # 改名
            if aid in self._actions:
                messagebox.showerror("错误",
                                     f"动作ID '{aid}' 已存在", parent=self.win)
                return
            del self._actions[self._selected_action]
            self._selected_action = aid

        # 收集启用的指标和规则
        enabled_metrics: list[str] = []
        metric_rules: dict = {}
        for mid, w in self._metric_widgets.items():
            if w["enabled"].get():
                enabled_metrics.append(mid)
                lo = w["lo"].get()
                hi = w["hi"].get()
                # 确保 lo < hi
                if lo > hi:
                    lo, hi = hi, lo
                metric_rules[mid] = {
                    "normal_lo": round(lo, 2),
                    "normal_hi": round(hi, 2),
                    "severity_rules": [],
                }

        if not enabled_metrics:
            messagebox.showerror("错误",
                                 "请至少启用一个指标", parent=self.win)
            return

        self._actions[aid] = {
            "action_id": aid,
            "name": self._var_name.get().strip() or aid,
            "action_type": self._var_type.get(),
            "description": "",
            "hold_frames": max(1, self._var_hold.get()),
            "enabled_metrics": enabled_metrics,
            "metric_rules": metric_rules,
            "conflict_group": self._var_cgroup.get(),
        }

        # 更新按键映射到档案
        key = self._var_key.get().strip()
        if key and self._selected_profile:
            self._update_key_mapping(aid, key)

        self._save_actions()
        self._refresh_action_list()
        messagebox.showinfo("已保存",
                            f"动作 '{aid}' 已保存", parent=self.win)

    def _update_key_mapping(self, aid: str, key: str) -> None:
        """将按键映射同步到当前档案"""
        pid = self._selected_profile
        if not pid or pid not in self._profiles:
            return
        mappings = self._profiles[pid].get("mappings", [])
        found = False
        for m in mappings:
            if m.get("action_id") == aid:
                m["key"] = key
                m["hold"] = self._var_hold_mode.get()
                found = True
                break
        if not found:
            mappings.append({
                "action_id": aid,
                "action_name": self._var_name.get(),
                "key": key,
                "hold": self._var_hold_mode.get(),
                "description": "",
            })
        self._profiles[pid]["mappings"] = mappings
        self._save_profiles(pid)

    def _on_delete_action(self) -> None:
        aid = self._selected_action
        if not aid:
            return
        if not messagebox.askyesno("确认删除",
                                   f"确定要删除动作 '{aid}' 吗？\n此操作不可恢复。",
                                   parent=self.win):
            return
        del self._actions[aid]
        self._save_actions()
        self._selected_action = None
        self._refresh_action_list()
        for w in self._right_frame.winfo_children():
            w.destroy()

    def _on_save_profile(self) -> None:
        pid = self._var_pid.get().strip()
        if not pid or self._selected_profile is None:
            return
        # 收集映射
        mappings = []
        for rdata in self._mapping_rows:
            aid = rdata["aid"].get()
            if not aid:
                continue
            # 获取动作名
            adef = self._actions.get(aid, {})
            name = adef.get("name", aid) if isinstance(adef, dict) else getattr(
                adef, "name", aid)
            mappings.append({
                "action_id": aid,
                "action_name": name,
                "key": rdata["key"].get(),
                "hold": rdata["hold"].get(),
                "description": rdata["desc"].get(),
            })

        self._profiles[pid] = {
            "profile_id": pid,
            "profile_name": self._var_pname.get() or pid,
            "description": "",
            "version": "1.0.0",
            "player_count": 1,
            "mappings": mappings,
        }
        self._save_profiles(pid)
        self._refresh_profile_list()
        messagebox.showinfo("已保存",
                            f"档案 '{pid}' 已保存", parent=self.win)


def open_editor() -> EditorWindow:
    """外部调用入口 —— 返回 EditorWindow 实例让调用方可管理生命周期"""
    editor = EditorWindow()
    editor.win.focus_set()
    return editor
