# -*- coding: utf-8 -*-
"""使用本地摄像头手工验证低头比例和持续时间判定。"""
import os
import sys
import time

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2

from gaze_detector import GazeTracker
from result_pusher import BehaviorAnalyzer

RATIO_DELTA = 0.10
DURATION_SECONDS = 3.0
ALERT_DISPLAY_SECONDS = 3.0
SIDE_YAW_START = 15.0
SIDE_YAW_FULL = 45.0
SIDE_THRESHOLD_SCALE = 0.50


def main():
    tracker = GazeTracker()
    analyzer = BehaviorAnalyzer(
        head_down_duration_threshold=DURATION_SECONDS,
        head_down_ratio_delta=RATIO_DELTA,
        calibration_frames=30,
        side_yaw_start=SIDE_YAW_START,
        side_yaw_full=SIDE_YAW_FULL,
        side_threshold_scale=SIDE_THRESHOLD_SCALE,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[错误] 无法打开摄像头")
        tracker.release()
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)

    print("=== 低头检测测试 ===")
    print("启动后请正视摄像头，前 30 个有效人脸帧用于校准。")
    print("低头时 ratio 上升 >= {:.2f}，持续 {:.0f} 秒触发告警。".format(
        RATIO_DELTA, DURATION_SECONDS))
    print("按 q 退出。")
    alert_visible_until = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            result = tracker.process_frame(frame)
            h, w = frame.shape[:2]

            if result.face_detected:
                ratio = result.head_down_ratio
                event = analyzer.analyze(result)
                ratio_rise = analyzer.get_ratio_rise(ratio)
                relative_yaw = analyzer.get_relative_yaw(result.head_yaw)
                effective_delta = analyzer.get_effective_ratio_delta(relative_yaw)
                is_head_down = analyzer.is_head_down(result)
                head_down_seconds = analyzer.get_head_down_duration(result.timestamp)
                progress = analyzer.get_calibration_progress()
                baseline = analyzer.get_baseline_ratio()
                if event:
                    alert_visible_until = time.time() + ALERT_DISPLAY_SECONDS
                    print("[ALERT] {}".format(event[1]))

                if progress < 1.0:
                    cv2.putText(
                        frame,
                        "CALIBRATING {:.0f}% - LOOK STRAIGHT".format(progress * 100),
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2,
                    )
                    bar_w = int(w * 0.5)
                    bar_x = (w - bar_w) // 2
                    cv2.rectangle(frame, (bar_x, h - 50), (bar_x + bar_w, h - 30), (60, 60, 60), -1)
                    cv2.rectangle(
                        frame,
                        (bar_x, h - 50),
                        (bar_x + int(bar_w * progress), h - 30),
                        (0, 255, 255),
                        -1,
                    )
                else:
                    color = (0, 0, 255) if is_head_down else (0, 255, 0)
                    state = "HEAD DOWN" if is_head_down else "NORMAL"
                    cv2.putText(
                        frame,
                        "RATIO {:.3f} RISE {:+.3f} LIMIT {:.3f}".format(
                            ratio, ratio_rise, effective_delta),
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        color,
                        2,
                    )
                    cv2.putText(
                        frame,
                        "{}  {:.1f}/{:.1f}s".format(
                            state, head_down_seconds, DURATION_SECONDS),
                        (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        color,
                        2,
                    )
                    cv2.putText(
                        frame,
                        "BASE {:.3f} YAW {:+.1f} REL {:+.1f}".format(
                            baseline, result.head_yaw, relative_yaw),
                        (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (180, 180, 180),
                        1,
                    )
                    if time.time() < alert_visible_until:
                        cv2.putText(
                            frame,
                            "ALERT: HEAD DOWN",
                            (w // 2 - 170, h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 0, 255),
                            3,
                        )
            else:
                cv2.putText(
                    frame,
                    "NO FACE",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2,
                )

            cv2.imshow("Head Down Test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        tracker.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
