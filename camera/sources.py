"""
摄像头管理器 —— 支持三种输入源：
  1. 本地摄像头（笔记本内置 / USB 外接）
  2. IP 摄像头（手机通过 IP Webcam / DroidCam 传输）
  3. 双摄像头模式（双人对战）

使用方式:
    mgr = CameraManager(config)
    mgr.open()
    while True:
        frames = mgr.read()   # 返回列表 [frame0, frame1, ...]
    mgr.close()
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List

import cv2
import numpy as np


class CameraType(Enum):
    LOCAL = auto()      # 本地摄像头
    IP = auto()         # IP 网络摄像头
    DUAL = auto()       # 双摄像头模式


class CameraSource:
    """单个摄像头源的抽象"""

    def __init__(self, name: str) -> None:
        self.name = name
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        raise NotImplementedError

    def read(self) -> Optional[np.ndarray]:
        raise NotImplementedError

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def get_fps(self) -> float:
        if self._cap is not None:
            return self._cap.get(cv2.CAP_PROP_FPS)
        return 0.0


class LocalCameraSource(CameraSource):
    """本地 USB / 内置摄像头"""

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480,
                 name: str = "本地摄像头") -> None:
        super().__init__(name)
        self.camera_index = camera_index
        self.width = width
        self.height = height

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            print(f"[Camera] 无法打开本地摄像头 index={self.camera_index}")
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, 30)
        print(f"[Camera] 已打开 {self.name} (index={self.camera_index})")
        return True

    def read(self) -> Optional[np.ndarray]:
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        return cv2.flip(frame, 1)  # 镜像


class IPCameraSource(CameraSource):
    """IP 网络摄像头 —— 手机安装 IP Webcam 或 DroidCam 后使用"""

    def __init__(self, url: str, name: str = "手机摄像头") -> None:
        super().__init__(name)
        self.url = url

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.url)
        if not self._cap.isOpened():
            print(f"[Camera] 无法连接 IP 摄像头 {self.url}")
            print("  请确认: 1) 手机和电脑在同一网络  2) 手机端 App 已开启")
            return False
        print(f"[Camera] 已连接 {self.name} ({self.url})")
        return True

    def read(self) -> Optional[np.ndarray]:
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        return frame


@dataclass
class CameraConfig:
    """摄像头配置（从 settings.AppConfig 转换而来）"""
    cam_type: CameraType = CameraType.LOCAL
    camera_index: int = 0
    ip_url: str = ""
    camera_index_2: int = 1
    width: int = 640
    height: int = 480


class CameraManager:
    """
    统一管理一个或多个摄像头源。
    双人模式 (DUAL) 会同时打开两个本地摄像头。
    """

    def __init__(self, cfg: CameraConfig) -> None:
        self.cfg = cfg
        self.sources: List[CameraSource] = []
        self._current_source: Optional[CameraType] = None

    def open(self) -> bool:
        self.close()

        if self.cfg.cam_type == CameraType.LOCAL:
            src = LocalCameraSource(
                camera_index=self.cfg.camera_index,
                width=self.cfg.width,
                height=self.cfg.height,
                name=f"摄像头 #{self.cfg.camera_index}",
            )
            if src.open():
                self.sources.append(src)
                self._current_source = CameraType.LOCAL
                return True
            return False

        elif self.cfg.cam_type == CameraType.IP:
            src = IPCameraSource(url=self.cfg.ip_url)
            if src.open():
                self.sources.append(src)
                self._current_source = CameraType.IP
                return True
            return False

        elif self.cfg.cam_type == CameraType.DUAL:
            src1 = LocalCameraSource(
                camera_index=self.cfg.camera_index,
                width=self.cfg.width,
                height=self.cfg.height,
                name="玩家1 摄像头",
            )
            src2 = LocalCameraSource(
                camera_index=self.cfg.camera_index_2,
                width=self.cfg.width,
                height=self.cfg.height,
                name="玩家2 摄像头",
            )
            ok1 = src1.open()
            ok2 = src2.open()
            if ok1:
                self.sources.append(src1)
            if ok2:
                self.sources.append(src2)
            if self.sources:
                self._current_source = CameraType.DUAL
                return True
            return False

        print(f"[Camera] 未知的摄像头类型: {self.cfg.cam_type}")
        return False

    def read(self) -> List[np.ndarray]:
        """读取所有摄像头的当前帧"""
        frames = []
        for src in self.sources:
            frame = src.read()
            if frame is not None:
                frames.append(frame)
        return frames

    def close(self) -> None:
        for src in self.sources:
            src.close()
        self.sources.clear()
        self._current_source = None

    @property
    def source_count(self) -> int:
        return len(self.sources)

    def __enter__(self):
        if not self.open():
            raise RuntimeError("无法打开摄像头")
        return self

    def __exit__(self, *args):
        self.close()
