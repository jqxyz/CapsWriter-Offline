import os
from collections.abc import Iterable
from pathlib import Path

# 版本信息
__version__ = '2.6'

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# 客户端配置
class ClientConfig:
    addr = '127.0.0.1'          # Server 地址
    port = '6016'               # Server 端口

    # 快捷键配置列表
    # 说明：可同时配置多个候选快捷键，但同一时间只会有一个生效
    #       （由 settings.json 的 hotkey 字段决定激活哪一个，默认 'alt+`'）。
    #       hold_mode=False 为「单击切换」：按一次开始说话、再按一次结束。
    shortcuts = [
        {
            'key': 'caps_lock',     # 监听大写锁定键
            'type': 'keyboard',     # 是键盘快捷键
            'suppress': True,      # 阻塞按键（短按会补发）
            'hold_mode': True,      # 长按模式
            'enabled': False        # 默认不启用（由托盘菜单选择激活）
        },
        {
            'key': 'x2',
            'type': 'mouse',
            'suppress': True,
            'hold_mode': True,
            'enabled': False
        },
        {
            'key': 'alt+`',         # Alt + 反引号（单击切换模式）
            'type': 'keyboard',
            'suppress': False,      # 不拦截，避免影响其他程序的 Alt 组合
            'hold_mode': False,     # 单击切换：按一下开始、再按一下结束
            'enabled': True         # 默认激活
        },
        {
            'key': 'alt+q',         # Alt + Q（单击切换模式，备选）
            'type': 'keyboard',
            'suppress': False,
            'hold_mode': False,
            'enabled': False
        },
    ]

    # 默认激活的快捷键（在 settings.json 中可被覆盖）
    default_hotkey = 'alt+`'

    threshold    = 0.3          # 快捷键触发阈值（秒）

    paste        = False        # 是否以写入剪切板然后模拟 Ctrl-V 粘贴的方式输出结果
    restore_clip = True         # 模拟粘贴后是否恢复剪贴板
    paste_apps   = ['WeiXin.exe', 'Telegram.exe']  # 匹配时强制粘贴

    enter_apps   = [('happ.exe', 0.5), ('hexin.exe', 0.5)]  # (应用名, 延迟秒数) 输出完成后自动回车，如同花顺，输入股票名后，需要回车才能切换

    save_audio = True           # 是否保存录音文件
    audio_name_len = 20         # 将录音识别结果的前多少个字存储到录音文件名中，建议不要超过200
    
    context = ''                # 提示词上下文，用于辅助 Fun-ASR-Nano 模型识别（例如输入人名、地名、专业术语等）
    language = 'auto'           # 识别语言：'auto', 'chinese', 'english', 'japanese' 等（各引擎支持范围不同）

    trash_punc = '，。,.'       # 识别结果要消除的末尾标点
    trash_punc_thresh = 8       # 识别结果的单词数量低于阈值时，强制去除末尾标点
    trash_punc_apps = ['WeiXin.exe', ]   # 对于指定的应用，强制去除末尾标点

    traditional_convert = False     # 是否将识别结果转换为繁体中文
    traditional_locale = 'zh-hant'  # 繁体地区：'zh-hant'（标准繁体）, 'zh-tw'（台湾繁体）, 'zh-hk'（香港繁体）

    hot = True                 # 是否启用热词替换（统一 RAG 匹配）
    hot_thresh = 0.85           # RAG 替换热词阈值（高阈值，用于实际替换）
    hot_similar = 0.6           # RAG 相似热词阈值（低阈值，用于 LLM 上下文）
    hot_rule = True             # 是否启用自定义规则替换（基于正则表达式）

    llm_enabled = True          # 是否启用 LLM 润色功能，需要配置 LLM/ 目录下的角色文件
    llm_stop_key = 'esc'        # 中断 LLM 输出的快捷键

    enable_tray = True          # 客户端默认启用托盘图标功能

    # 日志配置
    log_level = 'DEBUG'          # 日志级别：'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'

    mic_seg_duration = 60       # 麦克风听写时分段长度：60秒（VAD 模式下不用于切分）
    mic_seg_overlap = 4         # 麦克风听写时分段重叠：4秒

    # —— VAD 停顿分句（语音输入法风格：说完一句停顿即出字）——
    vad_enabled          = True     # 开启停顿自动分句
    vad_silence_threshold= 0.004    # 静音能量阈值（RMS），低于此算静音（环境安静可调更低以保留轻语气词）
    vad_silence_duration = 0.8      # 连续静音多少秒判定为一次停顿
    vad_min_utterance    = 0.3      # 一句话最短多少秒才提交（过滤咳嗽/键盘声等误触）
    vad_max_utterance    = 15.0     # 一句话最长多少秒强制截断（防持续说话无限长）
    vad_tail_trim        = 0.15     # 提交时裁掉尾部多少秒静音（保留尾音，别裁太多）

    file_seg_duration = 60      # 转录文件时分段长度
    file_seg_overlap = 4        # 转录文件时分段重叠

    file_save_srt = True        # 转录文件时是否保存 srt 字幕
    file_save_txt = True        # 转录文件时是否保存 txt 文本（按标点切分后的）
    file_save_json = True       # 转录文件时是否保存 json 结果（含原始时间戳）
    file_save_merge = False      # 转录文件时是否保存 merge.txt（未切分的段落长文本）

    udp_broadcast = False               # 是否启用 UDP 广播输出结果
    udp_broadcast_targets = [           # UDP 广播目标地址列表，格式: (地址, 端口)
        ('127.255.255.255', 6017),      # 本地回环广播
        # ('192.168.1.255', 6017),      # 局域网广播（示例，按需启用）
    ]

    udp_control = False             # 是否启用 UDP 控制录音（外部程序发送 START/STOP 命令）
    udp_control_addr = '127.0.0.1'  # UDP 控制监听地址（'0.0.0.0' 允许外部访问）
    udp_control_port = 6018         # UDP 控制监听端口


# 快捷键配置说明
r"""
快捷键配置字段说明：
  key        - 按键名称（见下方可用按键列表）
  type       - 输入类型：'keyboard'（键盘）或 'mouse'（鼠标）
  suppress   - 是否阻塞按键（True=阻塞，False=不阻塞）
  hold_mode  - 长按模式（True=按下录音松开停止，False=单击开始再次单击停止）
  enabled    - 是否启用此快捷键

阻塞模式说明：
  - 阻塞模式  ：长按录音识别，短按（<0.3秒）则自动补发按键，不影响单击功能
  - 非阻塞模式：对于 CapsLock/NumLock/ScrollLock 这类切换键，松开时会自动补发，以恢复按键状态

可用按键名称：

  字母数字：a - z, 0 - 9（大键盘）

  符号键：, . / \ ` ' - = [ ] ; '


  功能键：f1 - f24

  控制键:
      ctrl_l,   ctrl_r,
      shift,  shift_r,
      alt_l,    alt_gr,
      cmd,    cmd_r

  特殊键：
      space, enter, tab, backspace, delete, insert, home, end
      page_up, page_down, esc, caps_lock, num_lock, scroll_lock
      print_screen, pause, menu

  方向键：up, down, left, right

  鼠标键：x1, x2

示例配置：
  {'key': 'caps_lock', 'type': 'keyboard', 'suppress': False, 'hold_mode': True, 'enabled': True}, 
  {'key': 'f12', 'type': 'keyboard', 'suppress': True, 'hold_mode': True, 'enabled': True}, 
  {'key': 'x2', 'type': 'mouse', 'suppress': True, 'hold_mode': True, 'enabled': True}, 
"""

