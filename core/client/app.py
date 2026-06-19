# coding: utf-8
"""
CapsWriter Offline 客户端主程序门面类 (Facade)

采用外观模式统一管理音频流 (AudioStreamManager)、
识别结果处理 (ResultProcessor) 和快捷键管理 (ShortcutManager)。
"""

import os
import sys
import asyncio
from pathlib import Path

from .state import ClientState
from . import logger
from config_client import ClientConfig as Config, __version__
from core.tools.signal_handler import register_signal
from .state import console
from .connection import WebSocketManager
from typing import TYPE_CHECKING, Optional
from .manager import (
    TrayManager,
    MicRunner, FileRunner
)
from .audio.stream import AudioStreamManager
from .shortcut.shortcut_manager import ShortcutManager
from .shortcut.shortcut_config import Shortcut

from .udp.udp_control import UDPController

from .hotword.manager import HotwordManager
from .llm.llm_handler import LLMHandler
from .output.text_output import TextOutput
from .diary.diary_writer import DiaryWriter
from core.tools.empty_working_set import empty_current_working_set
from platform import system



class CapsWriterClient:
    """
    CapsWriter 客户端门面类
    
    管理的外部接口简洁：start()。
    """
    def __init__(self):
        # 确保正确的工作目录
        self.base_dir = Path(__file__).parents[2]
        os.chdir(self.base_dir)
            
        # 初始化事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
            
        # 初始化状态容器
        self.state = ClientState(app=self)

        # 初始化热词管理器
        self.hotword = HotwordManager(
            hotword_files=None,
            threshold=Config.hot_thresh,
            similar_threshold=Config.hot_similar
        )

        # 4. 初始化 LLM 润色系统
        self.llm = LLMHandler(app=self)
        
        self.output = TextOutput()
        self.diary = DiaryWriter(base_path=self.base_dir)

        # 初始化各管理器
        self.ws = WebSocketManager(self)
        self.tray = TrayManager(self)

        # 实例化硬件资源管理组件
        self.stream = AudioStreamManager(self)
        self.shortcut = ShortcutManager(self, self._build_shortcuts())
        self.udp = UDPController(self.shortcut)

        # 内存清理
        empty_current_working_set()

    def _build_shortcuts(self):
        """根据 settings.json 选中的快捷键，构建 Shortcut 列表（仅激活选中项）。"""
        from core.client import settings_store

        active = settings_store.get_setting('hotkey', Config.default_hotkey)
        # 规范化键名（与 Shortcut._normalize_key 一致：小写 + backquote->`）
        active = active.lower().strip().replace('backquote', '`')

        shortcuts = []
        for sc in Config.shortcuts:
            cfg = dict(sc)
            cfg['enabled'] = (cfg['key'].lower().strip().replace('backquote', '`') == active)
            shortcuts.append(Shortcut(**cfg))
        self._active_hotkey = active
        return shortcuts

    @property
    def active_hotkey(self) -> str:
        """当前激活的快捷键名（规范化后）。"""
        return getattr(self, '_active_hotkey', Config.default_hotkey)

    def set_active_hotkey(self, hotkey: str) -> bool:
        """切换激活的快捷键，写盘并热重载监听器（不重启程序）。

        Args:
            hotkey: 快捷键名，如 'alt+`'、'alt+q'、'caps_lock'、'x2'

        Returns:
            True 表示切换成功
        """
        from core.client import settings_store
        hotkey = hotkey.lower().strip().replace('backquote', '`')

        # 校验是否为已配置的候选键
        valid_keys = [sc['key'].lower().strip().replace('backquote', '`') for sc in Config.shortcuts]
        if hotkey not in valid_keys:
            logger.warning(f"未知的快捷键候选: {hotkey}")
            return False

        # 写入持久化
        settings_store.set_setting('hotkey', hotkey)

        # 停掉旧监听器（取消进行中的录音）
        try:
            self.shortcut.stop()
        except Exception as e:
            logger.warning(f"停止旧快捷键监听器时出错: {e}")

        # 重建并启动新监听器
        self.shortcut = ShortcutManager(self, self._build_shortcuts())
        self.shortcut.start()
        self.udp.manager = self.shortcut  # UDP 控制器引用更新（指向新管理器）
        logger.info(f"已切换激活快捷键: {hotkey}")
        return True

    def stop(self):
        """
        统一释放所有资源（清理顺序：硬件 -> 托盘 -> WebSocket -> State）
        """
        logger.info("正在执行 CapsWriterClient 资源释放...")

        # 1. 停止核心运行组件
        self.udp.stop()
        self.shortcut.stop()
        self.stream.stop()

        # 1.5 终止由本客户端拉起的服务端子进程（避免残留累积）
        try:
            from .server_launcher import stop_server
            stop_server()
        except Exception as e:
            logger.warning(f"清理服务端子进程时出错: {e}")

        # 2. 托盘资源
        self.tray.stop()

        # 3. 关闭监控
        self.hotword.stop()
        self.llm.stop()

        # 4. 关闭 WebSocket 连接
        self.ws.close_sync()

        # 5. 重置 State
        try:
            self.state.reset()
        except Exception as e:
            logger.warning(f"重置状态时发生错误: {e}")

        # 6. 停止事件循环（最后一步，确保前面的异步操作已调度）
        self.loop.stop()

        logger.info("资源释放完成")
        console.print('[green4]再见！')


    def start(self):
        """
        启动客户端 (唯一入口)
        
        自动根据命令行参数识别模式。内部管理异步循环。
        """

        # 注册退出函数
        register_signal(self.stop)

        files = [Path(f) for f in sys.argv[1:] if os.path.exists(f)]

        if files:
            # 文件转录模式
            runner = FileRunner(self, files)
        else:
            # 麦克风实时模式
            runner = MicRunner(self)
        
        try:
            self.loop.run_until_complete(runner.run())
        except RuntimeError:
            ...


