from __future__ import annotations

import ctypes
import logging
import threading
from dataclasses import dataclass
from ctypes import wintypes
from typing import Optional


@dataclass(frozen=True, slots=True)
class OverlayGeometry:
    width: int
    height: int
    x: int
    y: int


def get_system_dpi() -> int:
    get_dpi_for_system = getattr(user32, "GetDpiForSystem", None)
    if get_dpi_for_system is not None:
        try:
            return max(96, int(get_dpi_for_system()))
        except Exception:
            pass
    screen_dc = user32.GetDC(None)
    try:
        return max(96, int(gdi32.GetDeviceCaps(screen_dc, 88)))
    finally:
        user32.ReleaseDC(None, screen_dc)


def scale_dip(value: float, dpi: int) -> int:
    return max(1, int(round(value * dpi / 96.0)))


def compute_top_center_geometry(
    screen_width: int,
    *,
    width: int = 168,
    height: int = 30,
    top_margin: int = 0,
) -> OverlayGeometry:
    x = max(0, (screen_width - width) // 2)
    y = max(0, top_margin)
    return OverlayGeometry(width=width, height=height, x=x, y=y)


if ctypes.sizeof(ctypes.c_void_p) == 8:
    LONG_PTR = ctypes.c_longlong
else:
    LONG_PTR = ctypes.c_long

LRESULT = LONG_PTR


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_byte),
        ("rgbGreen", ctypes.c_byte),
        ("rgbRed", ctypes.c_byte),
        ("rgbReserved", ctypes.c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", RGBQUAD * 1),
    ]


class RECTF(ctypes.Structure):
    _fields_ = [
        ("X", ctypes.c_float),
        ("Y", ctypes.c_float),
        ("Width", ctypes.c_float),
        ("Height", ctypes.c_float),
    ]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", wintypes.BOOL),
        ("SuppressExternalCodecs", wintypes.BOOL),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
gdiplus = ctypes.windll.gdiplus

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_APP_SHOW = 0x8001
WM_APP_HIDE = 0x8002
WM_APP_CLOSE = 0x8003
WM_APP_SET_MODE = 0x8004
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
HWND_TOPMOST = -1
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SM_CXSCREEN = 0
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0
DT_CENTER = 0x00000001
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
StringAlignmentCenter = 1
StringAlignmentNear = 0
FontStyleRegular = 0
UnitPixel = 2
SmoothingModeAntiAlias = 4
TextRenderingHintAntiAliasGridFit = 3
CombineModeReplace = 0
FillModeWinding = 0

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    wintypes.HDC,
    ctypes.POINTER(POINT),
    wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL

gdiplus.GdiplusStartup.argtypes = [
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(GdiplusStartupInput),
    ctypes.c_void_p,
]
gdiplus.GdiplusStartup.restype = ctypes.c_int
gdiplus.GdiplusShutdown.argtypes = [ctypes.c_ulonglong]
gdiplus.GdiplusShutdown.restype = None
gdiplus.GdipCreateFromHDC.argtypes = [wintypes.HDC, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreateFromHDC.restype = ctypes.c_int
gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetSmoothingMode.restype = ctypes.c_int
gdiplus.GdipSetTextRenderingHint.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetTextRenderingHint.restype = ctypes.c_int
gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreatePath.restype = ctypes.c_int
gdiplus.GdipStartPathFigure.argtypes = [ctypes.c_void_p]
gdiplus.GdipStartPathFigure.restype = ctypes.c_int
gdiplus.GdipAddPathLine.argtypes = [
    ctypes.c_void_p,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
]
gdiplus.GdipAddPathLine.restype = ctypes.c_int
gdiplus.GdipAddPathArc.argtypes = [
    ctypes.c_void_p,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
]
gdiplus.GdipAddPathArc.restype = ctypes.c_int
gdiplus.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
gdiplus.GdipClosePathFigure.restype = ctypes.c_int
gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreateSolidFill.restype = ctypes.c_int
gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipFillPath.restype = ctypes.c_int
gdiplus.GdipFillEllipse.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
]
gdiplus.GdipFillEllipse.restype = ctypes.c_int
gdiplus.GdipCreateFontFamilyFromName.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
gdiplus.GdipCreateFontFamilyFromName.restype = ctypes.c_int
gdiplus.GdipCreateFont.argtypes = [
    ctypes.c_void_p,
    ctypes.c_float,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_void_p),
]
gdiplus.GdipCreateFont.restype = ctypes.c_int
gdiplus.GdipStringFormatGetGenericDefault.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipStringFormatGetGenericDefault.restype = ctypes.c_int
gdiplus.GdipSetStringFormatAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetStringFormatAlign.restype = ctypes.c_int
gdiplus.GdipSetStringFormatLineAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetStringFormatLineAlign.restype = ctypes.c_int
gdiplus.GdipDrawString.argtypes = [
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.POINTER(RECTF),
    ctypes.c_void_p,
    ctypes.c_void_p,
]
gdiplus.GdipDrawString.restype = ctypes.c_int
gdiplus.GdipDeleteStringFormat.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteStringFormat.restype = ctypes.c_int
gdiplus.GdipDeleteFont.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteFont.restype = ctypes.c_int
gdiplus.GdipDeleteFontFamily.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteFontFamily.restype = ctypes.c_int
gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteBrush.restype = ctypes.c_int
gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeletePath.restype = ctypes.c_int
gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteGraphics.restype = ctypes.c_int

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class RecordingOverlay:
    _CLASS_NAME = "ChirpRecordingOverlay"
    _TRANSCRIBING_LABEL = "Transcribing"
    _LOADING_LABEL = "Loading model"
    _BACKGROUND_COLOR = 0xFFF5F5F7
    _TEXT_COLOR = 0xFF111111
    _DOT_COLOR = 0xFFFF3B30

    def __init__(
        self,
        *,
        logger: logging.Logger,
        enabled: bool = True,
    ) -> None:
        self._logger = logger
        self._enabled = enabled and hasattr(ctypes, "windll")
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hwnd: Optional[int] = None
        self._geometry: Optional[OverlayGeometry] = None
        self._dpi = 96
        self._mode = "transcribing"
        self._label = self._TRANSCRIBING_LABEL
        self._wndproc = WNDPROC(self._window_proc)

        if not self._enabled:
            return

        self._thread = threading.Thread(
            target=self._run_window,
            name="RecordingOverlay",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=2.0):
            self._logger.warning("Recording overlay did not initialize in time; disabling it")
            self._enabled = False

    def show(self, mode: str = "transcribing") -> None:
        if self._enabled and self._hwnd:
            self.set_mode(mode)
            user32.PostMessageW(self._hwnd, WM_APP_SHOW, 0, 0)

    def hide(self) -> None:
        if self._enabled and self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_HIDE, 0, 0)

    def close(self) -> None:
        if self._enabled and self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_CLOSE, 0, 0)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._label = self._LOADING_LABEL if mode == "loading" else self._TRANSCRIBING_LABEL
        if self._enabled and self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_SET_MODE, 0, 0)

    def _run_window(self) -> None:
        gdiplus_token = ctypes.c_ulonglong()
        try:
            startup_input = GdiplusStartupInput(1, None, False, False)
            self._check_status(
                gdiplus.GdiplusStartup(
                    ctypes.byref(gdiplus_token),
                    ctypes.byref(startup_input),
                    None,
                ),
                "GdiplusStartup",
            )

            h_instance = kernel32.GetModuleHandleW(None)
            wnd_class = WNDCLASSW()
            wnd_class.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
            wnd_class.hInstance = h_instance
            wnd_class.lpszClassName = self._CLASS_NAME
            atom = user32.RegisterClassW(ctypes.byref(wnd_class))
            if not atom and kernel32.GetLastError() != 1410:
                raise OSError("RegisterClassW failed")

            self._dpi = get_system_dpi()
            screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
            geometry = compute_top_center_geometry(
                screen_width,
                width=scale_dip(168, self._dpi),
                height=scale_dip(30, self._dpi),
                top_margin=0,
            )
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
                self._CLASS_NAME,
                self._label,
                WS_POPUP,
                geometry.x,
                geometry.y,
                geometry.width,
                geometry.height,
                None,
                None,
                h_instance,
                None,
            )
            if not hwnd:
                raise OSError("CreateWindowExW failed")

            self._hwnd = hwnd
            self._geometry = geometry
            self._render_layered_window()
            user32.ShowWindow(hwnd, SW_HIDE)
            self._ready.set()

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:  # pragma: no cover - runtime safety
            self._logger.warning("Recording overlay unavailable: %s", exc)
            self._ready.set()
        finally:
            if gdiplus_token.value:
                gdiplus.GdiplusShutdown(gdiplus_token)

    def _window_proc(self, hwnd, msg, w_param, l_param):
        if msg == WM_APP_SET_MODE:
            self._render_layered_window()
            return 0
        if msg == WM_APP_SHOW:
            self._render_layered_window()
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            return 0
        if msg == WM_APP_HIDE:
            user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        if msg == WM_APP_CLOSE or msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, w_param, l_param)

    def _render_layered_window(self) -> None:
        if not self._hwnd or not self._geometry:
            return

        width = self._geometry.width
        height = self._geometry.height
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        old_bitmap = gdi32.SelectObject(mem_dc, dib)

        try:
            ctypes.memset(bits, 0, width * height * 4)
            self._draw_overlay(mem_dc, width, height)

            src_pt = POINT(0, 0)
            dst_pt = POINT(self._geometry.x, self._geometry.y)
            size = SIZE(width, height)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            user32.UpdateLayeredWindow(
                self._hwnd,
                screen_dc,
                ctypes.byref(dst_pt),
                ctypes.byref(size),
                mem_dc,
                ctypes.byref(src_pt),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(dib)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)

    def _draw_overlay(self, hdc: int, width: int, height: int) -> None:
        graphics = ctypes.c_void_p()
        path = ctypes.c_void_p()
        brush = ctypes.c_void_p()
        dot_brush = ctypes.c_void_p()
        font_family = ctypes.c_void_p()
        font = ctypes.c_void_p()
        string_format = ctypes.c_void_p()

        try:
            self._check_status(gdiplus.GdipCreateFromHDC(hdc, ctypes.byref(graphics)), "GdipCreateFromHDC")
            self._check_status(gdiplus.GdipSetSmoothingMode(graphics, SmoothingModeAntiAlias), "GdipSetSmoothingMode")
            self._check_status(
                gdiplus.GdipSetTextRenderingHint(graphics, TextRenderingHintAntiAliasGridFit),
                "GdipSetTextRenderingHint",
            )
            self._check_status(gdiplus.GdipCreatePath(FillModeWinding, ctypes.byref(path)), "GdipCreatePath")

            radius = float(scale_dip(15, self._dpi))
            diameter = radius * 2.0
            self._check_status(gdiplus.GdipStartPathFigure(path), "GdipStartPathFigure")
            self._check_status(gdiplus.GdipAddPathLine(path, 0.0, 0.0, float(width), 0.0), "GdipAddPathLine top")
            self._check_status(
                gdiplus.GdipAddPathLine(path, float(width), 0.0, float(width), float(height - radius)),
                "GdipAddPathLine right",
            )
            self._check_status(
                gdiplus.GdipAddPathArc(
                    path,
                    float(width) - diameter,
                    float(height) - diameter,
                    diameter,
                    diameter,
                    0.0,
                    90.0,
                ),
                "GdipAddPathArc right",
            )
            self._check_status(
                gdiplus.GdipAddPathLine(path, float(width - radius), float(height), radius, float(height)),
                "GdipAddPathLine bottom",
            )
            self._check_status(
                gdiplus.GdipAddPathArc(
                    path,
                    0.0,
                    float(height) - diameter,
                    diameter,
                    diameter,
                    90.0,
                    90.0,
                ),
                "GdipAddPathArc left",
            )
            self._check_status(gdiplus.GdipClosePathFigure(path), "GdipClosePathFigure")

            self._check_status(
                gdiplus.GdipCreateSolidFill(self._BACKGROUND_COLOR, ctypes.byref(brush)),
                "GdipCreateSolidFill background",
            )
            self._check_status(gdiplus.GdipFillPath(graphics, brush, path), "GdipFillPath")

            self._check_status(
                gdiplus.GdipCreateSolidFill(self._DOT_COLOR, ctypes.byref(dot_brush)),
                "GdipCreateSolidFill dot",
            )
            self._check_status(
                gdiplus.GdipFillEllipse(
                    graphics,
                    dot_brush,
                    ctypes.c_float(float(scale_dip(16, self._dpi))),
                    ctypes.c_float(float(scale_dip(10, self._dpi))),
                    ctypes.c_float(float(scale_dip(6, self._dpi))),
                    ctypes.c_float(float(scale_dip(6, self._dpi))),
                ),
                "GdipFillEllipse",
            )

            self._check_status(
                gdiplus.GdipCreateFontFamilyFromName("Segoe UI", None, ctypes.byref(font_family)),
                "GdipCreateFontFamilyFromName",
            )
            self._check_status(
                gdiplus.GdipCreateFont(
                    font_family,
                    ctypes.c_float(float(scale_dip(11, self._dpi))),
                    FontStyleRegular,
                    UnitPixel,
                    ctypes.byref(font),
                ),
                "GdipCreateFont",
            )
            self._check_status(gdiplus.GdipStringFormatGetGenericDefault(ctypes.byref(string_format)), "GdipStringFormatGetGenericDefault")
            self._check_status(gdiplus.GdipSetStringFormatAlign(string_format, StringAlignmentCenter), "GdipSetStringFormatAlign")
            self._check_status(gdiplus.GdipSetStringFormatLineAlign(string_format, StringAlignmentCenter), "GdipSetStringFormatLineAlign")

            text_brush = ctypes.c_void_p()
            try:
                self._check_status(
                    gdiplus.GdipCreateSolidFill(self._TEXT_COLOR, ctypes.byref(text_brush)),
                    "GdipCreateSolidFill text",
                )
                left_padding = float(scale_dip(30, self._dpi))
                right_padding = float(scale_dip(10, self._dpi))
                layout_rect = RECTF(left_padding, 0.0, float(width) - left_padding - right_padding, float(height))
                self._check_status(
                    gdiplus.GdipDrawString(
                        graphics,
                        self._label,
                        -1,
                        font,
                        ctypes.byref(layout_rect),
                        string_format,
                        text_brush,
                    ),
                    "GdipDrawString",
                )
            finally:
                if text_brush:
                    gdiplus.GdipDeleteBrush(text_brush)
        finally:
            if string_format:
                gdiplus.GdipDeleteStringFormat(string_format)
            if font:
                gdiplus.GdipDeleteFont(font)
            if font_family:
                gdiplus.GdipDeleteFontFamily(font_family)
            if dot_brush:
                gdiplus.GdipDeleteBrush(dot_brush)
            if brush:
                gdiplus.GdipDeleteBrush(brush)
            if path:
                gdiplus.GdipDeletePath(path)
            if graphics:
                gdiplus.GdipDeleteGraphics(graphics)

    def _check_status(self, status: int, name: str) -> None:
        if status != 0:
            raise OSError(f"{name} failed with status {status}")


def enable_dpi_awareness() -> None:
    awareness_context = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if set_context is not None:
        try:
            if set_context(awareness_context):
                return
        except Exception:
            pass

    shcore = getattr(ctypes.windll, "shcore", None)
    if shcore is not None:
        try:
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
