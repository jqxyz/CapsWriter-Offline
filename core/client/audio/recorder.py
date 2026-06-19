# coding: utf-8
"""
音频录制模块

提供 AudioRecorder 类用于管理录音会话，包括开始录音、
发送音频数据到服务端、结束录音等功能。
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import TYPE_CHECKING, Optional

import numpy as np
import websockets

from config_client import ClientConfig as Config
from core.client.state import console
from core.client.audio.file_manager import AudioFileManager
from core.client.connection import WebSocketManager
from core.protocol import AudioMessage
from . import logger

if TYPE_CHECKING:
    from core.client.state import ClientState
    from core.client.app import CapsWriterClient

# 日志记录器


class AudioRecorder:
    """
    音频录制器
    
    管理一次完整的录音会话，包括：
    - 从音频流接收数据
    - 可选地保存到本地文件
    - 将音频数据发送到识别服务端
    """
    
    def __init__(self, app: CapsWriterClient):
        """
        初始化录制器
        
        Args:
            app: 客户端 App 实例
        """
        self.app = app
        self.task_id: Optional[str] = None
        self._file_manager: Optional[AudioFileManager] = None
        self._start_time: float = 0.0
        self._duration: float = 0.0
        self._cache: list = []

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    @property
    def _ws_manager(self) -> WebSocketManager:
        """快捷访问桥接到 app.ws"""
        return self.app.ws
    
    async def _send_message(self, message: AudioMessage) -> None:
        """发送消息到服务端"""
        if not self._ws_manager.is_connected:
            if message.is_final:
                self.state.pop_audio_file(message.task_id)
                console.print('    服务端未连接，无法发送\n')
                logger.warning("服务端未连接，无法发送音频数据")
            return
        
        # 使用 WebSocketManager 发送协议消息
        success = await self._ws_manager.send(message)
        if not success and message.is_final:
            self.state.pop_audio_file(message.task_id)
            # 具体错误日志由 WebSocketManager 记录
    
    async def record_and_send(self) -> None:
        """
        录音并发送数据

        从队列中读取音频数据，保存到文件（如果启用），
        并发送到服务端进行识别。

        分段策略：
        - VAD 模式（默认）：检测停顿自动分句，每句用独立 task_id 发 is_final=True，
          实现"说完一句停顿即出字"的语音输入法风格。
        - 非 VAD 模式：按 mic_seg_duration 固定时长分段（原行为）。
        """
        try:
            # 生成首个任务 ID
            self.task_id = str(uuid.uuid1())
            logger.debug(f"创建录音任务，任务ID: {self.task_id}")

            self._start_time = 0.0
            self._duration = 0.0
            self._archive_path = None  # 会话级音频归档路径（VAD 多句共享）

            # VAD 分句器（VAD 模式下使用）
            vad = None
            if Config.vad_enabled:
                from core.client.audio.vad_segmenter import VadSegmenter
                vad = VadSegmenter(
                    silence_threshold=Config.vad_silence_threshold,
                    silence_duration=Config.vad_silence_duration,
                    min_utterance=Config.vad_min_utterance,
                    max_utterance=Config.vad_max_utterance,
                    tail_trim=Config.vad_tail_trim,
                    sample_rate=48000,
                )

            # 音频文件管理
            file_path = None
            if Config.save_audio:
                self._file_manager = AudioFileManager()

            # 原固定分段模式的缓存
            self._cache: list = []

            # 从队列读取数据
            while task := await self.state.queue_in.get():
                self.state.queue_in.task_done()

                if task['type'] == 'begin':
                    self._start_time = task['time']
                    logger.debug(f"录音开始，时间戳: {self._start_time}")

                elif task['type'] == 'data':
                    block = task['data']

                    # 创建音频文件（仅一次）
                    if Config.save_audio and self._file_manager and file_path is None:
                        file_path, _ = self._file_manager.create(
                            block.shape[1],
                            self._start_time
                        )
                        self._archive_path = file_path
                        self.state.register_audio_file(self.task_id, file_path)

                    if vad is not None:
                        # —— VAD 模式：喂入分句器，每出一句就独立提交 ——
                        # 每句都用 is_final=True，让服务端立刻独立识别并返回结果，
                        # 而非累积（is_final=False 会被服务端攒着不返回）。
                        utterance = vad.feed(block)
                        if utterance is not None:
                            await self._submit_utterance(utterance)
                    else:
                        # —— 原固定分段模式 ——
                        # 在阈值之前积攒音频数据
                        if task['time'] - self._start_time < Config.threshold:
                            self._cache.append(block)
                            continue
                        if self._cache:
                            data = np.concatenate(self._cache)
                            self._cache.clear()
                        else:
                            data = block
                        await self._send_segment(data, is_final=False)

                elif task['type'] == 'finish':
                    # VAD 模式：把残余的最后一句也提交
                    if vad is not None:
                        utterance = vad.flush_tail()
                        if utterance is not None:
                            await self._submit_utterance(utterance)
                    else:
                        # 原模式：发送残留缓存
                        if self._cache:
                            data = np.concatenate(self._cache)
                            self._cache.clear()
                            await self._send_segment(data, is_final=False)

                    # 完成写入本地文件
                    if Config.save_audio and self._file_manager:
                        self._file_manager.finish()
                        logger.debug("完成音频文件写入")

                    console.print(f'    录音总时长：{self._duration:.2f}s')
                    logger.info(f"录音会话完成，总时长: {self._duration:.2f}s")
                    break

        except Exception as e:
            logger.error(f"录音任务错误: {e}", exc_info=True)

    async def _submit_utterance(self, utterance: np.ndarray) -> None:
        """提交 VAD 切出的一句话（用全新的 task_id，独立识别）。

        每句都用 is_final=True：让服务端立刻独立识别并返回，
        实现"停顿即出字"。每句独立 task_id 保证服务端不跨句累积、客户端干净追加。

        Args:
            utterance: 单声道或多声道的 float32 音频块。
        """
        self.task_id = str(uuid.uuid1())
        # 归档：让这个新 task_id 也指向同一个（会话级）音频文件，
        # 这样 result_processor 的 pop_audio_file(task_id) 能正确取到
        if Config.save_audio and self._file_manager and getattr(self, '_archive_path', None):
            self.state.register_audio_file(self.task_id, self._archive_path)
        await self._send_segment(utterance, is_final=True)

    async def _send_segment(self, data: np.ndarray, is_final: bool) -> None:
        """把一段音频发送给服务端识别（48k 多声道 → 16k 单声道降采样）。"""
        if not Config.save_audio:
            # 非 VAD 模式下原逻辑用 len(data)/48000 累加；这里统一也累加
            pass
        self._duration += len(data) / 48000
        if Config.save_audio and self._file_manager:
            self._file_manager.write(data)

        payload = np.mean(data[::3], axis=1).tobytes()
        message = AudioMessage(
            task_id=self.task_id,
            source='mic',
            data=base64.b64encode(payload).decode('utf-8'),
            is_final=is_final,
            time_start=self._start_time,
            seg_duration=Config.mic_seg_duration,
            seg_overlap=Config.mic_seg_overlap,
            context=Config.context,
            language=Config.language,
        )
        asyncio.create_task(self._send_message(message))
    
    def get_file_manager(self) -> Optional[AudioFileManager]:
        """获取当前的文件管理器"""
        return self._file_manager
