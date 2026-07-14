# 视线检测系统 - 部署文档

## 一、环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04/24.04 或 CentOS 7+ |
| Docker | 20.10+ |
| 内存 | 8GB+（推荐16GB） |
| CPU | 4核+（推荐8核） |
| 网络 | 能访问内网RTSP摄像头和监居平台 |

## 二、部署步骤

### 2.1 安装Docker（如未安装）

```bash
# Ubuntu
sudo apt update
sudo apt install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker

# CentOS
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
```

### 2.2 上传文件

将以下文件上传到服务器 `/home/gaze_tracker/` 目录：

```
gaze_tracker/
├── *.pyc              # 编译后的程序文件
├── rooms.json         # 房间配置文件
├── Dockerfile         # Docker构建文件
├── requirements.txt   # Python依赖
├── models/            # 模型文件夹
│   └── face_landmarker.task
└── gaze-tracker.tar   # Docker镜像（如有）
```

### 2.3 加载Docker镜像

**方式一：如果有tar包**
```bash
cd /home/gaze_tracker
docker load -i gaze-tracker.tar
```

**方式二：如果没有tar包，现场构建**
```bash
cd /home/gaze_tracker
docker build -t gaze-tracker .
```

### 2.4 配置房间信息

编辑 `rooms.json`，配置摄像头和平台信息：

```json
{
    "global": {
        "ear_threshold": 0.2,
        "width": 640,
        "push_interval": 10,
        "api_url": "http://监居平台IP:8081",
        "username": "admin",
        "password": "admin123",
        "away_duration": 3.0,
        "drowsy_duration": 2.0
    },
    "rooms": [
        {
            "room_no": "房间号1",
            "device_id": "设备ID1",
            "rtsp_url": "rtsp://摄像头IP:端口/路径"
        },
        {
            "room_no": "房间号2",
            "device_id": "设备ID2",
            "rtsp_url": "rtsp://摄像头IP:端口/路径"
        }
    ]
}
```

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| api_url | 监居平台API地址 | http://192.168.1.90:8081 |
| username | 平台登录用户名 | admin |
| password | 平台登录密码 | admin123 |
| room_no | 房间号（从平台获取） | - |
| device_id | 设备ID（从平台获取） | - |
| rtsp_url | 摄像头RTSP地址 | - |
| push_interval | 告警推送间隔（秒） | 10 |
| ear_threshold | 闭眼检测阈值（越小越严格） | 0.2 |
| away_duration | 视线偏离触发时长（秒） | 3.0 |
| drowsy_duration | 困倦触发时长（秒） | 2.0 |

### 2.5 启动服务

```bash
cd /home/gaze_tracker

# 启动容器
docker run -d \
  --name gaze-tracker \
  --network host \
  --restart always \
  -v $(pwd)/rooms.json:/app/rooms.json \
  -e DEMO_PORT=8081 \
  gaze-tracker
```

**参数说明：**
- `--network host`：使用宿主机网络（必须，用于访问内网RTSP和平台）
- `--restart always`：开机自启
- `-v rooms.json`：挂载配置文件（修改后重启容器生效）
- `-e DEMO_PORT=8081`：Demo页面端口（可改为其他端口避免冲突）

## 三、验证部署

### 3.1 检查容器状态

```bash
# 查看容器是否运行
docker ps | grep gaze-tracker

# 查看日志
docker logs -f gaze-tracker
```

正常日志应显示：
```
Started room 002
Demo: http://0.0.0.0:8081
[002] Connected
```

### 3.2 访问Demo页面

浏览器打开：`http://服务器IP:8081`

应看到：
- 实时视频画面
- 视线方向（GAZE）
- 眼睛状态（EYE）
- 困倦检测（DROWSY）
- EAR值
- FPS等统计信息

### 3.3 检查告警推送

登录监居平台 `http://平台IP/rsdl`，查看告警列表是否有新记录。

## 四、常用命令

```bash
# 查看日志
docker logs -f gaze-tracker

# 停止服务
docker stop gaze-tracker

# 启动服务
docker start gaze-tracker

# 重启服务（修改rooms.json后需要重启）
docker restart gaze-tracker

# 进入容器调试
docker exec -it gaze-tracker /bin/bash

# 查看容器资源占用
docker stats gaze-tracker
```

## 五、修改配置

修改 `rooms.json` 后需要重启容器：

```bash
docker restart gaze-tracker
```

## 六、修改端口

如果默认端口8081被占用，修改启动命令：

```bash
docker run -d \
  --name gaze-tracker \
  --network host \
  --restart always \
  -v $(pwd)/rooms.json:/app/rooms.json \
  -e DEMO_PORT=9090 \
  gaze-tracker
```

然后访问 `http://服务器IP:9090`

## 七、多路摄像头

在 `rooms.json` 的 `rooms` 数组中添加多个房间：

```json
{
    "rooms": [
        {"room_no": "001", "device_id": "1", "rtsp_url": "rtsp://192.168.1.100:554/cam1"},
        {"room_no": "002", "device_id": "2", "rtsp_url": "rtsp://192.168.1.101:554/cam2"},
        {"room_no": "003", "device_id": "3", "rtsp_url": "rtsp://192.168.1.102:554/cam3"}
    ]
}
```

重启容器生效：
```bash
docker restart gaze-tracker
```

## 八、常见问题

### Q1: 容器启动后立即退出
```bash
docker logs gaze-tracker
```
查看错误日志，常见原因：
- rooms.json格式错误
- RTSP地址不可达
- 平台API地址不可达

### Q2: Demo页面没有画面
- 检查RTSP地址是否正确
- 检查服务器能否ping通摄像头IP
- 查看日志是否有"Connected"字样

### Q3: 没有告警推送到平台
- 检查api_url、username、password是否正确
- 检查room_no和device_id是否在平台注册
- 手动测试API连接：`curl http://平台IP:8081/auth/login`

### Q4: 检测不准确
- 调整 `ear_threshold`（默认0.2，增大则更难触发闭眼）
- 调整 `away_duration`（默认3秒，增大则需要更久才触发视线偏离）
- 调整 `drowsy_duration`（默认2秒，增大则需要更久才触发困倦）
- 确保摄像头角度正对人脸，光线充足

### Q5: CPU占用过高
- 降低 `width`（默认640，可改为480）
- 增加 `push_interval`（默认10秒，可改为15-20秒）

## 九、卸载

```bash
docker stop gaze-tracker
docker rm gaze-tracker
docker rmi gaze-tracker
rm -rf /home/gaze_tracker
```

## 十、技术支持

- GitHub: https://github.com/Mawenxuan1002/Gaze-Estimation
- 源码分支: `git checkout source-code`
