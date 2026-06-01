# 🎮 MotionKeyboardMapper

> 体感游戏通用键盘映射服务 —— 把身体动作变成键盘按键

[![Version](https://img.shields.io/badge/version-v1.02--final-e94560)](https://github.com/dissdannm/MotionKeyboardMapper-v1.02/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ✨ 简介

通过摄像头捕捉**全身姿态动作**，实时映射为键盘事件，让任何 PC 游戏都能用身体来玩。

- 🥊 **右直拳** → K 键普攻
- 👐 **双手举过头顶** → J 键大招
- 🏃 **向前大步走** → W 键前进
- ⬇️ **下蹲** → R 键通灵
- 🔄 **左右侧身** → 空格键替身
- 🦘 **原地跳** → E 键密卷

> 💡 以上为「火影忍者格斗」预设，支持**自定义任意动作→任意按键**映射

## 📦 设备要求

| 项目 | 最低要求 |
|------|---------|
| 🖥️ 操作系统 | Windows 10 / 11 (64-bit) |
| 📷 摄像头 | USB 摄像头 / 笔记本内置 / 手机 IP 摄像头 |
| 💾 硬盘空间 | 300 MB |
| 🧠 内存 | 4 GB RAM |
| ⚡ CPU | Intel i5 第8代 或同等性能 (需支持 AVX2) |
| 🌐 网络 | 无需联网 (手机摄像头模式需同 WiFi) |

## 🚀 快速开始

### 方式一：直接运行 (无需 Python)

1. 从 [Releases](https://github.com/dissdannm/MotionKeyboardMapper-v1.02/releases) 下载 `MotionKeyboardMapper.exe`
2. 双击运行
3. 选择摄像头 → 选择游戏档案 → 点击「启动服务」
4. 打开游戏，开始用身体玩！

### 方式二：源码运行

```bash
git clone https://github.com/dissdannm/MotionKeyboardMapper-v1.02.git
cd MotionKeyboardMapper-v1.02
pip install -r requirements.txt
python launcher.py
```

## 🎯 摄像头支持

| 模式 | 说明 |
|------|------|
| 🖥️ 本地摄像头 | 笔记本内置或 USB 外接 |
| 📱 IP 摄像头 | 手机安装 IP Webcam App，同 WiFi 下传输 |
| 👥 双人模式 | 两个摄像头同时接入，左右站位分别对应 P1/P2 |

## 🛠️ 自定义动作

内置图形化编辑器，无需写代码：

1. 点击「编辑配置」
2. 勾选指标 + 拖滑块调整阈值
3. 选择映射按键
4. 保存 → 立即生效

## 📁 项目结构

```
MotionKeyboardMapper/
├── launcher.py          # GUI 启动器
├── editor.py            # 动作/档案编辑器
├── main.py              # CLI 入口
├── analysis/            # 分层分析引擎
│   ├── angle_calculator.py    # 10个关节角度
│   ├── alignment_analyzer.py  # 10个力线偏移
│   ├── temporal_analyzer.py   # 时序速度追踪
│   ├── noise_filter.py        # 5帧滑动平均
│   └── rule_engine.py         # 阈值判定
├── actions/             # 动作定义 (JSON)
├── config/profiles/     # 按键映射档案 (JSON)
├── pose/                # MediaPipe 姿态估计
├── camera/              # 摄像头管理
└── keyboard/            # pynput 键盘模拟
```

## 🔧 技术栈

| 层 | 技术 |
|----|------|
| 姿态检测 | Google MediaPipe (33 关键点) |
| 摄像头 | OpenCV |
| 键盘模拟 | pynput |
| GUI | Tkinter |
| 打包 | PyInstaller |

## 📝 License

MIT
