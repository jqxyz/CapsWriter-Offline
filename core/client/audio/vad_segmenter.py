# coding: utf-8
"""
VAD（语音活动检测）分句器

按"停顿"自动切分连续音频流为一句句独立片段，用于实现语音输入法风格的
"说完一句停顿即出字"。

工作原理：
- 每次喂入一小块音频（如 50ms），计算其 RMS 能量
- 能量低于阈值 → 视为静音；否则视为语音
- 跟踪状态：是否正在说话、连续静音时长、当前句长度
- 触发提交的两种条件：
  1. 正在说话 → 转为足够长的静音，且当前句达到最短长度（停顿分句）
  2. 当前句达到最长限制（强制截断，防无限长）
- feed() 返回完整一句的音频（已去除尾部静音），或 None（尚未到切分点）

纯算法、无 IO、无副作用，可单元测试。
"""
from __future__ import annotations

from typing import Optional, List

import numpy as np


class VadSegmenter:
    """VAD 停顿分句器。

    Args:
        silence_threshold: 静音能量阈值（RMS）。低于此值视为静音。
        silence_duration:  连续静音多少秒判定为一次停顿（句子边界）。
        min_utterance:     一句话最短多少秒才提交（过滤太短的噪音/误触）。
        max_utterance:     一句话最长多少秒强制截断（防持续说话无限长）。
        sample_rate:       音频采样率（Hz）。默认 48000。
    """

    def __init__(
        self,
        silence_threshold: float = 0.008,
        silence_duration: float = 0.8,
        min_utterance: float = 0.3,
        max_utterance: float = 15.0,
        tail_trim: float = 0.15,
        sample_rate: int = 48000,
    ):
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.min_utterance = min_utterance
        self.max_utterance = max_utterance
        self.tail_trim = tail_trim  # 提交时裁掉的尾部静音秒数（保留尾音）
        self.sample_rate = sample_rate

        # 当前句的音频缓冲（每块 float32 数组的列表）
        self._buffer: List[np.ndarray] = []
        # 当前句累计的样本数（含语音和静音，用于 max_utterance 上限）
        self._samples_in_utterance: int = 0
        # 当前句中"语音"样本数（只统计非静音块，用于 min_utterance 下限）
        self._speech_samples: int = 0
        # 当前连续静音的样本数
        self._silence_samples: int = 0
        # 是否已经检测到语音（用于忽略开头纯静音）
        self._had_speech: bool = False

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _rms(block: np.ndarray) -> float:
        """计算一个音频块的 RMS 能量。

        输入可能是 (n,) 或 (n, channels)。多声道先取均值压成单声道。
        """
        if block.ndim > 1:
            block = np.mean(block, axis=1)
        block = block.astype(np.float64, copy=False)
        if block.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(block * block)))

    def _utterance_seconds(self) -> float:
        """当前句总时长（含语音和尾部静音），用于 max_utterance 上限判定。"""
        return self._samples_in_utterance / self.sample_rate

    def _speech_seconds(self) -> float:
        """当前句中纯语音的时长，用于 min_utterance 下限判定。"""
        return self._speech_samples / self.sample_rate

    def _silence_seconds(self) -> float:
        return self._silence_samples / self.sample_rate

    def _flush(self) -> np.ndarray:
        """拼接当前缓冲为单个数组并清空状态（不重置 had_speech）。"""
        if not self._buffer:
            return np.zeros(0, dtype=np.float32)
        data = np.concatenate(self._buffer, axis=0)
        self._buffer.clear()
        self._samples_in_utterance = 0
        self._speech_samples = 0
        self._silence_samples = 0
        return data

    # ------------------------------------------------------------------
    # 主接口
    # ------------------------------------------------------------------
    def feed(self, block: np.ndarray) -> Optional[np.ndarray]:
        """喂入一块音频，返回切分出的完整句子（或 None）。

        Args:
            block: 一小段音频（如 50ms），float32，任意声道数。

        Returns:
            若判定为一次句子边界，返回该句的完整音频（float32, 单声道）；
            否则返回 None。
        """
        n = block.shape[0] if block.ndim > 0 else 0
        if n == 0:
            return None

        energy = self._rms(block)
        is_silence = energy < self.silence_threshold

        # 缓冲这块音频（无论静音与否——静音也可能属于句子的尾部，
        # 但提交时会按 silence_duration 裁掉尾巴）
        self._buffer.append(block)
        self._samples_in_utterance += n

        if is_silence:
            self._silence_samples += n
        else:
            self._silence_samples = 0
            self._speech_samples += n
            self._had_speech = True

        utt_sec = self._utterance_seconds()
        speech_sec = self._speech_seconds()

        # 条件 2：超过最长限制 → 强制截断（不管静音状态）
        if utt_sec >= self.max_utterance:
            data = self._flush()
            self._had_speech = False
            # 截断时保留全部（包括可能正在说的话），直接提交
            return data if data.size > 0 else None

        # 条件 1：检测到停顿（正在说话后，静音累积够长，且语音够长）
        # 注意：min_utterance 用纯语音时长判断，避免"短噪音+长静音"误触发
        if (
            self._had_speech
            and self._silence_seconds() >= self.silence_duration
            and speech_sec >= self.min_utterance
        ):
            data = self._flush()
            self._had_speech = False
            # 去除尾部静音：只裁 tail_trim 秒（而非整个 silence_duration），
            # 保留更多可能的尾音/语气词，避免"末尾被吃掉"。
            trim = int(self.tail_trim * self.sample_rate)
            if trim > 0 and data.size > trim:
                data = data[:-trim]
            return data if data.size > 0 else None

        return None

    def flush_tail(self) -> Optional[np.ndarray]:
        """取出当前缓冲里残余的（最后未因停顿结束的）一句话。

        在会话结束（用户按结束键）时调用，把最后那句也提交出去。
        仅当确实有过语音、且达到最短长度时才返回。
        """
        if not self._had_speech or self._speech_seconds() < self.min_utterance:
            # 没说过话，或残余语音太短，丢弃
            self.reset()
            return None
        data = self._flush()
        self._had_speech = False
        return data if data.size > 0 else None

    def reset(self) -> None:
        """彻底重置（用于会话结束时清理）。"""
        self._buffer.clear()
        self._samples_in_utterance = 0
        self._speech_samples = 0
        self._silence_samples = 0
        self._had_speech = False
