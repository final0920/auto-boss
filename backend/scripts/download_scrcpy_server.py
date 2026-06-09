"""
下载 scrcpy-server JAR 到 app/scrcpy/resources/scrcpy-server.jar。

用法：
    uv run python scripts/download_scrcpy_server.py [--version 3.2]

下载走代理 http://127.0.0.1:7890（可通过 --proxy 覆盖，或传空字符串跳过代理）。
目标路径：backend/app/scrcpy/resources/scrcpy-server.jar
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# 默认版本与代理
DEFAULT_VERSION = "3.2"
DEFAULT_PROXY = "http://127.0.0.1:7890"

# JAR 写入路径（相对脚本位置：scripts/ 的上级即 backend/）
_RESOURCES_DIR = Path(__file__).parent.parent / "app" / "scrcpy" / "resources"
_JAR_NAME = "scrcpy-server.jar"

# GitHub release asset URL 模板
_URL_TEMPLATE = (
    "https://github.com/Genymobile/scrcpy/releases/download/"
    "v{version}/scrcpy-server-v{version}"
)


def _build_opener(proxy: str) -> urllib.request.OpenerDirector:
    if proxy:
        proxy_handler = urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy}
        )
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(version: str = DEFAULT_VERSION, proxy: str = DEFAULT_PROXY) -> Path:
    """下载指定版本 scrcpy-server，返回保存路径。已存在则跳过。"""
    _RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _RESOURCES_DIR / _JAR_NAME

    url = _URL_TEMPLATE.format(version=version)
    print(f"[scrcpy] 目标版本: v{version}")
    print(f"[scrcpy] 下载地址: {url}")
    if proxy:
        print(f"[scrcpy] 使用代理: {proxy}")
    print(f"[scrcpy] 保存路径: {dest}")

    if dest.exists():
        sha = _sha256_hex(dest)
        print(f"[scrcpy] 已存在，跳过下载。SHA-256: {sha}")
        return dest

    opener = _build_opener(proxy)
    print("[scrcpy] 开始下载...")
    try:
        with opener.open(url, timeout=60) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"[scrcpy] 下载失败: {exc}", file=sys.stderr)
        print(
            "提示：若网络不通，请手动下载并重命名：\n"
            f"  {url}\n"
            f"  → {dest}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    dest.write_bytes(data)
    sha = _sha256_hex(dest)
    print(f"[scrcpy] 下载完成，{len(data):,} 字节，SHA-256: {sha}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 scrcpy-server JAR")
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"scrcpy 版本号（默认 {DEFAULT_VERSION}）",
    )
    parser.add_argument(
        "--proxy",
        default=DEFAULT_PROXY,
        help=f"HTTP 代理（默认 {DEFAULT_PROXY}，传空字符串跳过）",
    )
    args = parser.parse_args()
    download(version=args.version, proxy=args.proxy)


if __name__ == "__main__":
    main()
