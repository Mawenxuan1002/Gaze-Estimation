# -*- coding: utf-8 -*-
import time
import unittest
import threading
import sys
import math
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from head_pose import rotation_matrix_to_head_angles
from result_pusher import BehaviorAnalyzer, ResultPusher, SeverityLevel

with patch.dict(sys.modules, {"gaze_detector": SimpleNamespace(GazeTracker=object)}):
    from stream_worker import StreamWorker


def frame(timestamp, ratio, face_detected=True, head_yaw=0.0):
    return SimpleNamespace(
        timestamp=timestamp,
        face_detected=face_detected,
        head_down_ratio=ratio,
        head_yaw=head_yaw,
    )


def axis_rotation(axis, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


class HeadPoseTests(unittest.TestCase):
    def test_y_axis_rotation_is_yaw(self):
        yaw, pitch, roll = rotation_matrix_to_head_angles(axis_rotation("y", 30))
        self.assertAlmostEqual(abs(yaw), 30.0, places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(roll, 0.0, places=5)

    def test_x_axis_rotation_is_pitch(self):
        yaw, pitch, roll = rotation_matrix_to_head_angles(axis_rotation("x", 30))
        self.assertAlmostEqual(yaw, 0.0, places=5)
        self.assertAlmostEqual(abs(pitch), 30.0, places=5)
        self.assertAlmostEqual(roll, 0.0, places=5)

    def test_z_axis_rotation_is_roll_not_yaw(self):
        yaw, pitch, roll = rotation_matrix_to_head_angles(axis_rotation("z", 30))
        self.assertAlmostEqual(yaw, 0.0, places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(abs(roll), 30.0, places=5)


class BehaviorAnalyzerTests(unittest.TestCase):
    def test_ratio_rise_triggers_after_configured_duration(self):
        analyzer = BehaviorAnalyzer(
            head_down_duration_threshold=2.0,
            head_down_ratio_delta=0.10,
            calibration_frames=2,
        )

        self.assertIsNone(analyzer.analyze(frame(0.0, 0.30)))
        self.assertIsNone(analyzer.analyze(frame(1.0, 0.30)))
        self.assertAlmostEqual(analyzer.get_ratio_rise(0.42), 0.12)
        self.assertIsNone(analyzer.analyze(frame(2.0, 0.42)))

        event = analyzer.analyze(frame(4.0, 0.42))
        self.assertIsNotNone(event)
        self.assertEqual(event[2], SeverityLevel.HIGH)

    def test_ratio_drop_does_not_trigger_head_down(self):
        analyzer = BehaviorAnalyzer(
            head_down_duration_threshold=1.0,
            head_down_ratio_delta=0.10,
            calibration_frames=1,
        )
        analyzer.analyze(frame(0.0, 0.30))
        analyzer.analyze(frame(1.0, 0.15))
        self.assertIsNone(analyzer.analyze(frame(3.0, 0.15)))

    def test_short_threshold_interruption_does_not_reset_timer(self):
        analyzer = BehaviorAnalyzer(
            head_down_duration_threshold=2.0,
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            ratio_hysteresis=0.02,
            interruption_grace_seconds=0.5,
        )
        analyzer.analyze(frame(0.0, 0.30))
        analyzer.analyze(frame(1.0, 0.42))
        analyzer.analyze(frame(1.8, 0.35))
        analyzer.analyze(frame(2.0, 0.42))

        event = analyzer.analyze(frame(3.0, 0.42))
        self.assertIsNotNone(event)

    def test_sustained_interruption_resets_timer(self):
        analyzer = BehaviorAnalyzer(
            head_down_duration_threshold=2.0,
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            interruption_grace_seconds=0.5,
        )
        analyzer.analyze(frame(0.0, 0.30))
        analyzer.analyze(frame(1.0, 0.42))
        analyzer.analyze(frame(1.5, 0.30))
        analyzer.analyze(frame(2.1, 0.30))

        self.assertEqual(analyzer.get_head_down_duration(3.0), 0.0)

    def test_side_yaw_reduces_threshold_symmetrically(self):
        analyzer = BehaviorAnalyzer(
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            side_yaw_start=15.0,
            side_yaw_full=45.0,
            side_threshold_scale=0.50,
        )

        self.assertAlmostEqual(analyzer.get_effective_ratio_delta(0.0), 0.10)
        self.assertAlmostEqual(analyzer.get_effective_ratio_delta(45.0), 0.05)
        self.assertAlmostEqual(analyzer.get_effective_ratio_delta(-45.0), 0.05)

    def test_side_head_down_starts_timer_below_front_threshold(self):
        analyzer = BehaviorAnalyzer(
            head_down_duration_threshold=2.0,
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            side_threshold_scale=0.50,
        )
        analyzer.analyze(frame(0.0, 0.30))

        side_result = frame(1.0, 0.36, head_yaw=-45.0)
        self.assertIsNone(analyzer.analyze(side_result))
        self.assertTrue(analyzer.is_head_down(side_result))
        self.assertEqual(analyzer.get_head_down_duration(1.5), 0.5)

    def test_same_ratio_rise_does_not_trigger_when_facing_front(self):
        analyzer = BehaviorAnalyzer(
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            side_threshold_scale=0.50,
        )
        analyzer.analyze(frame(0.0, 0.30))
        front_result = frame(1.0, 0.36, head_yaw=0.0)

        self.assertIsNone(analyzer.analyze(front_result))
        self.assertFalse(analyzer.is_head_down(front_result))

    def test_calibrated_yaw_offset_does_not_enable_side_threshold_at_front(self):
        analyzer = BehaviorAnalyzer(
            head_down_ratio_delta=0.10,
            calibration_frames=2,
            side_threshold_scale=0.50,
        )
        analyzer.analyze(frame(0.0, 0.30, head_yaw=30.0))
        analyzer.analyze(frame(1.0, 0.30, head_yaw=32.0))

        front_result = frame(2.0, 0.36, head_yaw=31.0)
        self.assertAlmostEqual(analyzer.get_baseline_yaw(), 31.0)
        self.assertAlmostEqual(analyzer.get_relative_yaw(front_result.head_yaw), 0.0)
        self.assertFalse(analyzer.is_head_down(front_result))

    def test_relative_side_yaw_enables_compensation_with_baseline_offset(self):
        analyzer = BehaviorAnalyzer(
            head_down_ratio_delta=0.10,
            calibration_frames=1,
            side_threshold_scale=0.50,
        )
        analyzer.analyze(frame(0.0, 0.30, head_yaw=30.0))
        side_result = frame(1.0, 0.36, head_yaw=75.0)

        self.assertAlmostEqual(analyzer.get_relative_yaw(side_result.head_yaw), 45.0)
        self.assertTrue(analyzer.is_head_down(side_result))


class StubResultPusher(ResultPusher):
    def __init__(self, result):
        super().__init__(push_interval=0)
        self.result = result
        self.received = []

    def _do_push(self, behavior_type, behavior_desc, severity):
        self.received.append((behavior_type, behavior_desc, severity))
        return self.result


class ResultPusherTests(unittest.TestCase):
    def wait_for_completion(self, pusher):
        deadline = time.time() + 1.0
        while pusher.get_stats()["push_pending"] and time.time() < deadline:
            time.sleep(0.01)

    def test_push_event_submits_precomputed_event_and_counts_success(self):
        pusher = StubResultPusher(True)
        event = ("低头不看屏幕", "低头不看屏幕 (30秒)", SeverityLevel.HIGH)

        self.assertTrue(pusher.push_event(event))
        self.wait_for_completion(pusher)

        self.assertEqual(pusher.received, [event])
        self.assertEqual(pusher.get_stats(), {
            "push_submitted": 1,
            "push_successes": 1,
            "push_failures": 0,
            "push_pending": 0,
        })

    def test_failed_http_result_is_not_counted_as_success(self):
        pusher = StubResultPusher(False)
        event = ("低头不看屏幕", "低头不看屏幕 (30秒)", SeverityLevel.HIGH)

        self.assertTrue(pusher.push_event(event))
        self.wait_for_completion(pusher)

        self.assertEqual(pusher.get_stats()["push_successes"], 0)
        self.assertEqual(pusher.get_stats()["push_failures"], 1)


class WorkerLifecycleTests(unittest.TestCase):
    def test_stop_waits_for_worker_thread(self):
        worker = StreamWorker("001", "1", "rtsp://example.invalid/stream")
        worker._stop_event.clear()
        worker._set_state("running")
        worker._thread = threading.Thread(target=worker._stop_event.wait, daemon=True)
        worker._thread.start()

        self.assertTrue(worker.stop(timeout=1.0))
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker.get_status()["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
