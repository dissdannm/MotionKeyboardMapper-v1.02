"""
MediaPipe 姿态估计器封装。
支持的模型复杂度: 0 (Lite), 1 (Full), 2 (Heavy)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode


# 33 个关键点的语义名称映射
KEYPOINT_NAMES: Dict[int, str] = {
    0: "nose",
    1: "left_eye_inner", 2: "left_eye", 3: "left_eye_outer",
    4: "right_eye_inner", 5: "right_eye", 6: "right_eye_outer",
    7: "left_ear", 8: "right_ear",
    9: "mouth_left", 10: "mouth_right",
    11: "left_shoulder", 12: "right_shoulder",
    13: "left_elbow", 14: "right_elbow",
    15: "left_wrist", 16: "right_wrist",
    17: "left_pinky", 18: "right_pinky",
    19: "left_index", 20: "right_index",
    21: "left_thumb", 22: "right_thumb",
    23: "left_hip", 24: "right_hip",
    25: "left_knee", 26: "right_knee",
    27: "left_ankle", 28: "right_ankle",
    29: "left_heel", 30: "right_heel",
    31: "left_foot_index", 32: "right_foot_index",
}

NAME_TO_INDEX: Dict[str, int] = {v: k for k, v in KEYPOINT_NAMES.items()}


@dataclass
class Landmark:
    """单个关键点的归一化坐标"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    visibility: float = 0.0


@dataclass
class PoseResult:
    """单次姿态检测结果"""
    landmarks: Dict[str, Landmark] = field(default_factory=dict)
    detected: bool = False
    timestamp_ms: int = 0

    def get(self, name: str) -> Optional[Landmark]:
        return self.landmarks.get(name)

    def __bool__(self) -> bool:
        return self.detected


class PoseEstimator:
    """
    MediaPipe 姿态估计器。
    num_poses=1 单人模式, num_poses=2 双人模式。
    """

    def __init__(self, num_poses: int = 1, model_path: str = "") -> None:
        self.num_poses = min(num_poses, 2)  # Heavy 模型最多支持 2 人
        self.model_path = model_path
        self._landmarker: Optional[PoseLandmarker] = None
        self._frame_count: int = 0

    def open(self) -> bool:
        opts = PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=self.model_path if self.model_path else None,
                delegate=mp.tasks.BaseOptions.Delegate.CPU,
            ),
            running_mode=RunningMode.VIDEO,
            num_poses=self.num_poses,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = PoseLandmarker.create_from_options(opts)
        print(f"[Pose] 姿态估计器已就绪 (num_poses={self.num_poses})")
        return True

    def process(self, frame: np.ndarray, timestamp_ms: Optional[int] = None) -> List[PoseResult]:
        """
        处理一帧，返回检测到的所有人姿态。
        单人模式通常返回列表长度为 1，双人模式可能返回 2。
        """
        if self._landmarker is None:
            return []

        if timestamp_ms is None:
            self._frame_count += 1
            timestamp_ms = self._frame_count * 33  # ~30 fps

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        results: List[PoseResult] = []
        if result.pose_landmarks:
            for pose_lm in result.pose_landmarks:
                pr = PoseResult(detected=True, timestamp_ms=timestamp_ms)
                for idx, lm in enumerate(pose_lm):
                    name = KEYPOINT_NAMES.get(idx, str(idx))
                    pr.landmarks[name] = Landmark(
                        x=lm.x, y=lm.y, z=lm.z,
                        visibility=lm.visibility,
                    )
                results.append(pr)
        return results

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
