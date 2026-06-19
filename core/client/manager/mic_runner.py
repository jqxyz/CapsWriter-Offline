# coding: utf-8
import asyncio
from . import logger
from ..ui import TipsDisplay
from config_client import ClientConfig as Config, __version__


class MicRunner:
    """
    麦克风模式运行器：负责麦克风模式下的资源初始化、识别处理器循环及生命周期监控。
    """
    def __init__(self, app):
        self.app = app
        self.processor = None

    @property
    def state(self):
        return self.app.state

    @property
    def ws_manager(self):
        return self.app.ws

    @property
    def tray_manager(self):
        return self.app.tray

    def start_resources(self):
        """初始化麦克风模式特有资源 (音频硬件、快捷键、UI 托盘)"""
        # 1. 托盘
        self.tray_manager.start()

        # 2. UI 提示
        TipsDisplay.show_mic_tips()

        # 3. 探测音频设备（仅检测并打印，不占用麦克风——
        #    实际的音频流在用户按下快捷键开始录音时才开启，停止即关闭）
        try:
            import sounddevice as sd
            from core.client.state import console
            device = sd.query_devices(kind='input')
            console.print(
                f'使用默认音频设备：[italic]{device.get("name", "未知")}，'
                f'声道数：{min(2, device["max_input_channels"])}',
                end='\n\n'
            )
        except Exception:
            pass

        # 4. 开启快捷键监听（音频流改为录音时按需开启）
        self.app.shortcut.start()
        
        # 4. 开启 UDP 控制 (如果启用)
        if Config.udp_control:
            self.app.udp.start()

        # 5. 开启后台服务 (热词、LLM)
        self.app.hotword.start()
        self.app.llm.start()

    async def run(self):
        """麦克风模式主入口"""

        logger.info("=" * 50)
        logger.info(f"CapsWriter Offline Client {__version__} (麦克风模式)")
        logger.info(f"日志级别: {Config.log_level}")

        # 0. 确保服务端在运行（没开则自动拉起，实现"单程序"体验）
        try:
            from ..server_launcher import ensure_server_running
            from core.client.state import console
            if not ensure_server_running():
                console.print('[bold yellow]提示：未能自动启动服务端，请手动运行 start_server[/bold yellow]')
        except Exception as e:
            logger.warning(f"自动拉起服务端时出错: {e}")

        # 1. 资源启动
        self.start_resources()
        
        # 2. 启动核心处理器 (内部处理连接与循环)
        
        from ..output import ResultProcessor
        self.processor = ResultProcessor(self.app)
        await self.processor.start()
            

