"""
MotionKeyboardMapper — 动作/档案编辑器 (Flet · Apple 风格)
独立 Flet 窗口，从启动器 [编辑配置] 按钮打开。
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import flet as ft

if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG


# ══════════════════════════════════════════════════════════════════════
# Apple 风格色彩 (与 launcher 保持一致)
# ══════════════════════════════════════════════════════════════════════

# ── 共享常量 ──
_FONT = "Microsoft YaHei"
_RADIUS_SM, _RADIUS_MD, _RADIUS_LG, _RADIUS_XL = 8, 12, 16, 24
_ACCENT = dict(BLUE="#007aff", RED="#ff3b30", GREEN="#34c759",
               ORANGE="#ff9500", TEAL="#64d2ff", PURPLE="#5e5ce6")


class _ThemeData:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        for k, v in _ACCENT.items():
            setattr(self, k, v)
        self.FONT = _FONT
        self.RADIUS_SM, self.RADIUS_MD = _RADIUS_SM, _RADIUS_MD
        self.RADIUS_LG, self.RADIUS_XL = _RADIUS_LG, _RADIUS_XL


AppleDark = _ThemeData(
    BG_BASE="#161618", BG_CARD="#1e1e22", BG_ELEVATED="#2c2c33", BG_HOVER="#36363e",
    GLASS="#ffffff07", GLASS_BORDER="#ffffff14",
    TEXT_PRIMARY="#f5f5f7", TEXT_SECONDARY="#a1a1a6", TEXT_TERTIARY="#6e6e73",
    BORDER="#2c2c33", BORDER_LIGHT="#3a3a42",
    GRADIENT_TOP="#1a1a20", GRADIENT_BOTTOM="#1e1e26",
    SHADOW="#00000040", TOGGLE_BG="#ffffff10",
)

AppleLight = _ThemeData(
    BG_BASE="#f2f2f7", BG_CARD="#fafafc", BG_ELEVATED="#ffffff", BG_HOVER="#e8e8ed",
    GLASS="#ffffff80", GLASS_BORDER="#0000000d",
    TEXT_PRIMARY="#1d1d1f", TEXT_SECONDARY="#6e6e73", TEXT_TERTIARY="#aeaeb2",
    BORDER="#d1d1d6", BORDER_LIGHT="#c7c7cc",
    GRADIENT_TOP="#f0f0f5", GRADIENT_BOTTOM="#f8f8fc",
    SHADOW="#00000010", TOGGLE_BG="#00000008",
)

Apple = AppleDark


KEY_OPTIONS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "space", "enter", "esc", "tab", "shift", "ctrl", "alt",
    "up", "down", "left", "right",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
]

CONFLICT_GROUPS = ["movement", "arm_action", "body_action"]


# ══════════════════════════════════════════════════════════════════════
# 编辑器应用
# ══════════════════════════════════════════════════════════════════════

class EditorApp:
    """Apple 风格编辑器"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._dark_mode = True
        self._setup_page()

        # 数据
        self._actions: dict = {}
        self._catalog: dict = {}
        self._profiles: dict[str, dict] = {}
        self._selected_action: str | None = None
        self._selected_profile: str | None = None

        # 指标控件 refs: mid → {enabled, lo_slider, hi_slider, lo_text, hi_text}
        self._metric_refs: dict = {}

        # 映射行数据
        self._mapping_rows: list[dict] = []

        # 主要 refs
        self._action_list = ft.Ref[ft.ListView]()
        self._profile_list = ft.Ref[ft.ListView]()
        self._detail_area = ft.Ref[ft.Column]()

        # 动作编辑 refs
        self._var_aid = ft.Ref[ft.TextField]()
        self._var_name = ft.Ref[ft.TextField]()
        self._var_type = ft.Ref[ft.Dropdown]()
        self._var_cgroup = ft.Ref[ft.Dropdown]()
        self._var_hold = ft.Ref[ft.TextField]()
        self._var_key = ft.Ref[ft.Dropdown]()

        # 档案编辑 refs
        self._var_pid = ft.Ref[ft.TextField]()
        self._var_pname = ft.Ref[ft.TextField]()

        self._load_data()
        self._build_ui()
        self._refresh_action_list()
        self._refresh_profile_list()

    def _setup_page(self) -> None:
        self.page.title = "动作/档案编辑器 — MotionKeyboardMapper"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.window.width = 1100
        self.page.window.height = 720
        self.page.window.min_width = 900
        self.page.window.min_height = 550
        self.page.font_family = Apple.FONT
        self.page.bgcolor = Apple.BG_BASE

    # ═══════════════════════════════════════════════════════════════
    # 数据加载 / 保存
    # ═══════════════════════════════════════════════════════════════

    def _load_data(self) -> None:
        with open(ACTIONS_DEFS, "r", encoding="utf-8") as f:
            self._actions = json.load(f).get("actions", {})
        with open(METRIC_CATALOG, "r", encoding="utf-8") as f:
            self._catalog = json.load(f).get("metrics", {})
        for fp in PROFILES_DIR.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                pid = data.get("profile_id", fp.stem)
                self._profiles[pid] = data
            except Exception:
                pass

    def _save_actions(self) -> None:
        data = {
            "_description": "火影忍者格斗 — 全身姿态动作定义",
            "version": "1.0.0",
            "player_count": 1,
            "actions": self._actions,
        }
        with open(ACTIONS_DEFS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_profiles(self, pid: str) -> None:
        fp = PROFILES_DIR / f"{pid}.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(self._profiles[pid], f, ensure_ascii=False, indent=2)

    # ═══════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.page.controls.clear()
        bg = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[Apple.GRADIENT_TOP, Apple.GRADIENT_BOTTOM],
            ),
            padding=20,
            content=ft.Column(
                [
                    self._build_header(),
                    self._build_main(),
                ],
                spacing=12,
                expand=True,
            ),
        )
        self.page.add(bg)

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.EDIT_NOTE, color=Apple.BLUE, size=20),
                            ft.Text("动作 / 档案编辑器", size=16,
                                    weight=ft.FontWeight.W_700,
                                    color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
                        ],
                        spacing=10,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.DARK_MODE if self._dark_mode else ft.Icons.LIGHT_MODE,
                                    color=Apple.TEXT_SECONDARY, size=16,
                                ),
                                width=32, height=32, border_radius=16,
                                bgcolor=Apple.TOGGLE_BG,
                                alignment=ft.Alignment.CENTER,
                                on_click=lambda e: self._toggle_theme(),
                            ),
                            ft.Text("修改保存后立即生效，无需重启", size=11,
                                    color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                        ],
                        spacing=10,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding(bottom=8),
        )

    def _build_main(self) -> ft.Row:
        return ft.Row(
            [
                self._build_left_sidebar(),
                self._build_right_detail(),
            ],
            spacing=14,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    # ── 左侧栏 ──

    def _build_left_sidebar(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    self._build_action_list_section(),
                    ft.Divider(height=1, color=Apple.BORDER),
                    self._build_profile_list_section(),
                ],
                spacing=8,
                expand=True,
            ),
            width=250,
            border_radius=Apple.RADIUS_LG,
            bgcolor=Apple.BG_CARD,
            border=ft.BorderSide(1, Apple.BORDER),
            padding=14,
        )

    def _build_action_list_section(self) -> ft.Column:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("动作定义", size=13, weight=ft.FontWeight.W_600,
                                color=Apple.TEAL, font_family=Apple.FONT),
                        ft.Container(
                            content=ft.Text("+", size=16, weight=ft.FontWeight.W_700, color=Apple.BLUE),
                            width=26, height=26, border_radius=13,
                            bgcolor=f"{Apple.BLUE}20", alignment=ft.Alignment.CENTER,
                            on_click=lambda e: self._on_new_action(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(
                    content=ft.ListView(
                        ref=self._action_list, spacing=2, expand=True, height=260,
                    ),
                    expand=True,
                ),
            ],
            spacing=6,
            expand=1,
        )

    def _build_profile_list_section(self) -> ft.Column:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("按键档案", size=13, weight=ft.FontWeight.W_600,
                                color=Apple.TEAL, font_family=Apple.FONT),
                        ft.Container(
                            content=ft.Text("+", size=16, weight=ft.FontWeight.W_700, color=Apple.GREEN),
                            width=26, height=26, border_radius=13,
                            bgcolor=f"{Apple.GREEN}20", alignment=ft.Alignment.CENTER,
                            on_click=lambda e: self._on_new_profile(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(
                    content=ft.ListView(
                        ref=self._profile_list, spacing=2, expand=True, height=260,
                    ),
                    expand=True,
                ),
            ],
            spacing=6,
            expand=1,
        )

    # ── 右侧详情 ──

    def _build_right_detail(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                ref=self._detail_area,
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Icon(ft.Icons.TOUCH_APP, color=Apple.TEXT_TERTIARY, size=48),
                                ft.Text("从左侧列表选择动作或档案进行编辑",
                                        size=14, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=12,
                        ),
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                    ),
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            border_radius=Apple.RADIUS_LG,
            bgcolor=Apple.BG_CARD,
            border=ft.BorderSide(1, Apple.BORDER),
            padding=18,
        )

    # ═══════════════════════════════════════════════════════════════
    # 列表刷新
    # ═══════════════════════════════════════════════════════════════

    def _refresh_action_list(self) -> None:
        lv = self._action_list.current
        lv.controls.clear()
        for aid, adef in self._actions.items():
            name = adef.get("name", aid) if isinstance(adef, dict) else aid
            is_selected = aid == self._selected_action
            lv.controls.append(
                ft.Container(
                    content=ft.Text(f"  {name}", size=12, color=Apple.TEXT_PRIMARY if is_selected else Apple.TEXT_SECONDARY, font_family=Apple.FONT),
                    padding=ft.Padding(left=12, top=10, right=12, bottom=10),
                    border_radius=Apple.RADIUS_SM,
                    bgcolor=f"{Apple.BLUE}30" if is_selected else Apple.BG_CARD,
                    on_click=lambda e, a=aid: self._on_action_select(a),
                    animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
                )
            )
        self.page.update()

    def _refresh_profile_list(self) -> None:
        lv = self._profile_list.current
        lv.controls.clear()
        for pid, pdata in self._profiles.items():
            name = pdata.get("profile_name", pid)
            is_selected = pid == self._selected_profile
            lv.controls.append(
                ft.Container(
                    content=ft.Text(f"  {name}", size=12, color=Apple.TEXT_PRIMARY if is_selected else Apple.TEXT_SECONDARY, font_family=Apple.FONT),
                    padding=ft.Padding(left=12, top=10, right=12, bottom=10),
                    border_radius=Apple.RADIUS_SM,
                    bgcolor=f"{Apple.BLUE}30" if is_selected else Apple.BG_CARD,
                    on_click=lambda e, p=pid: self._on_profile_select(p),
                    animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
                )
            )
        self.page.update()

    # ═══════════════════════════════════════════════════════════════
    # 选择事件
    # ═══════════════════════════════════════════════════════════════

    def _on_action_select(self, aid: str) -> None:
        self._selected_action = aid
        self._selected_profile = None
        self._refresh_action_list()
        self._refresh_profile_list()
        self._build_action_detail()

    def _on_profile_select(self, pid: str) -> None:
        self._selected_profile = pid
        self._selected_action = None
        self._refresh_action_list()
        self._refresh_profile_list()
        self._build_profile_detail()

    # ═══════════════════════════════════════════════════════════════
    # 动作详情面板
    # ═══════════════════════════════════════════════════════════════

    def _build_action_detail(self) -> None:
        detail = self._detail_area.current
        detail.controls.clear()

        aid = self._selected_action
        adef = self._actions.get(aid, {})
        self._metric_refs.clear()

        # ── 基本信息 ──
        info_items = [
            ft.Row([
                ft.Text("动作ID", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=70),
                ft.TextField(
                    ref=self._var_aid, value=aid or "", text_size=13,
                    border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, content_padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                    width=200, height=34,
                ),
                ft.Text("名称", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=50),
                ft.TextField(
                    ref=self._var_name, value=adef.get("name", ""), text_size=13,
                    border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, content_padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                    width=180, height=34,
                ),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),

            ft.Row([
                ft.Text("类型", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=70),
                ft.Dropdown(
                    ref=self._var_type, width=120, height=34, text_size=12,
                    bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, border_radius=8,
                    value=adef.get("action_type", "pose"),
                    options=[
                        ft.dropdown.Option(key="pose", text="pose"),
                        ft.dropdown.Option(key="motion", text="motion"),
                    ],
                ),
                ft.Text("冲突组", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=55),
                ft.Dropdown(
                    ref=self._var_cgroup, width=130, height=34, text_size=12,
                    bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, border_radius=8,
                    value=adef.get("conflict_group", ""),
                    options=[ft.dropdown.Option(key=g, text=g) for g in CONFLICT_GROUPS],
                ),
                ft.Text("hold帧", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=50),
                ft.TextField(
                    ref=self._var_hold, value=str(adef.get("hold_frames", 1)),
                    text_size=13, border_radius=8, bgcolor=Apple.BG_ELEVATED,
                    border_color=Apple.BORDER_LIGHT, color=Apple.TEXT_PRIMARY,
                    content_padding=ft.Padding(left=8, top=8, right=8, bottom=8),
                    width=60, height=34, text_align=ft.TextAlign.CENTER,
                ),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]

        # ── 指标选择区域 ──
        enabled_metrics = adef.get("enabled_metrics", [])
        metric_rules = adef.get("metric_rules", {})

        metric_header = ft.Row([
            ft.Text("指标选择与阈值", size=13, weight=ft.FontWeight.W_600,
                    color=Apple.TEAL, font_family=Apple.FONT),
        ])

        metric_rows = []
        for mid in self._catalog:
            minfo = self._catalog[mid]
            enabled = mid in enabled_metrics
            rule = metric_rules.get(mid, {})
            lo = rule.get("normal_lo", 0)
            hi = rule.get("normal_hi", 100)
            unit = minfo.get("unit", "")

            # 滑块范围
            if unit == "°":
                rmin, rmax = 0.0, 200.0
            elif unit in ("ratio", "ratio/s"):
                rmin, rmax = -0.5, 0.5
            elif unit == "ms":
                rmin, rmax = 0.0, 5000.0
            elif unit == "count":
                rmin, rmax = 0.0, 100.0
            else:
                rmin, rmax = 0.0, 200.0

            lo_norm = (lo - rmin) / (rmax - rmin) if rmax != rmin else 0
            hi_norm = (hi - rmin) / (rmax - rmin) if rmax != rmin else 1
            # clamp to [0, 1] — 实际数据可能超出预设 min/max
            lo_norm = max(0.0, min(1.0, lo_norm))
            hi_norm = max(0.0, min(1.0, hi_norm))

            name = minfo.get("display_name", mid)

            cb_ref = ft.Ref[ft.Checkbox]()
            lo_text_ref = ft.Ref[ft.Text]()
            hi_text_ref = ft.Ref[ft.Text]()
            lo_slider_ref = ft.Ref[ft.Slider]()
            hi_slider_ref = ft.Ref[ft.Slider]()

            def make_on_change(slider_ref, text_ref, rng_min, rng_max):
                def on_change(e):
                    val = rng_min + slider_ref.current.value * (rng_max - rng_min)
                    text_ref.current.value = f"{val:.1f}"
                    self.page.update()
                return on_change

            row = ft.Row(
                [
                    ft.Checkbox(
                        ref=cb_ref, value=enabled, width=20,
                        active_color=Apple.BLUE, check_color="#fff",
                    ),
                    ft.Text(name, size=11, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT, width=130),
                    ft.Text(ref=lo_text_ref, value=f"{lo:.1f}", size=11,
                            color=Apple.TEAL, font_family="Consolas", width=50, text_align=ft.TextAlign.END),
                    ft.Slider(
                        ref=lo_slider_ref, value=lo_norm, width=80, height=24,
                        active_color=Apple.BLUE, inactive_color=Apple.BORDER,
                    ),
                    ft.Text(value="–", size=11, color=Apple.TEXT_TERTIARY),
                    ft.Slider(
                        ref=hi_slider_ref, value=hi_norm, width=80, height=24,
                        active_color=Apple.BLUE, inactive_color=Apple.BORDER,
                    ),
                    ft.Text(ref=hi_text_ref, value=f"{hi:.1f}", size=11,
                            color=Apple.TEAL, font_family="Consolas", width=50),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

            lo_slider_ref.current.on_change = make_on_change(lo_slider_ref, lo_text_ref, rmin, rmax)
            hi_slider_ref.current.on_change = make_on_change(hi_slider_ref, hi_text_ref, rmin, rmax)

            metric_rows.append(row)
            self._metric_refs[mid] = {
                "enabled": cb_ref,
                "lo_slider": lo_slider_ref,
                "hi_slider": hi_slider_ref,
                "lo_text": lo_text_ref,
                "hi_text": hi_text_ref,
                "rmin": rmin,
                "rmax": rmax,
            }

        # ── 按键映射 ──
        key_row = ft.Row([
            ft.Text("映射按键", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=70),
            ft.Dropdown(
                ref=self._var_key, width=100, height=34, text_size=12,
                bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                color=Apple.TEXT_PRIMARY, border_radius=8,
                options=[ft.dropdown.Option(key=k, text=k.upper()) for k in KEY_OPTIONS],
            ),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self._load_key_mapping(aid)

        # ── 按钮 ──
        btn_row = ft.Row(
            [
                ft.Container(
                    content=ft.Text("删除动作", size=13, weight=ft.FontWeight.W_600,
                                    color=Apple.RED, font_family=Apple.FONT),
                    padding=ft.Padding(left=20, top=10, right=20, bottom=10),
                    border_radius=20,
                    bgcolor=f"{Apple.RED}20",
                    on_click=lambda e: self._on_delete_action(),
                ),
                ft.Container(
                    content=ft.Text("保存动作", size=13, weight=ft.FontWeight.W_600,
                                    color="#fff", font_family=Apple.FONT),
                    padding=ft.Padding(left=24, top=10, right=24, bottom=10),
                    border_radius=20,
                    bgcolor=Apple.BLUE,
                    on_click=lambda e: self._on_save_action(),
                ),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.END,
        )

        # 组装
        detail.controls.append(
            ft.Column(
                [
                    ft.Text(f"编辑动作: {adef.get('name', aid)}", size=15,
                            weight=ft.FontWeight.W_600, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
                    ft.Divider(height=1, color=Apple.BORDER),
                    *info_items,
                    ft.Divider(height=1, color=Apple.BORDER),
                    metric_header,
                    ft.Column(metric_rows, spacing=4, height=240, scroll=ft.ScrollMode.AUTO),
                    ft.Divider(height=1, color=Apple.BORDER),
                    key_row,
                    btn_row,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        )

        self.page.update()

    # ── 按键映射加载 ──

    def _load_key_mapping(self, aid: str) -> None:
        pid = self._selected_profile
        dd = self._var_key.current
        if not dd:
            return
        dd.value = None
        if not pid or pid not in self._profiles:
            return
        for m in self._profiles[pid].get("mappings", []):
            if m.get("action_id") == aid:
                dd.value = m.get("key", "")
                return

    # ═══════════════════════════════════════════════════════════════
    # 档案详情面板
    # ═══════════════════════════════════════════════════════════════

    def _build_profile_detail(self) -> None:
        detail = self._detail_area.current
        detail.controls.clear()

        pid = self._selected_profile
        pdata = self._profiles.get(pid, {})
        mappings = pdata.get("mappings", [])

        self._mapping_rows.clear()

        # 档案基本信息
        info_row = ft.Row([
            ft.Text("档案ID", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=60),
            ft.TextField(
                ref=self._var_pid, value=pid or "", text_size=13,
                border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                color=Apple.TEXT_PRIMARY, content_padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                width=180, height=34,
            ),
            ft.Text("名称", size=12, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT, width=50),
            ft.TextField(
                ref=self._var_pname, value=pdata.get("profile_name", ""), text_size=13,
                border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                color=Apple.TEXT_PRIMARY, content_padding=ft.Padding(left=10, top=8, right=10, bottom=8),
                width=180, height=34,
            ),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # 映射表
        action_ids = list(self._actions.keys())
        mapping_rows_container = ft.Ref[ft.Column]()

        def make_mapping_row(m: dict | None = None):
            if m is None:
                m = {"action_id": "", "key": "", "hold": False, "description": ""}

            var_aid = ft.Ref[ft.Dropdown]()
            var_key = ft.Ref[ft.Dropdown]()
            var_desc = ft.Ref[ft.TextField]()

            row_data = {"aid": var_aid, "key": var_key, "desc": var_desc}
            self._mapping_rows.append(row_data)

            row = ft.Row(
                [
                    ft.Dropdown(
                        ref=var_aid, value=m.get("action_id", ""), width=180, height=34,
                        text_size=11, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, border_radius=8,
                        options=[ft.dropdown.Option(key=a, text=a) for a in action_ids],
                    ),
                    ft.Dropdown(
                        ref=var_key, value=m.get("key", ""), width=80, height=34,
                        text_size=11, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, border_radius=8,
                        options=[ft.dropdown.Option(key=k, text=k.upper()) for k in KEY_OPTIONS],
                    ),
                    ft.TextField(
                        ref=var_desc, value=m.get("description", ""), text_size=11,
                        border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, content_padding=ft.Padding(left=8, top=8, right=8, bottom=8),
                        width=200, height=34, hint_text="描述",
                    ),
                    ft.Container(
                        content=ft.Text("✕", size=12, color=Apple.RED),
                        width=24, height=24, border_radius=12,
                        bgcolor=f"{Apple.RED}15", alignment=ft.Alignment.CENTER,
                        on_click=lambda e, rd=row_data: self._remove_mapping(rd, row),
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            return row, row_data

        map_rows = ft.Ref[ft.Column]()
        initial_rows = ft.Column(ref=map_rows, spacing=4)
        for m in mappings:
            r, _ = make_mapping_row(m)
            initial_rows.controls.append(r)

        # 按钮
        btn_row = ft.Row(
            [
                ft.Container(
                    content=ft.Text("删除档案", size=12, weight=ft.FontWeight.W_500,
                                    color=Apple.RED, font_family=Apple.FONT),
                    padding=ft.Padding(left=16, top=8, right=16, bottom=8),
                    border_radius=16,
                    bgcolor=f"{Apple.RED}15",
                    on_click=lambda e: self._on_delete_profile(),
                ),
                ft.Container(
                    content=ft.Text("+ 添加映射", size=12, weight=ft.FontWeight.W_500,
                                    color=Apple.BLUE, font_family=Apple.FONT),
                    padding=ft.Padding(left=16, top=8, right=16, bottom=8),
                    border_radius=16,
                    bgcolor=f"{Apple.BLUE}15",
                    on_click=lambda e: self._add_mapping_row(map_rows, make_mapping_row),
                ),
                ft.Container(
                    content=ft.Text("保存档案", size=13, weight=ft.FontWeight.W_600,
                                    color="#fff", font_family=Apple.FONT),
                    padding=ft.Padding(left=24, top=10, right=24, bottom=10),
                    border_radius=20,
                    bgcolor=Apple.BLUE,
                    on_click=lambda e: self._on_save_profile(map_rows),
                ),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.END,
        )

        detail.controls.append(
            ft.Column(
                [
                    ft.Text(f"编辑档案: {pdata.get('profile_name', pid)}", size=15,
                            weight=ft.FontWeight.W_600, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
                    ft.Divider(height=1, color=Apple.BORDER),
                    info_row,
                    ft.Divider(height=1, color=Apple.BORDER),
                    ft.Text("动作→按键映射", size=13, weight=ft.FontWeight.W_600,
                            color=Apple.TEAL, font_family=Apple.FONT),
                    ft.Container(
                        content=ft.Column(
                            [initial_rows],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        border_radius=Apple.RADIUS_SM,
                        bgcolor=Apple.BG_CARD,
                        padding=10,
                        expand=True,
                    ),
                    btn_row,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        )

        self.page.update()

    def _add_mapping_row(self, map_rows_ref, make_mapping_row):
        r, _ = make_mapping_row()
        map_rows_ref.current.controls.append(r)
        self.page.update()

    def _remove_mapping(self, row_data, row):
        if row_data in self._mapping_rows:
            self._mapping_rows.remove(row_data)
        # 找到 row 的父容器并移除
        parent = row.parent
        if parent and row in parent.controls:
            parent.controls.remove(row)
        self.page.update()

    # ═══════════════════════════════════════════════════════════════
    # 新建 / 删除
    # ═══════════════════════════════════════════════════════════════

    def _on_new_action(self) -> None:
        base = "custom"
        i = 1
        while f"{base}_{i}" in self._actions:
            i += 1
        new_id = f"{base}_{i}"
        self._actions[new_id] = {
            "action_id": new_id, "name": f"自定义动作{i}",
            "action_type": "pose", "description": "",
            "hold_frames": 2, "enabled_metrics": [],
            "metric_rules": {}, "conflict_group": "",
        }
        self._selected_action = new_id
        self._selected_profile = None
        self._refresh_action_list()
        self._refresh_profile_list()
        self._build_action_detail()

    def _on_new_profile(self) -> None:
        base = "new_profile"
        i = 1
        while f"{base}_{i}" in self._profiles:
            i += 1
        pid = f"{base}_{i}"
        self._profiles[pid] = {
            "profile_id": pid, "profile_name": f"新档案{i}",
            "description": "", "version": "1.0.0",
            "player_count": 1, "mappings": [],
        }
        self._save_profiles(pid)
        self._selected_profile = pid
        self._selected_action = None
        self._refresh_action_list()
        self._refresh_profile_list()
        self._build_profile_detail()

    def _on_save_action(self) -> None:
        aid = self._var_aid.current.value.strip()
        if not aid:
            self._show_snack("动作ID不能为空", is_error=True)
            return
        if aid != self._selected_action:
            if aid in self._actions:
                self._show_snack(f"动作ID '{aid}' 已存在", is_error=True)
                return
            del self._actions[self._selected_action]
            self._selected_action = aid

        # 收集启用的指标和规则
        enabled_metrics = []
        metric_rules = {}
        for mid, refs in self._metric_refs.items():
            if refs["enabled"].current.value:
                enabled_metrics.append(mid)
                rmin, rmax = refs["rmin"], refs["rmax"]
                lo = rmin + refs["lo_slider"].current.value * (rmax - rmin)
                hi = rmin + refs["hi_slider"].current.value * (rmax - rmin)
                if lo > hi:
                    lo, hi = hi, lo
                metric_rules[mid] = {
                    "normal_lo": round(lo, 3),
                    "normal_hi": round(hi, 3),
                    "severity_rules": [],
                }

        if not enabled_metrics:
            self._show_snack("请至少启用一个指标", is_error=True)
            return

        self._actions[aid] = {
            "action_id": aid,
            "name": self._var_name.current.value.strip() or aid,
            "action_type": self._var_type.current.value,
            "description": "",
            "hold_frames": max(1, int(self._var_hold.current.value or 1)),
            "enabled_metrics": enabled_metrics,
            "metric_rules": metric_rules,
            "conflict_group": self._var_cgroup.current.value,
        }

        # 更新按键映射到档案
        key = self._var_key.current.value
        if key and self._selected_profile:
            self._update_key_mapping(aid, key)

        self._save_actions()
        self._refresh_action_list()
        self._show_snack(f"动作 '{aid}' 已保存")

    def _update_key_mapping(self, aid: str, key: str) -> None:
        pid = self._selected_profile
        if not pid or pid not in self._profiles:
            return
        mappings = self._profiles[pid].get("mappings", [])
        found = False
        for m in mappings:
            if m.get("action_id") == aid:
                m["key"] = key
                found = True
                break
        if not found:
            mappings.append({
                "action_id": aid,
                "action_name": self._var_name.current.value,
                "key": key,
                "hold": False,
                "description": "",
            })
        self._profiles[pid]["mappings"] = mappings
        self._save_profiles(pid)

    def _on_delete_action(self) -> None:
        aid = self._selected_action
        if not aid:
            return
        # 简单确认：直接删除（无模态对话框，使用 snackbar 提示）
        del self._actions[aid]
        self._save_actions()
        self._selected_action = None
        self._refresh_action_list()
        self._detail_area.current.controls.clear()
        self._detail_area.current.controls.append(
            ft.Container(
                content=ft.Text("动作已删除，请选择其他项目", size=14,
                                color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                expand=True, alignment=ft.Alignment.CENTER,
            )
        )
        self._show_snack(f"动作 '{aid}' 已删除")

    def _on_save_profile(self, map_rows_ref) -> None:
        pid = self._var_pid.current.value.strip()
        if not pid or self._selected_profile is None:
            return

        mappings = []
        for row_data in self._mapping_rows:
            aid = row_data["aid"].current.value
            if not aid:
                continue
            adef = self._actions.get(aid, {})
            name = adef.get("name", aid) if isinstance(adef, dict) else aid
            mappings.append({
                "action_id": aid,
                "action_name": name,
                "key": row_data["key"].current.value,
                "hold": False,
                "description": row_data["desc"].current.value,
            })

        self._profiles[pid] = {
            "profile_id": pid,
            "profile_name": self._var_pname.current.value or pid,
            "description": "",
            "version": "1.0.0",
            "player_count": 1,
            "mappings": mappings,
        }
        self._save_profiles(pid)
        self._refresh_profile_list()
        self._show_snack(f"档案 '{pid}' 已保存")

    def _on_delete_profile(self) -> None:
        """删除当前选中的档案"""
        pid = self._selected_profile
        if not pid:
            return
        profile_path = PROFILES_DIR / f"{pid}.json"
        try:
            profile_path.unlink()
        except Exception:
            pass
        if pid in self._profiles:
            del self._profiles[pid]
        self._selected_profile = None
        self._refresh_profile_list()
        self._detail_area.current.controls.clear()
        self._detail_area.current.controls.append(
            ft.Container(
                content=ft.Text("档案已删除，请选择其他项目", size=14,
                                color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                expand=True, alignment=ft.Alignment.CENTER,
            )
        )
        self._show_snack(f"档案 '{pid}' 已删除")

    def _toggle_theme(self) -> None:
        """切换 Light / Dark 主题"""
        global Apple
        self._dark_mode = not self._dark_mode
        Apple = AppleDark if self._dark_mode else AppleLight
        self.page.bgcolor = Apple.BG_BASE
        self._build_ui()
        self._refresh_action_list()
        self._refresh_profile_list()
        self.page.update()

    def _show_snack(self, msg: str, is_error: bool = False) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
            bgcolor=Apple.RED if is_error else Apple.BG_ELEVATED,
            duration=3000,
        )
        self.page.snack_bar.open = True
        self.page.update()


# ══════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════

def open_editor(page: ft.Page | None = None) -> None:
    """以独立子进程方式打开编辑器"""
    import subprocess
    subprocess.Popen(
        [sys.executable, str(ROOT / "editor.py")],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def main(page: ft.Page) -> None:
    EditorApp(page)


if __name__ == "__main__":
    ft.run(main)
