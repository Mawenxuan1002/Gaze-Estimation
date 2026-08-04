# -*- coding: utf-8 -*-
from pathlib import Path
import os

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def config_path():
    return Path(os.environ.get("GAZE_CONFIG", PROJECT_ROOT / "config" / "rooms.json"))


def calibration_path():
    return Path(os.environ.get("GAZE_CALIBRATION", PROJECT_ROOT / "config" / "calib_config.json"))


def model_path():
    return Path(os.environ.get(
        "GAZE_MODEL",
        PROJECT_ROOT / "models" / "face_landmarker.task",
    ))
