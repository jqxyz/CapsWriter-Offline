# coding: utf-8
"""
服务端自动拉起器

让用户只需双击客户端即可——客户端启动时自动检测服务端是否在运行，
若没运行则拉起 start_server 作为子进程，并等待其就绪。
实现"单 exe 体验"（无需手动开两个程序）。
"""
from __future__ import annotations

import os
import sys
import time
import socket
import subprocess
from pathlib import Path

from config_client import ClientConfig as Config
from . import logger

# 由本客户端拉起的服务端子进程（仅记录"自己拉起的"，退出时才清理；
# 若服务端是用户手动启动的，则此处为 None，不会被误杀）
_server_proc = None


def _is_port_listening(host: str, port: int, timeout: float = 0.3) -> bool:
    """检查指定端口是否有人在监听（即 server 是否已起）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _find_server_executable() -> str | None:
    """查找 start_server 的可执行入口。

    优先找同目录的 start_server.exe（打包版），否则用 python start_server.py（源码版）。
    """
    # 项目根目录 / dist 目录
    candidates = []
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境：exe 同级目录
        base = Path(sys.executable).parent
        candidates.append(base / 'start_server.exe')
    # 源码运行：项目根目录
    root = Path(__file__).parents[2]
    candidates.append(root / 'start_server.exe')
    candidates.append(root / 'start_server.py')

    for c in candidates:
        if c.exists():
            return str(c)
    return None


def ensure_server_running(max_wait: float = 90.0) -> bool:
    """确保服务端在运行。若没运行则自动拉起子进程并等待就绪。

    Args:
        max_wait: 拉起后最长等待就绪秒数（模型加载较慢，默认 90 秒）。

    Returns:
        True 表示服务端已就绪（已运行或成功拉起）。
    """
    host = Config.addr
    port = int(Config.port)

    # 1. 已经在运行
    if _is_port_listening(host, port):
        logger.info(f"检测到服务端已在运行 ({host}:{port})，无需拉起")
        return True

    # 2. 查找入口
    entry = _find_server_executable()
    if entry is None:
        logger.warning("未找到 start_server 入口，无法自动拉起服务端")
        # 不阻塞，让客户端正常启动（连接会失败重试，用户能看到提示）
        return False

    # 3. 拉起子进程
    logger.info(f"自动拉起服务端: {entry}")
    global _server_proc
    try:
        is_py = entry.endswith('.py')
        creationflags = 0
        if os.name == 'nt':
            # CREATE_NEW_CONSOLE: 让 server 有自己的控制台窗口（能看到它的日志）。
            # 注意：用独立控制台意味着 client 退出时 server 不会自动跟着退，
            # 因此 client 在退出时会主动终止它（见 stop_server）。
            creationflags = subprocess.CREATE_NEW_CONSOLE

        if is_py:
            # 源码版：用当前 python 跑
            _server_proc = subprocess.Popen(
                [sys.executable, entry],
                creationflags=creationflags,
                cwd=str(Path(entry).parent),
                env={**os.environ, 'CAPSWRITER_EMBEDDED': '1'},
            )
        else:
            # 打包版 exe
            _server_proc = subprocess.Popen(
                [entry],
                creationflags=creationflags,
                cwd=str(Path(entry).parent),
                env={**os.environ, 'CAPSWRITER_EMBEDDED': '1'},
            )
        proc = _server_proc
        logger.info(f"服务端子进程已启动，PID={proc.pid}，等待就绪...")
    except Exception as e:
        logger.error(f"拉起服务端失败: {e}")
        return False

    # 4. 等待就绪（轮询端口）
    deadline = time.time() + max_wait
    dots = 0
    while time.time() < deadline:
        if _is_port_listening(host, port):
            logger.info("服务端已就绪")
            return True
        time.sleep(1.0)
        dots += 1
        if dots % 5 == 0:
            logger.debug(f"等待服务端就绪... ({dots}s)")

    logger.warning(f"等待服务端就绪超时（{max_wait}s），可能仍在加载模型")
    return False


def stop_server() -> None:
    """终止由本客户端拉起的服务端子进程（若有）。

    仅清理"自己拉起的"进程；用户手动启动的服务端不会被误杀。
    在客户端退出时调用，避免服务端残留累积。
    """
    global _server_proc
    if _server_proc is None:
        return
    try:
        # server 是多进程结构（主进程 + worker 子进程），终止主进程后
        # 用 taskkill /T 连带终止其子进程，避免 worker 残留
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(_server_proc.pid), '/T', '/F'],
                capture_output=True, timeout=10,
            )
            logger.info(f"已终止服务端子进程树 (PID={_server_proc.pid})")
        else:
            _server_proc.terminate()
            logger.info(f"已终止服务端子进程 (PID={_server_proc.pid})")
    except Exception as e:
        logger.warning(f"终止服务端子进程时出错: {e}")
    finally:
        _server_proc = None

