# -*- coding: utf-8 -*-
import logging
import os
import sys
import threading
import time
from datetime import datetime

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaze_detector import GazeTracker
from result_pusher import BehaviorAnalyzer, ResultPusher

logger = logging.getLogger(__name__)

frame_cache = {}
frame_lock = threading.Lock()
stats_cache = {}
stats_lock = threading.Lock()


def update_stats(room_no, data):
    with stats_lock:
        stats_cache[room_no] = data


def get_stats(room_no):
    with stats_lock:
        return stats_cache.get(room_no, {})


class StreamWorker:
    def __init__(self, room_no, device_id, rtsp_url, config=None):
        self.room_no = room_no
        self.device_id = device_id
        self.rtsp_url = rtsp_url
        self.config = config or {}
        self._stop_event = threading.Event()
        self._thread = None
        self._state = "stopped"
        self._state_lock = threading.Lock()
        self._last_error = None

    def _set_state(self, state, error=None):
        with self._state_lock:
            self._state = state
            self._last_error = error

    def start(self):
        if self.is_alive():
            return False
        self._stop_event.clear()
        self._set_state("starting")
        self._thread = threading.Thread(
            target=self._run,
            name="stream-{}".format(self.room_no),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout=5.0):
        self._stop_event.set()
        if self.is_alive():
            self._set_state("stopping")
            self._thread.join(timeout)
        stopped = not self.is_alive()
        if stopped:
            self._set_state("stopped")
        return stopped

    def is_alive(self):
        return bool(self._thread and self._thread.is_alive())

    def get_status(self):
        with self._state_lock:
            state = self._state
            error = self._last_error
        if not self.is_alive() and state not in ("stopped", "error"):
            state = "stopped"
        return {"status": state, "alive": self.is_alive(), "last_error": error}

    def _run(self):
        cfg = self.config
        pusher = ResultPusher(
            api_url=cfg.get("api_url"),
            room_no=self.room_no,
            device_id=self.device_id,
            push_interval=cfg.get("push_interval", 10),
            username=cfg.get("username") or os.environ.get("GAZE_USERNAME", "admin"),
            password=cfg.get("password") or os.environ.get("GAZE_PASSWORD", ""),
        )
        tracker = None
        cap = None
        fps_counter = 0
        fps_timer = time.time()
        total_frames = 0
        detected_count = 0
        current_fps = 0
        ratio_delta = cfg.get("head_down_ratio_delta", 0.10)
        side_yaw_start = cfg.get("head_down_side_yaw_start", 15.0)
        side_yaw_full = cfg.get("head_down_side_yaw_full", 45.0)
        side_threshold_scale = cfg.get("head_down_side_threshold_scale", 0.50)

        try:
            tracker = GazeTracker(ear_threshold=cfg.get("ear_threshold", 0.2))
            analyzer = BehaviorAnalyzer(
                head_down_duration_threshold=cfg.get("head_down_duration", 30.0),
                head_down_ratio_delta=ratio_delta,
                side_yaw_start=side_yaw_start,
                side_yaw_full=side_yaw_full,
                side_threshold_scale=side_threshold_scale,
            )

            while not self._stop_event.is_set():
                try:
                    if cap is None or not cap.isOpened():
                        self._set_state("connecting")
                        logger.info("[{}] Connecting: {}".format(self.room_no, self.rtsp_url))
                        cap = cv2.VideoCapture(self.rtsp_url)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        if not cap.isOpened():
                            self._set_state("connecting", "无法连接视频流")
                            self._stop_event.wait(2)
                            continue
                        self._set_state("running")
                        logger.info("[{}] Connected".format(self.room_no))

                    ret, frame = cap.read()
                    if not ret:
                        cap.release()
                        cap = None
                        self._set_state("connecting", "读取视频帧失败")
                        self._stop_event.wait(2)
                        continue

                    result = tracker.process_frame(frame)
                    event = analyzer.analyze(result)
                    if event:
                        detected_count += 1
                        if pusher.push_event(event):
                            logger.info("[{}] Alert submitted: {} - {}".format(
                                self.room_no, event[0], event[1]))

                    fps_counter += 1
                    total_frames += 1
                    if time.time() - fps_timer >= 1.0:
                        current_fps = fps_counter
                        fps_counter = 0
                        fps_timer = time.time()

                    ratio_rise = analyzer.get_ratio_rise(result.head_down_ratio)
                    relative_yaw = analyzer.get_relative_yaw(result.head_yaw)
                    effective_ratio_delta = analyzer.get_effective_ratio_delta(relative_yaw)
                    is_head_down = analyzer.is_head_down(result)
                    head_down_seconds = analyzer.get_head_down_duration(result.timestamp)
                    push_stats = pusher.get_stats()
                    worker_status = self.get_status()
                    update_stats(self.room_no, {
                        "room_no": self.room_no,
                        "status": worker_status["status"],
                        "alive": worker_status["alive"],
                        "last_error": worker_status["last_error"],
                        "fps": current_fps,
                        "frames": total_frames,
                        "detected_count": detected_count,
                        "pushes": push_stats["push_successes"],
                        **push_stats,
                        "head_pitch": round(result.head_pitch, 1),
                        "head_yaw": round(result.head_yaw, 1),
                        "baseline_yaw": round(analyzer.get_baseline_yaw() or 0.0, 1),
                        "relative_yaw": round(relative_yaw, 1),
                        "head_down": is_head_down,
                        "head_down_seconds": round(head_down_seconds, 1),
                        "ratio_rise": round(ratio_rise, 3),
                        "effective_ratio_delta": round(effective_ratio_delta, 3),
                        "calibration_progress": analyzer.get_calibration_progress(),
                        "face_detected": result.face_detected,
                        "time": datetime.now().isoformat(),
                    })

                    encoded, jpeg = cv2.imencode(".jpg", frame)
                    if encoded:
                        with frame_lock:
                            frame_cache[self.room_no] = jpeg.tobytes()

                except Exception as e:
                    message = str(e)
                    logger.error("[{}] Error: {}".format(self.room_no, message))
                    self._set_state("error", message)
                    if cap:
                        cap.release()
                        cap = None
                    if not self._stop_event.wait(2):
                        self._set_state("connecting", message)
        except Exception as e:
            message = str(e)
            logger.exception("[{}] Worker stopped unexpectedly".format(self.room_no))
            self._set_state("error", message)
        finally:
            if cap:
                cap.release()
            if tracker:
                tracker.release()
            if self._stop_event.is_set():
                self._set_state("stopped")

            status = self.get_status()
            push_stats = pusher.get_stats()
            previous = get_stats(self.room_no)
            update_stats(self.room_no, {
                **previous,
                **push_stats,
                "status": status["status"],
                "alive": False,
                "last_error": status["last_error"],
                "time": datetime.now().isoformat(),
            })


def get_frame(room_no):
    with frame_lock:
        return frame_cache.get(room_no)
