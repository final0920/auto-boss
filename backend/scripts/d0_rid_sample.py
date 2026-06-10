"""D0 rid 采样 — slim-v3 M3 硬前置（docs/refactor-plan.md §8 步骤6）。

自动流程（真机需 USB 在线、Boss 已登录）：
  1. prepare_device：唤醒/解锁/重启 Boss 到主页职位列表
  2. dump 列表页 → _rd_d0_list.txt（验证 fl_require_info 标签：学历/经验）
  3. 点第一张岗位卡进详情页 → dump → _rd_d0_detail.txt
     （目标：公司规模/融资/学历/经验/HR活跃/HR名 的 rid 或文本特征）
  4. back 回列表 → 点底部「消息」tab → dump 会话列表 → _rd_d0_msg.txt
     （目标：会话项容器/HR名/最后消息/时间/未读角标 rid）
  5. stdout 打印各页关键候选节点，人工判读后固化进 app/pages/boss.py 常量区

用法：cd backend && uv run python scripts/d0_rid_sample.py [--serial 99ede571]
输出文件均为 _rd_* 前缀（.gitignore 忽略，不污染仓库）。
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from app.pages.boss import BossDriver, _rid_last  # noqa: E402

PKG = "com.hpbr.bosszhipin"


def dump_to(driver: BossDriver, path: str) -> ET.Element | None:
    root = driver.dump()
    if root is None:
        print(f"[!] dump 失败 -> {path}")
        return None
    lines = []
    for node in root.iter("node"):
        if node.attrib.get("package") != PKG:
            continue
        rid = _rid_last(node.attrib.get("resource-id", ""))
        text = node.attrib.get("text", "")
        desc = node.attrib.get("content-desc", "")
        clk = node.attrib.get("clickable", "false")
        bounds = node.attrib.get("bounds", "")
        cls = node.attrib.get("class", "").split(".")[-1]
        if rid or text or desc:
            lines.append(f"[{rid}] text={text!r} desc={desc!r} <{cls}> click={clk} {bounds}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[*] {path}: {len(lines)} 个有效节点")
    return root


def pick(root: ET.Element, label: str, kw_re: str, show: int = 8) -> None:
    """按文本正则打印候选节点（rid 优先判读依据）。"""
    pat = re.compile(kw_re)
    print(f"  -- {label} 候选 --")
    n = 0
    for node in root.iter("node"):
        if node.attrib.get("package") != PKG:
            continue
        text = node.attrib.get("text", "") or ""
        if not text or not pat.search(text):
            continue
        rid = _rid_last(node.attrib.get("resource-id", ""))
        print(f"     [{rid or '<无rid>'}] {text!r} {node.attrib.get('bounds','')}")
        n += 1
        if n >= show:
            break
    if n == 0:
        print("     (无文本命中 — 该字段可能不在当前页或需滚动)")


def find_tap(driver: BossDriver, root: ET.Element, text_eq: str) -> bool:
    """按 text 精确匹配找节点（含父级 clickable 兜底），tap 中心点。"""
    cand = None
    for node in root.iter("node"):
        if node.attrib.get("package") != PKG:
            continue
        if (node.attrib.get("text") or "") == text_eq or (node.attrib.get("content-desc") or "") == text_eq:
            cand = node
            break
    if cand is None:
        return False
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", cand.attrib.get("bounds", ""))
    if not m:
        return False
    x = (int(m.group(1)) + int(m.group(3))) // 2
    y = (int(m.group(2)) + int(m.group(4))) // 2
    driver.dev.tap(x, y)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="99ede571")
    args = ap.parse_args()

    d = BossDriver(args.serial)

    print("== 0. 准备设备（唤醒/解锁/重启 Boss 到主页）==")
    d.prepare_device()
    time.sleep(1.5)
    print(f"   前台: {d.current_activity()}")

    print("== 1. 列表页 dump ==")
    root = dump_to(d, "_rd_d0_list.txt")
    if root is not None:
        pick(root, "学历标签(fl_require_info?)", r"^(本科|大专|硕士|博士|学历不限|高中|中专)$")
        pick(root, "经验标签", r"^\d+-?\d*年|经验不限|应届")
        cards = d.scrape_page()
        print(f"   岗位卡片: {len(cards)} 张")

    print("== 2. 详情页 dump（点第一张卡）==")
    cards = d.scrape_page()
    if not cards:
        print("[!] 列表无卡片，跳过详情采样")
    else:
        c = cards[0]
        print(f"   目标: {c.raw.title} @ {c.raw.company}")
        if d._tap_until(c.cx, c.cy, "JobPager"):
            time.sleep(1.0)
            droot = dump_to(d, "_rd_d0_detail.txt")
            if droot is not None:
                pick(droot, "公司规模", r"^\d+-?\d*人(以上)?$|^\d+人以上$")
                pick(droot, "融资阶段", r"融资|上市|天使|不需要")
                pick(droot, "学历要求", r"^(本科|大专|硕士|博士|学历不限|高中|中专)$")
                pick(droot, "经验要求", r"^\d+-?\d*年|经验不限|应届")
                pick(droot, "HR活跃度", r"活跃|在线|刚刚")
                pick(droot, "HR名/职务", r"·")
            d.back_to_list()
        else:
            print("[!] 未进详情页")

    print("== 3. 消息 tab dump ==")
    root = dump_to(d, "_rd_d0_home.txt")  # 先存主页（看 tab 栏 rid）
    tapped = False
    if root is not None:
        for label in ("消息", "聊天"):
            if find_tap(d, root, label):
                tapped = True
                print(f"   已点 tab: {label}")
                break
    if tapped:
        time.sleep(2.0)
        print(f"   前台: {d.current_activity()}")
        mroot = dump_to(d, "_rd_d0_msg.txt")
        if mroot is not None:
            pick(mroot, "会话项时间", r"^\d{1,2}:\d{2}$|昨天|前天|月")
            pick(mroot, "招呼语/最后消息", r"您好|你好|沟通|简历")
            pick(mroot, "HR名·职务", r"·")
    else:
        print("[!] 未找到消息 tab（看 _rd_d0_home.txt 人工判读 tab rid）")

    print("== D0 采样完成 ==")
    print("产物: _rd_d0_list.txt / _rd_d0_detail.txt / _rd_d0_home.txt / _rd_d0_msg.txt")
    print("下一步: 人工判读 rid -> 固化 app/pages/boss.py 常量区")


if __name__ == "__main__":
    main()
