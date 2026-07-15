"""
gaze_calibrate.py  -  启动校准模式
=================
启动后依次注视屏幕 四角 + 中心 五个点, 自动采集虹膜坐标
输出个性化校准参数, 写入 calib_config.json

运行:  python gaze_calibrate.py [--camera 0]
"""

import json, os, sys, time
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import cv2
import numpy as np
import mediapipe as mp
from gaze_detector import (
    GazeTracker, compute_gaze_offset,
    L_EYE, R_EYE, L_IRIS_CENTER, R_IRIS_CENTER,
)

CALIB_POINTS = [
    ("左上", 0.15, 0.15),
    ("右上", 0.85, 0.15),
    ("中心", 0.50, 0.50),
    ("左下", 0.15, 0.85),
    ("右下", 0.85, 0.85),
]

COUNTDOWN_SEC = 3   # 每个点倒计时
SAMPLE_SEC   = 3   # 每个点采样时长


def main():
    parser = argparse.ArgumentParser(description="视线校准")
    parser.add_argument("--camera", type=int, default=0, help="摄像头编号")
    args = parser.parse_args()

    tracker = GazeTracker()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[错误] 无法打开摄像头 {args.camera}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(960 * 9 / 16))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"[校准] 摄像头已打开, 窗口中绿点位置即为注视目标")
    print(f"[校准] 共 {len(CALIB_POINTS)} 个点, 每个点倒计时{COUNTDOWN_SEC}秒 + 采样{SAMPLE_SEC}秒")
    print(f"[校准] 按 ESC 可随时退出\n")

    calib_data = {}
    total = len(CALIB_POINTS)

    for idx, (name, sx, sy) in enumerate(CALIB_POINTS):
        target_x = int(sx * w)
        target_y = int(sy * h)

        # ── 倒计时 (持续读取摄像头帧, 检测人脸) ──
        t0 = time.time()
        while time.time() - t0 < COUNTDOWN_SEC:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)

            # 检测人脸 (仅用于显示)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            det = tracker._landmarker.detect_for_video(mp_img, int(time.time() * 1000))

            face_ok = len(det.face_landmarks) > 0

            # 画注视点
            color = (0, 255, 0) if face_ok else (0, 0, 255)
            cv2.circle(frame, (target_x, target_y), 14, color, -1)

            # 信息文字
            remaining = COUNTDOWN_SEC - (time.time() - t0)
            status = "人脸已检测" if face_ok else "未检测到人脸 - 请正对摄像头"
            cv2.putText(frame, f"({idx+1}/{total}) {name} - {remaining:.0f}s",
                        (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, status,
                        (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0) if face_ok else (0, 0, 255), 2)
            cv2.putText(frame, "请注视绿点", (w // 2 - 60, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("校准", frame)
            if cv2.waitKey(30) & 0xFF == 27:  # ESC 退出
                cap.release()
                tracker.release()
                cv2.destroyAllWindows()
                print("[校准] 已取消")
                return

        # ── 正式采样 ──
        print(f"  [{idx+1}/{total}] {name} - 开始采样 ({SAMPLE_SEC}秒)...")
        samples = []
        t1 = time.time()
        while time.time() - t1 < SAMPLE_SEC:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            det = tracker._landmarker.detect_for_video(mp_img, int(time.time() * 1000))

            if det.face_landmarks:
                lm = det.face_landmarks[0]
                ldx, ldy = compute_gaze_offset(lm, L_IRIS_CENTER, L_EYE); lx, ly = (ldx+1)/2, (ldy+1)/2
                rdx, rdy = compute_gaze_offset(lm, R_IRIS_CENTER, R_EYE); rx, ry = (rdx+1)/2, (rdy+1)/2
                ax, ay = (lx + rx) / 2, (ly + ry) / 2
                samples.append((ax, ay))
                status = f"采集中... {len(samples)}帧"
            else:
                status = "未检测到人脸"

            # 画注视点 + 进度
            cv2.circle(frame, (target_x, target_y), 14, (0, 255, 0), -1)
            elapsed = time.time() - t1
            cv2.putText(frame, f"({idx+1}/{total}) {name}", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"{SAMPLE_SEC - elapsed:.1f}s  {status}", (20, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 220), 2)

            cv2.imshow("校准", frame)
            if cv2.waitKey(30) & 0xFF == 27:
                cap.release()
                tracker.release()
                cv2.destroyAllWindows()
                print("[校准] 已取消")
                return

        if samples:
            xs = [s[0] for s in samples]
            ys = [s[1] for s in samples]
            calib_data[name] = {
                "screen_x": sx, "screen_y": sy,
                "iris_x_mean": float(np.mean(xs)),
                "iris_y_mean": float(np.mean(ys)),
                "iris_x_std": float(np.std(xs)),
                "iris_y_std": float(np.std(ys)),
                "samples": len(samples),
            }
            print(f"         iris_x={np.mean(xs):.3f} +/- {np.std(xs):.3f}, "
                  f"iris_y={np.mean(ys):.3f} +/- {np.std(ys):.3f}  ({len(samples)}帧)")
        else:
            print(f"         未采集到数据!")

    cap.release()
    tracker.release()
    cv2.destroyAllWindows()

    if not calib_data:
        print("\n[错误] 所有校准点均未采集到数据, 请确认摄像头可用")
        return

    # 保存
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(calib_data, f, ensure_ascii=False, indent=2)

    print(f"\n[校准] 完成! 共校准 {len(calib_data)}/{total} 个点")
    print(f"[校准] 参数已保存: {out_path}")
    print(f"[校准] 重启 main.py 时将自动加载校准参数")


if __name__ == "__main__":
    main()
