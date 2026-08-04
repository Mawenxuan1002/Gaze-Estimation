# 视线检测服务部署文档

## 一、服务概述

基于 MediaPipe FaceMesh 的视线方向检测和困倦识别服务，支持多路视频流并发处理，检测结果自动推送到监居平台。

**检测能力：**
- 视线方向：左/右/上/下/中心
- 困倦瞌睡：基于 EAR（眼睛纵横比）判断
- 告警类型：视线偏离、困倦瞌睡

---

## 二、环境要求

| 项目 | 要求 |
|------|------|
| Docker | 20.10+ |
| 内存 | ≥ 4GB（每路流约 500MB） |
| 磁盘 | ≥ 5GB（镜像约 2.2GB） |
| 网络 | 能访问摄像头 RTSP 流和监居平台 |

---

## 三、部署步骤

### 3.1 导入镜像

```bash
# .tar.gz 格式
gunzip -c gaze-tracker-v3.tar.gz | docker load

# .tar 格式
docker load -i gaze-tracker-v3.tar
```

### 3.2 启动容器

```bash
docker run -d \
  --name gaze-tracker \
  --network host \
  -e DEMO_PORT=8085 \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  gaze-tracker:v3 python multi_stream.py
```

**环境变量说明：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DEMO_PORT | 8081 | Web Demo 和 API 端口 |
| TZ | UTC | 时区，建议设为 Asia/Shanghai |

### 3.3 验证服务

```bash
# 查看容器状态
docker ps | grep gaze-tracker

# 查看日志
docker logs -f gaze-tracker

# 测试 API
curl http://localhost:8085/api/rooms
```

---

## 四、API 接口

### 4.1 开始检测

```
POST http://IP:8085/analyze_start
Content-Type: application/json

{
    "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1",
    "key": "{\"roomNo\":\"001\",\"deviceId\":\"2\"}"
}
```

**返回：**
```json
{"code": 1, "msg": "Started"}
```

### 4.2 结束检测

```
POST http://IP:8085/analyze_end
Content-Type: application/json

{
    "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1"
}
```

**返回：**
```json
{"code": 1, "msg": "Stopped"}
```

### 4.3 状态查询

```
POST http://IP:8085/analyze_status
Content-Type: application/json

{
    "rtspUrl": "rtsp://camera.example.com/live/camera_1_ch1"
}
```

**返回：**
```json
{"code": 1, "msg": "running", "room_no": "001"}
```

### 4.4 查看所有房间

```
GET http://IP:8085/api/rooms
```

### 4.5 返回格式

| code | 含义 |
|------|------|
| 1 | 成功 |
| 0 | 失败，msg 字段为失败原因 |

**失败示例：**
```json
{"code": 0, "msg": "缺少摄像头地址或房间参数"}
{"code": 0, "msg": "房间未找到"}
```

---

## 五、平台接入

将监居平台的"开始检测"/"结束检测"接口地址改为：

| 功能 | 接口地址 |
|------|----------|
| 开始检测 | `http://服务器IP:8085/analyze_start` |
| 结束检测 | `http://服务器IP:8085/analyze_end` |
| 状态查询 | `http://服务器IP:8085/analyze_status` |

参数格式不变，与原分析服务一致。

---

## 六、告警推送

检测到异常时自动推送到平台：

| 告警类型 | 行为类型 | 触发条件 |
|----------|----------|----------|
| 视线偏离 | 持续向左/右/上/下方向偏视 | 超过 3 秒 |
| 困倦瞌睡 | 眼睛闭合持续时间过长 | 超过 2 秒 |

推送接口：`POST http://平台地址/wuyu-statistics/statistics/electronLog/result`

---

## 七、Web Demo

浏览器访问：`http://服务器IP:8085/demo`

功能：
- 实时视频画面
- 视线方向 HUD 显示
- 困倦状态指示
- FPS 和帧数统计

---

## 八、常用运维命令

```bash
# 查看日志
docker logs -f gaze-tracker

# 重启容器
docker restart gaze-tracker

# 停止容器
docker stop gaze-tracker

# 启动容器
docker start gaze-tracker

# 进入容器
docker exec -it gaze-tracker bash

# 查看房间状态
curl http://localhost:8085/api/rooms
```

---

## 九、配置调优

在 `rooms.json` 的 `global` 中可调整：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| ear_threshold | 0.2 | EAR 阈值，越小越不容易触发困倦告警 |
| push_interval | 10 | 告警推送间隔（秒） |
| away_duration | 3.0 | 视线偏离触发时长（秒） |
| drowsy_duration | 2.0 | 困倦触发时长（秒） |
| width | 640 | 视频处理宽度 |

---

## 十、多房间示例

```bash
# 房间1
curl -X POST http://localhost:8085/analyze_start \
  -H "Content-Type: application/json" \
  -d '{"rtspUrl":"rtsp://camera.example.com/live/camera_1_ch1","key":"{\"roomNo\":\"001\",\"deviceId\":\"2\"}"}'

# 房间2
curl -X POST http://localhost:8085/analyze_start \
  -H "Content-Type: application/json" \
  -d '{"rtspUrl":"rtsp://camera.example.com/live/camera_2_ch1","key":"{\"roomNo\":\"002\",\"deviceId\":\"3\"}"}'

# 房间3
curl -X POST http://localhost:8085/analyze_start \
  -H "Content-Type: application/json" \
  -d '{"rtspUrl":"rtsp://camera.example.com/live/camera_3_ch1","key":"{\"roomNo\":\"003\",\"deviceId\":\"4\"}"}'
```
