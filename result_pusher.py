# -*- coding: utf-8 -*-
import json, os, time, threading, logging
from datetime import datetime
from urllib import request as urllib_request

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaze_detector import GazeDirection, EyeState

logger = logging.getLogger(__name__)

class BehaviorType:
    DISTRACTED = "视线偏离"
    DROWSY = "困倦瞌睡"
    EYES_CLOSED = "持续闭眼"

class SeverityLevel:
    MEDIUM = "中"
    HIGH = "高"

class BehaviorAnalyzer:
    def __init__(self, away_duration_threshold=3.0, drowsy_duration_threshold=2.0):
        self.away_duration_threshold = away_duration_threshold
        self.drowsy_duration_threshold = drowsy_duration_threshold
        self._away_start = None
        self._drowsy_start = None
        self._closed_start = None
        self._last_alert_time = 0

    def reset(self):
        self._away_start = None
        self._drowsy_start = None
        self._closed_start = None

    def analyze(self, result):
        now = result.timestamp
        if not result.face_detected:
            self.reset()
            return None
        if result.gaze in (GazeDirection.LEFT, GazeDirection.RIGHT, GazeDirection.UP, GazeDirection.DOWN):
            if self._away_start is None:
                self._away_start = now
            duration = now - self._away_start
            if duration > self.away_duration_threshold:
                direction_map = {GazeDirection.LEFT: "左", GazeDirection.RIGHT: "右", GazeDirection.UP: "上", GazeDirection.DOWN: "下"}
                direction = direction_map.get(result.gaze, "未知")
                severity = SeverityLevel.MEDIUM if duration < 10 else SeverityLevel.HIGH
                self._away_start = now  # Reset to prevent continuous firing
                return (BehaviorType.DISTRACTED, "持续向{}方向偏视 ({:.0f}秒)".format(direction, duration), severity)
        else:
            self._away_start = None
        if result.eye_state == EyeState.CLOSED:
            if self._closed_start is None:
                self._closed_start = now
            duration = now - self._closed_start
            if duration > self.drowsy_duration_threshold:
                self._closed_start = now
                return (BehaviorType.EYES_CLOSED, "持续闭眼 ({:.0f}秒)".format(duration), SeverityLevel.HIGH)
        else:
            self._closed_start = None
        if result.drowsy:
            if self._drowsy_start is None:
                self._drowsy_start = now
            duration = now - self._drowsy_start
            if duration > self.drowsy_duration_threshold:
                self._drowsy_start = now
                return (BehaviorType.DROWSY, "检测到困倦状态".format(result.perclos), SeverityLevel.HIGH)
        else:
            self._drowsy_start = None
        return None

class ResultPusher:
    def __init__(self, api_url=None, room_no=None, device_id=None, push_interval=None, username=None, password=None):
        self.api_url = (api_url or 'http://192.168.1.90:8081').rstrip("/")
        self.room_no = room_no or '002'
        self.device_id = device_id or '5'
        self.push_interval = push_interval or 10
        self.username = username or 'admin'
        self.password = password or 'admin123'
        self._analyzer = BehaviorAnalyzer()
        self._last_push_time = 0.0
        self._push_count = 0
        self._token = None
        self._token_expires = 0.0

    def _get_token(self):
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        url = self.api_url + "/auth/login"
        payload = json.dumps({"username": self.username, "password": self.password}).encode("utf-8")
        req = urllib_request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib_request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("code") == 200 and body.get("data"):
                    self._token = body["data"]["access_token"]
                    self._token_expires = now + body["data"].get("expires_in", 1440)
                    return self._token
        except Exception as e:
            logger.error("[{}] Auth failed: {}".format(self.room_no, e))
        return None

    def _build_key(self):
        return json.dumps({"roomNo": self.room_no, "deviceId": self.device_id}, ensure_ascii=False)

    def _do_push(self, behavior_type, behavior_desc, severity):
        token = self._get_token()
        if not token:
            return
        url = self.api_url + "/wuyu-statistics/statistics/electronLog/result"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "key": self._build_key(),
            "psychology": {"psychologyDescription": "无", "emotionalState": "正常"},
            "behavior": {"behaviorDescription": behavior_desc, "behaviorType": behavior_type, "severity": severity},
            "startTime": now_str,
            "endTime": now_str
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib_request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("code") == 200:
                    logger.info("[{}] Push OK: {}".format(self.room_no, behavior_type))
        except Exception as e:
            logger.error("[{}] Push failed: {}".format(self.room_no, e))

    def push_frame_result(self, result):
        now = time.time()
        if now - self._last_push_time < self.push_interval:
            return False
        event = self._analyzer.analyze(result)
        if not event:
            return False
        behavior_type, behavior_desc, severity = event
        if severity not in (SeverityLevel.MEDIUM, SeverityLevel.HIGH):
            return False
        self._last_push_time = now
        self._push_count += 1
        threading.Thread(target=self._do_push, args=(behavior_type, behavior_desc, severity), daemon=True).start()
        return True

    def test_push(self):
        self._do_push("困倦瞌睡", "测试推送", "低")

    def get_stats(self):
        return {"push_count": self._push_count}
