import ctypes

from app.input_sender import HARDWAREINPUT, INPUT, KEYBDINPUT, MOUSEINPUT


def test_windows_input_structure_sizes() -> None:
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(KEYBDINPUT) == 24
        assert ctypes.sizeof(MOUSEINPUT) == 32
        assert ctypes.sizeof(INPUT) == 40
    else:
        assert ctypes.sizeof(KEYBDINPUT) == 16
        assert ctypes.sizeof(MOUSEINPUT) == 24
        assert ctypes.sizeof(INPUT) == 28
    assert ctypes.sizeof(HARDWAREINPUT) == 8
