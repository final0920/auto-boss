"""test_planner_no_bypass.py — AC19：planner/executor 无直达 adb-send 旁路。

两类验证：
  1. 静态扫描：检查 agent/planner.py 和 agent/executor.py 源码，
     禁止出现直接调用 run_adb / AdbDevice 写操作的路径。
  2. 运行时断言（executor 已实现时）：确认 executor 调用链经过 dispatcher。
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).parent.parent / "app"
_AGENT_DIR = _BACKEND_ROOT / "agent"

# 禁止在 planner/executor 中直接出现的符号（adb 直写旁路）
_FORBIDDEN_DIRECT_CALLS = {
    "run_adb",
    "run_adb_global",
    "humanized_tap",
    "humanized_swipe",
    "motionevent_down",
    "motionevent_up",
    "send_text_once",
}

# executor 必须引用的 dispatcher 相关符号
_REQUIRED_DISPATCH_SYMBOLS = {
    "dispatch_one",
    "dispatch_loop",
    "check_and_consume_apply",
}


# ---------------------------------------------------------------------------
# AST 扫描辅助
# ---------------------------------------------------------------------------

class _CallCollector(ast.NodeVisitor):
    def __init__(self):
        self.calls: set[str] = set()
        self.imports: set[str] = set()

    def visit_Call(self, node: ast.Call):
        match node.func:
            case ast.Name(id=name):
                self.calls.add(name)
            case ast.Attribute(attr=attr):
                self.calls.add(attr)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[-1])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)


def _scan_file(path: Path) -> tuple[set[str], set[str]]:
    if not path.exists():
        return set(), set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    c = _CallCollector()
    c.visit(tree)
    return c.calls, c.imports


# ---------------------------------------------------------------------------
# 静态测试
# ---------------------------------------------------------------------------

class TestStaticNoBypass:
    @pytest.mark.parametrize("filename", ["planner.py", "executor.py"])
    def test_no_direct_adb_calls(self, filename):
        path = _AGENT_DIR / filename
        calls, imports = _scan_file(path)
        if not path.exists():
            pytest.skip(f"{filename} 尚未实现")

        violations = _FORBIDDEN_DIRECT_CALLS & (calls | imports)
        assert not violations, (
            f"{filename} 包含禁止的直达 adb 调用: {violations}\n"
            "任何发送操作必须经 dispatcher.dispatch_one + RateLimiter（AC19）"
        )

    @pytest.mark.parametrize("filename", ["planner.py", "executor.py"])
    def test_no_subprocess_import(self, filename):
        path = _AGENT_DIR / filename
        _, imports = _scan_file(path)
        if not path.exists():
            pytest.skip(f"{filename} 尚未实现")
        assert "subprocess" not in imports, (
            f"{filename} 直接 import subprocess，可能旁路 adb 原语层（AC19）"
        )

    def test_executor_references_dispatcher(self):
        path = _AGENT_DIR / "executor.py"
        if not path.exists():
            pytest.skip("executor.py 尚未实现")
        calls, imports = _scan_file(path)
        all_symbols = calls | imports
        has_dispatch = bool(_REQUIRED_DISPATCH_SYMBOLS & all_symbols)
        assert has_dispatch, (
            "executor.py 未引用 dispatcher/rate_limiter，"
            "投递发送必须经 dispatcher 状态机（AC19）"
        )

    def test_planner_no_business_decision_methods(self):
        path = _AGENT_DIR / "planner.py"
        if not path.exists():
            pytest.skip("planner.py 尚未实现")

        # planner 不应定义包含 send/dispatch/apply/submit 的顶级函数/类方法
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden_patterns = ["send", "dispatch", "apply", "submit"]
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name.lower()
                if not name.startswith("_") and any(p in name for p in forbidden_patterns):
                    # 排除合法的辅助函数（如 _apply_patch）
                    violations.append(node.name)

        assert not violations, (
            f"planner.py 定义了疑似业务决策函数: {violations}\n"
            "planner 只应包含定位/点击/输入执行逻辑，投递决策属于 dispatcher（AC19）"
        )


# ---------------------------------------------------------------------------
# 运行时断言（executor 实现后生效）
# ---------------------------------------------------------------------------

class TestRuntimeNoBypass:
    def _install_stubs(self):
        for mod_name, attrs in [
            ("app.config", {"settings": MagicMock(daily_apply_limit=150)}),
            ("app.db", {"engine": MagicMock()}),
        ]:
            if mod_name not in sys.modules:
                stub = types.ModuleType(mod_name)
                for k, v in attrs.items():
                    setattr(stub, k, v)
                sys.modules[mod_name] = stub

    @pytest.mark.anyio
    async def test_executor_does_not_call_run_adb_directly(self):
        self._install_stubs()
        try:
            import app.agent.executor as executor_mod
        except ImportError:
            pytest.skip("executor 尚未实现")
        if not hasattr(executor_mod, "execute_apply"):
            pytest.skip("execute_apply 未定义")

        called_run_adb = []

        def _spy(*args, **kwargs):
            called_run_adb.append(args)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("app.adb._run.run_adb", side_effect=_spy):
            with patch("app.pipeline.dispatcher.dispatch_one", new=AsyncMock(return_value="SENT")):
                try:
                    await executor_mod.execute_apply(1)
                except Exception:
                    pass

        assert not called_run_adb, (
            "executor.execute_apply 直接调用了 run_adb，违反 AC19 旁路禁令"
        )
