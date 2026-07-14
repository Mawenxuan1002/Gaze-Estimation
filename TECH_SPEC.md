# 视线追踪与睁眼状态识别系统 — 技术方案文档

> 版本: v1.0 | 日期: 2026-07-10 | 状态: 原型验证

---

## 1. 项目概述

### 1.1 功能目标

| 功能模块 | 描述 |
|---------|------|
| 视线方向检测 | 通过摄像头采集面部数据，分析虹膜位置判定用户是否注视屏幕 |
| 睁眼状态识别 | 监测眼睑开合程度，判断闭眼 / 打盹状态 |
| 困倦告警 | 基于 PERCLOS 指标进行多级告警 |

### 1.2 应用场景

- 驾驶员疲劳监测
- 工位注意力检测
- 在线考试监考
- 长时间办公健康提醒

---

## 2. 技术架构

### 2.1 系统架构图

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  USB Camera │───▶│  MediaPipe       │───▶│  GazeDetector   │
│  (30 FPS)   │    │  Face Mesh       │    │  ├─ EAR 计算     │
└─────────────┘    │  (478 landmarks) │    │  ├─ 虹膜定位     │
                   └──────────────────┘    │  ├─ 视线分类     │
                                           │  └─ PERCLOS 困倦 │
                                           └────────┬────────┘
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              ┌──────────┐   ┌──────────┐   ┌──────────┐
                              │ HUD 叠加  │   │ CSV 日志  │   │ 告警事件  │
                              │ 实时显示  │   │ 离线分析  │   │ 外部通知  │
                              └──────────┘   └──────────┘   └──────────┘
```

### 2.2 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 人脸检测 | MediaPipe Face Mesh | Google 预训练模型, 478 关键点含虹膜 |
| 图像处理 | OpenCV 4.x | 摄像头采集、图像预处理、HUD 绘制 |
| 数值计算 | NumPy | 向量化运算、距离计算 |
| 运行环境 | Python 3.10+ | 跨平台, CPU 实时推理 |

---

## 3. 核心算法

### 3.1 视线方向检测

#### 原理

MediaPipe Face Mesh 的 `refine_landmarks=True` 模式提供 10 个额外虹膜关键点:
- 左眼虹膜: landmark 468-472, 中心点 = **468**
- 右眼虹膜: landmark 473-477, 中心点 = **473**

通过计算虹膜中心相对眼睛边界的归一化位置判定视线方向。

#### 虹膜位置归一化

```
            上眼睑 (top)
               │
    左眼角 ────┼──── 右眼角
    (left)     │    (right)
               │
            下眼睑 (bottom)

iris_x = dist(left, iris) / dist(left, right)   # 水平: 0=最左, 1=最右
iris_y = dist(top,  iris) / dist(top,  bottom)   # 垂直: 0=最上, 1=最下
```

#### 方向分类阈值

| 方向 | 条件 | 阈值 |
|------|------|------|
| 左看 | iris_x < 0.42 | 可调 |
| 右看 | iris_x > 0.58 | 可调 |
| 上看 | iris_y < 0.38 | 可调 |
| 下看 | iris_y > 0.62 | 可调 |
| 正视 | 其他 | - |

### 3.2 Eye Aspect Ratio (EAR) 眼睛开合度

#### 公式

```
          ‖p₂ − p₆‖ + ‖p₃ − p₅‖
EAR  =  ────────────────────────────
                 2 × ‖p₁ − p₄‖

       p₂ ●───────────● p₁ (左眼角)
          │   ● p₃     │
          │   ● p₆     │
       p₅ ●───────────● p₄ (右眼角)
```

MediaPipe 关键点映射:

| 点位 | 左眼索引 | 右眼索引 | 位置 |
|------|---------|---------|------|
| p₁ | 33 | 263 | 外眼角 |
| p₂ | 159 | 386 | 上眼睑中 |
| p₃ | 153 | 380 | 上眼睑偏内 |
| p₄ | 133 | 362 | 内眼角 |
| p₅ | 145 | 374 | 下眼睑中 |
| p₆ | 154 | 381 | 下眼睑偏内 |

#### 阈值设定

| EAR 范围 | 眼睛状态 |
|----------|---------|
| > 0.25 | 正常睁眼 |
| 0.20 - 0.25 | 半闭合 (注意) |
| < 0.20 | 闭眼 |

### 3.3 PERCLOS 困倦检测

**PERCLOS** (Percentage of Eye Closure over Time) 是业界标准的困倦指标。

#### 计算方式

```
PERCLOS = 闭眼帧数 / 滑动窗口总帧数

滑动窗口 = 30 秒 (可调)
```

#### 告警等级

| 等级 | 条件 | 响应 |
|------|------|------|
| 0 - 正常 | PERCLOS < 20% | 无 |
| 1 - 注意 | PERCLOS 20%-40% 或连续闭眼 > 1秒 | 黄色提示 |
| 2 - 警告 | PERCLOS > 40% 或连续闭眼 > 2秒 | 红色告警 |

---

## 4. 模块设计

### 4.1 文件结构

```
gaze_tracker/
├── gaze_detector.py     # 核心检测引擎
│   ├── GazeTracker      # 主检测器类
│   ├── DrowsinessDetector  # 困倦检测器
│   └── 工具函数          # EAR、虹膜位置、方向分类
├── main.py              # 实时可视化应用
│   ├── HUD 绘制
│   ├── CSV 日志记录
│   └── 摄像头主循环
├── TECH_SPEC.md         # 本文档
└── outputs/             # 输出目录
    ├── session_*.csv    # 检测日志
    └── screenshot_*.png # 截图
```

### 4.2 核心类接口

```python
class GazeTracker:
    def __init__(self, max_faces=1, refine_landmarks=True,
                 min_detection_confidence=0.5, ear_threshold=0.20): ...
    def process_frame(self, frame_bgr: np.ndarray) -> FrameResult: ...
    def release(self): ...

@dataclass
class FrameResult:
    timestamp: float
    face_detected: bool
    gaze: GazeDirection          # LEFT / CENTER / RIGHT / UP / DOWN
    eye_state: EyeState          # OPEN / CLOSED
    ear: float                   # Eye Aspect Ratio
    iris_x: float                # 归一化水平 0-1
    iris_y: float                # 归一化垂直 0-1
    drowsy: bool                 # 是否困倦
    perclos: float               # PERCLOS 百分比
    alert_level: int             # 0/1/2
```

---

## 5. 使用说明

### 5.1 环境要求

```
Python >= 3.10
pip install opencv-python mediapipe numpy
```

### 5.2 启动命令

```bash
# 默认运行 (摄像头 0, 960px 宽)
python main.py

# 指定摄像头和分辨率
python main.py --camera 1 --width 1280

# 无头模式 (仅记录日志)
python main.py --headless --duration 300

# 调整闭眼阈值 (更敏感)
python main.py --ear-threshold 0.22
```

### 5.3 快捷键

| 按键 | 功能 |
|------|------|
| q | 退出 |
| s | 保存截图 |
| r | 重置统计 (TODO) |

### 5.4 输出文件

- **CSV 日志**: `outputs/session_YYYYMMDD_HHMMSS.csv`
  - 字段: timestamp, face_detected, gaze, eye_state, ear, iris_x, iris_y, perclos, alert_level, fps
- **截图**: `outputs/screenshot_NNNN.png`

---

## 6. 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 推理帧率 | ≥ 25 FPS | CPU i5 级别 |
| 视线精度 | ±5° | 中心区域检测 |
| 闭眼检测率 | > 95% | EAR 阈值 0.20 |
| 误报率 | < 5% | 正常眨眼不触发告警 |
| 延迟 | < 40ms | 单帧处理 |

---

## 7. 后续迭代方向

### 7.1 近期 (v1.1)
- [ ] 个人校准模式: 启动时让用户注视屏幕中心, 自动校准阈值
- [ ] 多人支持: max_faces > 1
- [ ] 声音告警: 困倦时播放提示音

### 7.2 中期 (v2.0)
- [ ] 深度学习视线估计: 使用 ETH-X Gaze 或 GazeNet 提升精度
- [ ] 3D 头部姿态估计: 结合 PnP 算法计算 yaw/pitch/roll
- [ ] 数据看板: Web 实时仪表盘

### 7.3 长期
- [ ] 多摄像头融合
- [ ] 边缘设备部署 (ONNX / TensorRT)
- [ ] 行为模式分析 (注意力热力图)

---

## 8. 参考文献

1. MediaPipe Face Mesh — https://google.github.io/mediapipe/solutions/face_mesh.html
2. Soukupová, T. & Čech, J. (2016). Real-Time Eye Blink Detection Using Facial Landmarks.
3. PERCLOS — NHTSA Drowsy Driver Detection Standard
4. Kazemi, V. & Sullivan, J. (2014). One Millisecond Face Alignment with an Ensemble of Regression Trees.
