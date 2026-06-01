"""
全局配置——通过环境变量或直接修改此文件来调整参数。
"""

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "config" / "profiles"
GESTURE_DEFS = ROOT / "gesture" / "definitions" / "standard.json"
ACTIONS_DEFS = ROOT / "actions" / "definitions" / "naruto_actions.json"
METRIC_CATALOG = ROOT / "actions" / "definitions" / "metric_catalog.json"
MODEL_PATH = ROOT / "assets" / "models" / "pose_landmarker_heavy.task"


@dataclass
class AppConfig:
    # --- 摄像头 ---
    camera_type: str = "local"        # "local" | "ip" | "dual"
    camera_index: int = 0             # 本地摄像头索引
    ip_camera_url: str = ""           # IP 摄像头地址 (e.g. http://192.168.1.5:8080/video)
    camera_index_2: int = 1           # 双人模式的第二个摄像头
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30

    # --- 姿态检测 ---
    model_path: str = ""              # 留空则自动使用 assets/models/ 内置模型
    num_poses: int = 1                # 1 或 2

    # --- 键盘映射 ---
    profile: str = "naruto_fighting"  # 当前使用的映射配置名称
    cooldown_ms: int = 300            # 同个按键的冷却时间
    hold_mode: bool = True            # True: 按住不放/False: 单次点击

    # --- 服务器 ---
    web_host: str = "127.0.0.1"
    web_port: int = 8888
    show_video_feed: bool = True

    # --- 调试 ---
    verbose: bool = False
