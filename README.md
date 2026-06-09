# boss-autoapply

真机端自动筛选 + 半自动投递 Boss 直聘的自动求职系统。设备控制与 Web 控制台对齐 [AutoGLM-GUI](https://github.com/suyiiyii/AutoGLM-GUI)：adb 原语 + 可插拔双后端（控件树 / 视觉）+ scrcpy 投屏 + Web Terminal。

> 完整设计见 `.omc/plans/boss-autoapply-plan.md`（经 6 轮 consensus 评审定稿）。

## 架构要点

- **执行层**：adb 原语（`input tap/swipe/motionevent` + `exec-out screencap` + ADBKeyboard）+ 可插拔双后端（`uia_backend` 控件树主用 / `vision_backend` gpt-5.5 多模态兜底）。
- **决策权威**：pipeline 唯一（`screener` 阈值 → `dispatcher` 幂等状态机 + `RateLimiter`）；分层 agent 的 `planner` 仅受限单步执行器，无业务决策权、不旁路。
- **半自动边界**：自动筛选+投递+打招呼；HR 回复经 `inbox_watcher` 常驻巡检 → 转人工接管（系统不自动续聊）。
- **安全**：所有控制端点（terminal/control/scrcpy/SSE）统一 localhost + token + Origin 鉴权；adb 白名单仅纵深防御；手动操控与 Terminal 仅 MANUAL 模式放行。
- **设备**：仅真机（已 root，标准 adb），默认 USB 连接。

## 开发

### 后端（uv）

```bash
cd backend
uv sync --extra dev          # 安装依赖
cp .env.example .env         # 填入 GPT_API_KEY
# 开发（不连真机，可热重载）
uv run uvicorn app.main:asgi_app --reload --host 127.0.0.1 --port 8000
# ⚠️ 真机联调（Windows）必须去掉 --reload：
#    uvicorn --reload 在 Windows 用 multiprocessing spawn 的 worker 子进程，
#    其内部 subprocess 调 adb 拿不到设备，会导致设备/scrcpy/投递全部不可用。
uv run uvicorn app.main:asgi_app --host 127.0.0.1 --port 8000
uv run pytest                # 单元测试
```

### 前端（pnpm）

```bash
cd frontend
pnpm install
pnpm dev
```

### 真机准备（M0 / M0.5）

```bash
adb devices                  # 确认真机 USB 在线
# M0.5 三探针闸门（控件可得率 / 视觉命中成本 / input 反检测）
uv run python -m app.probe.probe_backends --device <serial>
```

## 状态

第一波：后端骨架 + 核心可测逻辑 + 单测 + 前端脚手架（**真机相关代码就绪，待接设备验证**）。
