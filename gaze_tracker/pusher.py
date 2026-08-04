# -*- coding: utf-8 -*-
import json
import logging
import os
import threading
import time
from datetime import datetime
from urllib import request as urllib_request


logger = logging.getLogger(__name__)


class BehaviorType:
    HEAD_DOWN = "低头不看屏幕"


class SeverityLevel:
    MEDIUM = "中"
    HIGH = "高"


class BehaviorAnalyzer:
    def __init__(
        self,
        head_down_duration_threshold=30.0,
        head_down_ratio_delta=0.10,
        calibration_frames=30,
        ratio_hysteresis=0.02,
        interruption_grace_seconds=0.5,
        side_yaw_start=15.0,
        side_yaw_full=45.0,
        side_threshold_scale=0.50,
    ):
        self.head_down_duration_threshold = head_down_duration_threshold
        self.head_down_ratio_delta = head_down_ratio_delta
        self.calibration_frames = calibration_frames
        self.ratio_hysteresis = ratio_hysteresis
        self.interruption_grace_seconds = interruption_grace_seconds
        self.side_yaw_start = side_yaw_start
        self.side_yaw_full = max(side_yaw_full, side_yaw_start + 1.0)
        self.side_threshold_scale = min(max(side_threshold_scale, 0.1), 1.0)
        self._head_down_start = None
        self._interruption_start = None
        self._baseline_ratio = None
        self._calib_ratios = []
        self._baseline_yaw = None
        self._calib_yaws = []
        self._calibrating = True

    def reset(self):
        self._head_down_start = None
        self._interruption_start = None

    def _calibrate(self, ratio, head_yaw):
        self._calib_ratios.append(ratio)
        self._calib_yaws.append(float(head_yaw or 0.0))
        if len(self._calib_ratios) >= self.calibration_frames:
            self._baseline_ratio = sum(self._calib_ratios) / len(self._calib_ratios)
            self._baseline_yaw = sum(self._calib_yaws) / len(self._calib_yaws)
            self._calibrating = False
            logger.info(
                "[校准] 基准 ratio = {:.4f}, yaw = {:.1f} (基于 {} 帧)".format(
                    self._baseline_ratio, self._baseline_yaw, len(self._calib_ratios))
            )

    def analyze(self, result):
        now = result.timestamp
        if not result.face_detected:
            self.reset()
            return None

        ratio = result.head_down_ratio
        if self._calibrating:
            self._calibrate(ratio, getattr(result, "head_yaw", 0.0))
            return None

        ratio_rise = self.get_ratio_rise(ratio)
        relative_yaw = self.get_relative_yaw(getattr(result, "head_yaw", 0.0))
        effective_delta = self.get_effective_ratio_delta(relative_yaw)
        if self._head_down_start is None:
            if ratio_rise >= effective_delta:
                self._head_down_start = now
            else:
                return None
        else:
            release_threshold = max(
                0.0, effective_delta - self.ratio_hysteresis)
            if ratio_rise >= release_threshold:
                self._interruption_start = None
            elif self._interruption_start is None:
                self._interruption_start = now
            elif now - self._interruption_start > self.interruption_grace_seconds:
                self.reset()
                return None

        duration = now - self._head_down_start
        if duration >= self.head_down_duration_threshold:
            self._head_down_start = now
            self._interruption_start = None
            return (
                BehaviorType.HEAD_DOWN,
                "低头不看屏幕 ({:.0f}秒)".format(duration),
                SeverityLevel.HIGH,
            )
        return None

    def get_calibration_progress(self):
        if not self._calibrating:
            return 1.0
        return min(len(self._calib_ratios) / self.calibration_frames, 1.0)

    def get_baseline_ratio(self):
        return self._baseline_ratio

    def get_baseline_yaw(self):
        return self._baseline_yaw

    def get_relative_yaw(self, head_yaw):
        if self._baseline_yaw is None:
            return 0.0
        return float(head_yaw or 0.0) - self._baseline_yaw

    def get_ratio_rise(self, ratio):
        if self._baseline_ratio is None:
            return 0.0
        return ratio - self._baseline_ratio

    def get_effective_ratio_delta(self, head_yaw):
        yaw = abs(float(head_yaw or 0.0))
        if yaw <= self.side_yaw_start:
            return self.head_down_ratio_delta
        progress = min(
            (yaw - self.side_yaw_start) / (self.side_yaw_full - self.side_yaw_start),
            1.0,
        )
        scale = 1.0 - progress * (1.0 - self.side_threshold_scale)
        return self.head_down_ratio_delta * scale

    def is_head_down(self, result):
        if not result.face_detected or self._baseline_ratio is None:
            return False
        relative_yaw = self.get_relative_yaw(getattr(result, "head_yaw", 0.0))
        return self.get_ratio_rise(result.head_down_ratio) >= self.get_effective_ratio_delta(
            relative_yaw)

    def get_head_down_duration(self, timestamp):
        if self._head_down_start is None:
            return 0.0
        return max(0.0, timestamp - self._head_down_start)



class ResultPusher:
    def __init__(self, api_url=None, room_no=None, device_id=None, push_interval=None, username=None, password=None):
        self.api_url = (api_url or os.environ.get("API_URL", "http://localhost:8081")).rstrip("/")
        self.room_no = room_no
        self.device_id = device_id
        self.push_interval = 10 if push_interval is None else push_interval
        self.username = username or os.environ.get("GAZE_USERNAME", "admin")
        self.password = password or os.environ.get("GAZE_PASSWORD", "")
        self._last_submit_time = 0.0
        self._submit_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._pending_count = 0
        self._token = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    def _get_token(self):
        now = time.time()
        with self._lock:
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
                    token = body["data"]["access_token"]
                    expires = now + body["data"].get("expires_in", 1440)
                    with self._lock:
                        self._token = token
                        self._token_expires = expires
                    return token
                logger.error("[{}] Auth rejected: {}".format(self.room_no, body))
        except Exception as e:
            logger.error("[{}] Auth failed: {}".format(self.room_no, e))
        return None

    def _build_key(self):
        return json.dumps({"roomNo": self.room_no, "deviceId": self.device_id}, ensure_ascii=False)

    def _do_push(self, behavior_type, behavior_desc, severity):
        token = self._get_token()
        if not token:
            return False

        url = self.api_url + "/wuyu-statistics/statistics/electronLog/result"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "key": self._build_key(),
            "psychology": {"psychologyDescription": "无", "emotionalState": "正常"},
            "behavior": {
                "behaviorDescription": behavior_desc,
                "behaviorType": behavior_type,
                "severity": severity,
            },
            "startTime": now_str,
            "endTime": now_str,
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
                    return True
                logger.error("[{}] Push rejected: {}".format(self.room_no, body))
        except Exception as e:
            logger.error("[{}] Push failed: {}".format(self.room_no, e))
        return False

    def _push_event_worker(self, event):
        success = False
        try:
            success = self._do_push(*event)
        finally:
            with self._lock:
                self._pending_count -= 1
                if success:
                    self._success_count += 1
                else:
                    self._failure_count += 1

    def push_event(self, event):
        if not event or len(event) != 3:
            return False
        if event[2] not in (SeverityLevel.MEDIUM, SeverityLevel.HIGH):
            return False

        now = time.time()
        with self._lock:
            if now - self._last_submit_time < self.push_interval:
                return False
            self._last_submit_time = now
            self._submit_count += 1
            self._pending_count += 1

        threading.Thread(target=self._push_event_worker, args=(event,), daemon=True).start()
        return True

    def test_push(self):
        return self._do_push("低头不看屏幕", "测试推送", "低")

    def get_stats(self):
        with self._lock:
            return {
                "push_submitted": self._submit_count,
                "push_successes": self._success_count,
                "push_failures": self._failure_count,
                "push_pending": self._pending_count,
            }
