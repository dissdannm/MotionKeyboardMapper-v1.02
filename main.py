"""
MotionKeyboardMapper —— 体感游戏通用键盘映射服务

启动方式:
  1. Web 控制面板 (推荐):
     python main.py web
     浏览器打开 http://127.0.0.1:8888

  2. 本地桌面模式:
     python main.py local
     使用 OpenCV 窗口直接运行

  3. 双人模式:
     python main.py dual
     同时打开两个摄像头

参数:
  --profile    映射配置名称 (默认 naruto_fighting)
  --camera     摄像头索引 (默认 0)
  --camera2    双人模式第二个摄像头 (默认 1)
  --ip-url     IP 摄像头地址
  --port       Web 服务器端口 (默认 8888)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import AppConfig, PROFILES_DIR, ACTIONS_DEFS, METRIC_CATALOG, MODEL_PATH
from camera.sources import CameraManager, CameraConfig, CameraType
from pose.estimator import PoseEstimator
from actions.engine import ActionEngine
from keyboard.emitter import KeyboardEmitter


# ══════════════════════════════════════════════════════════════════════
# 本地桌面模式
# ══════════════════════════════════════════════════════════════════════

def run_local(config: AppConfig) -> None:
    """本地 OpenCV 窗口模式 —— 适合调试与单人使用。"""
    print("=" * 55)
    print("  MotionKeyboardMapper — 本地桌面模式")
    print("  按 Q 退出 | 按 P 暂停/继续")
    print("=" * 55)

    # 摄像头
    cam_type = CameraType.IP if config.camera_type == "ip" else CameraType.LOCAL
    cam_cfg = CameraConfig(
        cam_type=cam_type,
        camera_index=config.camera_index,
        ip_url=config.ip_camera_url,
        width=config.camera_width,
        height=config.camera_height,
    )
    mgr = CameraManager(cam_cfg)
    if not mgr.open():
        print("[ERROR] 摄像头打开失败")
        return

    # 姿态估计
    pose = PoseEstimator(num_poses=config.num_poses, model_path=config.model_path or str(MODEL_PATH))
    pose.open()

    # 手势引擎
    action_engine = ActionEngine(str(ACTIONS_DEFS))

    # 键盘映射
    profile_path = PROFILES_DIR / f"{config.profile}.json"
    emitter = KeyboardEmitter(cooldown_ms=config.cooldown_ms)
    if profile_path.exists():
        emitter.load_profile(str(profile_path))
    else:
        print(f"[WARN] 配置 {config.profile}.json 不存在；仅手势识别，无按键输出")
        emitter.load_profile(str(PROFILES_DIR / "naruto_fighting.json"))

    print("[INFO] 已启动，开始捕捉...\n")

    paused = False
    fps_window = []

    try:
        while True:
            if not paused:
                loop_start = time.perf_counter()

                frames = mgr.read()
                if not frames:
                    time.sleep(0.005)
                    continue

                frame = frames[0]
                ts = int(time.time() * 1000)
                pose_results = pose.process(frame, ts)
                active_names = []
                active_aids = set()

                if pose_results:
                    pr = pose_results[0]
                    if pr:
                        action_engine.update(pr)
                        active_aids = action_engine.active_actions
                        active_names = [
                            action_engine.definitions.get(g, object()).name
                            for g in active_aids
                        ]

                # 键盘映射
                emitter.update(active_aids)

                # 可视化
                if pose_results and pose_results[0]:
                    _draw_skeleton(frame, pose_results[0])
                _draw_hud(frame, active_names, paused, fps_window)

                cv2.imshow("MotionKeyboardMapper", frame)

                # FPS
                dur = time.perf_counter() - loop_start
                if dur > 0:
                    fps_window.append(1.0 / dur)
                if len(fps_window) > 30:
                    fps_window.pop(0)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("p"):
                paused = not paused
                print(f"[INFO] {'暂停' if paused else '继续'}")

    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
    finally:
        emitter.release_all()
        mgr.close()
        pose.close()
        cv2.destroyAllWindows()
        print("[INFO] 已退出")


# ══════════════════════════════════════════════════════════════════════
# Web 模式
# ══════════════════════════════════════════════════════════════════════

def run_web(config: AppConfig) -> None:
    """启动 FastAPI Web 控制面板。"""
    from server.app import start_server

    print("=" * 55)
    print("  MotionKeyboardMapper — Web 控制面板")
    print(f"  打开浏览器访问: http://{config.web_host}:{config.web_port}")
    print("=" * 55)

    start_server(host=config.web_host, port=config.web_port)


# ══════════════════════════════════════════════════════════════════════
# 双人模式 (本地窗口)
# ══════════════════════════════════════════════════════════════════════

def run_dual(config: AppConfig) -> None:
    """双人本地模式 —— 同时打开两个摄像头，分屏显示。"""
    print("=" * 55)
    print("  MotionKeyboardMapper — 双人对战模式")
    print("  按 Q 退出")
    print("=" * 55)

    cam_cfg = CameraConfig(
        cam_type=CameraType.DUAL,
        camera_index=config.camera_index,
        camera_index_2=config.camera_index_2,
        width=config.camera_width,
        height=config.camera_height,
    )
    mgr = CameraManager(cam_cfg)
    if not mgr.open():
        print("[ERROR] 双摄像头打开失败")
        return
    if mgr.source_count < 2:
        print("[WARN] 只打开了一个摄像头，但仍以双人模式运行")

    pose_p1 = PoseEstimator(num_poses=1, model_path=str(MODEL_PATH))
    pose_p1.open()
    pose_p2 = PoseEstimator(num_poses=1, model_path=str(MODEL_PATH))
    pose_p2.open()

    ge1 = ActionEngine(str(ACTIONS_DEFS))
    ge2 = ActionEngine(str(ACTIONS_DEFS))

    profile_path = PROFILES_DIR / f"{config.profile}.json"
    em1 = KeyboardEmitter(cooldown_ms=config.cooldown_ms)
    em2 = KeyboardEmitter(cooldown_ms=config.cooldown_ms)
    if profile_path.exists():
        em1.load_profile(str(profile_path))
        em2.load_profile(str(profile_path))

    print("[INFO] 玩家1(左) / 玩家2(右) 已就绪\n")

    try:
        while True:
            frames = mgr.read()
            if not frames:
                time.sleep(0.005)
                continue

            display_frames = []
            players = [
                (frames[0] if len(frames) > 0 else None, pose_p1, ge1, em1, "P1"),
                (frames[1] if len(frames) > 1 else frames[0] if len(frames) == 1 else None,
                 pose_p2, ge2, em2, "P2"),
            ]

            for frame, pose_est, act_eng, emitter, label in players:
                if frame is None:
                    continue
                ts = int(time.time() * 1000)
                pose_results = pose_est.process(frame, ts)
                active_names = []
                active_aids = set()

                if pose_results and pose_results[0]:
                    act_eng.update(pose_results[0])
                    active_aids = act_eng.active_actions
                    active_names = [
                        act_eng.definitions.get(g, object()).name for g in active_aids
                    ]
                emitter.update(active_aids)

                if pose_results and pose_results[0]:
                    _draw_skeleton(frame, pose_results[0])
                cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 255, 255), 2)
                if active_names:
                    cv2.putText(frame, "|".join(active_names), (10, 55),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                display_frames.append(frame)

            # 合并显示
            if len(display_frames) >= 2:
                h = min(f.shape[0] for f in display_frames[:2])
                resized = []
                for f in display_frames[:2]:
                    fh, fw = f.shape[:2]
                    scale = h / fh
                    resized.append(cv2.resize(f, (int(fw * scale), h)))
                combined = cv2.hconcat(resized)
            elif display_frames:
                combined = display_frames[0]
            else:
                continue

            cv2.imshow("MotionKeyboardMapper — Dual Mode", combined)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
    finally:
        em1.release_all()
        em2.release_all()
        mgr.close()
        pose_p1.close()
        pose_p2.close()
        cv2.destroyAllWindows()
        print("[INFO] 已退出")


# ══════════════════════════════════════════════════════════════════════
# 共享绘制工具
# ══════════════════════════════════════════════════════════════════════

def _draw_skeleton(frame, pose) -> None:
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
    # 关键点
    for lm in pose.landmarks.values():
        if lm.visibility > 0.5:
            cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 3, (0, 200, 255), -1)


def _draw_hud(frame, action_names, paused, fps_window) -> None:
    y = 25
    for name in action_names:
        cv2.putText(frame, f"[{name}]", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        y += 24

    if paused:
        cv2.putText(frame, "PAUSED", (frame.shape[1] - 120, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    avg_fps = sum(fps_window) / len(fps_window) if fps_window else 0
    cv2.putText(frame, f"FPS: {avg_fps:.0f}", (frame.shape[1] - 100, frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


# ══════════════════════════════════════════════════════════════════════
# 参数解析
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MotionKeyboardMapper - 体感游戏通用键盘映射服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py web                    启动 Web 控制面板
  python main.py local                  本地桌面模式
  python main.py dual                   双人对战模式
  python main.py local --camera 1       使用第二个摄像头
  python main.py local --camera ip \\
      --ip-url http://192.168.1.5:8080/video  使用手机摄像头
        """,
    )
    parser.add_argument(
        "mode", nargs="?", default="web",
        choices=["web", "local", "dual"],
        help="运行模式: web(控制面板) | local(桌面窗口) | dual(双人)",
    )
    parser.add_argument("--profile", default="naruto_fighting", help="映射配置名称")
    parser.add_argument("--camera", default="0", help="摄像头索引 (0-9) 或 'ip'")
    parser.add_argument("--camera2", type=int, default=1, help="双人模式第二个摄像头")
    parser.add_argument("--ip-url", default="", help="IP 摄像头地址")
    parser.add_argument("--port", type=int, default=8888, help="Web 服务器端口")
    parser.add_argument("--cooldown", type=int, default=300, help="按键冷却时间(ms)")
    parser.add_argument("--no-hold", action="store_true", help="关闭按键保持模式")
    parser.add_argument("--list-profiles", action="store_true", help="列出所有可用配置")

    args = parser.parse_args()

    # 列出配置
    if args.list_profiles:
        print("可用的映射配置:")
        for f in sorted(PROFILES_DIR.glob("*.json")):
            import json
            data = json.loads(f.read_text(encoding="utf-8"))
            print(f"  {data.get('profile_id', f.stem):30s} {data.get('profile_name', '')}")
        return

    # 构建配置
    config = AppConfig()
    config.profile = args.profile
    config.cooldown_ms = args.cooldown
    config.hold_mode = not args.no_hold
    config.web_port = args.port

    cam_str = args.camera
    if cam_str == "ip":
        config.camera_type = "ip"
        config.ip_camera_url = args.ip_url
    elif cam_str.isdigit():
        config.camera_type = "local"
        config.camera_index = int(cam_str)
    else:
        config.camera_type = "local"
        config.camera_index = 0

    if args.mode == "dual":
        config.camera_type = "dual"
        config.camera_index_2 = args.camera2

    # 启动
    if args.mode == "web":
        run_web(config)
    elif args.mode == "dual":
        run_dual(config)
    else:
        run_local(config)


if __name__ == "__main__":
    main()
