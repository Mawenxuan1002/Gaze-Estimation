# -*- coding: utf-8 -*-
"""Helpers for platform-provided stream identity."""
import json
from urllib.parse import quote


def parse_platform_key(key):
    if isinstance(key, str):
        key = json.loads(key or "{}")
    if not isinstance(key, dict):
        raise ValueError("key 必须是 JSON 对象或 JSON 字符串")

    room_no = str(key.get("roomNo", "")).strip()
    device_id = str(key.get("deviceId", "")).strip()
    return room_no, device_id


def make_stream_id(room_no, device_id):
    """Build a collision-free, URL-safe ID for worker and cache indexing."""
    room = quote(str(room_no), safe="")
    device = quote(str(device_id), safe="")
    return "{}~{}".format(room, device)
