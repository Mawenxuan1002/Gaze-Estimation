# 视线检测服务部署文档

## 1. 服务概述

该服务基于 MediaPipe 和 OpenCV，支持多路 RTSP 视频流并发处理，可检测低头、视线偏离和困倦行为，并把持续异常推送到平台。

平台调用 `/analyze_start` 时，通过 `key` 动态传入 `roomNo` 和 `deviceId`。服务不会固定使用某个房间或设备编号。

## 2. 环境要求

| 项目 | 要求 |
|---|---|
| Docker | 20.10+，建议使用 Docker Compose v2 |
| 内存 | 至少 4 GB，每路流约需 500 MB |
| 磁盘 | 至少 5 GB |
| 网络 | 可访问 RTSP 摄像头和平台 API |

## 3. Docker Compose 部署

将完整项目放到服务器，按环境修改 `config/rooms.json`，然后执行：

```bash
docker compose up -d --build
docker compose logs -f
```

默认端口为 `8081`。需要修改宿主机端口时：

```bash
DEMO_PORT=8085 docker compose up -d
```

Compose 将宿主机的 `config/` 挂载到容器 `/app/config`。人工校准生成的 `config/calib_config.json` 也会自动生效。

## 4. 离线镜像部署

在有网络和 Docker 的构建机上执行：

```bash
# Linux
sh scripts/build.sh

# Windows
scripts\build.bat
```

将生成的 `gaze-tracker.tar` 和 `config/` 目录传到目标服务器：

```bash
docker load -i gaze-tracker.tar
docker run -d \
  --name gaze-tracker \
  --restart unless-stopped \
  -p 8081:8081 \
  -e TZ=Asia/Shanghai \
  -e API_URL=http://platform.example.com:8081 \
  -e GAZE_USERNAME=admin \
  -e GAZE_PASSWORD='<password>' \
  -v "$PWD/config:/app/config" \
  gaze-tracker
```

## 5. 配置

服务默认读取 `config/rooms.json`：

```json
{
  "global": {
    "head_down_ratio_delta": 0.10,
    "head_down_duration": 30.0,
    "head_down_side_yaw_start": 15.0,
    "head_down_side_yaw_full": 45.0,
    "head_down_side_threshold_scale": 0.50,
    "width": 640,
    "push_interval": 10,
    "api_url": "http://platform.example.com:8081",
    "username": "admin",
    "password": ""
  },
  "rooms": []
}
```

`rooms` 为空表示启动时不预加载固定视频流，等待平台动态调用 `/analyze_start`。可通过以下环境变量覆盖文件或平台连接参数：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEMO_PORT` | `8081` | HTTP 服务端口 |
| `GAZE_CONFIG` | `/app/config/rooms.json` | 配置文件 |
| `GAZE_CALIBRATION` | `/app/config/calib_config.json` | 校准文件 |
| `GAZE_MODEL` | `/app/models/face_landmarker.task` | 模型文件 |
| `API_URL` | 配置文件值 | 平台地址 |
| `GAZE_USERNAME` | 配置文件值 | 平台账号 |
| `GAZE_PASSWORD` | 配置文件值 | 平台密码 |

## 6. 平台接口

### 开始检测

```http
POST /analyze_start
Content-Type: application/json

{
  "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1",
  "key": "{\"roomNo\":\"002\",\"deviceId\":\"5\"}"
}
```

成功返回：

```json
{"code": 1, "msg": "Started", "startTime": "2026-08-04 10:00:00"}
```

### 停止检测

优先携带相同的 `key`，也可只通过 RTSP 地址查找：

```http
POST /analyze_end
Content-Type: application/json

{
  "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1",
  "key": "{\"roomNo\":\"002\",\"deviceId\":\"5\"}"
}
```

### 状态查询

```http
POST /analyze_status
Content-Type: application/json

{
  "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1",
  "key": "{\"roomNo\":\"002\",\"deviceId\":\"5\"}"
}
```

其他接口：

| 路径 | 用途 |
|---|---|
| `GET /health` | 全局健康状态 |
| `GET /api/rooms` | 活跃视频流列表 |
| `GET /demo` | 实时状态页面 |

## 7. 验证与运维

```bash
curl http://localhost:8081/health
curl http://localhost:8081/api/rooms
docker logs -f gaze-tracker
docker restart gaze-tracker
```

本地运行测试：

```bash
python -m unittest -v tests.test_behavior
python -m tools.test_head_down
```

`test_head_down` 需要摄像头和图形桌面。自动化测试不需要连接平台或摄像头。
