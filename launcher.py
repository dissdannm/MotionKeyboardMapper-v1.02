"""
MotionKeyboardMapper — 图形化启动器 (Tkinter)
双击运行或: python launcher.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import Tk, Frame, Label, Button, OptionMenu, StringVar, IntVar, \
    Entry, messagebox, ttk, DISABLED, NORMAL, BooleanVar

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG, MODEL_PATH
from camera.sources import CameraManager, CameraConfig, CameraType
from pose.estimator import PoseEstimator
from actions.engine import ActionEngine
from keyboard.emitter import KeyboardEmitter
import cv2

# ── 样式常量 ──────────────────────────────────────────────────────
BG_MAIN = "#1a1a2e"
BG_PANEL = "#16213e"
BG_BUTTON = "#0f3460"
FG_ACCENT = "#e94560"
FG_ACCENT2 = "#00d2ff"
FG_TEXT = "#eaeaea"
FG_DIM = "#8899aa"
BG_ACTIVE = "#e94560"
BG_SUCCESS = "#1e5631"
FONT_TITLE = ("Microsoft YaHei", 14, "bold")
FONT_NORMAL = ("Microsoft YaHei", 10)
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_MONO = ("Consolas", 10)


class App:
    """图形化启动器"""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("MotionKeyboardMapper — 体感键盘映射启动器")
        self.root.geometry("900x680")
        self.root.configure(bg=BG_MAIN)
        self.root.resizable(True, True)
        self.root.minsize(800, 600)

        # ── 运行时状态 ──
        self.running = False
        self._stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._camera_mgr: CameraManager | None = None
        self._pose_est: PoseEstimator | None = None
        self._action_engine: ActionEngine | None = None
        self._keyboard_emitter: KeyboardEmitter | None = None

        # 共享状态（线程安全——只在 GUI 线程读取）
        self._current_action = "—"
        self._current_key = "—"
        self._fps = 0.0
        self._frame_bytes: bytes | None = None

        # ── 构建 UI ──
        self._build_ui()
        self._load_profiles()
        self._load_mapping_table()

    # ═══════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        """构建完整 UI 布局"""
        # ── 顶部标题栏 ──
        top_bar = Frame(self.root, bg=BG_MAIN)
        top_bar.pack(fill="x", padx=16, pady=(14, 0))

        Label(top_bar, text="MotionKeyboardMapper", font=FONT_TITLE,
              fg=FG_ACCENT, bg=BG_MAIN).pack(side="left")
        self._status_label = Label(top_bar, text="● 就绪", font=FONT_NORMAL,
                                   fg=FG_ACCENT2, bg=BG_MAIN)
        self._status_label.pack(side="right")

        # ── 主区域（左右两栏） ──
        main = Frame(self.root, bg=BG_MAIN)
        main.pack(fill="both", expand=True, padx=16, pady=10)

        # 左栏：摄像头选择 + 状态
        left = Frame(main, bg=BG_MAIN)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self._build_camera_panel(left)
        self._build_status_panel(left)

        # 右栏：档案选择 + 操作按钮 + 映射表
        right = Frame(main, bg=BG_MAIN)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self._build_profile_panel(right)
        self._build_control_panel(right)
        self._build_mapping_panel(right)

    def _make_panel(self, parent, title: str) -> Frame:
        """创建一个带标题的圆角面板"""
        panel = Frame(parent, bg=BG_PANEL, bd=0, highlightthickness=0)
        lbl = Label(panel, text=title, font=FONT_NORMAL, fg=FG_ACCENT2,
                    bg=BG_PANEL, anchor="w")
        lbl.pack(fill="x", padx=12, pady=(10, 4))
        return panel

    # ── 摄像头面板 ──

    def _build_camera_panel(self, parent: Frame) -> None:
        panel = self._make_panel(parent, "摄像头选择")
        panel.pack(fill="x", pady=(0, 10))

        # 三选一按钮组
        btn_frame = Frame(panel, bg=BG_PANEL)
        btn_frame.pack(fill="x", padx=12, pady=6)

        self._cam_type = StringVar(value="local")
        self._cam_buttons: dict[str, Button] = {}

        opts = [
            ("local", "本地摄像头"),
            ("ip", "IP 摄像头 (手机)"),
            ("dual", "双人模式"),
        ]
        for val, text in opts:
            btn = Button(btn_frame, text=text, font=FONT_NORMAL,
                         command=lambda v=val: self._on_cam_type_change(v))
            btn.pack(side="left", padx=(0, 6), ipadx=10, ipady=4)
            self._cam_buttons[val] = btn

        # 本地摄像头索引
        self._row_index = Frame(panel, bg=BG_PANEL)
        self._row_index.pack(fill="x", padx=12, pady=2)
        Label(self._row_index, text="摄像头索引:", font=FONT_SMALL,
              fg=FG_DIM, bg=BG_PANEL).pack(side="left")
        self._cam_index = IntVar(value=0)
        Entry(self._row_index, textvariable=self._cam_index, width=5,
              font=FONT_MONO, bg=BG_MAIN, fg=FG_TEXT,
              insertbackground=FG_TEXT).pack(side="left", padx=6)

        # IP 地址输入
        self._row_ip = Frame(panel, bg=BG_PANEL)
        Label(self._row_ip, text="IP 地址:", font=FONT_SMALL,
              fg=FG_DIM, bg=BG_PANEL).pack(side="left")
        self._ip_url = StringVar(value="http://192.168.1.5:8080/video")
        Entry(self._row_ip, textvariable=self._ip_url, width=30,
              font=FONT_MONO, bg=BG_MAIN, fg=FG_TEXT,
              insertbackground=FG_TEXT).pack(side="left", padx=6)

        # 第二个摄像头索引（双人模式）
        self._row_index2 = Frame(panel, bg=BG_PANEL)
        self._row_index2.pack(fill="x", padx=12, pady=2)
        Label(self._row_index2, text="玩家2 摄像头索引:", font=FONT_SMALL,
              fg=FG_DIM, bg=BG_PANEL).pack(side="left")
        self._cam_index2 = IntVar(value=1)
        Entry(self._row_index2, textvariable=self._cam_index2, width=5,
              font=FONT_MONO, bg=BG_MAIN, fg=FG_TEXT,
              insertbackground=FG_TEXT).pack(side="left", padx=6)

        self._on_cam_type_change("local")

    def _on_cam_type_change(self, cam_type: str) -> None:
        """切换摄像头模式，更新按钮高亮和输入框显示"""
        self._cam_type.set(cam_type)
        for val, btn in self._cam_buttons.items():
            if val == cam_type:
                btn.configure(bg=FG_ACCENT, fg="#fff", relief="flat",
                              activebackground=FG_ACCENT, activeforeground="#fff")
            else:
                btn.configure(bg=BG_BUTTON, fg=FG_TEXT, relief="raised",
                              activebackground=BG_BUTTON, activeforeground=FG_TEXT)

        # 显示/隐藏输入行
        self._row_index.pack_forget()
        self._row_ip.pack_forget()
        self._row_index2.pack_forget()

        if cam_type == "local":
            self._row_index.pack(fill="x", padx=12, pady=2)
        elif cam_type == "ip":
            self._row_ip.pack(fill="x", padx=12, pady=2)
        elif cam_type == "dual":
            self._row_index.pack(fill="x", padx=12, pady=2)
            self._row_index2.pack(fill="x", padx=12, pady=2)

    # ── 状态面板 ──

    def _build_status_panel(self, parent: Frame) -> None:
        panel = self._make_panel(parent, "实时状态")
        panel.pack(fill="both", expand=True)

        # 当前手势
        row1 = Frame(panel, bg=BG_PANEL)
        row1.pack(fill="x", padx=12, pady=6)
        Label(row1, text="当前手势:", font=FONT_NORMAL, fg=FG_DIM,
              bg=BG_PANEL, width=10, anchor="w").pack(side="left")
        self._action_label = Label(row1, text="—", font=("Microsoft YaHei", 16, "bold"),
                                    fg=FG_ACCENT2, bg=BG_PANEL, anchor="w")
        self._action_label.pack(side="left")

        # 映射按键
        row2 = Frame(panel, bg=BG_PANEL)
        row2.pack(fill="x", padx=12, pady=6)
        Label(row2, text="映射按键:", font=FONT_NORMAL, fg=FG_DIM,
              bg=BG_PANEL, width=10, anchor="w").pack(side="left")
        self._key_label = Label(row2, text="—", font=("Microsoft YaHei", 28, "bold"),
                                fg="#00ff88", bg=BG_PANEL)
        self._key_label.pack(side="left")

        # FPS
        row3 = Frame(panel, bg=BG_PANEL)
        row3.pack(fill="x", padx=12, pady=6)
        Label(row3, text="FPS:", font=FONT_SMALL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left")
        self._fps_label = Label(row3, text="0", font=FONT_MONO,
                                fg=FG_DIM, bg=BG_PANEL)
        self._fps_label.pack(side="left", padx=6)

        # 提示
        tips = Frame(panel, bg=BG_PANEL)
        tips.pack(fill="x", padx=12, pady=(10, 10))
        Label(tips, text="提示: 启动后会出现 OpenCV 窗口\n按 Q 退出 | 按 P 暂停",
              font=FONT_SMALL, fg=FG_DIM, bg=BG_PANEL, justify="left").pack(anchor="w")

    # ── 档案面板 ──

    def _build_profile_panel(self, parent: Frame) -> None:
        panel = self._make_panel(parent, "映射档案")
        panel.pack(fill="x", pady=(0, 10))

        row = Frame(panel, bg=BG_PANEL)
        row.pack(fill="x", padx=12, pady=6)

        Label(row, text="选择游戏:", font=FONT_NORMAL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left")
        self._profile_var = StringVar()
        self._profile_menu: OptionMenu | None = None
        # 下拉框稍后在 _load_profiles 中填充
        self._profile_menu = OptionMenu(row, self._profile_var, "")
        self._profile_menu.configure(font=FONT_NORMAL, bg=BG_BUTTON, fg=FG_TEXT,
                                     activebackground=BG_BUTTON,
                                     activeforeground=FG_TEXT, width=20)
        self._profile_menu.pack(side="left", padx=10)

        # 冷却时间
        Label(row, text="冷却ms:", font=FONT_SMALL, fg=FG_DIM,
              bg=BG_PANEL).pack(side="left")
        self._cooldown_var = IntVar(value=300)
        Entry(panel if False else row, textvariable=self._cooldown_var, width=5,
              font=FONT_MONO, bg=BG_MAIN, fg=FG_TEXT,
              insertbackground=FG_TEXT).pack(side="left", padx=4)

        # 档案变化时刷新映射表
        self._profile_var.trace("w", lambda *_: self._load_mapping_table())

    # ── 控制按钮面板 ──

    def _build_control_panel(self, parent: Frame) -> None:
        panel = self._make_panel(parent, "操作")
        panel.pack(fill="x", pady=(0, 10))

        btn_frame = Frame(panel, bg=BG_PANEL)
        btn_frame.pack(fill="x", padx=12, pady=10)

        self._btn_start = Button(btn_frame, text="启动服务",
                                 font=("Microsoft YaHei", 12, "bold"),
                                 bg=FG_ACCENT, fg="#fff",
                                 activebackground="#ff5a75",
                                 activeforeground="#fff",
                                 relief="flat", cursor="hand2",
                                 command=self._on_start, padx=20, pady=8)
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = Button(btn_frame, text="停止",
                                font=("Microsoft YaHei", 12),
                                bg="#555", fg=FG_TEXT,
                                activebackground="#777",
                                activeforeground="#fff",
                                relief="flat", cursor="hand2",
                                command=self._on_stop, state=DISABLED,
                                padx=20, pady=8)
        self._btn_stop.pack(side="left", padx=(0, 8))

        self._btn_web = Button(btn_frame, text="Web 控制面板",
                               font=("Microsoft YaHei", 12),
                               bg=BG_BUTTON, fg=FG_ACCENT2,
                               activebackground="#1a5080",
                               activeforeground=FG_ACCENT2,
                               relief="flat", cursor="hand2",
                               command=self._on_web, padx=16, pady=8)
        self._btn_web.pack(side="left")

        self._btn_editor = Button(btn_frame, text="编辑配置",
                                  font=("Microsoft YaHei", 12),
                                  bg=BG_BUTTON, fg=FG_ACCENT2,
                                  activebackground="#1a5080",
                                  activeforeground=FG_ACCENT2,
                                  relief="flat", cursor="hand2",
                                  command=self._on_editor, padx=16, pady=8)
        self._btn_editor.pack(side="left", padx=(8, 0))

    # ── 编辑器 ──

    def _on_editor(self) -> None:
        """打开动作/档案编辑器窗口"""
        from editor import open_editor
        open_editor()

    # ── 映射表面板 ──

    def _build_mapping_panel(self, parent: Frame) -> None:
        panel = self._make_panel(parent, "映射表预览")
        panel.pack(fill="both", expand=True)

        # Treeview 表格
        tree_frame = Frame(panel, bg=BG_PANEL)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=6)

        columns = ("action", "key", "mode")
        self._tree = ttk.Treeview(tree_frame, columns=columns,
                                  show="headings", height=10)
        self._tree.heading("action", text="体感动作")
        self._tree.heading("key", text="按键")
        self._tree.heading("mode", text="模式")
        self._tree.column("action", width=180)
        self._tree.column("key", width=80, anchor="center")
        self._tree.column("mode", width=70, anchor="center")

        # 滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 样式
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=BG_MAIN, foreground=FG_TEXT,
                        fieldbackground=BG_MAIN, rowheight=26,
                        font=FONT_SMALL)
        style.configure("Treeview.Heading",
                        background=BG_BUTTON, foreground=FG_ACCENT2,
                        font=("Microsoft YaHei", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", BG_BUTTON)])
        style.map("Treeview", background=[("selected", BG_BUTTON)],
                  foreground=[("selected", FG_ACCENT2)])

    # ═══════════════════════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════════════════════

    def _load_profiles(self) -> None:
        """加载所有映射档案到下拉框"""
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

        # 更新 OptionMenu
        menu = self._profile_menu["menu"]
        menu.delete(0, "end")
        for pid, pname in profiles:
            menu.add_command(label=f"{pname} ({pid})",
                             command=lambda v=pid: self._profile_var.set(v))
        self._profile_var.set(profiles[0][0])

    def _load_mapping_table(self) -> None:
        """加载选中档案的映射表到 Treeview"""
        for item in self._tree.get_children():
            self._tree.delete(item)

        profile_id = self._profile_var.get()
        profile_path = PROFILES_DIR / f"{profile_id}.json"
        if not profile_path.exists():
            return

        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            for m in data.get("mappings", []):
                gname = m.get("action_name", m.get("action_id", ""))
                key = m.get("key", "").upper()
                mode = "按住" if m.get("hold", False) else "点击"
                self._tree.insert("", "end",
                                  values=(gname, key, mode))
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # 控制逻辑
    # ═══════════════════════════════════════════════════════════════

    def _on_start(self) -> None:
        """启动体感映射服务"""
        if self.running:
            return
        self.running = True
        self._stop_event.clear()

        # 构建摄像头配置
        cam_type_str = self._cam_type.get()
        cam_type_map = {"local": CameraType.LOCAL, "ip": CameraType.IP,
                        "dual": CameraType.DUAL}
        cam_cfg = CameraConfig(
            cam_type=cam_type_map.get(cam_type_str, CameraType.LOCAL),
            camera_index=self._cam_index.get(),
            ip_url=self._ip_url.get(),
            camera_index_2=self._cam_index2.get(),
            width=640, height=480,
        )

        # 初始化模块
        try:
            self._camera_mgr = CameraManager(cam_cfg)
            if not self._camera_mgr.open():
                messagebox.showerror("错误", "摄像头打开失败！\n请检查:\n"
                                     "1) 摄像头是否已连接\n"
                                     "2) 索引是否正确\n"
                                     "3) IP 摄像头地址是否可达")
                self.running = False
                return
        except Exception as e:
            messagebox.showerror("错误", f"摄像头初始化失败:\n{e}")
            self.running = False
            return

        # 姿态估计
        num_poses = 2 if cam_type_str == "dual" else 1
        self._pose_est = PoseEstimator(num_poses=num_poses, model_path=str(MODEL_PATH))
        self._pose_est.open()

        # 手势引擎
        self._action_engine = ActionEngine(str(ACTIONS_DEFS))

        # 键盘映射
        profile_path = PROFILES_DIR / f"{self._profile_var.get()}.json"
        self._keyboard_emitter = KeyboardEmitter(
            cooldown_ms=self._cooldown_var.get())
        if profile_path.exists():
            self._keyboard_emitter.load_profile(str(profile_path))
        else:
            self._keyboard_emitter.load_profile(
                str(PROFILES_DIR / "naruto_fighting.json"))

        # 启动后台线程
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        # 更新 UI
        self._btn_start.configure(state=DISABLED)
        self._btn_stop.configure(state=NORMAL, bg="#aa3333")
        self._status_label.configure(text="● 运行中", fg="#2ecc71")
        self._on_cam_type_change(cam_type_str)  # 保持高亮

    def _on_stop(self) -> None:
        """停止服务"""
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

        # 更新 UI
        self._btn_start.configure(state=NORMAL)
        self._btn_stop.configure(state=DISABLED, bg="#555")
        self._status_label.configure(text="● 已停止", fg=FG_DIM)
        self._action_label.configure(text="—")
        self._key_label.configure(text="—")
        self._fps_label.configure(text="0")

    def _on_web(self) -> None:
        """打开 Web 控制面板"""
        self.root.after(100, lambda: webbrowser.open("http://127.0.0.1:8888"))
        from server.app import start_server
        threading.Thread(target=start_server, daemon=True).start()
        self._status_label.configure(text="● Web 面板已启动", fg=FG_ACCENT2)

    # ═══════════════════════════════════════════════════════════════
    # 后台采集循环
    # ═══════════════════════════════════════════════════════════════

    def _capture_loop(self) -> None:
        """后台线程: 摄像头采集 → 姿态识别 → 手势映射 → 键盘输出"""
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
                # 绘制骨架
                self._draw_skeleton(frame, pr)

            # 映射到键盘
            if self._keyboard_emitter:
                self._keyboard_emitter.update(active_aids)

            # 绘制 HUD
            y = 25
            for gname in action_names:
                cv2.putText(frame, f"[{gname}]", (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
                y += 24

            # 更新 GUI 共享状态
            self._current_action = action_names[0] if action_names else "—"
            # 获取当前按下的键
            active_keys = [g.upper() for g in active_aids
                           if g in self._keyboard_emitter._mapping] \
                if self._keyboard_emitter else []
            key_str = "+".join(
                self._keyboard_emitter._mapping[g]["key"].upper()
                for g in active_aids
                if g in self._keyboard_emitter._mapping
            ) if self._keyboard_emitter else "—"
            self._current_key = key_str if key_str else "—"

            dur = time.perf_counter() - loop_start
            if dur > 0:
                fps_window.append(1.0 / dur)
            if len(fps_window) > 30:
                fps_window.pop(0)
            self._fps = sum(fps_window) / len(fps_window) if fps_window else 0.0

            # 显示窗口
            cv2.imshow("MotionKeyboardMapper — Camera Feed", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self._stop_event.set()
            elif key == ord("p"):
                # 简单的暂停（阻塞等待）
                while True:
                    k2 = cv2.waitKey(100) & 0xFF
                    if k2 == ord("p") or k2 == ord("q"):
                        if k2 == ord("q"):
                            self._stop_event.set()
                        break

            # 定期刷新 GUI
            if int(time.time() * 2) % 2 == 0:
                self.root.after(0, self._refresh_ui)

        # 清理
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
        """在主线程更新 GUI"""
        if not self.running:
            return
        self._action_label.configure(text=self._current_action)
        self._key_label.configure(text=self._current_key)
        self._fps_label.configure(text=f"{self._fps:.0f}")

    # ═══════════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════════

    def run(self) -> None:
        """启动 GUI 主循环"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        """关闭窗口前清理"""
        if self.running:
            self._on_stop()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    App().run()
