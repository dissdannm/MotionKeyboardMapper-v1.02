"""
FastAPI 服务器 —— 体感键盘映射的 Web 控制面板。
提供:
  - 摄像头类型选择与预览
  - 映射配置切换
  - 单人/双人模式
  - 实时手势 + 按键状态 SSE 推送
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import AppConfig, PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG, MODEL_PATH
from camera.sources import CameraManager, CameraConfig, CameraType
from pose.estimator import PoseEstimator
from actions.engine import ActionEngine
from keyboard.emitter import KeyboardEmitter

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"


class AppState:
    """全局应用程序状态 —— 线程安全"""

    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.lock = threading.Lock()

        self.config = AppConfig()
        self.camera_mgr: Optional[CameraManager] = None
        self.pose_est: Optional[PoseEstimator] = None
        self.action_engine: Optional[ActionEngine] = None
        self.keyboard: Optional[KeyboardEmitter] = None

        # 当前状态（供 SSE 推送）
        self.current_actions: list = []
        self.current_keys: list = []
        self.fps: float = 0.0
        self.frame_base64: str = ""
        self.player_count: int = 1

    def init_modules(self) -> str:
        """初始化所有模块，返回错误信息或空字符串"""
        try:
            cfg = self.config

            # 摄像头
            cam_cfg = CameraConfig(
                cam_type=CameraType[cfg.camera_type.upper()] if cfg.camera_type.upper() in CameraType.__members__ else CameraType.LOCAL,
                camera_index=cfg.camera_index,
                ip_url=cfg.ip_camera_url,
                camera_index_2=cfg.camera_index_2,
                width=cfg.camera_width,
                height=cfg.camera_height,
            )
            self.camera_mgr = CameraManager(cam_cfg)
            if not self.camera_mgr.open():
                return "摄像头打开失败"

            # 姿态估计
            pc = 2 if cam_cfg.cam_type == CameraType.DUAL else cfg.num_poses
            self.pose_est = PoseEstimator(num_poses=pc, model_path=cfg.model_path or str(MODEL_PATH))
            self.pose_est.open()
            self.player_count = self.camera_mgr.source_count or 1

            # 手势引擎
            self.action_engine = ActionEngine(str(ACTIONS_DEFS))

            # 键盘
            self.keyboard = KeyboardEmitter(cooldown_ms=cfg.cooldown_ms)
            profile_path = PROFILES_DIR / f"{cfg.profile}.json"
            if profile_path.exists():
                self.keyboard.load_profile(str(profile_path))
            else:
                return f"配置文件不存在: {profile_path}"

            return ""
        except Exception as e:
            return str(e)

    def stop(self) -> None:
        self.running = False
        if self.keyboard:
            self.keyboard.release_all()
        if self.camera_mgr:
            self.camera_mgr.close()
        if self.pose_est:
            self.pose_est.close()


# ─── FastAPI App ────────────────────────────────────────────────────

app = FastAPI(title="MotionKeyboardMapper", version="1.0.0")
state = AppState()

# 静态文件
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ─── 页面路由 ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = TEMPLATES_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>模板文件缺失</h1>", status_code=500)


# ─── API 路由 ────────────────────────────────────────────────────────

@app.get("/api/profiles")
async def list_profiles():
    profiles = []
    for f in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles.append({
                "id": data.get("profile_id", f.stem),
                "name": data.get("profile_name", f.stem),
                "description": data.get("description", ""),
                "player_count": data.get("player_count", 1),
            })
        except Exception:
            pass
    return {"profiles": profiles}


@app.get("/api/actions")
async def list_actions():
    if state.action_engine is None:
        return {"actions": []}
    result = []
    for gid, gdef in state.action_engine.definitions.items():
        result.append({
            "id": gid,
            "name": gdef.get("name", gid),
            "type": gdef.get("type", "pose"),
            "conflict_group": gdef.get("conflict_group", ""),
        })
    return {"actions": result}


@app.get("/api/status")
async def get_status():
    return {
        "running": state.running,
        "paused": state.paused,
        "fps": state.fps,
        "current_actions": state.current_actions,
        "current_keys": state.current_keys,
        "player_count": state.player_count,
        "camera_type": state.config.camera_type,
        "profile": state.config.profile,
    }


@app.post("/api/start")
async def start_service():
    if state.running:
        return {"ok": True, "message": "已经在运行中"}

    err = state.init_modules()
    if err:
        raise HTTPException(status_code=400, detail=err)

    state.running = True
    threading.Thread(target=_capture_loop, daemon=True).start()
    return {"ok": True, "message": "已启动"}


@app.post("/api/stop")
async def stop_service():
    state.stop()
    return {"ok": True, "message": "已停止"}


@app.post("/api/pause")
async def toggle_pause():
    state.paused = not state.paused
    return {"paused": state.paused}


@app.post("/api/config")
async def update_config(data: dict):
    """动态更新配置（需要重启生效）"""
    cfg = state.config
    if "camera_type" in data:
        cfg.camera_type = data["camera_type"]
    if "camera_index" in data:
        cfg.camera_index = int(data["camera_index"])
    if "ip_camera_url" in data:
        cfg.ip_camera_url = data["ip_camera_url"]
    if "camera_index_2" in data:
        cfg.camera_index_2 = int(data["camera_index_2"])
    if "profile" in data:
        cfg.profile = data["profile"]
    if "cooldown_ms" in data:
        cfg.cooldown_ms = int(data["cooldown_ms"])
    if "hold_mode" in data:
        cfg.hold_mode = bool(data["hold_mode"])
    return {"ok": True, "config": {
        "camera_type": cfg.camera_type,
        "camera_index": cfg.camera_index,
        "profile": cfg.profile,
    }}


@app.get("/api/video_feed")
async def video_feed():
    """MJPEG 流 —— 可选，Web 界面也可通过 SSE 的 base64 帧来展示"""
    def generate():
        while state.running:
            if state.frame_base64:
                import base64
                frame_bytes = base64.b64decode(state.frame_base64)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                time.sleep(0.03)
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/events")
async def sse_events():
    """SSE 推送当前状态"""
    async def event_stream():
        while state.running:
            data = {
                "actions": state.current_actions,
                "keys": state.current_keys,
                "fps": round(state.fps, 1),
                "paused": state.paused,
                "frame": state.frame_base64,
            }
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.05)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── 采集主循环（后台线程）───────────────────────────────────────────

def _capture_loop() -> None:
    """后台持续采集、推理、映射"""
    fps_window = []
    last_frame_time = time.perf_counter()

    while state.running:
        if state.paused:
            time.sleep(0.1)
            continue

        loop_start = time.perf_counter()

        # 读取帧
        frames = state.camera_mgr.read()
        if not frames:
            time.sleep(0.01)
            continue

        all_actions = []
        all_keys = []

        for i, frame in enumerate(frames):
            # 姿态估计
            ts = int(time.time() * 1000)
            pose_results = state.pose_est.process(frame, ts)

            if not pose_results:
                all_actions.append([])
                all_keys.append([])
                continue

            # 手势识别（取第一个检测到的人）
            pr = pose_results[0]
            active = set()
            if pr and state.action_engine:
                state.action_engine.update(pr)
                active = state.action_engine.active_actions

            gnames = [(state.action_engine.definitions[g].name if g in state.action_engine.definitions else g)
                       for g in active] if state.action_engine else []
            all_actions.append(gnames)

            # 键盘映射
            if state.keyboard:
                state.keyboard.update(active)
            all_keys.append(list(active))

            # 可视化叠加
            if state.config.show_video_feed and pr:
                _draw_overlay(frame, pr, gnames, state.action_engine)

            # 编码帧
            if i == 0:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                import base64
                state.frame_base64 = base64.b64encode(buf).decode()

        # 更新状态
        state.current_actions = all_actions[0] if all_actions else []
        state.current_keys = all_keys[0] if all_keys else []

        # FPS 计算
        duration = time.perf_counter() - loop_start
        if duration > 0:
            fps_window.append(1.0 / duration)
        if len(fps_window) > 30:
            fps_window.pop(0)
        state.fps = sum(fps_window) / len(fps_window) if fps_window else 0.0

    # 退出清理
    if state.keyboard:
        state.keyboard.release_all()


def _draw_overlay(frame, pose, action_names, engine) -> None:
    """在帧上绘制简易骨架和手势名称"""
    h, w = frame.shape[:2]
    # 简易骨架连接
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
            pa = (int(a.x * w), int(a.y * h))
            pb = (int(b.x * w), int(b.y * h))
            cv2.line(frame, pa, pb, (0, 255, 0), 2)

    # 手势名
    y_off = 30
    for gname in action_names:
        cv2.putText(frame, gname, (10, y_off), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 255), 2)
        y_off += 25


# ─── 入口 ────────────────────────────────────────────────────────────

def start_server(host: str = "127.0.0.1", port: int = 8888) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")
