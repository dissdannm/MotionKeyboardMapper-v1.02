"""
MotionKeyboardMapper — 图形化启动器 (Flet · Apple 风格)
双击运行或: python launcher.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from pathlib import Path

import cv2
import flet as ft

if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG, MODEL_PATH
from camera.sources import CameraManager, CameraConfig, CameraType
from pose.estimator import PoseEstimator
from actions.engine import ActionEngine
from keyboard.emitter import KeyboardEmitter


# ══════════════════════════════════════════════════════════════════════
# Apple 风格色彩系统
# ══════════════════════════════════════════════════════════════════════

# ── 共享常量 ──
_FONT = "Microsoft YaHei"
_RADIUS_SM, _RADIUS_MD, _RADIUS_LG, _RADIUS_XL = 8, 12, 16, 24
_ACCENT = dict(BLUE="#007aff", RED="#ff3b30", GREEN="#34c759",
               ORANGE="#ff9500", TEAL="#64d2ff", PURPLE="#5e5ce6")


class _ThemeData:
    """可切换主题数据"""
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

# 当前主题（模块级变量，切换时直接重新赋值）
Apple = AppleDark


# ══════════════════════════════════════════════════════════════════════
# 可复用组件
# ══════════════════════════════════════════════════════════════════════

def _glass_card(
    content: ft.Control,
    expand: bool = False,
    padding: int = 20,
    radius: int = Apple.RADIUS_LG,
) -> ft.Container:
    """毛玻璃卡片"""
    return ft.Container(
        content=content,
        expand=expand,
        padding=padding,
        border_radius=radius,
        bgcolor=Apple.BG_CARD,
        border=ft.BorderSide(1, Apple.GLASS_BORDER),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=12,
            color="#00000030",
            offset=ft.Offset(0, 4),
        ),
    )


def _section_title(text: str) -> ft.Text:
    return ft.Text(
        text, size=14, weight=ft.FontWeight.W_600,
        color=Apple.TEXT_PRIMARY, font_family=Apple.FONT,
    )


def _pill_button(
    text: str,
    on_click,
    bgcolor: str = Apple.BLUE,
    color: str = "#ffffff",
    height: int = 42,
    disabled: bool = False,
) -> ft.Container:
    """胶囊按钮"""
    return ft.Container(
        content=ft.Text(
            text, size=14, weight=ft.FontWeight.W_600,
            color=color, font_family=Apple.FONT,
            text_align=ft.TextAlign.CENTER,
        ),
        height=height,
        border_radius=height // 2,
        bgcolor=bgcolor if not disabled else "#555555",
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding(left=24, right=24),
        shadow=ft.BoxShadow(
            spread_radius=0, blur_radius=8,
            color=f"{bgcolor}40", offset=ft.Offset(0, 2),
        ) if not disabled else None,
        on_click=on_click if not disabled else None,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
    )


def _stat_card(
    label: str,
    value_ref: ft.Ref[ft.Text],
    accent: str = Apple.TEAL,
) -> ft.Container:
    """状态指标卡片"""
    return _glass_card(
        content=ft.Column(
            [
                ft.Text(label, size=11, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                ft.Text(
                    ref=value_ref, value="—", size=26,
                    weight=ft.FontWeight.W_700, color=accent, font_family=Apple.FONT,
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=16,
        radius=Apple.RADIUS_MD,
    )


# ══════════════════════════════════════════════════════════════════════
# 主应用
# ══════════════════════════════════════════════════════════════════════

class LauncherApp:
    """Apple 风格图形化启动器"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._dark_mode = True
        self._setup_page()

        # 运行时状态
        self.running = False
        self._stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._camera_mgr: CameraManager | None = None
        self._pose_est: PoseEstimator | None = None
        self._action_engine: ActionEngine | None = None
        self._keyboard_emitter: KeyboardEmitter | None = None

        self._current_action = "—"
        self._current_key = "—"
        self._fps = 0.0

        # Refs
        self._status_dot = ft.Ref[ft.Container]()
        self._status_text = ft.Ref[ft.Text]()
        self._action_value = ft.Ref[ft.Text]()
        self._key_value = ft.Ref[ft.Text]()
        self._fps_value = ft.Ref[ft.Text]()

        # 摄像头
        self._cam_type = "local"
        self._cam_index = ft.Ref[ft.TextField]()
        self._cam_index2 = ft.Ref[ft.TextField]()
        self._ip_url = ft.Ref[ft.TextField]()
        self._cam_buttons: dict[str, ft.Container] = {}

        # 档案
        self._profile_dd = ft.Ref[ft.Dropdown]()
        self._cooldown_tf = ft.Ref[ft.TextField]()
        self._mapping_table = ft.Ref[ft.DataTable]()

        # 按钮
        self._btn_start: ft.Container | None = None
        self._btn_stop: ft.Container | None = None

        self._build_ui()
        self._load_profiles()
        self._load_mapping_table()

    def _setup_page(self) -> None:
        self.page.title = "MotionKeyboardMapper"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.window.width = 960
        self.page.window.height = 740
        self.page.window.min_width = 860
        self.page.window.min_height = 640
        self.page.font_family = Apple.FONT
        self.page.bgcolor = Apple.BG_BASE

    # ═══════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self.page.controls.clear()
        background = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[Apple.GRADIENT_TOP, Apple.GRADIENT_BOTTOM],
            ),
            padding=24,
            content=ft.Column(
                [
                    self._build_header(),
                    self._build_main_content(),
                    self._build_footer(),
                ],
                spacing=16,
                expand=True,
            ),
        )
        self.page.add(background)

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=36, height=36, border_radius=10,
                                gradient=ft.LinearGradient(
                                    begin=ft.Alignment.TOP_LEFT,
                                    end=ft.Alignment.BOTTOM_RIGHT,
                                    colors=[Apple.BLUE, Apple.PURPLE],
                                ),
                                content=ft.Icon(ft.Icons.SPORTS_KABADDI, color="#ffffff", size=18),
                                alignment=ft.Alignment.CENTER,
                                shadow=ft.BoxShadow(
                                    spread_radius=0, blur_radius=8,
                                    color=f"{Apple.BLUE}60", offset=ft.Offset(0, 2),
                                ),
                            ),
                            ft.Column(
                                [
                                    ft.Text("MotionKeyboardMapper", size=18,
                                            weight=ft.FontWeight.W_700,
                                            color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
                                    ft.Text("体感键盘映射服务", size=11,
                                            color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                                ],
                                spacing=0,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Row(
                        [
                            # 主题切换
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
                            # 状态指示器
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Container(
                                            ref=self._status_dot, width=8, height=8,
                                            border_radius=4, bgcolor=Apple.TEXT_TERTIARY,
                                        ),
                                        ft.Text(ref=self._status_text, value="就绪", size=12,
                                                color=Apple.TEXT_SECONDARY, font_family=Apple.FONT),
                                    ],
                                    spacing=8,
                                ),
                                padding=ft.Padding(left=16, top=8, right=16, bottom=8),
                                border_radius=Apple.RADIUS_XL,
                                bgcolor=Apple.BG_CARD,
                                border=ft.BorderSide(1, Apple.BORDER),
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding(bottom=4),
        )

    def _build_main_content(self) -> ft.Row:
        return ft.Row(
            [
                self._build_left_column(),
                self._build_right_column(),
            ],
            spacing=16,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    # ── 左栏 ──

    def _build_left_column(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [self._build_camera_panel(), self._build_status_panel()],
                spacing=16, expand=True,
            ),
            width=340,
        )

    def _build_camera_panel(self) -> ft.Container:
        cam_types = [("local", "本地摄像头"), ("ip", "IP 摄像头"), ("dual", "双人模式")]

        def make_cam_btn(val: str, label: str) -> ft.Container:
            is_active = val == self._cam_type
            btn = ft.Container(
                content=ft.Text(
                    label, size=12, weight=ft.FontWeight.W_500,
                    color=Apple.TEXT_PRIMARY if is_active else Apple.TEXT_SECONDARY,
                    font_family=Apple.FONT,
                ),
                padding=ft.Padding(left=14, top=8, right=14, bottom=8),
                border_radius=Apple.RADIUS_XL,
                bgcolor=Apple.BLUE if is_active else Apple.BG_CARD,
                border=ft.BorderSide(1, f"{Apple.BLUE}80" if is_active else Apple.BORDER),
                on_click=lambda e, v=val: self._on_cam_type_change(v),
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            )
            self._cam_buttons[val] = btn
            return btn

        cam_row = ft.Row([make_cam_btn(v, l) for v, l in cam_types], spacing=8)

        idx_row = ft.Row(
            [
                ft.Text("摄像头索引", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                ft.TextField(
                    ref=self._cam_index, value="0", width=60, height=32, text_size=13,
                    border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER,
                    content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                ),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        ip_row = ft.Row(
            [
                ft.Text("IP 地址", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                ft.TextField(
                    ref=self._ip_url, value="http://192.168.1.5:8080/video",
                    height=32, text_size=12, border_radius=8, bgcolor=Apple.BG_ELEVATED,
                    border_color=Apple.BORDER_LIGHT, color=Apple.TEXT_PRIMARY,
                    content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                    expand=True,
                ),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        idx2_row = ft.Row(
            [
                ft.Text("副摄像头", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                ft.TextField(
                    ref=self._cam_index2, value="1", width=60, height=32, text_size=13,
                    border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                    color=Apple.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER,
                    content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                ),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._cam_extra_rows_col = ft.Column([idx_row], spacing=6)

        return _glass_card(
            content=ft.Column(
                [
                    _section_title("📷 摄像头选择"),
                    ft.Divider(height=1, color=Apple.BORDER),
                    cam_row,
                    self._cam_extra_rows_col,
                ],
                spacing=12,
            ),
            padding=20,
        )

    def _on_cam_type_change(self, cam_type: str) -> None:
        self._cam_type = cam_type
        for val, btn in self._cam_buttons.items():
            is_active = val == cam_type
            btn.bgcolor = Apple.BLUE if is_active else Apple.BG_CARD
            btn.border = ft.BorderSide(1, f"{Apple.BLUE}80" if is_active else Apple.BORDER)
            btn.content.color = Apple.TEXT_PRIMARY if is_active else Apple.TEXT_SECONDARY

        self._cam_extra_rows_col.controls.clear()
        if cam_type == "local":
            self._cam_extra_rows_col.controls.append(
                ft.Row([
                    ft.Text("摄像头索引", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                    ft.TextField(
                        ref=self._cam_index, value="0", width=60, height=32, text_size=13,
                        border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER,
                        content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )
        elif cam_type == "ip":
            self._cam_extra_rows_col.controls.append(
                ft.Row([
                    ft.Text("IP 地址", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                    ft.TextField(
                        ref=self._ip_url, value="http://192.168.1.5:8080/video",
                        height=32, text_size=12, border_radius=8, bgcolor=Apple.BG_ELEVATED,
                        border_color=Apple.BORDER_LIGHT, color=Apple.TEXT_PRIMARY,
                        content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                        expand=True,
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )
        elif cam_type == "dual":
            self._cam_extra_rows_col.controls.extend([
                ft.Row([
                    ft.Text("主摄像头", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                    ft.TextField(
                        ref=self._cam_index, value="0", width=60, height=32, text_size=13,
                        border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER,
                        content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("副摄像头", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT, width=80),
                    ft.TextField(
                        ref=self._cam_index2, value="1", width=60, height=32, text_size=13,
                        border_radius=8, bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                        color=Apple.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER,
                        content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ])
        self.page.update()

    def _build_status_panel(self) -> ft.Container:
        return _glass_card(
            content=ft.Column(
                [
                    _section_title("⚡ 实时状态"),
                    ft.Divider(height=1, color=Apple.BORDER),
                    ft.Row(
                        [
                            _stat_card("当前手势", self._action_value, accent=Apple.TEAL),
                            _stat_card("映射按键", self._key_value, accent=Apple.GREEN),
                            _stat_card("FPS", self._fps_value, accent=Apple.TEXT_SECONDARY),
                        ],
                        spacing=10,
                    ),
                    ft.Container(
                        content=ft.Text(
                            "启动后出现 OpenCV 窗口\n按 Q 退出 | 按 P 暂停",
                            size=11, color=Apple.TEXT_TERTIARY,
                            font_family=Apple.FONT, text_align=ft.TextAlign.CENTER,
                        ),
                        padding=ft.Padding(top=8),
                    ),
                ],
                spacing=12, expand=True,
            ),
            padding=20, expand=True,
        )

    # ── 右栏 ──

    def _build_right_column(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    self._build_profile_panel(),
                    self._build_control_panel(),
                    self._build_mapping_panel(),
                ],
                spacing=16, expand=True,
            ),
            expand=True,
        )

    def _build_profile_panel(self) -> ft.Container:
        return _glass_card(
            content=ft.Column(
                [
                    _section_title("🎮 映射档案"),
                    ft.Divider(height=1, color=Apple.BORDER),
                    ft.Row(
                        [
                            ft.Text("选择游戏:", size=13, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT),
                            ft.Dropdown(
                                ref=self._profile_dd, width=220, height=36, text_size=13,
                                bgcolor=Apple.BG_ELEVATED, border_color=Apple.BORDER_LIGHT,
                                color=Apple.TEXT_PRIMARY, border_radius=8,
                                on_select=lambda e: self._load_mapping_table(),
                            ),
                            ft.Text("冷却ms:", size=12, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT),
                            ft.TextField(
                                ref=self._cooldown_tf, value="300", width=64, height=32,
                                text_size=13, border_radius=8, bgcolor=Apple.BG_ELEVATED,
                                border_color=Apple.BORDER_LIGHT, color=Apple.TEXT_PRIMARY,
                                text_align=ft.TextAlign.CENTER,
                                content_padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                            ),
                        ],
                        spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=12,
            ),
            padding=20,
        )

    def _build_control_panel(self) -> ft.Container:
        self._btn_start = _pill_button("▶  启动服务", lambda e: self._on_start(), bgcolor=Apple.BLUE)
        self._btn_stop = _pill_button("⏹  停止", lambda e: self._on_stop(), bgcolor=Apple.RED, disabled=True)
        btn_web = _pill_button("🌐 Web 面板", lambda e: self._on_web(), bgcolor=Apple.BG_ELEVATED, color=Apple.BLUE)
        btn_editor = _pill_button("✏️  编辑配置", lambda e: self._on_editor(), bgcolor=Apple.BG_CARD, color=Apple.TEXT_PRIMARY)

        return _glass_card(
            content=ft.Row(
                [self._btn_start, self._btn_stop, btn_web, btn_editor],
                spacing=10,
            ),
            padding=16,
        )

    def _build_mapping_panel(self) -> ft.Container:
        table = ft.DataTable(
            ref=self._mapping_table,
            columns=[
                ft.DataColumn(ft.Text("体感动作", size=12, weight=ft.FontWeight.W_600, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT)),
                ft.DataColumn(ft.Text("按键", size=12, weight=ft.FontWeight.W_600, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT)),
                ft.DataColumn(ft.Text("模式", size=12, weight=ft.FontWeight.W_600, color=Apple.TEXT_SECONDARY, font_family=Apple.FONT)),
            ],
            rows=[],
            border=ft.Border(bottom=ft.BorderSide(1, Apple.BORDER)),
            border_radius=Apple.RADIUS_MD,
            heading_row_color={"": "#ffffff08"},
            data_row_color={"": Apple.BG_CARD},
            heading_row_height=36,
            data_row_min_height=32,
            column_spacing=20,
            expand=True,
        )

        return _glass_card(
            content=ft.Column(
                [
                    _section_title("📋 映射表预览"),
                    ft.Divider(height=1, color=Apple.BORDER),
                    ft.Row([table], expand=True, scroll=ft.ScrollMode.AUTO),
                ],
                spacing=12, expand=True,
            ),
            padding=20, expand=True,
        )

    def _build_footer(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("MotionKeyboardMapper v1.03 · Apple Style", size=10, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                    ft.Text("体感游戏通用键盘映射服务", size=10, color=Apple.TEXT_TERTIARY, font_family=Apple.FONT),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding(left=4, top=4, right=4, bottom=4),
        )

    # ═══════════════════════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════════════════════

    def _load_profiles(self) -> None:
        profiles = []
        for f in sorted(PROFILES_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pid = data.get("profile_id", f.stem)
                pname = data.get("profile_name", f.stem)
                profiles.append((pid, pname))
            except Exception:
                pass
        if not profiles:
            profiles = [("naruto_fighting", "火影忍者格斗")]

        dd = self._profile_dd.current
        if dd:
            dd.options = [ft.dropdown.Option(key=pid, text=pname) for pid, pname in profiles]
            dd.value = profiles[0][0]
            self.page.update()

    def _load_mapping_table(self) -> None:
        table = self._mapping_table.current
        if not table:
            return
        dd = self._profile_dd.current
        profile_id = dd.value if dd else "naruto_fighting"

        table.rows.clear()
        profile_path = PROFILES_DIR / f"{profile_id}.json"
        if not profile_path.exists():
            self.page.update()
            return

        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            for m in data.get("mappings", []):
                gname = m.get("action_name", m.get("action_id", ""))
                key = m.get("key", "").upper()
                hold = m.get("hold", False)
                table.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(gname, size=12, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT)),
                    ft.DataCell(ft.Text(key, size=12, weight=ft.FontWeight.W_700, color=Apple.TEAL, font_family=Apple.FONT)),
                    ft.DataCell(ft.Container(
                        content=ft.Text("按住" if hold else "点击", size=11,
                                        color=Apple.BLUE if hold else Apple.TEXT_SECONDARY),
                        padding=ft.Padding(left=8, top=2, right=8, bottom=2),
                        border_radius=6,
                        bgcolor=f"{Apple.BLUE}15" if hold else Apple.BG_CARD,
                    )),
                ]))
        except Exception:
            pass
        self.page.update()

    # ═══════════════════════════════════════════════════════════════
    # 控制逻辑
    # ═══════════════════════════════════════════════════════════════

    def _on_start(self) -> None:
        if self.running:
            return

        cam_type_map = {"local": CameraType.LOCAL, "ip": CameraType.IP, "dual": CameraType.DUAL}
        cam_cfg = CameraConfig(
            cam_type=cam_type_map.get(self._cam_type, CameraType.LOCAL),
            camera_index=int(self._cam_index.current.value or 0) if self._cam_index.current else 0,
            ip_url=self._ip_url.current.value if self._ip_url.current else "",
            camera_index_2=int(self._cam_index2.current.value or 1) if self._cam_index2.current else 1,
            width=640, height=480,
        )

        try:
            self._camera_mgr = CameraManager(cam_cfg)
            if not self._camera_mgr.open():
                self._show_toast("摄像头打开失败！请检查连接和索引", is_error=True)
                return
        except Exception as e:
            self._show_toast(f"摄像头初始化失败: {e}", is_error=True)
            return

        try:
            num_poses = 2 if self._cam_type == "dual" else 1
            model_p = str(MODEL_PATH)
            if not Path(model_p).exists():
                self._show_toast(f"模型文件未找到:\n{model_p}", is_error=True)
                self._camera_mgr.close()
                return
            self._pose_est = PoseEstimator(num_poses=num_poses, model_path=model_p)
            self._pose_est.open()
        except Exception as e:
            self._show_toast(f"姿态检测初始化失败: {e}", is_error=True)
            self._camera_mgr.close()
            return

        try:
            actions_p = str(ACTIONS_DEFS)
            if not Path(actions_p).exists():
                self._show_toast(f"动作定义文件未找到:\n{actions_p}", is_error=True)
                self._camera_mgr.close()
                self._pose_est.close()
                return
            self._action_engine = ActionEngine(actions_p)
        except Exception as e:
            self._show_toast(f"动作引擎初始化失败: {e}", is_error=True)
            self._camera_mgr.close()
            self._pose_est.close()
            return

        dd = self._profile_dd.current
        profile_id = dd.value if dd else "naruto_fighting"
        profile_path = PROFILES_DIR / f"{profile_id}.json"
        cooldown = int(self._cooldown_tf.current.value or 300) if self._cooldown_tf.current else 300
        self._keyboard_emitter = KeyboardEmitter(cooldown_ms=cooldown)
        if profile_path.exists():
            self._keyboard_emitter.load_profile(str(profile_path))
        else:
            self._keyboard_emitter.load_profile(str(PROFILES_DIR / "naruto_fighting.json"))

        self.running = True
        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._set_running_ui(True)

    def _on_stop(self) -> None:
        if not self.running:
            return
        self._stop_event.set()
        self.running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)

        if self._keyboard_emitter:
            self._keyboard_emitter.release_all()
        if self._camera_mgr:
            self._camera_mgr.close()
        if self._pose_est:
            self._pose_est.close()

        self._camera_mgr = None
        self._pose_est = None
        self._action_engine = None
        self._keyboard_emitter = None

        cv2.destroyAllWindows()
        self._set_running_ui(False)

    def _on_web(self) -> None:
        webbrowser.open("http://127.0.0.1:8888")
        from server.app import start_server
        threading.Thread(target=start_server, daemon=True).start()
        self._status_dot.current.bgcolor = Apple.BLUE
        self._status_text.current.value = "Web 面板已启动"
        self.page.update()

    def _toggle_theme(self) -> None:
        """切换 Light / Dark 主题"""
        global Apple
        self._dark_mode = not self._dark_mode
        Apple = AppleDark if self._dark_mode else AppleLight
        self.page.bgcolor = Apple.BG_BASE
        self._build_ui()
        self._load_profiles()
        self._load_mapping_table()
        if self.running:
            self._set_running_ui(True)
        self.page.update()

    def _on_editor(self) -> None:
        import subprocess
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable, "--editor"])
        else:
            subprocess.Popen([sys.executable, str(ROOT / "editor.py")])

    def _set_running_ui(self, running: bool) -> None:
        if running:
            self._status_dot.current.bgcolor = Apple.GREEN
            self._status_text.current.value = "运行中"
            self._btn_start.bgcolor = "#555555"
            self._btn_start.on_click = None
            self._btn_stop.bgcolor = Apple.RED
            self._btn_stop.on_click = lambda e: self._on_stop()
        else:
            self._status_dot.current.bgcolor = Apple.TEXT_TERTIARY
            self._status_text.current.value = "就绪"
            self._btn_start.bgcolor = Apple.BLUE
            self._btn_start.on_click = lambda e: self._on_start()
            self._btn_stop.bgcolor = "#555555"
            self._btn_stop.on_click = None
            self._action_value.current.value = "—"
            self._key_value.current.value = "—"
            self._fps_value.current.value = "0"
        self.page.update()

    def _show_toast(self, message: str, is_error: bool = False) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=Apple.TEXT_PRIMARY, font_family=Apple.FONT),
            bgcolor=Apple.RED if is_error else Apple.BG_ELEVATED,
            duration=4000,
        )
        self.page.snack_bar.open = True
        self.page.update()

    # ═══════════════════════════════════════════════════════════════
    # 后台采集循环
    # ═══════════════════════════════════════════════════════════════

    def _capture_loop(self) -> None:
        fps_window: list[float] = []
        while not self._stop_event.is_set():
            if self._camera_mgr is None:
                break
            loop_start = time.perf_counter()

            frames = self._camera_mgr.read()
            if not frames:
                time.sleep(0.005)
                continue

            frame = frames[0]
            ts = int(time.time() * 1000)
            pose_results = self._pose_est.process(frame, ts) if self._pose_est else []
            active_aids: set[str] = set()
            action_names: list[str] = []

            if pose_results and pose_results[0]:
                pr = pose_results[0]
                if pr and self._action_engine:
                    self._action_engine.update(pr)
                    active_aids = self._action_engine.active_actions
                    action_names = [
                        self._action_engine.definitions.get(g, {}).name
                        for g in active_aids
                    ]
                self._draw_skeleton(frame, pr)

            if self._keyboard_emitter:
                self._keyboard_emitter.update(active_aids)

            y = 25
            for gname in action_names:
                cv2.putText(frame, f"[{gname}]", (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
                y += 24

            self._current_action = action_names[0] if action_names else "—"
            if self._keyboard_emitter:
                key_str = "+".join(
                    self._keyboard_emitter._mapping[g]["key"].upper()
                    for g in active_aids if g in self._keyboard_emitter._mapping
                )
                self._current_key = key_str if key_str else "—"
            else:
                self._current_key = "—"

            dur = time.perf_counter() - loop_start
            if dur > 0:
                fps_window.append(1.0 / dur)
            if len(fps_window) > 30:
                fps_window.pop(0)
            self._fps = sum(fps_window) / len(fps_window) if fps_window else 0.0

            cv2.imshow("MotionKeyboardMapper — Camera Feed", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self._stop_event.set()
            elif key == ord("p"):
                while True:
                    k2 = cv2.waitKey(100) & 0xFF
                    if k2 == ord("p") or k2 == ord("q"):
                        if k2 == ord("q"):
                            self._stop_event.set()
                        break

            if int(time.time() * 2) % 2 == 0:
                self._refresh_ui()

        if self._keyboard_emitter:
            self._keyboard_emitter.release_all()
        cv2.destroyAllWindows()

    def _draw_skeleton(self, frame, pose) -> None:
        h, w = frame.shape[:2]
        connections = [
            ("left_shoulder", "right_shoulder"),
            ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
            ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
            ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
            ("left_hip", "right_hip"),
            ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
            ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
        ]
        for a_name, b_name in connections:
            a = pose.get(a_name)
            b = pose.get(b_name)
            if a and b:
                cv2.line(frame, (int(a.x * w), int(a.y * h)),
                         (int(b.x * w), int(b.y * h)), (0, 255, 0), 2)
        for lm in pose.landmarks.values():
            if lm.visibility > 0.5:
                cv2.circle(frame, (int(lm.x * w), int(lm.y * h)),
                           3, (0, 200, 255), -1)

    def _refresh_ui(self) -> None:
        if not self.running:
            return
        try:
            av = self._action_value.current
            kv = self._key_value.current
            fv = self._fps_value.current
            if av:
                av.value = self._current_action
            if kv:
                kv.value = self._current_key
            if fv:
                fv.value = f"{self._fps:.0f}"
            self.page.update()
        except Exception:
            pass

    def run(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    LauncherApp(page)


if __name__ == "__main__":
    ft.run(main)
