# coding: utf-8
import os
import sys

# —— 单实例锁：防止重复启动多个客户端（避免快捷键重复触发、重复输出）——
def _acquire_single_instance():
    """通过 Windows 命名互斥体确保只有一个客户端实例运行。

    已有实例在跑时返回 None，否则返回互斥体句柄（需保活到进程结束）。
    """
    if os.name != 'nt':
        return True  # 非 Windows 不做单实例限制
    try:
        import ctypes
        from ctypes import wintypes
        mutex_name = "Global\\CapsWriterClient_SingleInstance"
        # CreateMutex(默认安全属性, 初始不占有, 名称)
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        # ERROR_ALREADY_EXISTS (183) 表示已存在
        if kernel32.GetLastError() == 183:
            return None
        return handle
    except Exception:
        return True  # 出错不阻塞启动


if __name__ == "__main__":
    mutex = _acquire_single_instance()
    if mutex is None:
        # 已有实例在运行，提示并退出，不重复启动
        try:
            print("CapsWriter 客户端已经在运行了，不要重复启动。")
        except Exception:
            pass
        # 短暂停留让用户看到提示
        import time
        time.sleep(2)
        sys.exit(0)

    # 直接实例化并启动门面类即可
    # 环境初始化职责已下放至 CapsWriterClient
    from core.client import CapsWriterClient
    CapsWriterClient().start()