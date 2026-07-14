"""
gaze_detector.py  -  视线方向检测 + 睁眼状态识别 核心模块 (v4)
================================================================
v4 改进:
  - 使用传统 EAR 6点法检测眼睛开合 (替换不可靠的iris 5点法)
  - 使用虹膜相对于眼眶的归一化偏移量做视线方向
  - 自动校准: 运行时学习用户平视时的虹膜中性位置
  - 头部姿态补偿 (solvePnP)
  - 帧间平滑 + 校准文件支持
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)


class GazeDirection(Enum):
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()
    UNKNOWN = auto()


class EyeState(Enum):
    OPEN = auto()
    CLOSING = auto()
    CLOSED = auto()
    OPENING = auto()


@dataclass
class FrameResult:
    timestamp: float
    face_detected: bool
    gaze: GazeDirection = GazeDirection.UNKNOWN
    eye_state: EyeState = EyeState.OPEN
    ear: float = 0.0
    iris_x: float = 0.5
    iris_y: float = 0.5
    drowsy: bool = False
    perclos: float = 0.0
    alert_level: int = 0
    landmarks: Optional[np.ndarray] = None
    head_yaw: float = 0.0
    head_pitch: float = 0.0


# 左眼 6 点 (EAR)
L_EYE = {"left": 33, "right": 133, "top": 159, "bottom": 145, "top2": 153, "bottom2": 154}
# 右眼 6 点
R_EYE = {"left": 362, "right": 263, "top": 386, "bottom": 374, "top2": 380, "bottom2": 381}

# 虹膜中心
L_IRIS_CENTER = 468
R_IRIS_CENTER = 473

# 头部姿态估计关键点
HEAD_POSE_IDX = [1, 33, 263, 61, 291, 199]
HEAD_MODEL_3D = np.array([
    [0.0,   0.0,   0.0],
    [-63.6, -32.7, -26.0],
    [63.6,  -32.7, -26.0],
    [-48.0,  36.4, -16.0],
    [48.0,   36.4, -16.0],
    [0.0,    74.2, -37.0],
], dtype=np.float64)


def _lm_xy(lm, idx) -> np.ndarray:
    return np.array([lm[idx].x, lm[idx].y], dtype=np.float64)


def _dist(a, b):
    return float(np.linalg.norm(a - b))


def compute_ear(lm, eye: dict) -> float:
    """传统 EAR 公式。正常睁眼 0.20~0.38, 闭眼 < 0.15"""
    p_l  = _lm_xy(lm, eye["left"])
    p_r  = _lm_xy(lm, eye["right"])
    p_t  = _lm_xy(lm, eye["top"])
    p_b  = _lm_xy(lm, eye["bottom"])
    p_t2 = _lm_xy(lm, eye["top2"])
    p_b2 = _lm_xy(lm, eye["bottom2"])

    v1 = _dist(p_t, p_b)
    v2 = _dist(p_t2, p_b2)
    h  = _dist(p_l, p_r)
    if h < 1e-8:
        return 0.0
    return float((v1 + v2) / (2.0 * h))


def compute_gaze_offset(lm, iris_center_idx: int, eye: dict) -> tuple:
    """虹膜相对于眼眶中心的归一化偏移量, 范围 [-1, 1]"""
    iris = _lm_xy(lm, iris_center_idx)
    left   = _lm_xy(lm, eye["left"])
    right  = _lm_xy(lm, eye["right"])
    top    = _lm_xy(lm, eye["top"])
    bottom = _lm_xy(lm, eye["bottom"])

    eye_cx = (left[0] + right[0]) / 2.0
    eye_cy = (top[1] + bottom[1]) / 2.0
    half_w = _dist(left, right) / 2.0
    half_h = _dist(top, bottom) / 2.0

    if half_w < 1e-8 or half_h < 1e-8:
        return (0.0, 0.0)

    dx = (iris[0] - eye_cx) / half_w
    dy = (iris[1] - eye_cy) / half_h
    return (float(np.clip(dx, -1, 1)), float(np.clip(dy, -1, 1)))


def estimate_head_pose(lm, frame_w, frame_h) -> tuple:
    points_2d = []
    for idx in HEAD_POSE_IDX:
        lm_point = lm[idx]
        points_2d.append([lm_point.x * frame_w, lm_point.y * frame_h])
    points_2d = np.array(points_2d, dtype=np.float64)

    focal = frame_w
    center = (frame_w / 2, frame_h / 2)
    cam_matrix = np.array([
        [focal, 0, center[0]],
        [0, focal, center[1]],
        [0, 0, 1]
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    success, rvec, tvec = cv2.solvePnP(
        HEAD_MODEL_3D, points_2d, cam_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not success:
        return (0.0, 0.0)

    rmat, _ = cv2.Rodrigues(rvec)
    sy = np.sqrt(rmat[0, 0]**2 + rmat[1, 0]**2)
    if sy < 1e-6:
        yaw   = np.arctan2(-rmat[1, 2], rmat[1, 1])
        pitch = np.arctan2(-rmat[2, 0], sy)
    else:
        yaw   = np.arctan2(rmat[1, 0], rmat[0, 0])
        pitch = np.arctan2(-rmat[2, 0], sy)

    return float(np.degrees(yaw)), float(np.degrees(pitch))


def classify_gaze_from_offset(dx, dy, h_thresh=0.25, v_thresh=0.30):
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    if abs_dx < h_thresh and abs_dy < v_thresh:
        return GazeDirection.CENTER
    if abs_dx > abs_dy:
        if dx < -h_thresh:
            return GazeDirection.LEFT
        elif dx > h_thresh:
            return GazeDirection.RIGHT
    else:
        if dy < -v_thresh:
            return GazeDirection.UP
        elif dy > v_thresh:
            return GazeDirection.DOWN
    return GazeDirection.CENTER


class GazeSmoother:
    def __init__(self, window=7, min_agree=4):
        self._window = window
        self._min_agree = min_agree
        self._history = deque(maxlen=window)

    def update(self, gaze):
        self._history.append(gaze)
        counts = Counter(self._history)
        best, best_n = counts.most_common(1)[0]
        return best if best_n >= self._min_agree else list(self._history)[-1]


class DrowsinessDetector:
    def __init__(self, ear_threshold=0.20, window_seconds=30.0,
                 perclos_warn=0.40, perclos_alert=0.20):
        self.ear_threshold = ear_threshold
        self.window_seconds = window_seconds
        self.perclos_warn = perclos_warn
        self.perclos_alert = perclos_alert
        self._history = []
        self._closed_duration = 0.0
        self._last_ts = None

    def update(self, ear, timestamp):
        is_closed = ear < self.ear_threshold
        dt = (timestamp - self._last_ts) if self._last_ts else 0.0
        self._last_ts = timestamp
        if is_closed:
            self._closed_duration += dt
        else:
            self._closed_duration = 0.0

        self._history.append((timestamp, is_closed))
        cutoff = timestamp - self.window_seconds
        self._history = [(t, c) for t, c in self._history if t > cutoff]

        perclos = sum(1 for _, c in self._history if c) / max(len(self._history), 1)
        eye_state = EyeState.CLOSED if is_closed else EyeState.OPEN
        is_drowsy = self._closed_duration > 1.0 or perclos > self.perclos_alert

        if perclos > self.perclos_warn or self._closed_duration > 2.0:
            alert_level = 2
        elif perclos > self.perclos_alert or self._closed_duration > 1.0:
            alert_level = 1
        else:
            alert_level = 0

        return eye_state, is_drowsy, alert_level, perclos


def load_calibration(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_config.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class NeutralCalibrator:
    """运行时自动学习用户平视时虹膜的中性位置"""
    def __init__(self, alpha=0.02, stable_threshold=0.15):
        self.alpha = alpha
        self.stable_threshold = stable_threshold
        self.neutral_dx = 0.0
        self.neutral_dy = 0.0
        self.initialized = False
        self._warmup_count = 0
        self._warmup_needed = 30

    def update(self, dx, dy):
        if not self.initialized:
            self._warmup_count += 1
            if self._warmup_count <= self._warmup_needed:
                n = self._warmup_count
                self.neutral_dx = (self.neutral_dx * (n - 1) + dx) / n
                self.neutral_dy = (self.neutral_dy * (n - 1) + dy) / n
            else:
                self.initialized = True
            return (dx - self.neutral_dx, dy - self.neutral_dy)

        if abs(dx) < self.stable_threshold and abs(dy) < self.stable_threshold:
            a = self.alpha
            self.neutral_dx = self.neutral_dx * (1 - a) + dx * a
            self.neutral_dy = self.neutral_dy * (1 - a) + dy * a

        return (dx - self.neutral_dx, dy - self.neutral_dy)


class GazeTracker:
    def __init__(self, max_faces=1, min_detection_confidence=0.5,
                 min_tracking_confidence=0.5, ear_threshold=0.20,
                 use_calibration=True):
        model_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "models", "face_landmarker.task"
        )
        if not os.path.exists(model_path):
            raise FileNotFoundError("模型文件不存在: " + model_path)

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_faces=max_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        self._drowsiness = DrowsinessDetector(ear_threshold=ear_threshold)
        self._smoother = GazeSmoother(window=7, min_agree=4)
        self._neutral_calibrator = NeutralCalibrator(alpha=0.02, stable_threshold=0.15)
        self._calib = load_calibration() if use_calibration else None

        self._h_thresh = 0.25
        self._v_thresh = 0.30

        if self._calib:
            self._apply_calibration()
            print("[校准] 已加载校准参数")
        else:
            print("[校准] 未找到校准文件, 使用默认阈值 (运行时自动校准中)")

    def _apply_calibration(self):
        c = self._calib
        center = c.get("中心")
        left   = c.get("左上", c.get("左下"))
        right  = c.get("右上", c.get("右下"))
        top    = c.get("左上", c.get("右上"))
        bottom = c.get("左下", c.get("右下"))
        if center and left and right:
            cx = center.get("iris_x_mean", 0.5)
            lx = left.get("iris_x_mean", 0.3)
            rx = right.get("iris_x_mean", 0.7)
            self._h_thresh = min(abs(cx - lx), abs(rx - cx)) * 0.7
        if center and top and bottom:
            cy = center.get("iris_y_mean", 0.5)
            ty = top.get("iris_y_mean", 0.3)
            by = bottom.get("iris_y_mean", 0.7)
            self._v_thresh = min(abs(cy - ty), abs(by - cy)) * 0.7
        print("  阈值: h={:.3f}  v={:.3f}".format(self._h_thresh, self._v_thresh))

    def process_frame(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        ts = time.time()
        ts_ms = int(ts * 1000)

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result_frame = FrameResult(timestamp=ts, face_detected=False)

        det = self._landmarker.detect_for_video(mp_image, ts_ms)
        if not det.face_landmarks:
            return result_frame

        result_frame.face_detected = True
        lm = det.face_landmarks[0]

        vis_indices = list(L_EYE.values()) + list(R_EYE.values()) + [L_IRIS_CENTER, R_IRIS_CENTER]
        result_frame.landmarks = np.array(
            [(int(lm[i].x * w), int(lm[i].y * h)) for i in vis_indices], dtype=np.int32
        )

        # 眼睛开合度 (传统 EAR 6点法)
        ear_l = compute_ear(lm, L_EYE)
        ear_r = compute_ear(lm, R_EYE)
        ear = (ear_l + ear_r) / 2.0
        result_frame.ear = ear

        # 虹膜偏移量
        dx_l, dy_l = compute_gaze_offset(lm, L_IRIS_CENTER, L_EYE)
        dx_r, dy_r = compute_gaze_offset(lm, R_IRIS_CENTER, R_EYE)
        dx_raw = (dx_l + dx_r) / 2.0
        dy_raw = (dy_l + dy_r) / 2.0

        # 自动校准中性点
        dx, dy = self._neutral_calibrator.update(dx_raw, dy_raw)
        result_frame.iris_x = (dx + 1) / 2.0
        result_frame.iris_y = (dy + 1) / 2.0

        # 头部姿态补偿
        yaw, pitch = estimate_head_pose(lm, w, h)
        result_frame.head_yaw = yaw
        result_frame.head_pitch = pitch
        dx_comp = dx + yaw * 0.003
        dy_comp = dy + pitch * 0.003

        # 视线方向判定
        gaze = classify_gaze_from_offset(dx_comp, dy_comp, self._h_thresh, self._v_thresh)
        result_frame.gaze = self._smoother.update(gaze)

        # 困倦检测
        eye_state, drowsy, alert, perclos = self._drowsiness.update(ear, ts)
        result_frame.eye_state = eye_state
        result_frame.drowsy = drowsy
        result_frame.alert_level = alert
        result_frame.perclos = perclos

        return result_frame

    def release(self):
        self._landmarker.close()
