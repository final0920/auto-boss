"""M0.5 三探针 — 真机可用性 go/no-go 报告。

探针：
  1. 控件树可得率：dump_hierarchy 抓取关键字段（resourceId/text/content-desc）
  2. 视觉后端命中率 + 单步 token 成本（截图 → gpt-5.5 定位几个固定目标）
  3. input 反检测：adb shell input tap 小样本后观测是否触发验证码/风控弹窗

用法：
    python -m app.probe.probe_backends --device <serial> [--samples 5]

真机未连接时优雅报错，提示接设备。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field


# ---------------------------------------------------------------------------
# 报告结构
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    serial: str
    # 探针1: 控件树
    uia_dump_attempts: int = 0
    uia_dump_success: int = 0
    uia_key_field_rate: float = 0.0   # (resourceId|text|content-desc) 有值的节点占比
    # 探针2: 视觉
    vision_attempts: int = 0
    vision_hits: int = 0
    vision_hit_rate: float = 0.0
    vision_avg_tokens: float = 0.0
    # 探针3: input 反检测
    input_tap_attempts: int = 0
    input_detection_triggered: bool = False
    input_detection_note: str = ""
    # go/no-go
    recommend_primary: str = ""     # "uia" | "vision"
    go: bool = False
    blocking_reason: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 探针 1：控件树可得率
# ---------------------------------------------------------------------------


def _probe_uia(serial: str, samples: int, result: ProbeResult) -> None:
    try:
        import uiautomator2 as u2
    except ImportError:
        result.errors.append("uiautomator2 未安装，跳过控件树探针")
        return

    try:
        dev = u2.connect(serial)
    except Exception as exc:
        result.errors.append(f"uia connect 失败: {exc}")
        return

    for i in range(samples):
        result.uia_dump_attempts += 1
        try:
            dump = dev.dump_hierarchy()
            import re
            nodes_raw = re.findall(r'<node\b[^>]+>', dump)
            total = len(nodes_raw)
            if total == 0:
                continue
            # 统计有 resourceId 或 text 或 content-desc 非空节点
            has_key = sum(
                1 for n in nodes_raw
                if re.search(r'resource-id="[^"]+?"', n)
                or re.search(r'text="[^"]+?"', n)
                or re.search(r'content-desc="[^"]+?"', n)
            )
            result.uia_dump_success += 1
            result.uia_key_field_rate += has_key / total
        except Exception as exc:
            result.errors.append(f"uia dump 第{i+1}次失败: {exc}")
        time.sleep(0.5)

    if result.uia_dump_success > 0:
        result.uia_key_field_rate /= result.uia_dump_success


# ---------------------------------------------------------------------------
# 探针 2：视觉后端命中率
# ---------------------------------------------------------------------------

# 固定目标列表（Boss 直聘首页常见控件）
_VISION_TARGETS = [
    "搜索岗位输入框",
    "推荐 Tab",
    "底部导航栏",
]


def _probe_vision(serial: str, result: ProbeResult) -> None:
    try:
        from app.backends.vision_backend import VisionBackend
    except ImportError as exc:
        result.errors.append(f"VisionBackend 导入失败: {exc}")
        return

    backend = VisionBackend(serial)
    try:
        backend.observe()
    except Exception as exc:
        result.errors.append(f"vision observe 失败: {exc}")
        return

    total_tokens = 0
    for target in _VISION_TARGETS:
        result.vision_attempts += 1
        try:
            from app.backends.vision_backend import screencap_png_bytes
            import base64
            png = screencap_png_bytes(serial)
            screenshot_b64 = base64.b64encode(png).decode("ascii")
            w, h = backend._get_screen_size()

            from app.backends.vision_backend import _inline_llm_locate
            coord = _inline_llm_locate(screenshot_b64, target, w, h)
            if coord is not None:
                result.vision_hits += 1
            # token 成本粗估（base64 len / 4 ≈ bytes；图片 token ≈ pixels/512）
            img_tokens = (w * h) // 512
            total_tokens += img_tokens
        except Exception as exc:
            result.errors.append(f"vision locate '{target}' 失败: {exc}")

    if result.vision_attempts > 0:
        result.vision_hit_rate = result.vision_hits / result.vision_attempts
    if result.vision_attempts > 0:
        result.vision_avg_tokens = total_tokens / result.vision_attempts


# ---------------------------------------------------------------------------
# 探针 3：input 反检测
# ---------------------------------------------------------------------------


def _probe_input_detection(serial: str, samples: int, result: ProbeResult) -> None:
    """发送小样本 tap，观测前台包名是否跳到验证/风控页面。"""
    from app.adb.device import AdbDevice
    from app.adb.appinfo import get_foreground_package

    dev = AdbDevice(serial)

    # 记录操作前包名
    before_pkg = get_foreground_package(serial) or ""

    for i in range(samples):
        result.input_tap_attempts += 1
        try:
            # 点屏幕中央，不针对具体控件
            dev.tap(540, 960)
            time.sleep(0.8)
        except Exception as exc:
            result.errors.append(f"input tap 第{i+1}次失败: {exc}")

    after_pkg = get_foreground_package(serial) or ""

    # 简单判断：前台包名是否切换到验证/安全相关包
    _CAPTCHA_HINTS = ["captcha", "verify", "security", "geetest", "slider", "validate"]
    switched = after_pkg != before_pkg and after_pkg
    if switched and any(h in after_pkg.lower() for h in _CAPTCHA_HINTS):
        result.input_detection_triggered = True
        result.input_detection_note = f"前台包切换至疑似验证页: {after_pkg}"
    elif switched:
        result.input_detection_note = f"前台包从 {before_pkg} 切换至 {after_pkg}（非验证包，可能正常导航）"
    else:
        result.input_detection_note = f"前台包未变化 ({after_pkg})，input tap 未触发明显检测"


# ---------------------------------------------------------------------------
# go/no-go 判定
# ---------------------------------------------------------------------------


def _evaluate(result: ProbeResult) -> None:
    uia_rate = result.uia_key_field_rate
    vision_rate = result.vision_hit_rate

    if result.input_detection_triggered:
        result.go = False
        result.blocking_reason = (
            "input tap 被检测为非真实触摸（触发验证），"
            "需启用 root sendevent/minitouch 方案（Follow-up AC15）"
        )
        result.recommend_primary = "vision"
        return

    if uia_rate >= 0.8:
        result.recommend_primary = "uia"
        result.go = True
    elif uia_rate >= 0.5:
        result.recommend_primary = "uia+vision"
        result.go = True
    elif vision_rate >= 0.85:
        result.recommend_primary = "vision"
        result.go = True
        result.blocking_reason = (
            f"控件树可得率 {uia_rate:.0%} < 50%，切 vision 主（成本上升，建议复议）"
        )
    else:
        result.go = False
        result.blocking_reason = (
            f"控件树可得率 {uia_rate:.0%} < 50%，且视觉命中率 {vision_rate:.0%} < 85%，"
            "建议检查设备连接 / uia 服务 / LLM 配置后重试"
        )
        result.recommend_primary = "unknown"


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def run_probe(serial: str, samples: int = 5) -> ProbeResult:
    result = ProbeResult(serial=serial)

    print(f"[探针] 目标设备: {serial}，采样次数: {samples}")
    print("[探针1] 控件树可得率...")
    _probe_uia(serial, samples, result)
    print(f"  dump 成功: {result.uia_dump_success}/{result.uia_dump_attempts}，关键字段率: {result.uia_key_field_rate:.1%}")

    print("[探针2] 视觉后端命中率...")
    _probe_vision(serial, result)
    print(f"  命中: {result.vision_hits}/{result.vision_attempts}，avg tokens≈{result.vision_avg_tokens:.0f}")

    print("[探针3] input 反检测...")
    _probe_input_detection(serial, min(samples, 3), result)
    print(f"  检测触发: {result.input_detection_triggered}，{result.input_detection_note}")

    _evaluate(result)

    verdict = "GO" if result.go else "NO-GO"
    print(f"\n[结论] {verdict} — 推荐主后端: {result.recommend_primary}")
    if result.blocking_reason:
        print(f"  阻断原因: {result.blocking_reason}")
    if result.errors:
        print(f"  错误({len(result.errors)}条):")
        for e in result.errors:
            print(f"    - {e}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="M0.5 三探针 go/no-go 报告")
    parser.add_argument("--device", required=True, help="adb 设备 serial")
    parser.add_argument("--samples", type=int, default=5, help="每项探针采样次数（默认 5）")
    parser.add_argument("--json", dest="output_json", metavar="FILE", help="将报告输出为 JSON 文件")
    args = parser.parse_args()

    # 验证设备在线
    from app.adb.connection import list_devices
    try:
        devices = list_devices()
    except RuntimeError as exc:
        print(f"错误：{exc}\n请连接设备后重试。", file=sys.stderr)
        sys.exit(1)

    online_serials = [d.serial for d in devices if d.online]
    if args.device not in online_serials:
        print(
            f"错误：设备 {args.device!r} 未在线。\n"
            f"当前在线设备: {online_serials or '（无）'}\n"
            "请确认 USB 调试已开启并重新连接。",
            file=sys.stderr,
        )
        sys.exit(1)

    result = run_probe(args.device, args.samples)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, ensure_ascii=False, indent=2)
        print(f"\n报告已写入: {args.output_json}")

    sys.exit(0 if result.go else 2)


if __name__ == "__main__":
    main()
