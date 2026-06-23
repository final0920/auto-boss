"""test_adb.py — mock subprocess 测试 adb 原语命令构造。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from app.adb._run import run_adb, run_adb_global, AdbResult, adb_exe
from app.adb.device import AdbDevice
from app.adb.screencap import screencap_png_bytes, _PNG_MAGIC


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    p = MagicMock()
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


# ---------------------------------------------------------------------------
# run_adb
# ---------------------------------------------------------------------------

class TestRunAdb:
    def test_constructs_serial_args(self):
        with patch("subprocess.run", return_value=_make_proc(b"ok")) as mock_run:
            result = run_adb("ABC123", ["shell", "input", "tap", "100", "200"])
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == [adb_exe(), "-s", "ABC123", "shell", "input", "tap", "100", "200"]

    def test_returns_adb_result(self):
        with patch("subprocess.run", return_value=_make_proc(b"hello\n")):
            result = run_adb("S1", ["shell", "echo", "hello"])
        assert isinstance(result, AdbResult)
        assert result.ok
        assert "hello" in result.stdout

    def test_raises_on_nonzero_with_check(self):
        with patch("subprocess.run", return_value=_make_proc(b"", b"error", 1)):
            with pytest.raises(RuntimeError, match="adb 命令失败"):
                run_adb("S1", ["shell", "bad"])

    def test_check_false_does_not_raise(self):
        with patch("subprocess.run", return_value=_make_proc(b"", b"err", 1)):
            result = run_adb("S1", ["shell", "bad"], check=False)
        assert not result.ok

    def test_timeout_raises(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["adb"], 5)):
            with pytest.raises(TimeoutError):
                run_adb("S1", ["shell", "sleep", "10"])

    def test_missing_adb_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="未找到 adb"):
                run_adb("S1", ["shell", "echo"])


class TestRunAdbGlobal:
    def test_no_serial_in_cmd(self):
        with patch("subprocess.run", return_value=_make_proc(b"List of devices\n")) as mock_run:
            run_adb_global(["devices"])
        cmd = mock_run.call_args[0][0]
        assert "-s" not in cmd
        assert cmd == [adb_exe(), "devices"]


# ---------------------------------------------------------------------------
# AdbDevice
# ---------------------------------------------------------------------------

class TestAdbDevice:
    def _device(self):
        return AdbDevice("TEST001")

    def test_tap_command(self):
        # Patch at the point of use inside app.adb.device (which imports run_adb directly)
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "", "")) as mock:
            self._device().tap(100, 200)
        args = mock.call_args[0]
        assert args[0] == "TEST001"
        assert "input tap 100 200" in " ".join(args[1])

    def test_swipe_command(self):
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "", "")) as mock:
            self._device().swipe(0, 0, 500, 500, 300)
        args = mock.call_args[0]
        assert "input swipe 0 0 500 500 300" in " ".join(args[1])

    def test_keyevent_back(self):
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "", "")) as mock:
            self._device().press_back()
        args = mock.call_args[0]
        assert "input keyevent 4" in " ".join(args[1])

    def test_monkey_start(self):
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "", "")) as mock:
            self._device().monkey_start("com.hpbr.bosszhipin")
        args = mock.call_args[0]
        shell_cmd = " ".join(args[1])
        assert "monkey" in shell_cmd
        assert "com.hpbr.bosszhipin" in shell_cmd

    def test_motionevent_down_up(self):
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "", "")) as mock:
            dev = self._device()
            dev.motionevent_down(300, 400)
            dev.motionevent_up(300, 400)
        calls = mock.call_args_list
        assert any("motionevent DOWN 300 400" in " ".join(c[0][1]) for c in calls)
        assert any("motionevent UP 300 400" in " ".join(c[0][1]) for c in calls)

    def test_dumpsys(self):
        with patch("app.adb.device.run_adb", return_value=AdbResult(0, "window info", "")) as mock:
            result = self._device().dumpsys("window")
        assert result.stdout == "window info"


# ---------------------------------------------------------------------------
# screencap
# ---------------------------------------------------------------------------

class TestScreencap:
    def test_returns_png_bytes(self):
        fake_png = _PNG_MAGIC + b"\x00" * 100
        mock_proc = _make_proc(stdout=fake_png)
        with patch("subprocess.run", return_value=mock_proc):
            data = screencap_png_bytes("S1")
        assert data.startswith(_PNG_MAGIC)

    def test_retries_on_bad_magic(self):
        bad = b"\x00" * 50
        good = _PNG_MAGIC + b"\x00" * 50
        results = [_make_proc(stdout=bad), _make_proc(stdout=bad), _make_proc(stdout=good)]
        with patch("subprocess.run", side_effect=results):
            data = screencap_png_bytes("S1", retries=3, retry_delay=0)
        assert data.startswith(_PNG_MAGIC)

    def test_raises_after_all_retries_fail(self):
        bad = b"\x00" * 50
        with patch("subprocess.run", return_value=_make_proc(stdout=bad)):
            with pytest.raises(RuntimeError, match="screencap 连续"):
                screencap_png_bytes("S1", retries=2, retry_delay=0)
