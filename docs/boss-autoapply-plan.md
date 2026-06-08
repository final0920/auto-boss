# 工作计划：boss-autoapply — 真机端自动筛选 + 半自动投递 Boss 直聘（AutoGLM-GUI 式）

**状态**: `pending approval`（**consensus 达成**：Architect + Critic 终审均 APPROVED；v6 收口全部 P0 + 安全反转，P2 实现期清单见 §11；本计划不会自动执行，待你批准执行路径）
**生成方式**: `/oh-my-claudecode:plan --consensus`（RALPLAN-DR short 模式）
**日期**: 2026-06-08

---

## 1. 需求摘要 (Requirements Summary)

PC 上通过 **adb 控制已 root 安卓真机**里的 Boss 直聘 App 的自动求职系统，**设备控制与 Web 控制台对齐 `suyiiyii/AutoGLM-GUI`**：自动抓取/筛选岗位 → 半自动投递+打招呼 → 常驻巡检 HR 回复转人工。Web 控制台含实时投屏+手动操控、Web Terminal（adb）、设备/岗位/投递/对话/规则/定时/日志管理。

### 已确认决策

| 维度 | 决策 | 理由 |
|---|---|---|
| 开发环境 | **uv**（pyproject.toml + uv.lock） | 快、可复现 |
| 配置 | **`.env` 文件** + pydantic-settings，不依赖系统环境变量 | 集中、可模板化 |
| 设备 | **仅真机（已 root）**，去模拟器；**默认 USB 连接**，WiFi 调试仅受控网络临时启用 | 真实指纹 + 收敛 adb 网络暴露面（见 §9/AC17） |
| root 利用 | 标准非特权 adb；root 仅保底（不做底层注入，留 Follow-up） | AutoGLM 本不需 root |
| 执行层 | adb 原语 + **可插拔双后端**（uia_backend 控件树主/vision_backend 视觉兜底）+ **受限分层 agent** | 对齐 AutoGLM 可插拔 + 控件树省 token |
| **决策权威** | **pipeline 是唯一投递权威**（screener 阈值 + dispatcher 幂等状态机 + RateLimiter）；**planner 是无业务决策权的单步执行器** | 防 planner 旁路安全机（见 §4/AC19） |
| Web 控制台 | scrcpy 投屏 + Web Terminal + 手动操控；**全部控制端点统一 localhost+token+Origin 鉴权** | "webshell" 照搬 AutoGLM，但安全主防线是鉴权边界（见 §4/AC12） |
| 前端 | React 19 + Vite + TanStack + shadcn（对齐 AutoGLM） | 复用其 ScrcpyPlayer/Terminal |
| LLM | `gpt-5.5`（文本 reasoning=high + 多模态），`base_url=https://gpt.pkpp.cn`，key 走 `.env` | 文本决策+视觉兜底 |
| 自动化程度 | 半自动（自动投+人工接管对话） | 不变 |

---

## 2. RALPLAN-DR 决策摘要

### 原则 (Principles)
1. **对齐成熟基座、但只搬匹配任务结构的部分**：照搬 AutoGLM 的 adb 原语/投屏/终端/可插拔后端；**不照搬其 open-ended agent 决策范式**（本项目是固定业务流）。
2. **控件优先、视觉兜底**：双后端，控件树主、视觉按判据兜底。
3. **pipeline 单一权威**：投递/转人工决策只属 pipeline；agent 不持业务决策权、不旁路状态机与配额。
4. **半自动安全边界**：自动化止于发送打招呼语，HR 对话转人工。
5. **安全边界前置**：所有设备控制端点 localhost+token+Origin 鉴权为主防线；adb 白名单仅纵深防御；收敛 adb 传输网络暴露面。
6. **风控合规拟人化**：限速、随机、单账号、夜停、真机指纹。
7. **配置/密钥/PII 最小外泄**：key 走 `.env`；外发 payload（简历/截图）最小化。
8. **假设前置证伪**：控件树可得率 + 视觉可用性 + **input 注入是否被识别为非真实触摸**，M0.5 三探针 go/no-go。

### 决策驱动 (Drivers)
1. 对齐 AutoGLM（用户要求）；2. 抗改版+控成本（控件树主+视觉兜底）；3. 低封号+安全（真机+半自动+限速+端点鉴权+收敛 adb 暴露面）。

### 候选方案（执行层后端架构；路线"安卓真机"已既定）
- **Option A（选定）可插拔双后端**：控件树主+视觉兜底。Pros：对齐 AutoGLM 可插拔、控件树省 token、视觉抗改版。Cons：维护两后端+切换判据。
- **Option B 纯视觉**：贴近 AutoGLM 默认但每步调多模态、token 最高 → 降为兜底后端。
- **Option C 控件树单一**：成本最低但无视觉兜底、不满足可插拔 → 降为后端之一。
- **选定 A**：Driver 1 要可插拔（含视觉）淘汰 C；Driver 2 控成本淘汰 B；统一 `ControlBackend` 把 B/C 收为可切后端。前提风险由 M0.5 三探针证伪。

---

## 3. 架构蓝本：AutoGLM-GUI 借鉴点（源码级）

| 能力 | AutoGLM 照搬抓手 | 本项目落点 |
|---|---|---|
| adb 原语 | `adb/device.py`(input tap/swipe/keyevent)、`adb/input.py`(ADBKeyboard `am broadcast ADB_INPUT_B64`)、`adb_plus/touch.py`(motionevent)、`adb_plus/screenshot.py`(exec-out screencap) | `backend/app/adb/` |
| 连接 | `adb/connection.py`+`adb_plus/{pair,qr_pair,mdns}.py` | `adb/connection.py`（**默认 USB**） |
| scrcpy 投屏 | `scrcpy_stream.py`+`scrcpy_protocol.py`+`socketio_server.py`(control=false，H.264 over Socket.IO)；前端 `ScrcpyPlayer.tsx`(`@yume-chan/scrcpy-decoder-webcodecs`)，降级 `useScreenshotPolling` | `backend/app/scrcpy/`+前端 ScrcpyPlayer |
| Web Terminal | `api/terminal.py`+`adb_terminal_service.py`(PTY)+`adb_terminal_repl.py`(adb REPL)；前端 xterm.js | `backend/app/terminal/`（**安全见 §4**） |
| 分层 agent | `layered_agent_service.py`（OpenAI Agents SDK） | `backend/app/agent/`（**降级为受限执行器，见 §4**） |
| 可插拔后端 | `agents/factory.py` AGENT_REGISTRY（glm/qwen/**droidrun=控件树**）；视觉坐标 0-1000 归一化 | `backend/app/backends/{uia,vision}_backend.py` |
| 前端形态 | React19+Vite+TanStack+Radix/shadcn+Tailwind | §13 |

> 业务参考（不变）：`Auto-JobHunter`(LangGraph screener)、`get_jobs`(打分+招呼语+150 限额)、`jobclaw`(验证码暂停转人工)。

---

## 4. 架构设计

```
React 控制台 (设备栏/投屏操控/岗位流/投递看板/HR收件箱/规则/定时/日志成本/Terminal/设置)
   │ REST  │ Socket.IO(视频)  │ WS(xterm)  │ SSE(事件)   ← 全部端点统一 localhost+token+Origin 鉴权
┌──▼───────▼─────────────────▼────────────▼──────────────────────┐
│ FastAPI + python-socketio (ASGI)                                 │
│ ┌ 调度 APScheduler ┐  ┌ inbox_watcher 常驻巡检(强制控件树读消息) ┐│
│ └────────┬─────────┘  └───────────────┬──────────────────────┘ │
│ ┌────────▼──── pipeline（唯一业务权威）────────┐                  │
│ │ collector → screener(LangGraph 打分) →        │                  │
│ │ dispatcher(幂等状态机 + RateLimiter)          │                  │
│ │   └─ 指派"明确单步子任务" ─┐                  │                  │
│ │ ┌─ 受限分层 agent ─────────▼──┐               │                  │
│ │ │ planner(给定子任务,无业务决策)│               │                  │
│ │ │  → executor → ControlBackend │               │                  │
│ │ │     ├ uia(控件树,主)         │               │                  │
│ │ │     └ vision(gpt-5.5,兜底)   │               │                  │
│ │ └──────────────┬──────────────┘               │                  │
│ └────────────────┼──────────────────────────────┘                  │
│ ┌ RateLimiter(配额+VLM 熔断 单源, 三消费者共享) ┐                   │
│ └────────────────┼──────────────────────────────┘                  │
│ ┌ device_mode AUTO/MANUAL/PAUSED + 单写者锁 ┐                      │
│ │  手动 /control 与 Terminal 仅 MANUAL 放行   │                      │
│ └────────────────┬──────────────────────────┘                      │
│ ┌ adb 原语层(input/screencap/ADBKeyboard/dumpsys) ┐ scrcpy(只读) · SQLite │
│ └────────────────┬───────────────────────────────┘                  │
└──────────────────┼──────────────────────────────────────────────┘
                   │ adb（默认 USB；WiFi 仅受控临时）
              已 root 安卓真机 — Boss 直聘 App
```

### 决策权威与受限分层 agent（收口 P0-A）
- **pipeline 是唯一业务权威**：`screener`（LangGraph 打分≥阈值）决定"是否投递"，`dispatcher` 经 `Application` 幂等状态机 + `RateLimiter` 执行。**"是否投递/是否转人工"决策权不属于 agent。**
- **planner 降级为受限单步执行器**：输入是 pipeline/dispatcher 指派的**明确子任务**（如"在当前页定位并点击'立即沟通'按钮""把这段文本输入聊天框"），planner 只决定**怎么定位/点哪个坐标**（选 backend、给坐标），**不决定是否投递、是否发送、是否转人工**。
- **不可旁路约束**：executor 的任何"发送/投递"动作必须经 dispatcher 状态机 + `RateLimiter.check_and_consume()`；planner/executor **无直达 adb-send 的旁路**（AC19）。

### 可插拔后端（`backends/base.py`）
- 统一 `ControlBackend`：`observe()`/`locate(target)`/`act(action)`。**uia_backend（主）**：控件树 + 缺字段区域局部 OCR + VLM 三级降级（T_ctrl=0.8/T_ocr=0.6）。**vision_backend（兜底）**：截图→gpt-5.5 多模态→0-1000 坐标→像素。
- **切换原子性（收口 C5/C7）**：后端热切以**页面/动作为原子边界**，禁止单个 act 中途换后端；切换为**持锁原子序列**（回锚点→重 observe→换后端），不被 v4 的"单次写操作级释放"打断。**手动覆盖后端**（前端设置）优先级**高于**自动判据，且锁定后自动判据不再切，直到人工解除。

### 端点安全模型（收口 P0-B / G1）
- **主防线 = localhost-bind + 会话 token + Origin 校验**，**统一适用于全部控制端点**：Web Terminal（WS）、`/control/{tap,swipe,touch}`（REST）、scrcpy 视频（Socket.IO）、事件（SSE）。默认仅 localhost；非本机访问须显式开关 + 强 token。
- **adb 白名单仅作纵深防御附加项，不作为 RCE 防线**：明确 **`adb shell`（设备已 root → `adb shell su`）/`adb forward`/`reverse`/`install`/`push`/`tcpip` 等价对设备完全控制**，"命令名是 adb"提供的安全增量≈0。Web Terminal 默认对上述高危子命令**二次确认或显式禁用**。
- token 由后端生成并仅经已鉴权会话下发，**前端不持久化 key**；trace/RunLog 不记录 Authorization。

### 关键运行时机制（沿用 v4 + 收口）
- **device_mode 锁（收口 C3）**：AUTO（流水线+巡检持锁轮转，单次写操作级释放，间隔锁外，巡检有界等待+提权）/MANUAL（人工接管，**自动化全停含 inbox_watcher 暂停**）/PAUSED。**手动 `/control` 操控与 Web Terminal 仅在 MANUAL 模式放行，AUTO 下拒绝**——以模式互斥替代"让外部 PTY 子进程穿透进程内 asyncio 锁"这一不可行设计。scrcpy 视频只读不占锁。持锁者遵循"导航到目标页→完成→释锁前回**锚点页（默认列表页，`base_page.ensure_anchor()`）**"。
- **inbox_watcher（收口 C4）**：常驻巡检 `SENT∧¬taken_over`，**强制走 uia_backend 控件树 + 廉价文本 diff** 读 HR 消息；控件树读不到才有限降级 vision，且**计入统一 VLM 预算**。
- **Application 幂等状态机**（不变）：`PENDING→CLAIMED→SENDING→SENT/FAILED`；只取 CLAIMED、永不自动重拾 SENDING、启动自检、确认后归位。
- **RateLimiter（收口 C4）**：配额/限速 + **VLM 熔断单源**；**三个 VLM 消费者（vision_backend 定位 / planner 视觉 / inbox_watcher 降级）共享同一日上限**，优先级 **投递 > 巡检**（巡检超额则退化为纯控件树或跳过该轮）。

---

## 5. 技术选型

| 层 | 选型 | 备注 |
|---|---|---|
| Python 环境 | **uv** | `uv sync`/`uv run` |
| 配置 | python-dotenv + pydantic-settings 读 `.env` | 不依赖系统环境变量 |
| 后端 | FastAPI + python-socketio（ASGI） | 端点统一鉴权 |
| 设备控制 | `adb`（input/screencap/motionevent）+ ADBKeyboard | 非特权；**默认 USB** |
| 控件树后端 | `uiautomator2` v3.5.2（可选 droidrun） | 主用 |
| 视觉后端 | `gpt-5.5` 多模态（0-1000 坐标） | 兜底，受熔断 |
| 投屏 | scrcpy-server + `@yume-chan/scrcpy-decoder-webcodecs`，降级截图 | H.264 over Socket.IO，**鉴权** |
| Web Terminal | PTY + adb REPL（纵深防御）；**主防线鉴权** | localhost+token+Origin；高危子命令管控 |
| 编排 | `langgraph`（仅 screener） | 其余 APScheduler+DB 状态机 |
| LLM | `gpt-5.5`（文本+多模态），`base_url=https://gpt.pkpp.cn` | key 走 `.env` 的 `GPT_API_KEY` |
| 数据 | SQLModel + SQLite | |
| 前端 | React 19 + Vite + TanStack + shadcn + socket.io-client + xterm | §13 |

### 模型与密钥配置（.env）
`.env`（`.gitignore` 排除）：`GPT_API_KEY=`、`GPT_BASE_URL=https://gpt.pkpp.cn/v1`、`GPT_MODEL=gpt-5.5`、`GPT_REASONING=high`、`TERMINAL_TOKEN=`、`BIND_HOST=127.0.0.1`。pydantic-settings 加载，缺 `GPT_API_KEY` 启动报错（AC14）。

---

## 6. 目录结构（规划）

```
boss-autoapply/
├─ backend/
│  ├─ pyproject.toml / uv.lock / .env.example
│  ├─ app/
│  │  ├─ main.py(FastAPI+SocketIO ASGI) config.py(pydantic-settings) db.py
│  │  ├─ models.py            # Job/Application(状态机)/Message/Config/RunLog/Quota
│  │  ├─ security/            # 端点鉴权(token/Origin/localhost) ★收口
│  │  │  └─ auth.py
│  │  ├─ api/                 # devices/control(仅MANUAL)/media/jobs/applications/messages/config/scheduled/terminal/logs/ws
│  │  ├─ adb/                 # device.py inputs.py screencap.py appinfo.py connection.py(默认USB) resources/ADBKeyboard.apk
│  │  ├─ scrcpy/ streamer.py protocol.py sio.py(鉴权)
│  │  ├─ terminal/ service.py(PTY) adb_repl.py(纵深防御白名单+高危子命令管控)
│  │  ├─ backends/ base.py uia_backend.py(三级降级) vision_backend.py
│  │  ├─ agent/ planner.py(受限单步执行器,无业务决策) executor.py(经dispatcher,不旁路)
│  │  ├─ automation/ device_mode.py(锁+模式互斥) inbox_watcher.py(控件树读) humanize.py
│  │  ├─ pipeline/ collector.py screener.py(LangGraph,唯一投递权威) dispatcher.py(幂等) rate_limiter.py(三消费者共享熔断)
│  │  ├─ llm/ client.py prompts.py
│  │  ├─ scheduler.py notify.py trace.py(不记 Authorization)
│  │  └─ probe/ probe_backends.py(三探针:控件/视觉/input反检测)
│  └─ tests/
├─ frontend/  src/{routes,components,lib,api.ts}  # §13
└─ README.md
```

`Application` 字段：`status∈{PENDING,CLAIMED,SENDING,SENT,FAILED}`、`taken_over`、`device_id`、`account_id`、`greeting`、`sent_at`、`last_poll_at`。不变量：dispatcher 只取 CLAIMED；SENDING 仅启动自检转人工；接管置 taken_over=true。

---

## 7. 实施步骤

### M0 — 环境与连通
1. `uv init`+依赖；`.env.example`
2. 真机 USB 调试；**默认 `adb` USB 连接**（WiFi 调试仅受控网络临时，用毕 `adb usb` 关闭）；**记录设备 Android 版本/补丁级别**（CVE-2026-0073 相关）；装 ADBKeyboard 设默认 IME
3. `adb/` 原语层 + `device_mode.py`（锁 + AUTO 下拒绝手动/terminal 的模式互斥骨架）
4. `security/auth.py`：localhost-bind + token + Origin，套到所有控制端点中间件；FastAPI+SocketIO ASGI；config 读 `.env`；SQLite 模型

### M0.5 — 三探针闸门（go/no-go）
5. `probe/probe_backends.py`：①控件树可得率 ②视觉命中率/单步成本 ③**input 注入反检测**——小样本实投观测 `adb shell input tap` 是否被 Boss 判为非真实触摸/触发验证
6. 闸门：控件树≥80%→uia 主；50-80%→双后端；<50%→vision 主（成本升，复议）。**input 若被检测**→按 Follow-up 启用 root sendevent/minitouch 重评（AC15）

### M1 — adb 原语 + scrcpy + Web Terminal（含统一鉴权）
7. scrcpy：streamer+sio（**Socket.IO 视频端点纳入鉴权**）；前端 ScrcpyPlayer（WebCodecs，降级截图）
8. Web Terminal：PTY+adb REPL（纵深防御白名单 + **高危子命令 `shell su`/`forward`/`reverse`/`install`/`tcpip` 二次确认或禁用**）；**主防线 localhost+token+Origin**；前端 xterm；**仅 MANUAL 模式可用**
9. 手动操控：canvas→REST `/control/*`→adb motionevent；**经 device_mode 锁、仅 MANUAL 模式放行**

### M2 — 双后端 + 受限分层 agent
10. `backends/base.py`+`uia_backend.py`（三级降级判据）+`vision_backend.py`（0-1000 坐标）；**后端切换持锁原子序列、手动覆盖优先**
11. `agent/planner.py`（**受限单步执行器：仅定位/点击/输入，无"是否投递/转人工"决策**）+`executor.py`（**任何发送经 dispatcher+RateLimiter，无旁路**）
12. `pages/{list,detail,chat}_page.py`：后端无关页面对象

### M3 — 流水线 + 筛选 + 半自动投递 + 巡检
13. `collector.py`→`Application(PENDING)`；`screener.py`（LangGraph 打分，**唯一投递决策**）→`CLAIMED`
14. `dispatcher.py` 两阶段幂等投递（只取 CLAIMED、启动自检、确认归位）；`rate_limiter.py` 限速 150/天+随机 20-90s+夜停+**三路 VLM 共享熔断**；geetest→PAUSED
15. `inbox_watcher.py` 常驻巡检（**强制控件树读消息**）→diff→notify→待接管

### M4 — 前端控制台（§13）
16-18. 脚手架+设备栏+配对；投屏操控（仅 MANUAL 可操控）、岗位流、投递看板（状态机+SENDING 待确认）、HR 收件箱（接管切 MANUAL+置 taken_over）、规则/定时/日志成本/Terminal/设置（后端覆盖优先级、key 走 .env 不在前端存）

### M5 — 健壮性与反风控
19-21. 异常恢复（登录失效探测→PAUSED 重登）；拟人化+单账号+夜停；可观测（截图+dump+trace 不记 key、RunLog 含 VLM 计数/后端切换/暂停原因）

---

## 8. 验收标准（可测试）

| # | 标准 | 指标 |
|---|---|---|
| AC1 | 真机 adb 连通 | USB 在线；连续 50 次原语成功率≥95%，截图<1.5s |
| AC2 | 控件树抓取 | 列表≥20 条，关键字段完整率≥90%（缺字段局部 OCR） |
| AC3 | 视觉后端定位 | 命中率≥85%，像素换算误差<2% |
| AC4 | 后端切换 | 命中率<T_ctrl 自动切 vision（**页面/动作原子边界，手动覆盖优先**）；有 RunLog |
| AC5 | LLM 筛选 | ≥50 标注 precision≥0.8、recall≥0.7 |
| AC6 | 半自动投递 | score≥阈值自动沟通+招呼；成功率≥90%（ADBKeyboard 无乱码 100%） |
| AC7 | HR 巡检 | 每 2-5min（可配抖动）；新回复一周期内通知；不自动回复；**强制控件树读**；**MANUAL 期间 inbox_watcher 暂停**（退出后下一周期补巡，半自动可接受） |
| AC8 | 投递幂等 | 崩溃中途不二次发送（只取 CLAIMED+启动自检）；确认后归位 |
| AC9 | 限速拟人化 | 每日≤上限；间隔随机；geetest→PAUSED；motionevent 非直线 |
| AC10 | 设备锁+模式互斥 | 切 MANUAL 1 写操作周期内让锁；高负载巡检延迟≤1 周期；**AUTO 下手动 `/control` 与 Terminal 被拒，MANUAL 下独占** |
| AC11 | scrcpy 投屏 | WebCodecs 播放，不可用降级截图；手动点击（MANUAL）经 adb 生效 |
| AC12 | **端点安全（重写）** | **全部带写/设备副作用端点**（terminal/`/control`/scrcpy/SSE/`/devices`/`/config`）：未鉴权被拒、跨 Origin 被拒、默认仅 localhost；`BIND_HOST≠127.0.0.1` 时强制 `TERMINAL_TOKEN` 非空高熵；**`adb shell su`/`forward`/`install` 类不因白名单被误判为安全**（高危子命令二次确认/禁用）；删除"拦 rm/bash"用例 |
| AC13 | VLM 成本熔断 | **三路 VLM（vision_backend/planner/inbox_watcher）计入同一日上限**；超额熔断+告警；投递优先于巡检 |
| AC14 | 密钥/配置 | `.env` 被 `.gitignore`；仓库/日志/前端无明文 key；缺 `GPT_API_KEY` 启动报错；`uv sync` 可复现 |
| AC15 | M0.5 三探针 | 产出 控件可得率+视觉命中/成本+**input 反检测** 报告 + go/no-go；控件<50% 阻断；**input 被检测则触发 root 注入复议** |
| AC16 | 前端模块 | §13 的 10 页面可用；投屏可操控（MANUAL）；收件箱接管联动 device_mode/taken_over；i18n 中英 |
| AC17 | **adb 传输暴露面** | 默认 USB；WiFi 调试仅受控网络临时、用毕 `adb usb` 关闭；启动检查未无意暴露 `tcpip 5555`；记录设备补丁级别 |
| AC18 | **PII 外发最小化** | 外发 gpt.pkpp.cn 的 payload（简历/JD/截图）有最小化/可选脱敏开关；日志不留原始截图明文 |
| AC19 | **planner 不旁路** | 静态检查 + 运行时断言：planner/executor 无直达 adb-send 路径；任何发送必经 dispatcher 状态机 + RateLimiter |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Boss 账号风控/封号 | 真机指纹；限速 150/天+随机；单账号；夜停；半自动 |
| geetest/验证码 | 检测→PAUSED+通知人工 |
| 控件树失效（命门） | M0.5 控件探针前置；失效切 vision；ADR 复议 |
| 视觉/LLM token 成本 | 控件优先+切换判据+**三路 VLM 共享熔断**（AC13） |
| HR 回复丢失 | inbox_watcher 常驻巡检（控件树读）+diff（AC7） |
| 单设备并发争用 | device_mode 锁 + **手动/Terminal 仅 MANUAL 模式互斥**（AC10） |
| 对 HR 二次发送 | Application 幂等（只取 CLAIMED/启动自检/确认归位）（AC8） |
| **planner 旁路安全机** | 架构禁止：pipeline 唯一权威，executor 经 dispatcher+RateLimiter，无 adb-send 旁路（AC19） |
| **Web Terminal/控制端点 RCE** | **主防线 localhost+token+Origin 统一所有端点**；adb 白名单仅纵深防御（明确不防 RCE）；高危 adb 子命令二次确认/禁用（AC12） |
| **设备 ADB-over-WiFi 网络远控面** | 默认 USB；WiFi 仅受控临时、用毕关闭；提示打 2026-05 补丁（CVE-2026-0073）、规避蠕虫面（AC17） |
| **简历/截图 PII 经第三方中转外泄** | 外发 payload 最小化/可选脱敏；不日志原始截图（AC18） |
| 不用 root 的 input 可检测 | M0.5 input 反检测探针前置；被检测则启用 root sendevent（Follow-up） |
| scrcpy WebCodecs 不兼容 | 降级截图轮询（限 Chrome/Edge） |
| 登录态失效 | 主动探测→PAUSED 人工重登 |
| 密钥泄露 | `.env`+`.gitignore`；不入日志/前端；可轮换（AC14） |
| uv/依赖不可复现 | `uv.lock` 锁定 |

---

## 10. 验证步骤

- **M0.5 三探针 go/no-go（前置）**：控件可得率 + 视觉命中/成本 + **input 反检测**（AC15）
- **安全（重点）**：端点鉴权（未鉴权/跨 Origin/非 localhost 被拒，覆盖 terminal/control/scrcpy/SSE）；Web Terminal `adb shell su`/`adb forward`/`adb install` 高危子命令被二次确认或拒绝；adb WiFi 用毕 `adb usb` 关闭验证；`.env` 不入库/日志；外发 payload 脱敏开关
- **单元**：adb 原语；uia 降级判据；vision 坐标换算；screener 回归；Application 状态机；rate_limiter 三路并发计数；**planner 无 adb-send 旁路（静态+断言，AC19）**
- **集成**：真机端到端单岗位（抓取→后端定位→SENDING→SENT→巡检→通知）；崩溃注入不二次发送；后端切换（控件失效→切视觉，原子边界）
- **并发/模式**：AUTO 下流水线+巡检仅一写者；**AUTO 下手动 `/control`/Terminal 被拒**；切 MANUAL 让锁+放行手动
- **前端**：投屏播放+手动（MANUAL）；WebCodecs 降级；10 页面冒烟；i18n
- **观测**：截图+dump+trace（不记 key）；RunLog 含 VLM 计数/后端切换/暂停

---

## 11. 开放问题 / 后续

**实现期注意（consensus P2，不阻塞批准）**：①AC12 端点清单补 `/devices`、`/config`，"带写/设备副作用端点一律纳鉴权"；②`BIND_HOST≠127.0.0.1` 时强制 `TERMINAL_TOKEN` 非空高熵；③AC7/ADR 已明示 MANUAL 期间 inbox_watcher 暂停；④`base_page` 定义规范回锚点页（默认列表页）。

- **N1**：真机限速吞吐能否达 150/天，实测
- gpt.pkpp.cn 速率/并发上限核对（决策+视觉+巡检三路争用）
- **root 底层注入（Follow-up）**：M0.5 input 若被检测，启用 root sendevent/minitouch 抗检测
- droidrun 后端作 uia 替代（其设备侧 Portal 权限面需单独评估）
- 多账号/多设备（schema 已带 device_id/account_id，锁/配额按设备实例化）
- CVE-2026-0073：M0 记录设备版本/补丁，受影响则优先 USB

---

## 12. ADR

**Decision**：对齐 AutoGLM 的 adb 原语+scrcpy+Web Terminal+可插拔双后端；**但 pipeline 为唯一投递权威、分层 agent 降级为无业务决策权的受限单步执行器**；**安全主防线 = localhost+token+Origin 统一所有控制端点，adb 白名单仅纵深防御**；仅真机（已 root，标准 adb，**默认 USB**）；uv+`.env`；前端 React。业务加固（半自动/限速/幂等/巡检/锁/M0.5）沿用 v4 并扩展。

**Drivers**：①对齐 AutoGLM ②抗改版+控成本 ③低封号+安全。

**Alternatives considered**：纯视觉(B,token 高→兜底后端)；控件树单一(C,无兜底→后端之一)；**全 agent 范式（planner 自主投递）→否决**（架空幂等+配额，且本项目是固定业务流不需 open-ended agent）；**adb 白名单作主防线→否决**（rooted 设备 `adb shell su`=整机 RCE，白名单≈0）；模拟器→去；root 注入→Follow-up；Vue3→React。

**Why chosen**：`ControlBackend` 统一控件树/视觉为可切后端，既"和 AutoGLM 一样"又控成本；pipeline 单一权威避免双决策头架空安全机；端点鉴权前置守住真机远控面。

**Consequences**：
- 维护两后端+切换判据；M0.5 三探针定主次
- planner 无业务决策权（牺牲 AutoGLM 式自主性，换确定性+安全）
- 安全主防线是鉴权边界，adb 白名单仅辅助；高危 adb 子命令受控
- 默认 USB 牺牲部分便利，换 adb 网络暴露面收敛（CVE-2026-0073/蠕虫）
- 简历/截图外发须最小化（PII 边界）
- 单设备并发由模式互斥（手动/Terminal 仅 MANUAL）+ 单写者锁仲裁
- v4 幂等/巡检/锁/熔断沿用并扩展为双后端+三 VLM 消费者

**Follow-ups**：M0.5 控件<50% 或 input 被检测则复议（视觉主/root 注入）；N1 吞吐校验；gpt.pkpp.cn 速率核对；多设备按 device 实例化；droidrun Portal 权限面评估；设备打 2026-05 补丁。

---

## 13. 前端功能模块设计（React，对齐 AutoGLM）

**技术栈**：React 19 + TS + Vite + TanStack Router + Radix/shadcn + Tailwind；React Context + hooks；redaxios(REST)+socket.io-client(投屏)+WS(终端)+SSE(事件)，**所有通道经统一鉴权**；i18n 中英。

### 页面（`src/routes/`）
| 路由 | 模块 | 关键功能 |
|---|---|---|
| `index` | 设备面板 | 设备列表/状态/USB 连接；今日投递/配额；当前后端指示 |
| `screen` | 投屏+手动操控 | ScrcpyPlayer(WebCodecs)；**仅 MANUAL 可操控**；一键接管(切 MANUAL)；降级截图 |
| `jobs` | 岗位流 | 抓取卡片+LLM 打分+理由+硬规则标记；加黑/置顶 |
| `applications` | 投递看板 | 状态机泳道；**SENDING 待人工确认队列**(确认已发/未发→归位)；失败原因 |
| `inbox` | HR 收件箱 | 巡检新回复+未读角标；**一键接管**(切 MANUAL+置 taken_over+跳投屏)；无自动回复 |
| `rules` | 画像/筛选规则 | 画像/硬规则/LLM 阈值/招呼语 prompt/限速；即时生效 |
| `scheduled` | 定时任务 | 巡检/夜停/限速窗口 |
| `logs` | 日志与成本 | SSE 日志+trace+**三路 VLM 成本/熔断状态**+后端切换 |
| `terminal` | Web Terminal | xterm；**仅 MANUAL 可用**；adb REPL+高危子命令确认；鉴权提示 |
| `settings` | 设置 | 模型配置(key 走 .env 不在前端存)；**后端主次手动覆盖(优先于自动判据)**；语言/主题 |

### 核心组件
DeviceSidebar/DeviceCard；ScrcpyPlayer(+useScreenshotPolling 降级)；JobCard/ScoreBadge；ApplicationBoard/PendingConfirmQueue(↔AC8)；InboxPanel/TakeoverButton(切 MANUAL)；RuleConfigForm/CronEditor；TerminalPanel(xterm)；CostMonitor(三路 VLM 熔断↔AC13)；ui/*(shadcn)。

### 数据流与半自动 UX
投屏 Socket.IO(H.264→WebCodecs)；事件 SSE；终端 WS；全部经鉴权。**半自动主线**：收件箱新回复→点接管→自动切 MANUAL+置 taken_over+跳投屏人工接手；投递看板 SENDING 待确认对接崩溃恢复(AC8)。前端验收并入 AC16。

---

## 附：MVP 最小闭环
**M0 → M0.5(三探针) → M1(adb+scrcpy+terminal+鉴权) → M2(uia_backend+受限 executor) → M3(单岗位投递+巡检) → M4 子集(投屏+投递看板+收件箱)**：真机 USB 连接 → 三探针确认后端与 input 可用性 → 抓 1 屏岗位 → gpt-5.5 打分(pipeline 决策) → 两阶段发招呼 → 巡检发现回复 → 收件箱一键接管。

---

## 变更记录 (Changelog)

- **v6（2026-06-08）✅ consensus 达成（Architect + Critic 终审均 APPROVED）**：复审 v5 REJECT 后收口（含并入 P2：端点枚举补 /devices·/config、token 强度、MANUAL 巡检暂停明示、锚点页定义）。**P0-A** planner 去业务决策权（pipeline 唯一投递权威、planner 降级受限单步执行器、executor 不旁路 dispatcher/RateLimiter，AC19）；**P0-B** 安全模型反转（localhost+token+Origin 统一 terminal/control/scrcpy/SSE 全端点为主防线，adb 白名单降为纵深防御、高危子命令管控，AC12 重写）；**P0-C** adb 传输暴露面（默认 USB、WiFi 受控临时、CVE-2026-0073 风险行，AC17）；**P0-D** M0.5 增 input 反检测第三探针（AC15）。收口 C3（手动/Terminal 仅 MANUAL 模式互斥，AC10）、C4（inbox 强制控件树+三路 VLM 共享熔断，AC13）、C5/C7（后端切换原子+手动覆盖优先，AC4）、G3（PII 外发最小化，AC18）。沿用 v4 幂等/巡检/锁/M0.5。
- **v5**：架构性更新（AutoGLM 式 adb/双后端/分层 agent/scrcpy/Terminal/React/uv/.env/仅真机）。
- **v4**：consensus APPROVED，收口 C1–C4。
- **v3**：解决 4×P0+3×P1+M0.5。
- **v2**：进入 consensus + RALPLAN-DR。
- **v1**：初版。
