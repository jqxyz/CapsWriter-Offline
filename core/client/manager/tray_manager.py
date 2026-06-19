# coding: utf-8
import os
from . import logger
import os, sys, subprocess
from config_client import ClientConfig as Config


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app):
        self.app = app

    @property
    def state(self):
        return self.app.state

    def start(self):
        """初始化系统托盘图标"""
        if not Config.enable_tray:
            return

        try:
            from ..ui import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')
        
        # 启用托盘
        enable_min_to_tray(
            'CapsWriter Client',
            icon_path,
            exit_callback=self.app.stop,
            more_options=[
                ('📋 复制结果', self._copy_last_result),
                ('📝 上下文', self._add_context),
                ('✨ 热词', self._add_hotword),
                ('🧹 清除记忆', self._clear_memory),
                ('♻️ 重开音频', self._restart_audio),
                self._build_hotkey_menu(),
            ]
        )
        logger.info("托盘图标已启用")

    def _build_hotkey_menu(self):
        """构建「快捷键」单选子菜单（pystray.MenuItem）。

        候选项来自 Config.shortcuts，点击即切换并热重载监听器。
        """
        import pystray
        from config_client import ClientConfig as Config

        # 候选快捷键：key -> 显示名
        def _norm(k):
            return k.lower().strip().replace('backquote', '`')
        candidates = {
            'alt+`':   'Alt + ` (单击切换)',
            'alt+q':   'Alt + Q (单击切换)',
            'caps_lock': 'CapsLock (长按)',
            'x2':      '鼠标侧键 X2 (长按)',
        }

        def _make_picker(candidate_key, disp):
            # pystray 点击回调签名各版本不一，用可变参数兼容
            def _on_pick(*args):
                self.app.set_active_hotkey(candidate_key)
                from core.client.ui import toast
                toast(f"快捷键已切换：{disp}", duration=2000, bg="#075077")
            return _on_pick

        def _checked(candidate):
            # pystray checked 回调签名各版本不一（有的传 icon，有的传 icon+item），
            # 用可变参数兼容，避免签名不匹配导致 icon.run 崩溃
            def _fn(*args):
                return _norm(self.app.active_hotkey) == candidate
            return _fn

        items = []
        for key, disp in candidates.items():
            items.append(pystray.MenuItem(
                disp, _make_picker(key, disp), radio=True, checked=_checked(key)
            ))
        return pystray.MenuItem('⌨️ 快捷键', pystray.Menu(*items))

    def stop(self):
        """停止托盘图标"""
        if not Config.enable_tray:
            return
            
        try:
            from ..ui import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")

    def _restart_audio(self):
        """重启音频流回调"""
        if hasattr(self.app, 'stream') and self.app.stream:
            self.app.stream.reopen()
            logger.info("用户请求重启音频")

    def _clear_memory(self):
        """清除 LLM 对话历史回调"""
        from ..ui import toast
        if self.app.llm:
            self.app.llm.clear_history()
            toast("清除成功：已清除所有角色的对话历史记录", duration=3000, bg="#075077")

    def _add_hotword(self):
        """用系统默认方式打开热词文件回调"""
        
        target = os.path.abspath('hot.txt')
        if sys.platform == 'win32':
            os.startfile(target)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', target])
        else:
            subprocess.Popen(['xdg-open', target])

    def _add_context(self):
        """打开编辑上下文界面回调"""
        try:
            from ..ui import on_edit_context
            on_edit_context()
        except ImportError as e:
            logger.warning(f"无法导入上下文菜单处理器: {e}")

    def _copy_last_result(self):
        """复制最后一次识别结果到剪贴板回调"""
        text = self.state.last_output_text
        if text:
            from ..llm.llm_clipboard import copy_to_clipboard
            copy_to_clipboard(text)

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()
