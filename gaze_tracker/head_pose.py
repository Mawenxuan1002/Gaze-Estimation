# -*- coding: utf-8 -*-
"""Head-pose angle conversion helpers."""
import numpy as np


def rotation_matrix_to_head_angles(rotation_matrix):
    """Return (yaw, pitch, roll) in degrees for R = Rz * Ry * Rx.

    Yaw is rotation around Y (left/right), pitch around X (up/down), and
    roll around Z (tilt). The signs depend on the camera/model coordinate
    system; side compensation uses abs(yaw), so left and right are symmetric.
    """
    rmat = np.asarray(rotation_matrix, dtype=np.float64)
    if rmat.shape != (3, 3):
        raise ValueError("rotation_matrix must have shape (3, 3)")

    horizontal = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
    singular = horizontal < 1e-6

    if not singular:
        pitch = np.arctan2(rmat[2, 1], rmat[2, 2])
        yaw = np.arctan2(-rmat[2, 0], horizontal)
        roll = np.arctan2(rmat[1, 0], rmat[0, 0])
    else:
        pitch = np.arctan2(-rmat[1, 2], rmat[1, 1])
        yaw = np.arctan2(-rmat[2, 0], horizontal)
        roll = 0.0

    return tuple(float(np.degrees(angle)) for angle in (yaw, pitch, roll))
