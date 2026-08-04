# 视线检测服务技术说明

## 1. 系统职责

服务读取本地配置或平台动态下发的 RTSP 视频流，使用 MediaPipe Face Landmarker 提取人脸关键点，并完成以下检测：

- 视线方向和注意力偏离
- 低头及左右侧低头
- 闭眼和困倦
- 持续异常行为计时
- 平台认证和告警推送

平台请求中的 `key` 包含 `roomNo` 和 `deviceId`。二者共同组成流标识，服务不固定绑定示例房间。

## 2. 处理流程

```text
平台启动请求
  -> 解析 roomNo/deviceId 与 RTSP 地址
  -> 创建 StreamWorker
  -> GazeTracker 提取单帧指标
  -> BehaviorAnalyzer 维护跨帧状态
  -> 生成告警事件
  -> ResultPusher 异步推送平台
```

每个视频流拥有独立的工作线程、检测器和行为状态。告警事件由 worker 中的唯一行为分析器产生，pusher 只接收并推送已经生成的事件，避免同一帧被第二个状态机重新校准。

## 3. 目录结构

```text
gaze_tracker/
├── gaze_tracker/
│   ├── detector.py      # MediaPipe 检测和帧指标
│   ├── head_pose.py     # 头部姿态计算
│   ├── pusher.py        # 行为分析与平台推送
│   ├── worker.py        # 单路 RTSP 工作线程
│   ├── server.py        # HTTP API 与 Demo
│   ├── identity.py      # 平台 key 解析和流标识
│   ├── paths.py         # 配置、校准和模型路径
│   └── main.py          # 服务入口
├── config/              # 运行配置
├── models/              # MediaPipe 模型
├── tools/               # 人工测试与校准工具
├── tests/               # 自动化测试
├── docs/                # 文档
└── scripts/             # Docker 构建脚本
```

## 4. 核心数据

`GazeTracker.process_frame()` 返回帧级结果，主要包含：

| 字段 | 含义 |
|---|---|
| `face_detected` | 是否检测到人脸 |
| `gaze` | 当前视线方向 |
| `eye_state` | 睁眼或闭眼状态 |
| `ear` | 眼睛纵横比 |
| `head_down_ratio` | 低头相关几何指标 |
| `yaw` | 相对校准基线的左右偏转角 |
| `alert_level` | 当前帧检测等级 |

行为分析器使用连续帧更新基线和持续时间。低头默认持续 30 秒才产生告警；侧脸时根据相对 yaw 对阈值进行补偿，以覆盖左侧低头和右侧低头。

## 5. 配置

运行配置位于 `config/rooms.json`。常用参数：

| 参数 | 说明 |
|---|---|
| `head_down_ratio_delta` | 低头指标相对正视基线的变化阈值 |
| `head_down_duration` | 低头持续告警时间，默认 30 秒 |
| `head_down_side_yaw_start` | 开始进行侧脸补偿的 yaw |
| `head_down_side_yaw_full` | 达到最大侧脸补偿的 yaw |
| `head_down_side_threshold_scale` | 最大侧脸情况下的阈值比例 |
| `width` | 输入帧处理宽度 |
| `push_interval` | 同类告警最短推送间隔 |
| `api_url` | 平台 API 根地址 |

检测器会在启动初期采集正视数据作为个人基线。人工测试时应先正视摄像头完成校准，再分别测试正面低头、左侧低头和右侧低头。

## 6. 运行与验证

```bash
# 启动服务
python -m gaze_tracker

# 自动化测试
python -m unittest -v tests.test_behavior

# 摄像头人工验证
python -m tools.test_head_down

# 五点视线校准
python -m tools.calibrate --camera 0
```

人工摄像头工具需要图形桌面。自动化测试使用合成帧级数据，不需要连接摄像头或平台。

## 7. HTTP API

| 方法与路径 | 用途 |
|---|---|
| `POST /analyze_start` | 启动平台指定的视频流 |
| `POST /analyze_end` | 停止视频流 |
| `POST /analyze_status` | 查询流状态 |
| `GET /api/rooms` | 查询所有活动流 |
| `GET /health` | 查询服务健康状态 |
| `GET /demo` | 打开实时状态页面 |

请求示例和 Docker 部署方式见 [DEPLOY.md](DEPLOY.md)。
