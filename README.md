# 视线检测系统 - 平台对接文档

## 项目信息
- **日期**: 2026-07-13
- **目录**: C:\Users\29733\Documents\Codex\2026-07-10\codex-3\work\gaze_tracker
- **Python**: C:\Users\29733\AppData\Local\Programs\Python\Python310\python.exe

---

## 一、系统架构

```
RTSP摄像头 → 视线检测程序 → 行为分析 → 推送告警 → 监居平台
                ↓
           Web可视化界面 (localhost:5000)
```

---

## 二、文件清单

| 文件 | 功能 |
|------|------|
| main.py | 主程序（命令行模式） |
| web_viewer.py | Web可视化界面 |
| gaze_detector.py | 视线检测核心算法 |
| result_pusher.py | 平台告警推送模块 |
| gaze_calibrate.py | 校准工具 |
| config.json | 配置文件 |
| gaze_trail.py | 视线轨迹追踪 |

---

## 三、平台接入

### 3.1 平台信息
- **平台地址**: http://192.168.1.90/rsdl (智慧看管研判系统)
- **API网关**: http://192.168.1.90:8081
- **登录账号**: admin / admin123

### 3.2 关键接口

#### 登录认证
```
POST http://192.168.1.90:8081/auth/login
Body: {"username":"admin", "password":"admin123"}
Response: {"code":200, "data":{"access_token":"eyJ...", "expires_in":1440}}
```

#### 告警推送（核心接口）
```
POST http://192.168.1.90:8081/wuyu-statistics/statistics/electronLog/result
Authorization: Bearer {token}
Content-Type: application/json

{
    "key": "{\"roomNo\":\"002\",\"deviceId\":\"5\"}",
    "psychology": {
        "psychologyDescription": "无",
        "emotionalState": "正常"
    },
    "behavior": {
        "behaviorDescription": "持续向左方向偏视 (5秒)",
        "behaviorType": "视线偏离",
        "severity": "高"
    },
    "startTime": "2026-07-13 10:30:00",
    "endTime": "2026-07-13 10:30:05"
}
```

#### 响应示例
```json
{"code": 200, "msg": "获取模型分析结果成功"}
```

### 3.3 设备配置
- **房间号**: roomNo = "002"
- **设备ID**: deviceId = "5"
- **说明**: 必须使用平台已注册的房间和设备，否则推送失败

---

## 四、推送策略

### 4.1 行为类型
| behaviorType | 说明 | 触发条件 |
|--------------|------|----------|
| 困倦瞌睡 | 闭眼/打盹 | EAR < 阈值持续2秒 |
| 视线偏离 | 注意力分散 | 视线偏离中心持续3秒 |

### 4.2 推送规则
- **推送间隔**: 10秒（可通过config.json调整）
- **严重程度**: severity = "高"（会触发告警）
- **不推送**: 未检测到人脸（避免误报）

---

## 五、配置文件

### config.json
```json
{
    "rtsp": "rtsp://192.168.1.97:8554/live/wykj001",
    "width": 640,
    "earThreshold": 0.2,
    "apiUrl": "http://192.168.1.90:8081",
    "username": "admin",
    "password": "admin123",
    "pushInterval": 10,
    "roomNo": "002",
    "deviceId": "5",
    "awayDuration": 3.0,
    "drowsyDuration": 2.0
}
```

### 参数说明
| 参数 | 默认值 | 说明 |
|------|--------|------|
| rtsp | - | RTSP摄像头地址 |
| width | 640 | 画面宽度（降低可提升性能） |
| earThreshold | 0.2 | 闭眼检测阈值（越小越难触发） |
| pushInterval | 10 | 推送间隔(秒) |
| awayDuration | 3.0 | 视线偏离持续时间阈值(秒) |
| drowsyDuration | 2.0 | 困倦持续时间阈值(秒) |

---

## 六、运行方式

### 6.1 Web可视化模式（推荐）
```bash
python web_viewer.py
```
- 访问地址: http://localhost:5000
- 局域网访问: http://192.168.1.108:5000
- 功能: 实时画面 + 状态显示 + 自动推送

### 6.2 命令行模式
```bash
python main.py
```

### 6.3 手动校准（可选）
```bash
python gaze_calibrate.py
```
- 注视屏幕5个点各3秒
- 生成 calib_config.json

---

## 七、平台查看告警

1. 打开 http://192.168.1.90/rsdl
2. 登录（admin/admin123）
3. 进入"告警列表"
4. 查看最新告警记录

---

## 八、代码修改记录

### 8.1 result_pusher.py
- 修改API端点: `/system/` → `/wuyu-statistics/statistics/electronLog/result`
- 添加JWT认证（Bearer Token）
- 修改数据格式: 包装为 {key, psychology, behavior, startTime, endTime}
- 移除"未检测到人脸"推送

### 8.2 main.py
- 添加RTSP流支持（--rtsp参数）
- 添加config.json自动加载
- 添加RTSP自动重连
- 添加错误处理

### 8.3 web_viewer.py（新建）
- Flask Web服务器
- 实时视频流显示
- 状态统计（FPS/推送次数）
- 自动重连和错误处理

### 8.4 config.json
- 添加RTSP地址
- 添加推送参数
- 添加检测阈值

---

## 九、常见问题

### Q1: 推送后平台看不到告警
A: 检查roomNo和deviceId是否为平台已注册设备（002/5可用）

### Q2: 读取帧失败
A: RTSP流不稳定，程序会自动重连；降低width到640可改善

### Q3: 误报太多
A: 调高earThreshold（如0.25）或增大drowsyDuration

### Q4: ping不通本机
A: 防火墙已关闭，直接用浏览器访问http://192.168.1.108:5000
