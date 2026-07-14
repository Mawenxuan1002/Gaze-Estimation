"""
gaze_trail.py  -  视线轨迹追踪模块
===================================
功能:
  1. 右下角迷你屏幕显示实时视线轨迹
  2. 滑动窗口轨迹 (最近30秒)
  3. 累计热力图模式
  4. 视线停留时间统计
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class GazePoint:
    timestamp: float
    x: float          # 归一化 0-1 (相对屏幕)
    y: float          # 归一化 0-1
    direction: str     # "左看"/"右看"/"正视" 等


class GazeTrail:
    """
    视线轨迹追踪器

    用法:
        trail = GazeTrail()
        while running:
            trail.update(result.iris_x, result.iris_y, "正视")
            frame = trail.draw_on_frame(frame)
    """

    def __init__(
        self,
        trail_duration: float = 30.0,      # 轨迹保留时长 (秒)
        mini_size: int = 160,               # 迷你屏幕尺寸 (px)
        trail_dot_radius: int = 3,          # 轨迹点半径
        trail_line_thickness: int = 1,      # 轨迹线宽
        show_heatmap: bool = False,         # 是否叠加热力图
        heatmap_decay: float = 0.98,        # 热力图衰减系数
    ):
        self.trail_duration = trail_duration
        self.mini_size = mini_size
        self.dot_r = trail_dot_radius
        self.line_t = trail_line_thickness
        self.show_heatmap = show_heatmap
        self.heatmap_decay = heatmap_decay

        # 轨迹历史 (最近N秒)
        self._trail: deque[GazePoint] = deque()
        # 热力图 (累计)
        self._heatmap = np.zeros((mini_size, mini_size), dtype=np.float32)
        # 停留时间统计
        self._dwell: dict[str, float] = {
            "左看": 0.0, "右看": 0.0, "正视": 0.0, "上看": 0.0, "下看": 0.0
        }
        self._last_ts: float | None = None

    def update(self, iris_x: float, iris_y: float, direction: str = "正视"):
        """更新视线位置"""
        now = time.time()
        dt = (now - self._last_ts) if self._last_ts else 0.0
        self._last_ts = now

        pt = GazePoint(timestamp=now, x=iris_x, y=iris_y, direction=direction)
        self._trail.append(pt)

        # 超时清理
        cutoff = now - self.trail_duration
        while self._trail and self._trail[0].timestamp < cutoff:
            self._trail.popleft()

        # 热力图累计
        px = int(np.clip(iris_x, 0, 1) * (self.mini_size - 1))
        py = int(np.clip(iris_y, 0, 1) * (self.mini_size - 1))
        self._heatmap[py, px] += 1.0

        # 衰减
        self._heatmap *= self.heatmap_decay

        # 停留时间
        if dt > 0 and dt < 1.0:
            self._dwell[direction] = self._dwell.get(direction, 0) + dt

    def get_trail_image(self) -> np.ndarray:
        """返回迷你轨迹图 (BGR)"""
        size = self.mini_size
        img = np.zeros((size, size, 3), dtype=np.uint8)

        if not self._trail:
            return img

        now = time.time()
        points = []
        colors = []

        for pt in self._trail:
            px = int(np.clip(pt.x, 0, 1) * (size - 1))
            py = int(np.clip(pt.y, 0, 1) * (size - 1))
            age = now - pt.timestamp

            # 颜色: 越新越亮 (青→绿→黄)
            if age < 1.0:
                color = (255, 255, 0)    # 亮青色 (最新)
            elif age < 3.0:
                color = (0, 255, 200)    # 绿色
            elif age < 10.0:
                color = (0, 180, 255)    # 橙色
            else:
                color = (0, 0, 200)      # 暗红 (最旧)

            points.append((px, py))
            colors.append(color)

        # 画连线
        for i in range(1, len(points)):
            cv2.line(img, points[i - 1], points[i], colors[i], self.line_t)

        # 画点
        for pt, col in zip(points, colors):
            cv2.circle(img, pt, self.dot_r, col, -1)

        # 当前位置 (大亮点)
        if points:
            cv2.circle(img, points[-1], 6, (0, 255, 255), -1)
            cv2.circle(img, points[-1], 6, (255, 255, 255), 1)

        # 热力图叠加
        if self.show_heatmap and self._heatmap.max() > 0:
            heatmap_norm = np.clip(self._heatmap / max(self._heatmap.max(), 1), 0, 1)
            heatmap_bgr = cv2.applyColorMap(
                (heatmap_norm * 255).astype(np.uint8), cv2.COLORMAP_JET
            )
            mask = heatmap_norm > 0.05
            for c in range(3):
                img[:, :, c] = np.where(mask, heatmap_bgr[:, :, c], img[:, :, c])

        return img

    def draw_on_frame(self, frame: np.ndarray,
                      margin: int = 10,
                      position: str = "bottom_right",
                      border_color: tuple = (100, 100, 100),
                      show_stats: bool = True) -> np.ndarray:
        """
        将迷你轨迹图叠加到主画面
        position: "bottom_right" / "bottom_left" / "top_right" / "top_left"
        """
        h, w = frame.shape[:2]
        trail_img = self.get_trail_image()
        ts = self.mini_size

        # 计算位置
        if position == "bottom_right":
            x1 = w - ts - margin
            y1 = h - ts - margin
        elif position == "bottom_left":
            x1 = margin
            y1 = h - ts - margin
        elif position == "top_right":
            x1 = w - ts - margin
            y1 = margin
        else:
            x1 = margin
            y1 = margin

        x2, y2 = x1 + ts, y1 + ts

        # 边框
        cv2.rectangle(frame, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), border_color, 1)
        # 轨迹图
        frame[y1:y2, x1:x2] = trail_img

        # 标题
        cv2.putText(frame, "Gaze Trail", (x1 + 4, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        # 停留时间统计
        if show_stats:
            total = sum(self._dwell.values()) or 1
            stats_y = y2 + 16
            stats = [
                ("Zheng", self._dwell.get("正视", 0), (0, 255, 200)),
                ("Zuo",   self._dwell.get("左看", 0), (0, 200, 255)),
                ("You",   self._dwell.get("右看", 0), (0, 200, 255)),
            ]
            sx = x1
            for label, t, color in stats:
                pct = t / total * 100
                cv2.putText(frame, f"{label}:{pct:.0f}%", (sx, stats_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
                sx += 80

        return frame

    def reset(self):
        """重置轨迹"""
        self._trail.clear()
        self._heatmap[:] = 0
        self._dwell = {k: 0.0 for k in self._dwell}
        self._last_ts = None
