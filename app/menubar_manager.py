"""
Campus-Agent MenuBar Pill Manager (macOS 状态栏常驻胶囊生命周期管理器)
负责原生 Cocoa 菜单栏常驻应用的编译、后台拉起、状态遥测与安全终结。
"""

import os
import signal
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("campus-agent.menubar")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = PROJECT_ROOT / "src" / "menubar" / "naiwa_menubar.m"
BIN_DIR = PROJECT_ROOT / "bin"
BINARY_PATH = BIN_DIR / "naiwa_menubar"


class MenuBarManager:
    """macOS 顶部状态栏常驻胶囊全局单例管理器"""

    _instance: Optional["MenuBarManager"] = None

    def __init__(self):
        self.binary_path = BINARY_PATH
        self.source_path = SOURCE_PATH
        self._process: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None

    @classmethod
    def get_instance(cls) -> "MenuBarManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_compiled(self, force: bool = False) -> bool:
        """检查并编译原生 Objective-C Cocoa 菜单栏常驻程序"""
        BIN_DIR.mkdir(parents=True, exist_ok=True)

        if not self.source_path.exists():
            logger.error("MenuBar 源码未找到: %s", self.source_path)
            return False

        needs_compile = force or (not self.binary_path.exists())
        if not needs_compile:
            # 比较源码与二进制的修改时间
            src_mtime = self.source_path.stat().st_mtime
            bin_mtime = self.binary_path.stat().st_mtime
            if src_mtime > bin_mtime:
                needs_compile = True

        if needs_compile:
            logger.info("正在编译原生 macOS 状态栏胶囊程序: %s -> %s", self.source_path, self.binary_path)
            cmd = [
                "clang",
                "-framework", "Cocoa",
                "-O2",
                "-o", str(self.binary_path),
                str(self.source_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error("编译 MenuBar 失败: %s", res.stderr)
                return False
            logger.info("原生 macOS 状态栏胶囊程序编译成功！")

            # 同步打包为带 LSUIElement 的原生 App Bundle，确保被 LaunchServices/WindowServer 稳定挂载
            try:
                import shutil
                app_bundle_dir = BIN_DIR / "NaiWaMenuBar.app" / "Contents" / "MacOS"
                app_bundle_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(self.binary_path), str(app_bundle_dir / "naiwa_menubar"))
                plist_path = BIN_DIR / "NaiWaMenuBar.app" / "Contents" / "Info.plist"
                plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>naiwa_menubar</string>
    <key>CFBundleIdentifier</key>
    <string>com.campus.naiwa.menubar</string>
    <key>CFBundleName</key>
    <string>奶蛙</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>"""
                plist_path.write_text(plist_content, encoding="utf-8")
            except Exception as e:
                logger.warning("打包 App Bundle 异常: %s", e)

        return True

    def is_running(self) -> bool:
        """检查状态栏胶囊进程是否正在运行"""
        # 1. 优先检查自身持有的子进程 handle
        if self._process is not None:
            if self._process.poll() is None:
                return True
            else:
                self._process = None
                self._pid = None

        # 2. 检查操作系统中是否存在同名进程
        try:
            res = subprocess.run(
                ["pgrep", "-f", str(self.binary_path.name)],
                capture_output=True,
                text=True
            )
            pids = res.stdout.strip().splitlines()
            if pids:
                pid = int(pids[0])
                try:
                    # 探测是否具有发信号管理权限
                    os.kill(pid, 0)
                    self._pid = pid
                    return True
                except PermissionError:
                    # 宿主隔离进程，沙箱内无权管理
                    pass
                except OSError:
                    pass
        except Exception as e:
            logger.debug("检查 menubar 进程失败: %s", e)

        return False

    def get_pid(self) -> Optional[int]:
        if self.is_running():
            return self._pid
        return None

    def start(self) -> Dict[str, Any]:
        """启动 macOS 状态栏常驻胶囊"""
        if self.is_running():
            return {
                "success": True,
                "running": True,
                "pid": self.get_pid(),
                "message": "奶蛙状态栏胶囊已在运行中",
            }

        # 确保二进制已编译
        if not self.ensure_compiled():
            return {
                "success": False,
                "running": False,
                "message": "编译原生状态栏程序失败，请检查编译环境",
            }

        try:
            # 优先从 App Bundle 启动，确保系统 LaunchServices 与 WindowServer 认可
            bundle_exec = BIN_DIR / "NaiWaMenuBar.app" / "Contents" / "MacOS" / "naiwa_menubar"
            target_exec = str(bundle_exec) if bundle_exec.exists() else str(self.binary_path)
            self._process = subprocess.Popen(
                [target_exec],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            self._pid = self._process.pid
            logger.info("🚀 奶蛙 macOS 状态栏常驻胶囊已启动 (PID: %d)", self._pid)
            return {
                "success": True,
                "running": True,
                "pid": self._pid,
                "message": f"奶蛙状态栏常驻胶囊已启动 (PID: {self._pid})",
            }
        except Exception as e:
            logger.error("启动状态栏胶囊失败: %s", e)
            return {
                "success": False,
                "running": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop(self) -> Dict[str, Any]:
        """安全停止 macOS 状态栏常驻胶囊"""
        pid = self.get_pid()
        if not self.is_running() or pid is None:
            return {
                "success": True,
                "running": False,
                "message": "状态栏常驻胶囊未运行",
            }

        try:
            os.kill(pid, signal.SIGTERM)
            if self._process:
                try:
                    self._process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None
            self._pid = None
            logger.info("⏹️ 奶蛙 macOS 状态栏常驻胶囊已安全退出 (PID: %d)", pid)
            return {
                "success": True,
                "running": False,
                "message": "奶蛙状态栏胶囊已成功退出",
            }
        except Exception as e:
            logger.error("停止状态栏胶囊失败: %s", e)
            # 兜底尝试 pkill
            try:
                subprocess.run(["pkill", "-f", str(self.binary_path.name)])
            except Exception:
                pass
            self._process = None
            self._pid = None
            return {
                "success": True,
                "running": False,
                "message": f"已执行强制终止退出: {str(e)}",
            }

    def get_status(self) -> Dict[str, Any]:
        """获取状态栏胶囊当前运行状态"""
        running = self.is_running()
        return {
            "running": running,
            "pid": self.get_pid() if running else None,
            "binary_path": str(self.binary_path),
            "binary_exists": self.binary_path.exists(),
        }


# 全局单例
menubar_manager = MenuBarManager.get_instance()
