from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter_ns

VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

# Fixed-width Windows ABI types. Using native c_long/c_ulong would have the
# wrong size when these structures are validated on a non-Windows host.
WORD = ctypes.c_uint16
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


@dataclass(frozen=True)
class SendResult:
    success: bool
    planned_at: datetime
    called_at: datetime
    perf_called_ns: int
    sent_events: int
    error_code: int | None = None
    error: str | None = None


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD))


class INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = (("type", DWORD), ("union", INPUT_UNION))


def send_enter(planned_at: datetime) -> SendResult:
    called_at = datetime.now()
    perf_called_ns = perf_counter_ns()
    if os.name != "nt":
        return SendResult(False, planned_at, called_at, perf_called_ns, 0, error="SendInput 仅支持 Windows")

    inputs = (INPUT * 2)(
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_RETURN, 0, 0, 0, 0)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_RETURN, 0, KEYEVENTF_KEYUP, 0, 0)),
    )
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send_input = user32.SendInput
    send_input.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    send_input.restype = wintypes.UINT
    sent = int(send_input(len(inputs), inputs, ctypes.sizeof(INPUT)))
    if sent == len(inputs):
        return SendResult(True, planned_at, called_at, perf_called_ns, sent)
    code = ctypes.get_last_error()
    return SendResult(
        False,
        planned_at,
        called_at,
        perf_called_ns,
        sent,
        error_code=code,
        error=ctypes.FormatError(code).strip() if code else "SendInput 未发送全部事件",
    )
