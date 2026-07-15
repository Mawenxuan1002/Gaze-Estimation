# -*- coding: utf-8 -*-
import os, sys, json, time, logging, threading, cv2
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaze_detector import GazeTracker, GazeDirection, EyeState
from result_pusher import ResultPusher, BehaviorAnalyzer

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

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        cfg = self.config
        pusher = ResultPusher(
            api_url=cfg.get('api_url'),
            room_no=self.room_no,
            device_id=self.device_id,
            push_interval=cfg.get('push_interval', 10),
            username=cfg.get('username', 'admin'),
            password=cfg.get('password', 'admin123')
        )
        tracker = GazeTracker(ear_threshold=cfg.get('ear_threshold', 0.2))
        analyzer = BehaviorAnalyzer(
            away_duration_threshold=cfg.get('away_duration', 3.0),
            drowsy_duration_threshold=cfg.get('drowsy_duration', 2.0)
        )
        cap = None
        fps_counter = 0
        fps_timer = time.time()
        total_frames = 0
        total_pushes = 0
        current_fps = 0
        last_alert_time = 0
        alert_interval = cfg.get('push_interval', 10)
        
        while not self._stop_event.is_set():
            try:
                if cap is None or not cap.isOpened():
                    logger.info("[{}] Connecting: {}".format(self.room_no, self.rtsp_url))
                    cap = cv2.VideoCapture(self.rtsp_url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        self._stop_event.wait(2)
                        continue
                    logger.info("[{}] Connected".format(self.room_no))
                
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    cap = None
                    self._stop_event.wait(2)
                    continue
                
                result = tracker.process_frame(frame)
                fps_counter += 1
                total_frames += 1
                
                if time.time() - fps_timer >= 1.0:
                    current_fps = fps_counter
                    fps_counter = 0
                    fps_timer = time.time()
                
                # Update stats for demo
                update_stats(self.room_no, {
                    'room_no': self.room_no,
                    'fps': current_fps,
                    'frames': total_frames,
                    'pushes': total_pushes,
                    'gaze': result.gaze.name if result.gaze else 'UNKNOWN',
                    'eye_state': result.eye_state.name if result.eye_state else 'UNKNOWN',
                    'ear': round(result.ear, 3) if result.ear else 0,
                    'drowsy': result.drowsy,
                    'face_detected': result.face_detected,
                    'time': datetime.now().isoformat()
                })
                
                # Check for alerts with rate limiting
                now = time.time()
                if now - last_alert_time >= alert_interval:
                    event = analyzer.analyze(result)
                    if event and event[2] in ('中', '高'):
                        if pusher.push_frame_result(result):
                            total_pushes += 1
                            last_alert_time = now
                            logger.info("[{}] Alert: {} - {}".format(self.room_no, event[0], event[1]))
                
                # Update frame for web display
                _, jpeg = cv2.imencode('.jpg', frame)
                with frame_lock:
                    frame_cache[self.room_no] = jpeg.tobytes()
                    
            except Exception as e:
                logger.error("[{}] Error: {}".format(self.room_no, e))
                self._stop_event.wait(2)
                if cap:
                    cap.release()
                    cap = None
        
        if cap:
            cap.release()
        tracker.release()

def get_frame(room_no):
    with frame_lock:
        return frame_cache.get(room_no)
