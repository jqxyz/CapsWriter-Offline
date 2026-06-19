# coding: utf-8
from __future__ import annotations
import os
from typing import TYPE_CHECKING
from config_server import ServerConfig as Config
from ..state import console
from .. import logger # Server module logger
if TYPE_CHECKING:
    from ..app import CapsWriterServer


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app: CapsWriterServer):
        self.app = app

    def start(self):
        """初始化系统托盘图标"""
        if not Config.enable_tray:
            return

        # 若本服务端是由客户端自动拉起的（CAPSWRITER_EMBEDDED=1），
        # 则不显示自己的托盘图标（避免桌面出现两个图标，统一由客户端托盘作为入口）。
        # 此时 server 是 CREATE_NO_WINDOW 启动的，本身无控制台窗口，无需最小化。
        if os.environ.get('CAPSWRITER_EMBEDDED') == '1':
            logger.info("服务端由客户端自动拉起，无窗口无托盘后台运行")
            return

        try:
            from . import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')
        
        # 启用托盘
        enable_min_to_tray(
            'CapsWriter Server',
            icon_path,
            exit_callback=self._request_exit
        )
        logger.info("托盘图标已启用")

    def _minimize_console_only(self):
        """嵌入式模式：只最小化控制台窗口，不创建托盘图标。

        用 Windows API 把控制台窗口最小化到任务栏（SW_MINIMIZE），
        不占用桌面空间；退出由客户端负责（client 退出时杀掉 server 进程树）。
        """
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                # SW_MINIMIZE = 6：最小化窗口并激活下一个顶层窗口
                user32.ShowWindow(hwnd, 6)
                logger.debug("已最小化服务端控制台窗口（嵌入式模式）")
        except Exception as e:
            logger.warning(f"最小化控制台窗口失败: {e}")

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()

    def stop(self):
        """停止托盘图标"""
        if not Config.enable_tray:
            return
            
        try:
            from core.ui.tray import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")
