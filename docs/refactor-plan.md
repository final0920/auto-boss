# boss-autoapply 精简重构计划（slim-v3）

**状态**: `pending approval`（本计划不自动执行，待批准）
**日期**: 2026-06-10
**关系**: 取代 `docs/boss-autoapply-plan.md`(v6) 的执行路线；v6 仅留作历史决策档案
**生成方式**: `/oh-my-claudecode:ralplan`（共识：Planner→Architect→Critic）
**评审状态**: ✅ **consensus 达成（第 2 轮 Architect + Critic 均 APPROVED）**。第 1 轮 ITERATE→v2 吸收 M-1~M-6/C1~C3/M-A~M-D；第 2 轮 Architect 复审确认充分吸收、新发现 N-1/N-2→v3 吸收 N-1~N-5；Critic 终审 APPROVE（残留均为实现期注意项，见 §11.6-8）

---

## 0. TL;DR

把对齐 AutoGLM-GUI 的过度设计砍掉，收敛为一条聚焦 Boss 直聘的链路：

```
条件设置(结构化硬过滤) → LLM 打分 → 真机投递(BossDriver,已跑通) → DB 留存全量记录 → 前端核对看板
                                                  └→ 同一循环内巡检 HR 回复 → 收件箱通知(回复在真机手动处理)
```

两条贯穿全计划的硬约束：
1. **前后端严格一致** —— 每个规则字段/数据字段/状态，DB → 后端消费 → API → 前端控件四点对齐，以 §5.3 一致性矩阵逐字段验收。
2. **唯一设备驱动 + 唯一投递权威** —— 单一常驻 `runner` 循环是真机的唯一驱动者（投递与巡检都在它内部串行编排），dispatcher 状态机是唯一投递权威；删除一切并行驱动源与设备层决策后门。

---

## 1. 目标与非目标

### 目标
1. **条件设置**（参考 Ocyss/boss-helper）：薪资区间、城市/区域黑白名单、关键词必含/排除、公司规模、学历/经验门槛、HR 活跃度、已沟通去重——全部结构化、前端可配、后端真实消费。
2. **先硬过滤，再 LLM 打分**：过滤不过不调 LLM（省成本）；打分≥阈值才投。
3. **投递**复用已跑通的 `BossDriver`（root dump + su input），纳入 dispatcher 幂等状态机与限速。
4. **DB 留存 + 核对看板**：投了哪家、岗位、JD 全文、薪资区间、城市、评分+理由、实发招呼语、状态、时间，前端可查可筛。
5. **巡检闭环真机验证**：runner 循环内巡检 HR 新回复 → diff → 收件箱通知；HR 回复人在真机上处理。

### 非目标（明确不做）
- 多账号/多设备、模拟器
- 视觉(VLM)后端、双后端切换、分层 agent
- Web 端操控真机（投屏只读）、Web Terminal
- 自动回复 HR、自动处理验证码（geetest → 停+通知）
- root sendevent 抗检测（现 root `su input` 已可用）
- RulesConfig 版本协商/多端热部署（localhost 单机自用，前后端同版本部署，见 §5.2）

---

## 2. 现状基线与实锤问题

### 已跑通资产（不重写）
- `backend/app/pages/boss.py` `BossDriver`：`prepare_device / scrape_jobs / apply_card / auto_apply_batch`，真机 2/2 投递成功；详情页读到`"继续沟通"`=已投是天然的设备级幂等护栏。**该文件当前未被 git 跟踪，必须入库。**
- `pipeline/dispatcher.py`：`dispatch_one` PENDING→CLAIMED→SENDING→SENT/FAILED 两阶段幂等 + `scan_sending` 启动自检 + 夜停 + RateLimiter 入口，结构可用。注意：`_execute_apply`(:135) 现 import `app.agent.executor`、`dispatch_loop`(:154) 是批量循环——二者均按 §7 改造。
- `pipeline/collector.py`：jd_hash(SHA256 company+title+jd[:200]) 去重建 Application(PENDING)，可用。
- scrcpy 投屏链路（`scrcpy/{streamer,protocol,sio}` + 前端 `ScrcpyPlayer`）已打通。

### 实锤断裂（本计划要修的根因）
| # | 断裂 | 证据 |
|---|---|---|
| B1 | 前端请求 `GET/PUT /config/rules`，后端无此路由；PUT 落入 `/{key}` 通配，`body.get("value")` 取空 → 规则存成空垃圾行 | `frontend/src/routes/rules.tsx:37,56` ↔ `backend/app/api/config_api.py:45-58` |
| B2 | 前端"硬性规则"自由文本 textarea，后端 `hard_filter` 只认结构化 `allowed_cities/min_salary_k`，字段名都不同 → 前端配的后端不消费 | `rules.tsx:7-15,96-110` ↔ `pipeline/screener.py:30,70-96` |
| B3 | `screen_application(hard_rules)` 无调用方传真实配置，`DEFAULT_HARD_RULES` 为空 → **硬过滤从未生效** | `screener.py:30-35,215-224` |
| B4 | `auto_apply_batch` 绕过 pipeline：抓到 JD 即弃(`_jd`)、不写 DB、无打分、无配额 | `pages/boss.py:297-325`、`backend/_rd_autoapply.py` |
| B5 | LangGraph 跑 3 节点直线流程，纯过度设计 | `screener.py:180-207` |

---

## 3. 目标架构与投递流程模型 v2

### 架构（砍后）
```
React 控制台: 概览 | 岗位流 | 投递看板 | 收件箱 | 规则 | 投屏(只读) | 日志 | 定时 | 设置
   │ REST + SSE + Socket.IO(只读视频)   ← localhost+token+Origin 鉴权（沿用 security/auth.py）
┌──▼──────────────────────────────────────────────┐
│ FastAPI + python-socketio                        │
│  api/{pipeline,jobs,applications,messages,       │
│      config_api(/config/rules),logs,devices,     │
│      scheduled,media} + scrcpy/sio(只读)         │
│  ┌ pipeline/runner.py(新)＝唯一设备驱动 ────────┐ │
│  │ 单一常驻 asyncio.Task（lifespan 拥有）        │ │
│  │ 状态机 IDLE→RUNNING→PAUSED_GEETEST→STOPPED   │ │
│  │ 循环内串行编排：                              │ │
│  │   采集→prefilter→[开详情→补全→screen          │ │
│  │     →dispatcher.dispatch_one]→回列表          │ │
│  │   每 K 卡 / 到点 → 巡检一轮(inbox 步骤)        │ │
│  └──────────────────────────────────────────────┘ │
│  rules.py(新)＝RulesConfig 唯一契约               │
│  SQLite: Job(扩) Application(+DUP) Message Config │
│          RunLog(瘦) Quota(瘦)                     │
└──────────────┬───────────────────────────────────┘
          adb(USB, root su) → 真机 Boss 直聘
```

**并发模型（消解双驱动 C2 / 锁争用 M-D）**：runner 是**唯一**驱动真机的常驻 Task，投递与巡检在**同一循环内串行编排**——不存在两个驱动源、不存在投递 vs 巡检的锁竞争。删除 APScheduler 的 `_dispatcher_job`/`_inbox_watcher_job`（§7）。保留一个轻量 `asyncio.Lock` 仅用于"未来手动单步 API vs runner"的互斥，主链单 Task 天然串行无需争用；锁的 acquire/release 一律 `try/finally` 或 `async with`（防异常泄漏）。

**runner 生命周期（补 M-A 缺口）**：
- **拥有者**：`main.py` lifespan `startup` 时 `scan_sending()` 先跑（处理上次残留 SENDING）→ 再 `create_task(runner.run())`；`shutdown` 时 `runner.stop()`（翻 flag）+ `await task`（真正等停）。
- **状态机**：`IDLE`（未启动）→`RUNNING`→`PAUSED_GEETEST`（检测到验证码，循环 break、置 paused_reason）→`STOPPED`。
- **`RUNNING` 两子态 + 流转（补 N-1）**：
  - **投递+巡检**（默认）：滚动采集→逐卡投递；每处理 K 卡 或 距上次巡检 > `inbox_poll_min_sec`，则在卡间隙（回列表安全点）插一轮巡检。
  - **仅巡检**（`daily_limit` 满 或 夜停）：**停投、不滚列表采集**；改为固定节奏 `open_message_tab→scrape_conversations→回列表`，每轮 sleep `inbox_poll_min~max_sec`——巡检节奏不再寄生于"卡间隙"，自带轮询源。
  - **子态切换**：每次主循环开头重算 `_is_night_stop()` 与配额余量（`Quota` 按 date 跨日归零）——满足投递条件→投递+巡检子态，否则→仅巡检子态。子态是同一循环的分支，无需独立 Task。
- **单例 + run 幂等（补 N-2）**：runner 为进程内单例，持当前 `asyncio.Task` 句柄。`POST /pipeline/run` **先断言无活跃 Task（`task is None or task.done()`）否则拒绝（409 已在运行）**——杜绝 PAUSED 态重复点 run 造出第二个 Task（即复活双驱动）。
- **两条停止路径，均干净回收（补 N-2）**：① 正常 stop：`/pipeline/stop` 置 `_running=False`→循环退出→lifespan/端点 `await task` 回收；② geetest 自停：循环内检测验证码 → **显式置 `_running=False` + 状态 `PAUSED_GEETEST` + paused_reason** → 函数返回（Task done），后续 `/pipeline/run` 因旧 Task 已 done 而允许干净重启。
- **控制面**：`POST /pipeline/run`（IDLE/PAUSED/STOPPED→RUNNING，幂等创建 Task）、`POST /pipeline/stop`（→STOPPED）、`GET /pipeline/status`（状态+子态+paused_reason+今日已投/配额）。geetest 恢复 = 人工真机过验证 → 前端点启动 → `/pipeline/run` 重新拉起。

### 投递流程模型 v2（按真机事实更新）
真机事实：用户在 Boss App 开了"自动打招呼"，**点"立即沟通"即完成投递**，无需打字/发送 → 原 v6 的"两阶段发送+ADBKeyboard+大窗口人工确认"简化。**DUP 预检前移，决策权不下放设备层（消 C3/M-3）**：

```
runner 对每张幸存卡片（已过 prefilter）：
  1. 开详情页 → 补全字段（规模/学历/经验/HR活跃/JD）
  2. 读沟通按钮文案 observed_label（apply_card 只上报中立事实，不判状态）
  3. ── DUP 预检（在扣配额、写 SENDING 之前）──
       observed_label=="继续沟通" → dispatcher 置 Application=DUP，return；
       【不调用 check_and_consume_apply、不写 SENDING】→ A5「DUP 不计配额」成立
  4. 详情级 screen（硬过滤→LLM 打分）：不过 → FAILED(fail_reason)；过 → 置 CLAIMED(commit)
  5. dispatcher.dispatch_one(app_id)：扣配额(check_and_consume) → 写 SENDING → 点 btn_chat →
       跳 ChatRoomActivity 且出现"由你发起的沟通" → SENT(sent_at, 抓 tv_content_text 存 greeting=实发招呼语)
       未跳/未验证 → FAILED(reason)
  6. 回列表页（卡间 interval 在锁外 sleep）
启动自检 scan_sending：残留 SENDING → 看板"待人工确认"队列（真机核对后点 已发/未发）
geetest/验证码检测（前台包名含 captcha/verify/geetest）→ runner→PAUSED_GEETEST + 通知
```
- `ApplicationStatus` 增 **`DUP`**（dispatcher 据设备上报译出，非设备层自定）；**DUP 由 `PENDING` 直接置入，不经 CLAIMED/SENDING**（预检在 screen 之前，记录仍是 collector 建的 PENDING；补 N-5）；其余枚举不变。
- 决策权边界（守原则④）：**设备层(`apply_card`)只上报 `observed_label` 等观测事实，所有状态判定(DUP/CLAIMED/SENT/FAILED)由 screener/dispatcher 做**。runner 只**编排**（调 collector/screener/`dispatch_one`），**不重写投递逻辑**——投递永远走 `dispatcher.dispatch_one`。
- SENDING 窗口缩到"点按钮→验证"几秒；DUP 在其之前判定，不进 SENDING，故不污染 scan_sending 恢复语义。

### 数据流关键点（真机约束决定）
列表页**抓不到 JD**，JD 与公司规模/学历/经验/HR活跃度在**详情页**。筛选拆两级：
- **列表级 prefilter**（零额外设备动作）：薪资区间、城市/区域、标题/公司关键词、列表标签里的学历/经验（`fl_require_info` 有则用）、jd_hash 去重。
- **详情级 screen**（开详情一次顺手做完）：补全 JD+详情字段 → 详情级硬过滤 → LLM 打分 → 通过则**当场投递**（人已在详情页，避免回列表重排）。

runner 持锁/节奏粒度＝**单卡设备动作**（继承被删 device_mode 的 act 粒度持锁直觉）：每处理完一张卡片回到列表页安全点后，卡间 `interval` 在锁外 sleep；巡检在卡间隙触发，最坏等待≈一张卡处理时长（量化 A7）。

---

## 4. 删除清单 / 保留清单

### 删除（D）—— 含【删除连锁】反向依赖善后（补 C1/M-1）
> 纪律：**先列依赖 → 改/删调用点 → 再删模块 → rg 复核零残留**（§8 M1）。直接删模块会在 import 期崩，无法增量验证。

| 删除目标 | 反向依赖善后（删模块前必须先处理） |
|---|---|
| `backend/app/backends/`（base/manager/uia_backend/vision_backend） | `inbox_watcher.py:26,52` 依赖 `BackendManager` → 随 inbox 重写消除；`rate_limiter.py` 三路 VLM 消费者(死代码)删除 |
| `backend/app/agent/`（planner/executor） | `dispatcher.py:143` `_execute_apply` import → 改调 BossDriver；`tests/test_planner_no_bypass.py` → 删除或重写 |
| `backend/app/automation/device_mode.py` | **5 处活引用先改**：`scheduler.py:25,44`(删 job)、`api/devices.py:51-75`(删 `/devices/mode` 两端点 + 前端 DeviceSidebar 同步去掉模式切换)、`api/applications.py:112-113`(takeover 去掉 `set_mode(MANUAL)`，与"无 MANUAL 态"自洽)、`api/control.py:13`(随 control 删)、`main.py:185-190`(health 去 device_mode 字段) |
| `backend/app/terminal/` + `api/terminal.py` | `main.py:120` `get_terminal_service` import + `:155-179` router 注册 → 删除 |
| `backend/app/api/control.py` | `main.py` router 注册删；前端 screen 页去 control 调用（§7） |
| `backend/app/probe/` | 无活引用（一次性工具，使命完成） |
| `frontend/src/routes/terminal.tsx`、`components/TerminalPanel.tsx`、`components/CostMonitor.tsx` | `__root.tsx:41` navItems `/terminal` 入口删；`routeTree.gen.ts` 重新生成 |
| `pages/{base_page,list_page,detail_page,chat_page}.py` | 被 boss.py 取代；**rg 确认零引用后删** |
| models 残留字段：`BackendType`、`RunLog.{vlm_calls,backend_switches,backend_used,paused_reason}`、`Quota.vlm_count` | 见 §6 重建表 |
| `config.py`/.env.example 残留：`vlm_daily_limit,default_backend,t_ctrl,t_ocr` | 同步删 |
| 依赖 `langgraph`（rg 确认仅 `screener.py` 引用，属实）→ pyproject 移除，`uv sync` | §7 screener 改纯函数 |
| `pipeline/dispatcher.py` 的 `dispatch_loop`(:154) | 删 `_dispatcher_job` 后成死代码 → 一并删（runner 用 `dispatch_one`） |
| 根目录/backend 的 `_rd_*.py/.txt`、`_boss_ui_*.xml`、`scrcpy-screen.jpeg` | 有价值 rid 沉淀进 boss.py 注释/docs 后删；`.gitignore` 加 `_rd_*`、`*_boss_ui*.xml` |

### 保留（K）
| 路径 | 形态 |
|---|---|
| `adb/{device,inputs,screencap,connection,appinfo,_run}` | 原样（device.py 含未提交的空格修复，入库） |
| `pages/boss.py` | **git add**，扩方法（§7） |
| `pipeline/{collector,dispatcher,rate_limiter}` | 改造（§7） |
| `pipeline/screener.py` | 重写为纯函数（§7） |
| `pipeline/runner.py`（新） | §3 唯一驱动循环 |
| `scrcpy/{streamer,protocol,sio}` + `api/media.py` + 前端 `ScrcpyPlayer` + `routes/screen.tsx` | 只读投屏（screen 页摘除点击控制） |
| `llm/{client,prompts}`、`security/auth.py`、`notify.py`、`db.py`、`main.py` | 小改对齐 |
| `automation/inbox_watcher.py` | **重写**（非小改）：删全部 BackendManager/VLM，基于 BossDriver 真机读消息（§7） |
| `scheduler.py` | **改造**：删 dispatcher/inbox job 与 device_mode 判断；若仅剩夜停窗口配置则退化为常量/Config（§7） |
| 前端 `routes/{index,jobs,rules,applications,inbox,logs,scheduled,settings}` + `DeviceSidebar/JobCard/ApplicationBoard/InboxPanel/RuleConfigForm/CronEditor/ThemeToggle` | 改造（§7） |

---

## 5. 【核心】条件设置前后端贯通

### 5.1 唯一契约：`backend/app/rules.py` 定义 `RulesConfig`（pydantic）

```python
class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")   # 未知字段 422，防前后端漂移
    # —— 列表级硬过滤 ——
    salary_min_k: float = 0      # 期望薪资下限(K)。0=不限。判据: 区间相交
    salary_max_k: float = 0      # 期望薪资上限(K)。0=不限
    allowed_cities: list[str] = []    # 空=不限；包含匹配 Job.area
    blocked_areas: list[str] = []     # 区域黑名单，包含匹配
    include_keywords: list[str] = []  # 空=不限；列表级对 title，详情级对 title+jd，含其一即过
    exclude_keywords: list[str] = []  # 命中即滤；作用域 title+company+jd（公司黑名单并入此项）
    # —— 详情级硬过滤（字段缺失/None → 放行并在 reasons 标注 missing:<field>）——
    company_scales: list[str] = []    # 允许的规模桶，空=不限；桶: 0-20人/20-99人/100-499人/500-999人/1000-9999人/10000人以上
    my_degree: str = ""               # 我的学历。岗位要求 > 我 → 滤。序: 不限<高中<中专/中技<大专<本科<硕士<博士。空=不限
    my_experience_years: int = 0      # 我的年限。岗位要求下限 > 我 → 滤。0=不限
    hr_active_within_days: int = 0    # HR 活跃天数门槛。0=不限。映射: 在线/刚刚/今日→1, 3日→3, 本周→7, 本月→30, 更久→999
    dedup_contacted: bool = True      # 设备级"继续沟通"跳过(→DUP) + jd_hash 去重
    # —— LLM ——
    llm_threshold: int = 80
    profile: str = ""                 # 候选人画像，喂打分 prompt
    greeting_prompt: str = ""         # 预留。当前 Boss App 端"自动打招呼"，系统不发文本；UI 注明置灰
    # —— 投递节奏 ——
    daily_limit: int = 100
    interval_min_sec: int = 20
    interval_max_sec: int = 90
    night_stop_start: str = "23:00"
    night_stop_end: str = "07:00"
```
取舍：`min_headcount`(招聘人数) 并入 `company_scales`；公司黑名单并入 `exclude_keywords`（作用域含 company）。**不设 `version` 字段**——localhost 单机自用、前后端同版本部署，YAGNI；未来确需多端演进时再引入 version + load 时升版迁移语义（避免"定义了不消费"反模式复发）。

### 5.2 贯通链（单一来源，四点对齐）
```
DB Config(key="rules", value=RulesConfig JSON)
  ↕ rules.py: load_rules()(缺省回退 pydantic 默认值)/save_rules()(全量校验后整体写)
  ↕ REST: GET /api/config/rules → 完整 RulesConfig；PUT /api/config/rules(body=RulesConfig, extra=forbid→422)
      （config_api.py 显式路由注册在 /{key} 之前——model-info 已踩过路由序坑）
  ↕ 前端 api.ts: interface RulesConfig 与 pydantic 字段一一同名同型
  ↕ rules.tsx 结构化表单（替换自由文本 textarea）
消费点: runner 每轮循环开始 load_rules() → 传 screener.prefilter/screen + dispatcher 节奏参数
```
`.env Settings` 仅作首次缺省（score_threshold/daily_apply_limit/interval 填充 RulesConfig 默认）；运行期 **Config.rules 唯一权威**，规则页保存即下轮生效，无需重启。
**前提假设**：前后端同版本部署（PUT 为全量覆盖，多端旧前端会把新字段重置为默认；localhost 单机不触发，故接受）。

### 5.3 前后端一致性矩阵（验收逐行核对）
| 字段 | 前端控件（rules.tsx） | 后端消费点 |
|---|---|---|
| salary_min_k / salary_max_k | 双数字输入"期望薪资(K)" | screener.prefilter 薪资区间相交 |
| allowed_cities | 标签输入(回车添加) | screener.prefilter |
| blocked_areas | 标签输入 | screener.prefilter |
| include_keywords | 标签输入 | screener.prefilter(title) + screen(title+jd) |
| exclude_keywords | 标签输入 | screener.prefilter + screen(title+company+jd) |
| company_scales | 多选桶 checkbox 组 | screener.screen |
| my_degree | 下拉(学历序) | screener.prefilter(列表标签有则用) + screen 兜底 |
| my_experience_years | 数字输入 | 同上 |
| hr_active_within_days | 下拉(不限/1/3/7/30) | screener.screen |
| dedup_contacted | 开关 | collector(jd_hash) + dispatcher(据 apply_card 上报"继续沟通"→DUP) |
| llm_threshold | 滑杆 0-100 | screener.screen 阈值判定 |
| profile | textarea | llm/prompts 打分 prompt |
| greeting_prompt | textarea(置灰注明"预留：当前由 Boss App 自动打招呼") | 暂无消费（预留字段，契约保留） |
| daily_limit | 数字输入 | rate_limiter.check_and_consume_apply |
| interval_min/max_sec | 双数字输入 | runner 卡间投递间隔 |
| night_stop_start/end | 两个 time 输入 | dispatcher._is_night_stop（改读 rules） |

---

## 6. DB 变更与迁移

### Job 表新增列（支撑核对看板与详情级过滤）
`salary_min_k REAL`、`salary_max_k REAL`（解析 "10-15K·13薪"/"2000-150000元/月"/"面议"→(0,0)放行）、`degree TEXT`、`experience TEXT`、`company_scale TEXT`、`finance_stage TEXT`、`hr_active TEXT`、`hr_name TEXT`、`detail_fetched_at DATETIME`。
> 不加 job_url：App 内无稳定 URL 可取，以 jd_hash 为业务标识。
> 存量行新列为 NULL；screener 所有比较前 `is None → 放行 + reasons.append("missing:<field>")`（**None-safe，补 M-C**）。详情/列表都可能写 `degree/experience`，**详情值覆盖列表值**（详情更权威）。

### Application
- `status` 枚举增 `DUP`（`status` 在 SQLite 是 **TEXT 列，加枚举值零迁移**，补 S-6）；`greeting` 语义改为**实发招呼语**（投递成功后从聊天页 `tv_content_text` 抓回存证）。

### 迁移脚本 `backend/scripts/migrate_001_slim.py`（裸 sqlite3，不经 SQLModel）
执行契约（补 M-C）：**停服务 → 跑 migrate → 启服务**。原因：`main.py:79` lifespan 每次启动 `init_db()`(create_all) 对已存在旧表**不会 ALTER**，新列必须由本脚本手动加；`create_all` 仅负责全新库建表。
1. 备份 `data/boss_autoapply.db` → `data/boss_autoapply.db.bak-<ts>`
2. 裸 `ALTER TABLE job ADD COLUMN ...`×9（纯增列，存量无损）
3. **重建** `run_log`、`quota`（SQLite 无法删列；`vlm_*` 是 NOT NULL 无默认，模型删字段后 INSERT 会炸 → 建新表迁数据：quota 迁 date+apply_count；run_log 按新结构重建，旧日志可弃）
4. 清掉 B1 产生的空 `rules` 垃圾 Config 行

---

## 7. 改造清单（按文件）

### 后端
| 文件 | 改造 |
|---|---|
| `rules.py`（新） | §5.1 契约 + load/save |
| `pipeline/screener.py` | **去 LangGraph 重写为纯函数**：`prefilter(job, rules)->(passed, fail_reason)`、`screen(job, rules)->ScreenResult{passed_hard, score, reasons, final}`；薪资/学历/经验/活跃度解析器；**所有比较 None-safe**（缺失→放行+missing 标注）；单测覆盖 NULL/None/边界 |
| `pipeline/runner.py`（新） | §3 唯一驱动 Task：状态机(IDLE/RUNNING/PAUSED_GEETEST/STOPPED)+子态(投递+巡检/仅巡检)；单卡粒度、卡间 interval 锁外；编排 collector→prefilter→[详情→DUP预检→screen→dispatch_one]→巡检；锁 `try/finally`；geetest 检测→PAUSED；`start/stop/status` |
| `pipeline/dispatcher.py` | `_execute_apply` 改调 `BossDriver`（删 agent import）；**DUP 预检前移**：执行前据 `apply_card` 上报的 `observed_label`，"继续沟通"→置 DUP 且**不扣配额、不写 SENDING**；夜停改读 rules；SENT 时抓实发招呼语；**删 `dispatch_loop`**（死代码）；`dispatch_one` 的 `account_id/device_id` 单设备单账号固定 "default"，CLAIMED 守卫保留为无害双保险（N-3） |
| `pipeline/collector.py` | RawJob 增列表标签字段(degree/experience)；入库写 salary_min/max_k 解析结果 |
| `pages/boss.py` | git add；新增 `scrape_detail_fields()`(详情 规模/融资/学历/经验/HR活跃/HR名, rid 待 D0 确认)、`read_chat_button_label()→observed_label`(已有, 仅上报事实)、`capture_sent_greeting()`、`open_message_tab()/scrape_conversations()`(巡检)、geetest 探测；`auto_apply_batch` 标 deprecated(仅留手工冒烟) |
| `pipeline/rate_limiter.py` | 删 VLM 路；只留 apply 配额(读 rules.daily_limit) |
| `automation/inbox_watcher.py` | **重写**（非小改）：删 BackendManager/VLM/vision 降级；改为 runner 调用的巡检步骤——`open_message_tab`→`scrape_conversations`→与 Message 表 diff→新回复建 Message+SSE 通知+置 `Application.taken_over` 待办→回列表 |
| `scheduler.py` | **改造**：删 `_dispatcher_job`/`_inbox_watcher_job` 与 device_mode 判断（runner 取代二者）；保留项若仅夜停窗口则并入 Config |
| `api/pipeline.py`（新） | `POST /pipeline/run`、`POST /pipeline/stop`、`GET /pipeline/status`、`POST /pipeline/collect`(可选手动采集) |
| `api/config_api.py` | 增 `GET/PUT /config/rules`（注册顺序在 `/{key}` 前） |
| `api/devices.py` | **删 `/devices/mode` 两端点**（GET/POST，device_mode 删后无意义） |
| `api/applications.py` | takeover 去 `set_mode(MANUAL)`；列表查询补新字段、状态(含 DUP)/关键词筛选参数 |
| `api/{jobs,messages}.py` | 补新字段、筛选参数 |
| `models.py / config.py` | §4 删除项落地 |
| `main.py` | lifespan：`scan_sending()` → `create_task(runner.run())`；shutdown `runner.stop()`+`await`；删 control/terminal router 与 `get_terminal_service`；health 去 device_mode |
| `docs/REALDEVICE_GUIDE.md` | 重写匹配精简系统（删探针/终端/操控章节） |

### 前端
| 文件 | 改造 |
|---|---|
| `routes/rules.tsx` + `RuleConfigForm` | 结构化表单（§5.3 全字段，分组：薪资地点/关键词/公司岗位要求/HR与去重/LLM/节奏）；对接 `/api/config/rules` |
| `routes/applications.tsx` + `ApplicationBoard` | **核对看板**：表格列 公司/岗位/薪资区间/城市/评分/状态(含 DUP)/sent_at；行展开抽屉：JD 全文、评分理由、实发招呼语、失败原因、时间线；筛选：状态/关键词/日期；SENDING 待确认队列保留 |
| `routes/jobs.tsx` + `JobCard` | 显示结构化标签(薪资/城市/学历/经验/规模/HR活跃) + 评分理由 + 被过滤原因（fail_reason 可见，验证硬过滤生效） |
| `routes/inbox.tsx` + `InboxPanel` | 新回复列表（HR 名/公司/岗位/最后消息/时间）+ 未读红点 + "已在真机处理"标记；删一键接管/切模式 |
| `routes/screen.tsx` | 摘除点击/拖拽→control 调用，纯只读播放 + 截图降级 |
| `routes/index.tsx` | 概览：设备在线/今日投递/配额余量/runner 状态(+子态+paused_reason)/最近投递；启停按钮 |
| `DeviceSidebar` | 删 terminal 入口、删模式切换控件 |
| `__root.tsx` / `routeTree.gen.ts` | 删 `/terminal` navItem；重新生成路由树 |
| `api.ts` | RulesConfig interface + pipeline/api 类型对齐 |

---

## 8. 里程碑与实施步骤

### M1 精简手术（半天）
1. 建分支 `refactor/slim-v1`；先提交现有未跟踪成果（boss.py、device.py/screener.py 改动）为基线 commit
2. **按删除连锁纪律**（§4）：`rg` 列出 `device_mode|BackendManager|get_terminal_service|require_manual|agent\.|backends|probe|vlm|CostMonitor|TerminalPanel|dispatch_loop` 全部引用 → **先改/删调用点**（devices `/mode`、applications takeover、main health/router、scheduler jobs、前端 navItem）→ **再删模块** → `rg` 复核零残留
3. models/config 清理；pyproject 删 langgraph；`uv sync`；后端可启动、前端可 build、`uv run pytest` 无 import-error（删/迁 `test_planner_no_bypass.py`；`test_models.py` 的 `LEGAL_TRANSITIONS` 加 `PENDING→DUP`；核对 `test_dispatcher_idempotent.py` 补 DUP/夜停用例）
4. `.gitignore` 增调试产物；清理 `_rd_*`

### M2 契约与数据（1 天）
5. `rules.py` + 迁移脚本(裸 sqlite3，停服务执行) + `GET/PUT /config/rules` + 前端结构化表单（§5 全量）
6. **D0 真机 rid 采样**（M3 起步的硬前置）：详情页/消息页各 dump 一次，固化 规模/融资/学历/经验/HR活跃/会话列表 rid 进 boss.py 常量区；**若关键控件无稳定 rid → 评估该字段降级为"仅 LLM 软判"并回看 A3 证据链**
7. screener 纯函数重写 + 解析器单测（薪资/学历/经验/活跃度 + NULL/None 边界）

### M3 投递流水线真机闭环（1 天）
8. runner 状态机+单卡循环 + dispatcher 接 BossDriver + DUP 预检前移 + 实发招呼语抓取
9. `api/pipeline`（run/stop/status）+ 前端概览启停 + lifespan 拥有 runner
10. **真机 E2E**：规则设真实条件，批量 ≥5 投递；验证 过滤→打分→投递→DB 全字段留存；故意设 `salary_min_k=99` 验证全员 FAILED（硬过滤生效证据）；"继续沟通"岗位→DUP 且配额不变

### M4 核对看板与巡检闭环（1 天）
11. applications 核对看板 + jobs 页改造
12. inbox 巡检步骤重写 + inbox 页；**真机验证**：投递后等 HR 回复（或小号回发）→ runner 巡检在卡间隙触发 → 一周期内收件箱出现新消息+通知
13. 子态验证：daily_limit 满后进入"仅巡检"子态，仍能巡检到 HR 回复

### M5 收尾（半天）
14. logs/scheduled/settings 页对齐（settings 只留模型只读信息/主题/语言）
15. REALDEVICE_GUIDE 重写；README 更新；验收 A1–A11 过单
16. 合并 `refactor/slim-v1` → master

---

## 9. 验收标准

| # | 标准 | 验证方法 |
|---|---|---|
| A1 | `/config/rules` GET 返完整 RulesConfig；PUT 全量回写 round-trip 等值；未知字段 422 | curl 三连 |
| A2 | **一致性矩阵逐行过**：§5.3 每字段有控件、保存→刷新值不丢、后端消费点真实读取 | 表单全填→保存→重载比对 + 看 RunLog |
| A3 | 硬过滤生效证据链：`salary_min_k=99` → 下轮全部 FAILED(薪资低于下限)，看板可见原因；详情级过滤同理（D0 后确认 rid 可得，否则注明降级字段） | 真机一轮 |
| A4 | LLM 只对过滤幸存者调用：RunLog llm 调用数 == prefilter+详情过滤幸存数 | 日志计数 |
| A5 | 真机 E2E 批量 ≥5：成功率 ≥90%；全程经 dispatcher 状态机；**"继续沟通"→DUP 且不调用 check_and_consume_apply（配额数不变）、不写 SENDING** | 真机批量 + 配额计数比对 |
| A6 | 看板核对：公司/岗位/薪资区间/城市/JD全文/评分+理由/实发招呼语/状态(含DUP)/时间/失败原因 全可见可筛 | 人工核对 |
| A7 | 巡检闭环：HR 新回复 → 投递+巡检子态在卡间隙触发（最坏等待≤一张卡处理时长）、仅巡检子态按 `inbox_poll` 固定轮询；≤1 巡检间隔内收件箱+通知 | 真机验证 + 计时 |
| A8 | 投屏只读：screen 页可看；全页面无任何 control 请求（network 审计），`/control`、`/devices/mode` 均 404 | 浏览器审计 |
| A9 | 删除完整性：rg 零残留引用；langgraph 出依赖；`uv run uvicorn` 启动无错；**`uv run pytest` 全绿（无 import-error）**；`pnpm build` 无错 | CI 式检查 |
| A10 | 节奏与幂等：达 daily_limit 拒投；间隔∈[min,max]；夜停拒投；杀进程重启→SENDING 进待确认队列、无二次发送 | 注入测试 |
| A11 | runner 生命周期：lifespan 启动 scan_sending 先于 runner；stop 后 Task 真停（无悬挂）；geetest→PAUSED_GEETEST 且 status 暴露 paused_reason；异常不泄漏锁；**PAUSED/RUNNING 态重复点 `/pipeline/run` 不产生第二个 Task（返 409）**；**daily_limit 满进仅巡检子态仍巡检、配额次日归零后自动回投递子态** | 故障注入 |

---

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| **删除连锁致 import 崩**（C1） | §4 删除连锁表 + §8 M1「先改调用点→再删模块」纪律 + rg 双向复核 + pytest 门禁(A9) |
| **双驱动争锁/双扣配额**（C2） | 架构改为单一 runner 循环统一编排投递+巡检；删 APScheduler dispatcher/inbox job + dispatch_loop |
| **runner 生命周期未定义**（M-A） | §3 状态机 + lifespan 拥有 + 锁 try/finally + geetest→PAUSED 恢复路径(A11) |
| **DUP 违反 A5/原则④**（C3） | DUP 预检前移到扣配额/写 SENDING 之前；设备层只上报 observed_label，dispatcher 译状态 |
| **巡检 SLA 不可达**（M-D） | runner 持锁粒度=单卡，卡间隙让巡检插入；A7 量化为"≤一张卡处理时长" |
| SQLite 迁移失误（M-C） | 裸 sqlite3 ALTER + 停服务执行契约 + 备份 .bak；screener None-safe |
| 详情页 rid 与预期不符 | D0 前置采样；字段缺失→放行+`missing:<field>`；关键控件无 rid→该字段降级 LLM 软判 |
| Boss 改版列表/详情结构 | rid 常量集中 boss.py 顶部；解析失败计数告警 |
| LLM 成本失控 | 先硬过滤；runner 每轮 LLM 调用计数入 RunLog；llm_threshold 可调 |
| 风控/验证码 | 限速+随机间隔+夜停+拟人滑动沿用；geetest→PAUSED+通知 |

**回滚路径（成对，补 S-5）**：分支制（master 不动）→ 回滚 = **`git` 回退到 migration 前 commit + 还原 `.bak` DB 文件**，二者缺一即崩（新代码读旧库或旧代码读新库都会失败）。任一里程碑失败可独立回退该 commit。

---

## 11. 开放问题（实现期确认，不阻塞批准）
1. **D0 采样 rid**（详情 公司规模/融资/学历/经验/HR活跃/HR名；消息 tab 会话列表项）：**不阻塞批准，但阻塞 M3 起步**，须在 M2 末（步骤6）完成；若关键控件无稳定 rid，相关详情级硬过滤降级为 LLM 软判，并回看 A3。
2. 会话→Application 匹配：按 HR名+公司/岗位 best-effort，未匹配会话也进收件箱（标"未关联"）。
3. `Job.degree/experience` 列表标签与详情值的覆盖优先级：**详情覆盖列表**（详情更权威），screen 阶段以详情为准。
4. 巡检是否跟随夜停：当前定为跟随（减少夜间设备活动），可后续放开。
5. `pages/{base,list,detail,chat}_page.py` 删除前 rg 引用复核（预期零）。
6. **K 卡巡检阈值**（§3 投递+巡检子态「每处理 K 卡插一轮巡检」）：`K` 取默认值（建议 5）并入 Config 可调；时间维 OR 兜底（`距上次巡检 > inbox_poll_min_sec`）已封顶最坏延迟，故非阻断。
7. **PAUSED_GEETEST 跨进程重启**：当前为内存态，进程被杀重启会经 lifespan 直接回 RUNNING 再戳一次真机（下一循环重测前台包名、一周期内自愈回 PAUSED）；若要更稳，把 paused_reason 落 Config，重启时若上次为 PAUSED_GEETEST 则起始置 IDLE 等人工点 run。
8. **夜停单一真值源**：`dispatcher._is_night_stop` 与 runner 子态判夜停**必须都读 `load_rules()` 的 `night_stop_*`**，避免常量/rules 两套真值源在边界期打架（同理 `test_dispatcher_idempotent.py` 的 mock 目标须从 `agent.executor` 改为 BossDriver）。

---

## 12. ADR & Changelog

### ADR（本轮共识决策）
- **Decision**：砍 AutoGLM 抽象层，收敛为「结构化硬过滤→LLM 打分→BossDriver 真机投递→DB 看板→同循环巡检」，**单一 runner 常驻循环为唯一设备驱动**，dispatcher 状态机为唯一投递权威，RulesConfig 为前后端唯一契约。
- **Drivers**：①核对看板是第一公民 ②修复前后端断裂(B1-B5) ③流程贴真机约束(JD在详情页/列表重排/root注入)。
- **Alternatives considered**：执行层 全删直连(选)/executor 薄层/先功能后清理；并发 单 runner 统一循环(选)/双 Task 共用锁(被 C2/M-D 否决)/APScheduler 双 job(被双驱动否决)；DUP 设备层判定(被 C3/原则④否决)/预检前移(选)；筛选 两级(选)/全详情级；投递 详情页当场(选)/回列表二次定位(重排风险否决)。
- **Why chosen**：单 runner 统一循环天然消除双驱动与锁争用（C2/M-A/M-D 一并解决），是比"双 Task 共用锁"更简单且更少 bug 的方案；DUP 预检前移守住"设备层只执行"不变量并满足 A5。
- **Consequences**：投递与巡检串行（吞吐与巡检延迟此消彼长，用单卡粒度+卡间隙巡检平衡）；inbox_watcher/scheduler 实为重写；迁移需停服务窗口。
- **Follow-ups**：D0 rid 可得性；详情字段覆盖优先级；多端若需要再引入 RulesConfig version。

### Changelog
- **v3（2026-06-10）**：吸收共识第 2 轮 Architect 复审（判定 M-1~M-6 全部充分吸收）新发现的 N-1~N-5：
  - **N-1**：§3 补「仅巡检」子态独立巡检节奏（inbox 固定轮询、不寄生卡间隙、不滚列表）+ 子态切换（每轮开头重算夜停/配额）；A7/A11 同步。
  - **N-2**：§3 补 runner 单例 + Task 句柄 + `/pipeline/run` 幂等（活跃 Task 拒 409）+ geetest 自停显式置 `_running=False`/PAUSED_GEETEST（两条停止路径均干净回收）；A11 加重复 run 不双开判据。
  - **N-3**：§7 `dispatch_one` account/device 固定 default。**N-4**：§8 步骤3 pytest 清单补 `test_models.py`（加 PENDING→DUP）。**N-5**：§3 标注 DUP 由 PENDING 直接置入不经 CLAIMED/SENDING。
- **v2（2026-06-10）**：吸收共识第 1 轮 Critic(ITERATE) + Architect 全部必修项：
  - **C1/M-1**：§4 增删除连锁表（device_mode 5 处反向依赖善后）、§8 改「先改调用点→再删模块」步骤序。
  - **C2/M-4**：架构改单一 runner 统一循环，删 APScheduler dispatcher/inbox job + dispatch_loop（消双驱动）。
  - **C3/M-3**：DUP 预检前移（扣配额/写 SENDING 之前）、设备层只上报 observed_label、§5.3/§3 改写、A5 加配额不变判据。
  - **M-A/M-2**：§3 补 runner 状态机 + lifespan 拥有 + 锁 try/finally + geetest 恢复 + A11。
  - **M-B/M-5**：inbox_watcher/scheduler 标重写、A9 加 pytest 门禁。
  - **M-C/M-6**：§6 迁移裸 sqlite3 + 停服务契约、screener None-safe、status TEXT 零迁移注明。
  - **M-D/S-2**：runner 持锁粒度=单卡、A7 量化。
  - **S-1**：删 version 字段（YAGNI）。**S-3**：§3 措辞改"runner 编排、投递调 dispatch_one"。**S-4**：§5.2 注前后端同版本前提。**S-5**：§10 回滚成对。**S-6**：status TEXT 注明。**S-7**：§11 D0 措辞改"不阻塞批准但阻塞 M3 起步"。
- **v1（2026-06-10）**：初版（Direct 模式），目标/删除/保留/改造/DB迁移/里程碑/验收/风险。
