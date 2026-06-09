# Boss 直聘真机联调方案

**最后更新**：2026-06-09  
**适用版本**：v6（consensus 批准）  
**对象**：已 root 安卓真机的端到端投递联调

本文档提供从硬件准备、三探针验证、后端启动到完整投递流程的可操作指南。

---

## 前置准备

### 1.1 硬件与系统要求

- **真机**（不用模拟器）：Android 8.0 以上，已获得 root 权限
- **开发者选项**：设置 → 关于手机 → 连续点击"版本号"七次开启开发者选项
- **USB 调试**：开发者选项 → USB 调试 ✓ 打开；USB 配置 ✓ 选择"文件传输(MTP)"
- **ADB 连接**：PC 通过 USB 连接，运行 `adb devices` 确认设备在线（显示 `device` 而非 `offline`）
- **输入法**：安装 [ADBKeyboard](https://github.com/senzhk/ADBKeyboard/releases)（用于模拟打字输入），设为默认输入法
  - `adb install app/adb/resources/ADBKeyboard.apk`
  - 进入系统输入法设置，选 ADBKeyboard 为默认
- **设备指纹记录**（重要）：运行 `adb shell getprop ro.build.fingerprint`，记录输出；打补丁时需对比
  - 如有关键 CVE（如 CVE-2026-0073），优先应用对应补丁

### 1.2 PC 环境准备

```bash
# 后端环境
cd backend
uv sync --extra dev    # 安装含测试依赖的环境

# 前端环境
cd ../frontend
pnpm install           # 或 npm install
```

### 1.3 验证 adb 连接

```bash
adb devices
# 预期输出：
# List of attached devices
# <YOUR_DEVICE_SERIAL>   device
```

如果显示 `offline`：
- 检查设备 USB 调试是否开启
- 重新插拔 USB，在设备上点击"信任此计算机"
- 运行 `adb kill-server && adb devices` 重试

---

## M0.5：三探针闸门与 go/no-go 判定

**目的**：前置验证真机是否满足两个基本条件：
1. 控件树（uiautomator2）是否可用
2. 视觉后端（gpt-5.5 多模态）是否可用
3. input 注入（adb shell input tap）是否被风控检测

### 2.1 运行三探针

在 Boss 直聘 App 已打开、位于首屏推荐列表的前提下：

```bash
cd backend
uv run python -m app.probe.probe_backends --device <YOUR_DEVICE_SERIAL> --samples 5
```

例如：
```bash
uv run python -m app.probe.probe_backends --device emulator-5554 --samples 5
```

### 2.2 探针说明

**探针 1：控件树可得率**
- 执行 `uiautomator2` 的 `dump_hierarchy()`，抽取 5 次样本
- 统计关键字段（resourceId / text / content-desc）非空的节点占比
- **判据**：≥80% 为绿灯，50–80% 为黄灯，<50% 为红灯

**探针 2：视觉后端命中率 + 成本**
- 对 3 个固定目标（搜索框、推荐 Tab、导航栏）进行 gpt-5.5 多模态定位
- 记录命中率、平均 token 消耗
- **判据**：≥85% 命中 + 平均 token ≤ 800 为绿灯

**探针 3：input 反检测**
- 向屏幕中央发送 3 次 `adb shell input tap`，每次间隔 0.8s
- 观测 App 前台包名是否切换到验证相关包（captcha / verify / geetest 等）
- **判据**：未检测到验证包为绿灯

### 2.3 go/no-go 判读

探针执行后输出判断结果，以下任一条件可接受：

| 场景 | 控件树 | 视觉 | input | 结论 | 后续 |
|------|-------|------|-------|------|------|
| 理想 | ≥80% | N/A | 无 | **GO** | 使用控件树主 + 视觉兜底 |
| 降级 | 50–80% | N/A | 无 | **GO** | 使用双后端（自动切换） |
| 视觉替代 | <50% | ≥85% | 无 | **GO** | 视觉主（成本升，建议复议） |
| **阻断** | <50% | <85% | — | **NO-GO** | 检查设备 / uia 服务 / LLM 配置后重试 |
| **特殊** | — | — | 被检测 | **NO-GO** | 触发风控，需启用 root sendevent（Follow-up） |

**示例输出**（GO）：
```
[探针] 目标设备: emulator-5554，采样次数: 5
[探针1] 控件树可得率...
  dump 成功: 5/5，关键字段率: 85.3%

[探针2] 视觉后端命中率...
  命中: 3/3，avg tokens≈650

[探针3] input 反检测...
  检测触发: False，前台包未变化 (com.boss.app)，input tap 未触发明显检测

[结论] GO — 推荐主后端: uia
```

如需保存 JSON 报告以便后续对比：
```bash
uv run python -m app.probe.probe_backends --device <SERIAL> --json probe_report.json
```

---

## M1：后端与基础设施

### 3.1 scrcpy-server 准备

scrcpy 用于实时投屏。下载 scrcpy-server jar 并放到固定位置：

```bash
# 下载 scrcpy-server（版本需与前端解码器兼容，推荐 2.2.x）
# 访问 https://github.com/Genymobile/scrcpy/releases
# 下载 scrcpy-server-v2.2.1 (或同版本)

# 放置到项目目录
mkdir -p backend/app/scrcpy/resources
cp /path/to/scrcpy-server backend/app/scrcpy/resources/

# 验证文件存在
ls -la backend/app/scrcpy/resources/scrcpy-server
```

### 3.2 后端启动

#### 3.2.1 配置 `.env` 文件

```bash
cd backend

# 从示例创建
cp .env.example .env

# 编辑 .env，填入必要项
# 使用你的编辑器打开 .env
```

编辑内容（**必填项**）：

```env
# ===== LLM（gpt-5.5 via OpenAI 兼容中转）=====
GPT_API_KEY=<YOUR_API_KEY>              # 从 gpt.pkpp.cn 获取
GPT_BASE_URL=https://gpt.pkpp.cn/v1
GPT_MODEL=gpt-5.5
GPT_REASONING=high

# ===== 端点安全（主防线）=====
BIND_HOST=127.0.0.1                     # 本地仅访问；远程需改为 0.0.0.0
TERMINAL_TOKEN=                         # 若 BIND_HOST≠127.0.0.1，须设高熵 token

# ===== 数据库 =====
DATABASE_URL=sqlite:///./data/boss_autoapply.db

# ===== 限速 / 配额 =====
DAILY_APPLY_LIMIT=150                   # 每日投递上限
APPLY_INTERVAL_MIN=20                   # 两次投递间隔（秒）
APPLY_INTERVAL_MAX=90
VLM_DAILY_LIMIT=200                     # 视觉 token 日上限

# ===== 后端选择 =====
DEFAULT_BACKEND=uia                     # uia / vision（根据 M0.5 探针结果调整）
T_CTRL=0.8                              # 控件树命中率阈值
T_OCR=0.6                               # OCR 可信度阈值

# ===== 巡检 =====
INBOX_POLL_MIN_SEC=120                  # 巡检间隔（秒）
INBOX_POLL_MAX_SEC=300
SCORE_THRESHOLD=80                      # LLM 打分阈值
```

**安全提示**：
- `.env` 已在 `.gitignore` 中，**不会提交到 git**
- 不要在前端存储 API key；始终走后端
- 若需远程访问（非本机调试），生成高熵 token：`python -c "import secrets; print(secrets.token_urlsafe(32))"`

#### 3.2.2 启动后端

```bash
cd backend

# 方式 1：直接运行（开发）
uvicorn app.main:asgi_app --reload --host 127.0.0.1 --port 8000

# 方式 2：通过 uv（推荐）
uv run uvicorn app.main:asgi_app --reload --host 127.0.0.1 --port 8000
```

预期日志：
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

若报错 `GPT_API_KEY not set` → 检查 `.env` 中 `GPT_API_KEY` 是否非空。

### 3.3 前端启动

在新的终端窗口中：

```bash
cd frontend
pnpm install        # 若尚未安装
pnpm dev            # 启动开发服务器
```

预期输出：
```
Local:   http://localhost:5173/
```

在浏览器打开 `http://localhost:5173/`。

---

## M2–M3：端到端联调步骤

### 4.1 连接真机与初始化

**①  Web 中确认设备在线**

1. 打开浏览器 → `http://localhost:5173/`
2. 导航到"设备"页面
3. 应显示设备列表，状态为"在线（USB）"

**②  确保 Boss App 已登录且位于首屏列表**

在真机上：
- 打开 Boss 直聘 App
- 登录（若尚未登录）
- 进入"推荐"或"搜索结果"列表页（需显示 ≥20 条岗位卡片）

### 4.2 运行三探针（再次验证）

若上次探针距现在超过 1 小时，或更换了设备，建议重新运行以确认环境稳定：

```bash
cd backend
uv run python -m app.probe.probe_backends --device <SERIAL>
```

若仍为 GO，继续。若变为 NO-GO → 诊断（见 7 常见排错）。

### 4.3 真机联调：端到端单岗位投递

#### 4.3.1 抓取岗位

在 Web 前端的"岗位"页面：

1. 点击"抓取岗位"按钮
2. 后端通过 uiautomator2 解析列表，提取岗位名 / 公司 / 薪资 / 要求等
3. 前端显示抓取结果的卡片列表（预期 ≥5 条）

**预期流程**：
```
Web 前端（抓取按钮）
  ↓ REST POST /api/jobs/fetch
后端 collector（列表控件树解析）
  ↓ 入库 Job 表
前端卡片流（刷新显示）
```

#### 4.3.2 LLM 筛选与打分

前端显示的每个岗位卡片上应有 LLM 评分，例如：

```
[岗位名] 某互联网公司 Python 开发
学历要求：本科  经验：3-5 年  薪资：25-35k

LLM 评分：82 分  ⭐️ 推荐
理由：符合技能栈、薪资范围、工作地点
```

该分数来自后端 `screener`（LangGraph 模型），基于规则 + LLM 判断。

**说明**：
- screener 是**唯一投递决策权**，决策逻辑见配置文件（rules/config 页面可调）
- planner 无权越过 screener 决策

#### 4.3.3 半自动投递（两阶段发送）

选择一个评分 ≥`SCORE_THRESHOLD`（默认 80）的岗位卡片，点击"立即沟通"：

**第一阶段**：
```
前端【投递看板】PENDING 卡片
  → 点【立即沟通】
  → 后端 dispatcher → Application 状态变 CLAIMED
  → 自动生成打招呼语（configurable，来自 rules）
  → 发送【沟通消息】到 App（adb input / ADBKeyboard）
  → Application 状态变 SENDING
  → 前端弹出【待人工确认】对话框
```

**第二阶段**：
在前端【投递看板】的"待确认队列"中：
- 观看投屏（scrcpy），确认"消息已发送"的弹窗 ✓
- 点击【确认已发送】
- Application 状态变 SENT，从待确认队列消失

**若中途崩溃**：
- 重启后端，前端刷新
- dispatcher 重新检查 SENDING 状态的 Application，若确实已发则直接转 SENT；否则仍挂在 SENDING 等人工确认

### 4.4 巡检与 HR 回复

后端 `inbox_watcher` 常驻运行，每 2–5 分钟轮询一次：

1. **自动巡检**：强制走控件树读取 HR 消息列表（不计 VLM 成本）
2. **检测新回复**：与上次快照 diff，发现新消息 → 通知前端
3. **前端提示**：【HR 收件箱】显示红点提示，列出新回复

示例流程：
```
【投递看板】SENT 状态的 Application
  ↓ 巡检发现 HR 回复
  → 【HR 收件箱】新消息提示
  → 点【一键接管】
  → 自动切 MANUAL 模式 + 置 taken_over=true
  → 前端跳转投屏，自动聚焦到聊天页面
  ↓ 人工接手，在投屏中手动回复
```

**注意**：
- MANUAL 模式期间，自动投递暂停；巡检也暂停（待接管完成）
- 退出 MANUAL 模式后，下一个巡检周期自动补巡

### 4.5 验收清单（对应 AC1–19）

以下项需逐一验证：

| # | 检查项 | 预期结果 | 操作/观测 |
|---|--------|--------|---------|
| AC1 | adb 连通 | `adb devices` 显示 device；原语 50 次成功率 ≥95% | 连续快速点击 50 次，查看 logcat 无异常 |
| AC2 | 控件树抓取 | 列表 ≥20 条，关键字段完整率 ≥90% | 【岗位】页面抓取，查看 RunLog |
| AC3 | 视觉后端定位 | 命中率 ≥85%，坐标误差 <2% | M0.5 三探针结果 |
| AC4 | 后端切换 | 命中率<T_ctrl 时自动切 vision；有 RunLog | 强制改 T_CTRL=0.99 观看切换日志 |
| AC5 | LLM 筛选 | ≥50 标注 precision≥0.8、recall≥0.7 | 人工验证投递列表的推荐准确度 |
| AC6 | 半自动投递 | 成功率 ≥90%；ADBKeyboard 无乱码 100% | 投递 10 个岗位，全部成功 |
| AC7 | HR 巡检 | 每 2–5min 一次；新回复一周期内通知；强制控件树读 | 观察 RunLog 的巡检时间戳 |
| AC8 | 投递幂等 | 崩溃中途不二次发送 | 投递中杀后端，重启观测状态 |
| AC9 | 限速拟人化 | 日≤150；间隔随机；geetest→PAUSED | 查看 RunLog 的投递间隔 |
| AC10 | 设备锁+模式互斥 | AUTO 下手动/Terminal 被拒；MANUAL 独占 | 尝试在 AUTO 模式下操控投屏，应拒绝 |
| AC11 | scrcpy 投屏 | WebCodecs 播放；手动点击生效 | 在投屏中手动点击控件，观看真机 |
| AC12 | 端点安全 | 未鉴权被拒；跨 Origin 被拒；默认 localhost | curl 测试无 token 访问，应 401 |
| AC13 | VLM 成本熔断 | 三路 VLM 计入同一日上限；超额告警 | 观看 RunLog 的 VLM 计数 |
| AC14 | 密钥/配置 | `.env` 不入库；日志无明文 key；缺 key 启动报错 | git status 确认 .env 未 staged；启动无 key 报错 |
| AC15 | M0.5 三探针 | 报告产出；go/no-go 判定；input 反检测 | 运行 `--json` 保存报告 |
| AC16 | 前端模块 | 10 页面可用；投屏可操控；收件箱接管 | 逐页访问；手动测试 |
| AC17 | adb 传输暴露 | 默认 USB；WiFi 用毕关闭；记录补丁 | 检查 adb 状态；记录设备指纹 |
| AC18 | PII 外发最小化 | 外发 payload 有脱敏选项；日志无原始截图 | 检查 Rules 配置中的脱敏开关 |
| AC19 | planner 不旁路 | 静态检查 + 断言：planner 无 adb-send 旁路 | grep 源码；运行单元测试 |

---

## 常见排错

### 7.1 adb 连接问题

**症状**：`adb devices` 显示 `offline` 或设备不显示

**排查**：
1. 设备开发者选项 → USB 调试 ✓ 确认打开
2. 设备屏幕上弹出"是否允许 USB 调试"对话框 → 勾选"总是允许" → 确定
3. 重新插拔 USB
4. PC 端运行 `adb kill-server && adb devices`

如仍不行，尝试：
```bash
adb connect 192.168.1.xxx:5555        # 若设备 IP 已知，可用 WiFi 调试（临时）
adb usb                               # 用毕立即关闭 WiFi 调试
```

### 7.2 控件树抓不到（空节点树或关键字段缺失）

**症状**：M0.5 探针显示 uia_key_field_rate 接近 0，或前端【岗位】页面抓取为空

**排查**：
1. 确认 uiautomator2 已安装：`uv run python -c "import uiautomator2; print(uiautomator2.__version__)"`
2. 真机上确认 Boss 应用已打开且位于**列表页**（不是详情页 / 聊天页）
3. 运行探针时 Boss 应处于**前台**
4. 若 App 版本最近更新，控件树结构可能变化 → 降级使用视觉后端

**临时解决**：
```env
# .env 中改为视觉主后端（如果 M0.5 视觉命中率 ≥85%）
DEFAULT_BACKEND=vision
```

### 7.3 scrcpy 投屏黑屏或无法播放

**症状**：前端投屏区域全黑，或提示"WebCodecs 不支持"

**排查**：
1. 确认 scrcpy-server jar 已放置：`ls -la backend/app/scrcpy/resources/scrcpy-server`
2. 后端日志中是否有 scrcpy 启动错误：查看控制台输出
3. 浏览器兼容性：WebCodecs 仅支持 Chrome/Edge；FF/Safari 自动降级截图轮询

**临时解决**：
- 使用截图轮询代替：前端自动降级，性能下降但功能完整

### 7.4 中文输入乱码

**症状**：投递时打招呼语显示为"？？？"或乱码

**排查**：
1. 真机输入法是否为 ADBKeyboard：设置 → 输入法 → 默认输入法 ✓ ADBKeyboard
2. ADBKeyboard 是否已安装：`adb shell pm list packages | grep adb`（应显示 `com.android.adbkeyboard`）
3. 若未装，重新安装：
   ```bash
   adb install app/adb/resources/ADBKeyboard.apk
   ```

### 7.5 登录态失效（无法进入 App，显示登录页）

**症状**：巡检或投递时发现 App 跳到登录页；后端发送"验证码"等弹窗

**排查与恢复**：
1. 后端会自动检测并暂停流水线，置状态为 PAUSED
2. 真机上手动重新登录 → 等待进入推荐列表
3. 前端【设备】页面点"恢复"或 AUTO 模式按钮，自动恢复流水线
4. 若需要修改登录账号，在 MANUAL 模式下手动操作，完成后退出 MANUAL

### 7.6 验证码或 geetest 弹窗

**症状**：投递时 App 弹出滑块验证码或行为验证，后端自动暂停

**处理**：
1. 后端检测到 geetest 类验证 → Application 状态置 PAUSED
2. 前端通知"遇到风控验证，需人工处理"
3. 切至 MANUAL 模式，在投屏中手动完成验证
4. 验证通过后，退出 MANUAL，流水线自动恢复

**预防**：
- 严格遵守限速配置（DAILY_APPLY_LIMIT≤150）
- 启用夜停（23:00–08:00 暂停投递）
- 长期使用建议开启"随机间隔"和"随机点击偏移"

### 7.7 后端启动失败：`GPT_API_KEY not set`

**原因**：`.env` 文件缺失或 `GPT_API_KEY` 为空

**解决**：
```bash
# 1. 检查 .env 是否存在
cat backend/.env

# 2. 若不存在，从示例创建
cp backend/.env.example backend/.env

# 3. 编辑 .env，填入真实 API Key
# GPT_API_KEY=sk_xxx_yyy  （从 gpt.pkpp.cn 获取）

# 4. 重启后端
```

### 7.8 VLM（视觉）成本超限，自动降级或熔断

**症状**：前端日志显示"VLM daily limit exceeded"；视觉定位停止工作

**原因**：
- 三个 VLM 消费者（视觉定位 / planner 辅助 / 巡检降级）共享 `VLM_DAILY_LIMIT`（默认 200 tokens）
- 投递过多导致超额

**恢复**：
1. 等待次日自动重置（按 UTC 日期）
2. 或临时提高配额：编辑 `.env` 中 `VLM_DAILY_LIMIT=500`，重启后端

**优化**：
- 优先使用控件树后端（成本最低）
- 调整限速，降低投递频率（DAILY_APPLY_LIMIT）
- 启用"巡检降级"：若控件树可读则不调视觉（默认开启）

---

## 分阶段验收与交付

### 5.1 M0.5 阶段验收

- [ ] 硬件准备完毕，adb 连通率 100%
- [ ] 三探针运行成功，结论为 GO
- [ ] 生成 JSON 报告，保存为参考

**交付件**：`probe_report.json`、设备指纹截图

### 5.2 M1 阶段验收

- [ ] scrcpy-server jar 就位
- [ ] `.env` 配置完成，GPT_API_KEY 有效
- [ ] 后端启动无报错，监听 8000 端口
- [ ] 前端访问 localhost:5173 显示设备面板
- [ ] 设备在线，WebSocket 连接正常

**交付件**：后端日志（首次启动）、前端截图

### 5.3 M2–M3 阶段验收

- [ ] 真机岗位抓取 ≥5 条，字段完整
- [ ] LLM 评分显示正确（≥80 分可自动投递）
- [ ] 单岗位从 PENDING → CLAIMED → SENDING → SENT，全流程成功
- [ ] 巡检发现 HR 回复，前端提示（若有回复）
- [ ] 一键接管：切 MANUAL，跳投屏
- [ ] MANUAL 退出后，自动恢复 AUTO，流水线继续

**交付件**：投递链路视频录制、RunLog 片段

### 5.4 完整验收清单（AC1–19）

所有 19 项 AC（见 4.5 表）都应标记为"通过"或"已记录跳过原因"。

---

## 配置调优与微调

### 6.1 限速与拟人化

编辑 `.env`：

```env
# 每日最多投递 X 个岗位（建议 100–150）
DAILY_APPLY_LIMIT=150

# 两次投递的间隔范围（秒）— 系统随机取值
APPLY_INTERVAL_MIN=20
APPLY_INTERVAL_MAX=90

# VLM（视觉）日上限（token，三路共享）
VLM_DAILY_LIMIT=200
```

### 6.2 后端选择与切换

```env
# 默认后端：uia（控件树） | vision（视觉）
DEFAULT_BACKEND=uia

# 控件树命中率阈值（低于此值自动切视觉）
T_CTRL=0.8

# 控件树 OCR 降级阈值
T_OCR=0.6
```

M0.5 探针结果为参考：
- 若探针显示 uia_key_field_rate ≥80%，保持 DEFAULT_BACKEND=uia
- 若 50–80%，保持 uia 但自动切换启用
- 若 <50%，改为 DEFAULT_BACKEND=vision

### 6.3 巡检间隔

```env
# HR 消息巡检间隔（秒）
INBOX_POLL_MIN_SEC=120      # 最少 2 分钟
INBOX_POLL_MAX_SEC=300      # 最多 5 分钟
# 系统在此范围内随机选择间隔，避免规律性
```

### 6.4 LLM 打分阈值

```env
# 评分 ≥ 此值的岗位自动投递
SCORE_THRESHOLD=80          # 0–100 分
```

在前端【规则】页面可视化调整，无需重启后端。

### 6.5 端点安全（重要）

```env
# 仅本机访问（开发模式）
BIND_HOST=127.0.0.1
TERMINAL_TOKEN=             # 可为空

# 若需远程访问（生产模式，不推荐）
BIND_HOST=0.0.0.0
TERMINAL_TOKEN=<HIGH_ENTROPY_TOKEN>  # 必须设置，例如: abcdef1234567890
```

**生成高熵 token**：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 进阶：手动操控与 Terminal

### 7.1 手动投屏操控（MANUAL 模式）

仅在 **MANUAL 模式**下可用：

1. 前端切换模式：【设置】或【设备】页面 → 模式 → MANUAL
2. 投屏中鼠标点击 → 自动转化为 adb motionevent
3. 拖拽 / 长按也被识别并转化
4. 完成操作后点【退出 MANUAL】，自动回锚点页，恢复 AUTO 模式

**注意**：AUTO 模式下手动操控被拒绝（避免冲突）。

### 7.2 Web Terminal（调试用）

仅在 **MANUAL 模式**下可用，用于运行 adb 命令：

1. 前端打开【Terminal】标签页
2. 输入 adb 命令，例如：
   ```
   shell getprop ro.product.model      # 查询设备型号
   shell pm list packages | grep boss  # 查询 Boss App
   logcat | grep "boss"                # 查看实时日志（需 Ctrl+C 退出）
   ```
3. 高危命令（`adb shell su` / `adb forward` / `adb install` 等）需二次确认

**安全说明**：Terminal 受端点鉴权（localhost + token）保护；命令执行仅限 MANUAL 模式。

---

## 故障恢复与日志分析

### 8.1 查看运行日志

后端日志包含详细的投递链路、巡检、后端切换等信息：

```bash
# 在后端启动的终端中查看实时日志
# 或进入前端【日志】页面，SSE 实时显示

# 日志包含以下关键信息：
# - [collector] 岗位抓取
# - [screener] LLM 打分与决策
# - [dispatcher] 投递与幂等性
# - [inbox_watcher] 巡检与新回复检测
# - [planner] 单步动作执行
# - [vision_backend] 视觉定位（成本）
# - [device_mode] 模式切换与锁争用
```

### 8.2 查看投递成本

前端【日志】页面的"成本统计"显示：
- VLM 已消耗 token / 日上限
- 后端切换次数（控件 → 视觉）
- 暂停原因与次数（登录失效 / 验证码 / VLM 熔断）

### 8.3 数据库查询（高级）

SQLite 数据库位于 `backend/data/boss_autoapply.db`，可用 sqlite3 工具查询：

```bash
sqlite3 backend/data/boss_autoapply.db

# 查询所有投递记录
SELECT id, job_name, company, score, status, sent_at FROM application;

# 查询今日投递数
SELECT COUNT(*) FROM application WHERE date(sent_at) = date('now');

# 查询失败的投递
SELECT id, job_name, status FROM application WHERE status = 'FAILED';
```

### 8.4 崩溃恢复

若后端意外崩溃（例如进程被 kill / OOM / 异常退出）：

1. **检查最后状态**：
   ```bash
   # 查看数据库中 SENDING 的 Application
   sqlite3 backend/data/boss_autoapply.db \
     "SELECT id, job_name, status FROM application WHERE status = 'SENDING';"
   ```

2. **手动恢复**（一般不需要）：
   ```bash
   # dispatcher 在启动时会自检 SENDING，判断是否真的已发
   # 若已发则转 SENT；否则仍挂在 SENDING 等人工确认
   ```

3. **重启后端**，流程自动继续

---

## 安全与隐私检查清单

在投入真实账号前，确保以下安全配置已就位：

- [ ] `.env` 文件已创建且 **不在 git 版本控制中**（`.gitignore` 已配置）
- [ ] 真机设备已连接 USB，**不使用 WiFi adb**（或 WiFi 仅临时、用毕立即关闭 `adb usb`）
- [ ] 后端 `BIND_HOST=127.0.0.1`（开发阶段），仅本机访问
- [ ] 若需远程访问，`BIND_HOST=0.0.0.0` + `TERMINAL_TOKEN=<HIGH_ENTROPY>`
- [ ] 前端 **未存储 API key 或登录密码**（所有密钥走 `.env` 和后端）
- [ ] 限速配置合理（DAILY_APPLY_LIMIT ≤150），避免账号风控
- [ ] PII 脱敏开关已启用（【规则】页面可配置）
- [ ] 日志中不包含明文截图或简历内容（仅记录关键字和决策路径）
- [ ] 设备补丁级别已记录，重点关注 CVE-2026-0073（adb WiFi 远程控制漏洞）

---

## 快速参考

### 启动命令（完整流程）

```bash
# 终端 1：后端
cd backend
uv sync --extra dev
cp .env.example .env
# 编辑 .env，填 GPT_API_KEY
uvicorn app.main:asgi_app --reload --host 127.0.0.1 --port 8000

# 终端 2：前端
cd frontend
pnpm install
pnpm dev

# 终端 3：检查设备
adb devices

# 终端 4（可选）：三探针验证
cd backend
uv run python -m app.probe.probe_backends --device <SERIAL> --json probe_report.json
```

### 常用 adb 命令

```bash
# 列出在线设备
adb devices

# 获取设备信息
adb shell getprop ro.build.fingerprint   # 设备指纹
adb shell getprop ro.product.model       # 型号

# 安装 APK
adb install app/adb/resources/ADBKeyboard.apk

# 查看日志
adb logcat | grep "boss"

# 进入 shell
adb shell

# 检查前台应用
adb shell dumpsys window | grep mCurrentFocus

# 截图（保存到本地）
adb exec-out screencap -p > screenshot.png
```

### 前端页面快速导航

| 功能 | 路由 | 快捷键/按钮 |
|------|------|-----------|
| 设备状态 | `/` | 左侧栏顶部 |
| 实时投屏 | `/screen` | 左侧栏"投屏" |
| 岗位流 | `/jobs` | 左侧栏"岗位" |
| 投递看板 | `/applications` | 左侧栏"看板" |
| HR 收件箱 | `/inbox` | 左侧栏"收件箱"（红点提示） |
| 规则配置 | `/rules` | 左侧栏"规则" |
| 日志与成本 | `/logs` | 左侧栏"日志" |
| Web Terminal | `/terminal` | 左侧栏"Terminal" |
| 设置 | `/settings` | 左侧栏"设置" |

---

## 支持与反馈

若遇到问题或需要优化：

1. **查看日志**：后端控制台或前端【日志】页面
2. **运行三探针**：`uv run python -m app.probe.probe_backends --device <SERIAL> --json report.json`
3. **检查配置**：`.env` 所有必填项是否非空
4. **设备状态**：`adb devices` 确认在线
5. **数据库查询**：排查投递历史与失败原因

若问题持续，请保存：
- 后端完整日志（从启动到故障）
- 前端【日志】截图
- 三探针报告（JSON）
- 设备信息（型号 / Android 版本 / 补丁级别）
- 具体操作步骤（现象复现方式）

---

**文档版本**：v1（2026-06-09）  
**适用计划版本**：boss-autoapply-plan.md v6  
**最后审核**：consensus 达成（Architect + Critic）
