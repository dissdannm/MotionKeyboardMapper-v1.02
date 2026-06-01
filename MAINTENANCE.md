# MotionKeyboardMapper 维护文档

> 体感游戏通用键盘映射服务 — 将身体动作映射为键盘事件

## 1. 项目结构

```
MotionKeyboardMapper/
├── launcher.py                    # GUI 按钮化启动器 (推荐入口)
├── main.py                        # CLI 入口 (web / local / dual 三种模式)
├── 启动器.bat                     # Windows 双击启动
├── requirements.txt               # Python 依赖
├── assets/models/
│   └── pose_landmarker_heavy.task # MediaPipe 姿态检测模型 (30MB)
│
├── config/
│   ├── settings.py                # 全局配置常量
│   └── profiles/                  # ★ 游戏映射档案 (JSON, 可热插拔)
│       └── naruto_fighting.json
│
├── camera/
│   └── sources.py                 # 摄像头管理 (本地 / IP / 双人)
│
├── pose/
│   └── estimator.py               # MediaPipe 姿态估计器 (33个关键点)
│
├── gesture/
│   ├── engine.py                  # ★ 手势识别引擎 (规则打分 + 冲突解决)
│   └── definitions/
│       └── standard.json          # ★ 手势定义库 (12种手势)
│
├── keyboard/
│   └── emitter.py                 # 键盘事件模拟 (pynput)
│
├── server/
│   └── app.py                     # FastAPI Web 控制面板 + SSE 推送
│
├── templates/
│   └── index.html                 # Web 控制面板前端
│
└── static/
    ├── style.css
    └── app.js
```

## 2. 核心架构

```
┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌────────────┐    ┌──────────┐
│ 摄像头源 │───→│ 姿态估计  │───→│  手势识别引擎 │───→│ 键盘发射器 │───→│ 目标游戏 │
│ 3种模式  │    │ MediaPipe │    │ 规则打分+冲突 │    │ pynput模拟 │    │          │
└──────────┘    └───────────┘    └──────────────┘    └────────────┘    └──────────┘
                                      ↑     ↑
                           gesture/definitions/   config/profiles/
                           standard.json          naruto_fighting.json
                           (手势定义→规则)        (手势ID→按键映射)
```

**三层解耦：**

| 层 | 文件 | 职责 | 维护方式 |
|----|------|------|---------|
| 手势定义层 | `gesture/definitions/standard.json` | 定义如何从33个关键点识别手势 | 编辑 JSON，无需改 Python |
| 映射配置层 | `config/profiles/*.json` | 定义手势→键盘按键的对应关系 | 新增/编辑 JSON 文件 |
| 执行引擎层 | `gesture/engine.py` + `keyboard/emitter.py` | 规则评估、冲突解决、按键发射 | 修改 Python 代码 |

## 3. 三个摄像头源

| 模式 | camera_type | 说明 |
|------|-------------|------|
| 本地摄像头 | `local` | 笔记本内置或 USB 外接摄像头，通过 index 选择 (0, 1, 2...) |
| IP 摄像头 | `ip` | 手机安装 IP Webcam / DroidCam App，通过 HTTP 地址传输 |
| 双人模式 | `dual` | 同时打开两个摄像头，左右站位分别对应玩家 1/2 |

**手机充当摄像头的方法：**
1. 手机和电脑连接到同一 WiFi
2. 手机安装 "IP Webcam" App，开启后显示 URL 如 `http://192.168.1.5:8080/video`
3. 在 GUI 中选择 "IP 摄像头 (手机)"，填入该 URL

## 4. 手势识别原理

### 4.1 MediaPipe 33 关键点

```
        0 nose
      /         \
    11 L_shoulder  12 R_shoulder
      |              |
    13 L_elbow      14 R_elbow
      |              |
    15 L_wrist      16 R_wrist
      |              |
    23 L_hip        24 R_hip
      |              |
    25 L_knee       26 R_knee
      |              |
    27 L_ankle      28 R_ankle
```

每个关键点包含 `(x, y, z, visibility)` — 归一化坐标。

### 4.2 手势定义格式 (standard.json)

```json
{
  "gestures": {
    "手势ID": {
      "name": "中文名称",
      "type": "pose | motion",
      "hold_frames": 3,
      "rules": [
        {
          "id": "规则唯一标识",
          "type": "angle_range | relative_position | relative_height | distance_ratio",
          "points": ["point_a", "point_b", "point_c"],
          "min": 0, "max": 180,
          "weight": 0.5,
          "description": "规则描述"
        }
      ],
      "conflict_group": "组名"
    }
  }
}
```

### 4.3 四种规则类型

| 规则类型 | 参数 | 用途 | 示例 |
|---------|------|------|------|
| `angle_range` | points[3], min, max | 三点夹角是否在范围内 | 肘关节角度判断出拳 |
| `relative_position` | point_a, point_b, axis, threshold, operator | 两点在指定轴上的位置比较 | 手腕在肩膀前方 (z轴) |
| `relative_height` | point_a, point_b, threshold, operator | 两点的 y 坐标比较 | 手腕高于鼻子 |
| `distance_ratio` | point_a, point_b, ref_a, ref_b, min_ratio | 两组点对的距离比值 | 脚距 > 肩距判断侧步 |

### 4.4 识别流程

```
每帧进来:
  1. 对手势定义中所有启用的手势——逐条规则打分 (0.0~1.0)
  2. 按规则 weight 加权求平均 → 手势得分
  3. conflict_group 内只保留得分最高的手势 (mutual exclusion)
  4. 得分 ≥ score_threshold (0.55) → hold_count++
  5. hold_count ≥ hold_frames → 手势触发
```

## 5. 如何添加新动作（手势）

编辑 `gesture/definitions/standard.json`，在 `"gestures"` 对象中添加：

```json
"my_new_gesture": {
  "name": "新动作名称",
  "type": "pose",
  "hold_frames": 2,
  "rules": [
    {
      "id": "rule_example",
      "type": "angle_range",
      "points": ["left_shoulder", "left_elbow", "left_wrist"],
      "min": 80,
      "max": 120,
      "weight": 0.6,
      "description": "左臂弯曲约90度"
    }
  ],
  "conflict_group": "arm_action"
}
```

**可用的关键点名称见第 4.1 节（33 个点），或查阅 `pose/estimator.py` 的 `KEYPOINT_NAMES` 字典。**

## 6. 如何添加新游戏映射

在 `config/profiles/` 下新建一个 `.json` 文件：

```json
{
  "profile_id": "street_fighter",
  "profile_name": "街头霸王",
  "description": "体感动作 → 键盘映射",
  "version": "1.0.0",
  "player_count": 1,
  "mappings": [
    {
      "gesture_id": "right_punch",
      "gesture_name": "右手直拳",
      "key": "j",
      "hold": false,
      "description": "右臂前刺出拳 → 轻拳"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `gesture_id` | 必须在 `standard.json` 的 gestures 中存在 |
| `key` | 键盘键名 (a-z, 0-9, space, enter, esc, f1-f12 等) |
| `hold` | true = 按住不放，false = 单次点击 |

**不需要重启应用** — Web 面板和 GUI 启动器会自动扫描 `profiles/` 目录。

## 7. 配置参数说明 (config/settings.py)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `camera_type` | `"local"` | 摄像头模式 |
| `camera_index` | `0` | 本地摄像头设备编号 |
| `ip_camera_url` | `""` | IP 摄像头完整 URL |
| `camera_index_2` | `1` | 双人模式第二个摄像头 |
| `camera_width/height` | `640/480` | 分辨率 |
| `model_path` | `""` | 留空则用内置模型 |
| `num_poses` | `1` | 同时检测人数 |
| `profile` | `"naruto_fighting"` | 默认映射档案 |
| `cooldown_ms` | `300` | 同键冷却时间 (防连发) |
| `hold_mode` | `true` | true=按住, false=点击 |
| `web_port` | `8888` | Web 面板端口 |

## 8. 四种运行方式

| 方式 | 命令 | 适用场景 |
|------|------|---------|
| GUI 启动器 | 双击 `启动器.bat` | 日常使用，按钮操作 |
| 本地桌面 | `python main.py local --camera 0` | 调试，看 OpenCV 窗口 |
| Web 面板 | `python main.py web` | 远程控制，浏览器操作 |
| 双人对战 | `python main.py dual` | 两个摄像头双人 |

## 9. 调试技巧

1. **验证摄像头可用**: 确认 Windows 相机应用能正常打开摄像头
2. **确认 MediaPipe 加载成功**: 启动时会打印 `[Pose] 姿态估计器已就绪`
3. **手势不灵敏**: 降低 `score_threshold`（GestureEngine 构造参数，默认 0.55）
4. **按键连发太快**: 增大 `cooldown_ms` 值
5. **站立姿态**: 保持身体在摄像头画面中，关键点 visibility > 0.5 才会被处理
6. **光照条件**: 确保环境光线充足，避免逆光

## 10. 依赖清单

```
mediapipe>=0.10.0    # 姿态检测
opencv-python>=4.8.0  # 摄像头 + 画面渲染
pynput>=1.7.0        # 键盘模拟
fastapi>=0.100.0     # Web 服务器
uvicorn>=0.23.0      # ASGI 服务器
numpy>=1.24.0        # 数值计算
```

Python 版本要求: ≥ 3.10 (推荐 3.12)
