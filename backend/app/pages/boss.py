"""Boss 直聘 App 真机页面操作 —— 基于真机联调抓取的 resource-id + root input。

真机发现固化（2026-06-09 联调）：
- MIUI 禁止普通 adb 的 input 注入(INJECT_EVENTS)，所有点击/滑动走 root(AdbDevice 已统一 su)。
- uiautomator dump 走 root 最稳（不依赖 uiautomator2 server 的 wakeUp 注入）。
- 列表页(MainActivity 职位tab)：rv_list 容器 + boss_job_card_view 卡片；
  字段 tv_position_name/tv_salary_statue/tv_company_name/tv_distance + fl_require_info 标签。
- 详情页(BossJobPagerActivity)：tv_description(完整JD) + btn_chat(立即沟通) + iv_back。
- 聊天页(ChatRoomActivity)：tv_contact_time 含"由你发起的沟通" = 投递成功。
- 投递动作 = 点 btn_chat 跳转聊天页（用户开"自动打招呼"，Boss 自动发招呼语，无需输入/发送）。
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from app.adb.device import AdbDevice
from app.pipeline.collector import RawJob

PACKAGE = "com.hpbr.bosszhipin"

# resource-id 末段常量（真机抓取）
RID_JOB_CARD = "boss_job_card_view"
RID_POSITION_NAME = "tv_position_name"
RID_SALARY = "tv_salary_statue"
RID_COMPANY = "tv_company_name"
RID_DISTANCE = "tv_distance"
RID_JD = "tv_description"
RID_CHAT_BTN = "btn_chat"          # 「立即沟通」
RID_CONTACT_TIME = "tv_contact_time"  # 聊天页"由你发起的沟通"
APPLY_OK_MARK = "由你发起的沟通"

# ---- D0 采样固化（2026-06-10，docs/refactor-plan.md §8 步骤6）----
# 列表卡片扩展字段（全部列表级可得，prefilter 直接可用）
RID_STAGE = "tv_stage"                # 融资阶段 '未融资'
RID_SCALE = "tv_scale"                # 公司规模 '100-499人'
RID_EMPLOYER = "tv_employer"          # HR '刘女士 · 人事专员'
RID_ACTIVE = "tv_active_status"       # HR 活跃 '今日回复10+次'
RID_REQUIRE_INFO = "fl_require_info"  # 经验/学历/技能标签容器（子节点无 rid）
# 详情页（BossJobPagerActivity 首屏）
RID_D_LOCATION = "tv_required_location"   # '武汉·洪山区·光谷'
RID_D_EXP = "tv_required_work_exp"        # '1-3年'
RID_D_DEGREE = "tv_required_degree"       # '本科'
RID_D_BOSS_NAME = "tv_boss_name"          # '刘女士'
RID_D_BOSS_TITLE = "tv_boss_title"        # '武汉钧泽科技有限公司 • 人事专员'
RID_D_BOSS_LABEL = "boss_label_tv"        # '17分钟前回复 | 今日回复10+次'
# 主页底部 tab：文本节点(tv_tab_N) bounds 折叠为[0,0][0,0]，必须点容器 cl_tab_N
RID_TAB_JOB = "cl_tab_1"
RID_TAB_MSG = "cl_tab_3"
TAB_JOB_FALLBACK_XY = (135, 2247)
TAB_MSG_FALLBACK_XY = (675, 2247)
# 消息页会话列表（RecyclerView 项；系统通知项无 tv_position，借此过滤）
RID_MSG_NAME = "tv_name"          # HR 名 '蒋女士'
RID_MSG_POSITION = "tv_position"  # '上海君兴 | Java' —— 会话↔Application 匹配键
RID_MSG_LAST = "tv_msg"           # 最后一条消息全文
RID_MSG_TIME = "tv_time_v2"       # '13:01' / '昨天 23:56'
RID_MSG_STATUS = "iv_msg_status"  # '[新招呼]'(HR主动) / '[送达]'(我方消息)；HR 回复后无此前缀
RID_MSG_SEARCH = "et_input"       # 消息页搜索框（页面到位判据）

# 列表标签解析（fl_require_info 子节点）
DEGREE_LABELS = ("学历不限", "初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士")
_EXP_TAG_RE = re.compile(r"^(\d+-?\d*年(以上|以内)?|经验不限|应届|在校)")

_DEVICE_DUMP_PATH = "/sdcard/_boss_ui.xml"
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class JobCard:
    """列表页一张岗位卡片：RawJob + 卡片在屏幕上的点击中心。"""
    raw: RawJob
    cx: int
    cy: int


def _bounds_center(bounds: str) -> tuple[int, int]:
    m = _BOUNDS_RE.match(bounds or "")
    if not m:
        return 0, 0
    left, top, right, bottom = (int(m.group(i)) for i in range(1, 5))
    return (left + right) // 2, (top + bottom) // 2


def _rid_last(rid: str) -> str:
    return rid.split("/")[-1] if rid else ""


class BossDriver:
    """单台真机上的 Boss 直聘操作。dump 走 root，点击走 AdbDevice(root)。"""

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.dev = AdbDevice(serial)
        self._u2 = None

    def _u2dev(self):
        if self._u2 is None:
            import uiautomator2 as u2
            self._u2 = u2.connect(self.serial)
        return self._u2

    # ------------------------------------------------------------------
    # 设备准备：唤醒 + 解锁 + 保持唤醒 + 打开 Boss
    # ------------------------------------------------------------------

    def prepare_device(self) -> None:
        """唤醒屏幕、解锁 keyguard、充电保持唤醒、打开 Boss 直聘。"""
        self.dev._shell_su("input keyevent 224")   # WAKEUP
        time.sleep(0.6)
        self.dev._shell_su("wm dismiss-keyguard")
        time.sleep(0.6)
        self.dev._shell_su("svc power stayon true")
        # 干净重启 Boss（避免停在上次的聊天/详情页），启动到主页职位 tab
        self.dev.am_force_stop(PACKAGE)
        time.sleep(1.0)
        self.dev.monkey_start(PACKAGE)
        time.sleep(5.0)  # 等启动（可能有开屏广告）

    def current_activity(self) -> str:
        r = self.dev._shell(
            "dumpsys window | grep mCurrentFocus", check=False
        )
        return r.stdout.strip()

    # ------------------------------------------------------------------
    # 控件树 dump（root uiautomator）
    # ------------------------------------------------------------------

    def dump(self) -> Optional[ET.Element]:
        """root uiautomator dump（一次性命令，dump 完即释放）。

        用原生一次性 `uiautomator dump` 取控件树 XML，不用 uiautomator2 常驻
        server：u2 的 click/注入在本机 MIUI 被拒(SecurityException)，常驻 server
        亦无必要。点击统一走 root `su input`（device.py）。
        注：早期"dump 后 su tap 失效"实为 device.py 的 input f-string 缺空格
        (input tap{x}→input tap540) 静默失败，与 dump/UiAutomation 无关，已修复。
        """
        self.dev._shell_su(f"uiautomator dump {_DEVICE_DUMP_PATH}", timeout=20.0)
        local = f"_boss_ui_{self.serial}.xml"
        self.dev._run(["pull", _DEVICE_DUMP_PATH, local], check=False, timeout=20.0)
        try:
            with open(local, "rb") as f:
                return ET.fromstring(f.read())
        except (FileNotFoundError, ET.ParseError):
            return None

    # ------------------------------------------------------------------
    # 列表页采集
    # ------------------------------------------------------------------

    def scrape_page(self) -> list[JobCard]:
        """解析当前列表页可见的岗位卡片为 JobCard 列表。"""
        root = self.dump()
        if root is None:
            return []
        cards: list[JobCard] = []
        for node in root.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) != RID_JOB_CARD:
                continue
            fields = {
                RID_POSITION_NAME: "", RID_SALARY: "", RID_COMPANY: "", RID_DISTANCE: "",
                RID_STAGE: "", RID_SCALE: "", RID_EMPLOYER: "", RID_ACTIVE: "",
            }
            req_tags: list[str] = []
            for sub in node.iter("node"):
                rid = _rid_last(sub.attrib.get("resource-id", ""))
                if rid in fields and not fields[rid]:
                    fields[rid] = sub.attrib.get("text", "")
                elif rid == RID_REQUIRE_INFO:
                    for tag in sub.iter("node"):
                        t = (tag.attrib.get("text") or "").strip()
                        if t:
                            req_tags.append(t)
            title = fields[RID_POSITION_NAME].strip()
            if not title:
                continue
            cx, cy = _bounds_center(node.attrib.get("bounds", ""))
            cards.append(JobCard(
                raw=RawJob(
                    title=title,
                    company=fields[RID_COMPANY].strip(),
                    salary=fields[RID_SALARY].strip(),
                    area=fields[RID_DISTANCE].strip(),
                    degree=next((t for t in req_tags if t in DEGREE_LABELS), ""),
                    experience=next((t for t in req_tags if _EXP_TAG_RE.match(t)), ""),
                    company_scale=fields[RID_SCALE].strip(),
                    finance_stage=fields[RID_STAGE].strip(),
                    hr_name=fields[RID_EMPLOYER].split("·")[0].strip(),
                    hr_active=fields[RID_ACTIVE].strip(),
                ),
                cx=cx, cy=cy,
            ))
        return cards

    def scroll_list(self) -> None:
        """上滑列表加载更多（root swipe，非直线拟人）。"""
        self.dev.humanized_swipe(540, 1800, 540, 700, steps=8, step_delay_ms=25)
        time.sleep(1.2)

    def scrape_jobs(self, max_jobs: int = 20, max_scroll: int = 6) -> list[RawJob]:
        """滚动采集去重后的 RawJob 列表（按 公司+职位 去重）。"""
        seen: set[tuple[str, str]] = set()
        result: list[RawJob] = []
        for _ in range(max_scroll):
            for card in self.scrape_page():
                key = (card.raw.company, card.raw.title)
                if key in seen:
                    continue
                seen.add(key)
                result.append(card.raw)
                if len(result) >= max_jobs:
                    return result
            self.scroll_list()
        return result

    # ------------------------------------------------------------------
    # 投递动作：定位卡片 → 详情 → 读JD → 立即沟通 → 验证
    # ------------------------------------------------------------------

    def _find_node_center(self, root: ET.Element, rid_last: str) -> Optional[tuple[int, int]]:
        for node in root.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) == rid_last:
                return _bounds_center(node.attrib.get("bounds", ""))
        return None

    def _tap_until(self, cx: int, cy: int, target_kw: str,
                   retries: int = 4, checks: int = 6, wait: float = 0.6) -> bool:
        """点击坐标后轮询 activity 直到含 target_kw；input 注入偶发丢失时自动重试。"""
        for _ in range(retries):
            self.dev.tap(cx, cy)
            for _ in range(checks):
                time.sleep(wait)
                if target_kw in self.current_activity():
                    return True
        return False

    def open_job_detail(self, card: "JobCard") -> Optional[str]:
        """点开卡片进入详情页(带重试)，返回完整 JD(tv_description)。未进入返回 None。"""
        if not self._tap_until(card.cx, card.cy, "JobPager"):
            return None
        detail = self.dump()
        if detail is None:
            return ""
        for node in detail.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) == RID_JD:
                return node.attrib.get("text", "")
        return ""

    def find_chat_button(self, detail: ET.Element) -> Optional[tuple[int, int]]:
        """定位「立即沟通」按钮（位置/布局有多种，按控件特征而非硬坐标）。
        优先 resource-id=btn_chat；兜底 text 含 立即沟通/继续沟通。"""
        c = self._find_node_center(detail, RID_CHAT_BTN)
        if c is not None:
            return c
        for node in detail.iter("node"):
            txt = node.attrib.get("text", "") or ""
            if ("立即沟通" in txt or "继续沟通" in txt) and node.attrib.get("clickable") == "true":
                return _bounds_center(node.attrib.get("bounds", ""))
        # 再兜底：不限 clickable
        for node in detail.iter("node"):
            txt = node.attrib.get("text", "") or ""
            if "立即沟通" in txt or "继续沟通" in txt:
                return _bounds_center(node.attrib.get("bounds", ""))
        return None

    def tap_chat_and_verify(self) -> bool:
        """点「立即沟通」(带重试)，验证进入聊天页且出现"由你发起的沟通"。"""
        detail = self.dump()
        if detail is None:
            return False
        btn = self.find_chat_button(detail)
        if btn is None:
            return False
        if not self._tap_until(btn[0], btn[1], "ChatRoomActivity"):
            return False
        chat = self.dump()
        if chat is not None:
            for node in chat.iter("node"):
                if APPLY_OK_MARK in (node.attrib.get("text", "") or ""):
                    return True
        return "ChatRoomActivity" in self.current_activity()

    def back_to_list(self) -> None:
        """从聊天/详情返回列表（最多按两次返回）。"""
        self.dev.press_back()
        time.sleep(1.0)
        if "MainActivity" not in self.current_activity():
            self.dev.press_back()
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # 详情页字段补全（D0 固化）
    # ------------------------------------------------------------------

    def _find_text(self, root: ET.Element, rid_last: str) -> str:
        for node in root.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) == rid_last:
                return node.attrib.get("text", "") or ""
        return ""

    def scrape_detail_fields(self, detail: ET.Element) -> dict[str, str]:
        """从详情页控件树提取补全字段（screener 详情级硬过滤用）。

        注：公司规模/融资阶段在列表卡片(tv_scale/tv_stage)已可得，
        详情首屏不提供；此处只补详情独有字段，缺失返回空串。
        """
        return {
            "location": self._find_text(detail, RID_D_LOCATION),     # '武汉·洪山区·光谷'
            "experience": self._find_text(detail, RID_D_EXP),
            "degree": self._find_text(detail, RID_D_DEGREE),
            "hr_name": self._find_text(detail, RID_D_BOSS_NAME),
            "hr_title": self._find_text(detail, RID_D_BOSS_TITLE),   # '公司 • 职务'
            "hr_active": self._find_text(detail, RID_D_BOSS_LABEL),  # '17分钟前回复 | 今日回复10+次'
            "jd": self._find_text(detail, RID_JD),
        }

    # ------------------------------------------------------------------
    # 消息 tab 与会话列表（M4 inbox_watcher 底座，D0 固化）
    # ------------------------------------------------------------------

    def _tap_main_tab(self, rid_last: str, fallback_xy: tuple[int, int]) -> None:
        """点主页底部 tab：优先 cl_tab_N 容器中心；dump 失败用固化坐标兜底。"""
        root = self.dump()
        c = self._find_node_center(root, rid_last) if root is not None else None
        if c is None or c == (0, 0):
            c = fallback_xy
        self.dev.tap(c[0], c[1])
        time.sleep(2.0)

    def open_message_tab(self) -> bool:
        """切到消息 tab。返回是否到位（出现联系人搜索框）。"""
        self._tap_main_tab(RID_TAB_MSG, TAB_MSG_FALLBACK_XY)
        root = self.dump()
        return root is not None and self._find_node_center(root, RID_MSG_SEARCH) is not None

    def back_to_job_tab(self) -> None:
        """切回职位 tab（巡检结束回锚点）。"""
        self._tap_main_tab(RID_TAB_JOB, TAB_JOB_FALLBACK_XY)

    def scrape_conversations(self) -> list[dict[str, str]]:
        """解析消息页当前可见会话列表。

        返回 [{hr_name, position, last_msg, time, status, unread}]：
        - position 形如 '上海君兴 | Java'（会话↔Application 匹配键）；
          系统通知项（无 position）已过滤。
        - status: '[新招呼]'(HR主动) / '[送达]'(我方消息) / ''；
          ''+unread>0 且 last_msg 非我方招呼语 ≈ HR 新回复（由 inbox_watcher 判定）。
        """
        root = self.dump()
        if root is None:
            return []
        want = {
            RID_MSG_NAME: "hr_name", RID_MSG_POSITION: "position",
            RID_MSG_LAST: "last_msg", RID_MSG_TIME: "time", RID_MSG_STATUS: "status",
        }
        rows: list[tuple[int, str, str]] = []
        for node in root.iter("node"):
            text = (node.attrib.get("text") or "").strip()
            if not text:
                continue
            m = _BOUNDS_RE.match(node.attrib.get("bounds", ""))
            if not m:
                continue
            left, top = int(m.group(1)), int(m.group(2))
            kind = want.get(_rid_last(node.attrib.get("resource-id", "")))
            # 未读角标：badge_view 内无 rid 纯数字 TextView，位于头像右上(左缘 130~220)
            if kind is None and not _rid_last(node.attrib.get("resource-id", "")) \
                    and text.isdigit() and 130 <= left <= 220:
                kind = "unread"
            if kind:
                rows.append((top, kind, text))
        rows.sort()
        convs: list[dict[str, str]] = []
        cur: dict[str, str] | None = None
        pending_unread = ""
        for _top, kind, text in rows:
            if kind == "unread":
                pending_unread = text   # 角标先于 tv_name 出现，挂到下一个会话
                continue
            if kind == "hr_name":
                if cur is not None:
                    convs.append(cur)
                cur = {"hr_name": text, "position": "", "last_msg": "",
                       "time": "", "status": "", "unread": pending_unread}
                pending_unread = ""
            elif cur is not None and not cur[kind]:
                cur[kind] = text
        if cur is not None:
            convs.append(cur)
        return [c for c in convs if c["position"]]

    # ------------------------------------------------------------------
    # 批量自动投递
    # ------------------------------------------------------------------

    def read_chat_button_label(self, detail: ET.Element) -> str:
        """读详情页沟通按钮文案：立即沟通 / 继续沟通 / ''（用于跳过已投递）。"""
        for node in detail.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) == RID_CHAT_BTN:
                return node.attrib.get("text", "") or ""
        for node in detail.iter("node"):
            txt = node.attrib.get("text", "") or ""
            if "立即沟通" in txt or "继续沟通" in txt:
                return txt
        return ""

    def apply_card(self, card: "JobCard") -> tuple[str, str]:
        """对一张卡片完成投递：开详情→读JD→（未投递则）点立即沟通→验证→返回列表。

        返回 (状态, JD)。状态 ∈ {成功, 失败, 已投递, 无沟通按钮, 未进详情}。
        投递动作 = 点 btn_chat 跳聊天页，用户已开"自动打招呼"，Boss 自动发招呼语。
        """
        if not self._tap_until(card.cx, card.cy, "JobPager"):
            return "未进详情", ""
        detail = self.dump()
        if detail is None:
            self.back_to_list()
            return "失败", ""
        jd = ""
        for node in detail.iter("node"):
            if _rid_last(node.attrib.get("resource-id", "")) == RID_JD:
                jd = node.attrib.get("text", "") or ""
                break
        if "继续沟通" in self.read_chat_button_label(detail):
            self.back_to_list()
            return "已投递", jd
        btn = self.find_chat_button(detail)
        if btn is None:
            self.back_to_list()
            return "无沟通按钮", jd
        ok = self._tap_until(btn[0], btn[1], "ChatRoomActivity")
        if ok:
            chat = self.dump()
            verified = chat is not None and any(
                APPLY_OK_MARK in (n.attrib.get("text", "") or "") for n in chat.iter("node")
            )
            ok = verified or "ChatRoomActivity" in self.current_activity()
        self.back_to_list()
        return ("成功" if ok else "失败"), jd

    def auto_apply_batch(
        self, max_apply: int = 5, max_scroll: int = 4
    ) -> list[tuple[RawJob, str]]:
        """滚动采集并对未投递岗位逐个投递（点立即沟通）。

        每轮重新采集当前屏，取第一个未处理卡片投递（抗列表重排），按
        公司+职位 去重，命中"继续沟通"判为已投递跳过；达 max_apply 个成功即停。
        返回 [(RawJob, 状态), ...] 投递记录。
        """
        seen: set[tuple[str, str]] = set()
        results: list[tuple[RawJob, str]] = []
        applied = 0
        scrolls = 0
        while applied < max_apply and scrolls <= max_scroll:
            nxt: Optional[JobCard] = None
            for c in self.scrape_page():
                if (c.raw.company, c.raw.title) not in seen:
                    nxt = c
                    break
            if nxt is None:
                self.scroll_list()
                scrolls += 1
                continue
            seen.add((nxt.raw.company, nxt.raw.title))
            status, _jd = self.apply_card(nxt)
            results.append((nxt.raw, status))
            if status == "成功":
                applied += 1
        return results
