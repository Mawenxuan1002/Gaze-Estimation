# Gaze Tracker

基于 MediaPipe 和 OpenCV 的多路视频流视线、低头与困倦检测服务。平台通过 API 动态传入 RTSP 地址、`roomNo` 和 `deviceId`，检测到持续异常后向平台推送告警。

## 目录结构

```text
gaze_tracker/   服务、检测器、行为分析与推送代码
config/         运行配置及旧版配置参考
models/         MediaPipe 模型文件
tools/          摄像头校准和人工检测工具
tests/          自动化测试
docs/           部署文档和技术说明
scripts/        Docker 镜像构建脚本
assets/         调试示例图片
archives/       历史源码压缩包
```

根目录只保留项目入口文件、依赖和容器配置。

## 本地运行

要求 Python 3.10+。

```bash
pip install -r requirements.txt
python -m gaze_tracker
```

服务默认监听 `8081`：

- Demo：`http://localhost:8081/demo`
- 健康状态：`http://localhost:8081/health`
- 房间列表：`http://localhost:8081/api/rooms`

可用环境变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `DEMO_PORT` | `8081` | HTTP 服务端口 |
| `GAZE_CONFIG` | `config/rooms.json` | 服务配置文件 |
| `GAZE_CALIBRATION` | `config/calib_config.json` | 摄像头校准参数 |
| `GAZE_MODEL` | `models/face_landmarker.task` | MediaPipe 模型 |
| `API_URL` | 配置文件中的地址 | 平台 API 地址 |
| `GAZE_USERNAME` | 配置文件中的账号 | 平台账号 |
| `GAZE_PASSWORD` | 配置文件中的密码 | 平台密码 |

`config/rooms.json` 中的 `rooms` 可以为空。平台调用 `/analyze_start` 时，服务从请求的 `key` 动态解析 `roomNo` 和 `deviceId`，不会固定使用示例设备编号。

## 常用命令

```bash
# 运行自动化测试
python -m unittest -v tests.test_behavior

# 打开摄像头人工验证低头识别
python -m tools.test_head_down

# 生成个性化校准参数
python -m tools.calibrate --camera 0
```

校准文件 `config/calib_config.json` 属于设备本地数据，默认不提交 Git。

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

导出离线镜像：

```bash
# Windows
scripts\build.bat

# Linux
sh scripts/build.sh
```

生成的 `gaze-tracker.tar` 在目标服务器执行 `docker load -i gaze-tracker.tar` 后即可启动。完整步骤见 [部署文档](docs/DEPLOY.md)，算法说明见 [技术文档](docs/TECH_SPEC.md)。

## 平台启动示例

```http
POST /analyze_start
Content-Type: application/json

{
  "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1",
  "key": "{\"roomNo\":\"002\",\"deviceId\":\"5\"}"
}
```

同一房间可以有多个设备，服务内部使用 `roomNo~deviceId` 作为流标识。停止与状态查询接口详见部署文档。
