/*
 * gui_win32.h — Win32 定数と Win64 レイアウトの構造体 (lifted コードがメモリに置く形そのまま)。
 *
 * lift ABI 規約 (PROTOCOL.md §ABI):
 *  - 公開 API はすべて `int64_t NAME(int64_t a0, ...)` (引数・戻り値とも 64bit 整数)。
 *    lifter (RetDec) 産コードの `int64_t`/`int32_t`/ポインタ混在呼出を C の暗黙変換で受ける。
 *  - ポインタは wasm32 では 32bit アドレスを zero-extend した値。構造体内ポインタも 8 byte。
 */
#ifndef GUI_WIN32_H
#define GUI_WIN32_H
#include <stdint.h>

typedef int64_t  I64;
typedef uint64_t U64;

#define P_(x)    ((void *)(uintptr_t)(U64)(x))
#define H_(p)    ((int64_t)(uintptr_t)(p))

typedef struct { int32_t left, top, right, bottom; } WRECT;
typedef struct { int32_t x, y; } WPOINT;

typedef struct {            /* sizeof 48 */
  U64 hwnd; uint32_t message; uint32_t _pad;
  U64 wParam; I64 lParam;
  uint32_t time; WPOINT pt; uint32_t lPrivate;
} WMSG;

typedef struct {            /* WNDCLASSA/W sizeof 72 */
  uint32_t style; uint32_t _pad; U64 lpfnWndProc;
  int32_t cbClsExtra, cbWndExtra;
  U64 hInstance, hIcon, hCursor, hbrBackground, lpszMenuName, lpszClassName;
} WWNDCLASS;

typedef struct {            /* WNDCLASSEXA/W sizeof 80 */
  uint32_t cbSize, style; U64 lpfnWndProc;
  int32_t cbClsExtra, cbWndExtra;
  U64 hInstance, hIcon, hCursor, hbrBackground, lpszMenuName, lpszClassName, hIconSm;
} WWNDCLASSEX;

typedef struct {            /* PAINTSTRUCT sizeof 72 */
  U64 hdc; int32_t fErase; WRECT rcPaint; int32_t fRestore, fIncUpdate; uint8_t rgbReserved[32];
} WPAINTSTRUCT;

typedef struct {            /* BITMAPINFOHEADER */
  uint32_t biSize; int32_t biWidth, biHeight; uint16_t biPlanes, biBitCount;
  uint32_t biCompression, biSizeImage; int32_t biXPelsPerMeter, biYPelsPerMeter;
  uint32_t biClrUsed, biClrImportant;
} WBMIH;

typedef struct {            /* BITMAP (Win64) sizeof 32 */
  int32_t bmType, bmWidth, bmHeight, bmWidthBytes; uint16_t bmPlanes, bmBitsPixel; U64 bmBits;
} WBITMAP;

typedef struct {            /* LOGBRUSH sizeof 16 */
  uint32_t lbStyle; uint32_t lbColor; U64 lbHatch;
} WLOGBRUSH;

typedef struct {            /* TEXTMETRICA sizeof 56 / W sizeof 60 (共通先頭) */
  int32_t tmHeight, tmAscent, tmDescent, tmInternalLeading, tmExternalLeading;
  int32_t tmAveCharWidth, tmMaxCharWidth, tmWeight, tmOverhang, tmDigitizedAspectX, tmDigitizedAspectY;
} WTEXTMETRIC_HEAD;

typedef struct { int32_t cx, cy; } WSIZE;

typedef struct { uint8_t BlendOp, BlendFlags, SourceConstantAlpha, AlphaFormat; } WBLEND;

/* window messages */
enum {
  WM_NULL = 0, WM_CREATE = 1, WM_DESTROY = 2, WM_MOVE = 3, WM_SIZE = 5, WM_ACTIVATE = 6, WM_SETFOCUS = 7,
  WM_KILLFOCUS = 8, WM_ENABLE = 0xA, WM_SETTEXT = 0xC, WM_GETTEXT = 0xD, WM_GETTEXTLENGTH = 0xE, WM_PAINT = 0xF,
  WM_CLOSE = 0x10, WM_QUIT = 0x12, WM_ERASEBKGND = 0x14, WM_SHOWWINDOW = 0x18, WM_SETCURSOR = 0x20,
  WM_MOUSEACTIVATE = 0x21, WM_GETMINMAXINFO = 0x24, WM_WINDOWPOSCHANGING = 0x46, WM_WINDOWPOSCHANGED = 0x47,
  WM_NCCREATE = 0x81, WM_NCDESTROY = 0x82, WM_NCCALCSIZE = 0x83, WM_NCHITTEST = 0x84, WM_NCPAINT = 0x85,
  WM_KEYDOWN = 0x100, WM_KEYUP = 0x101, WM_CHAR = 0x102, WM_SYSKEYDOWN = 0x104, WM_SYSKEYUP = 0x105,
  WM_TIMER = 0x113, WM_MOUSEMOVE = 0x200, WM_LBUTTONDOWN = 0x201, WM_LBUTTONUP = 0x202, WM_LBUTTONDBLCLK = 0x203,
  WM_RBUTTONDOWN = 0x204, WM_RBUTTONUP = 0x205, WM_RBUTTONDBLCLK = 0x206, WM_MBUTTONDOWN = 0x207,
  WM_MBUTTONUP = 0x208, WM_MBUTTONDBLCLK = 0x209, WM_MOUSEWHEEL = 0x20A, WM_CAPTURECHANGED = 0x215,
  WM_USER = 0x400
};
enum { PM_NOREMOVE = 0, PM_REMOVE = 1, PM_NOYIELD = 2 };
enum { WS_POPUP = (int)0x80000000, WS_CHILD = 0x40000000, WS_VISIBLE = 0x10000000, WS_DISABLED = 0x08000000,
       WS_CLIPSIBLINGS = 0x04000000, WS_CLIPCHILDREN = 0x02000000, WS_CAPTION = 0x00C00000 };
enum { CS_DBLCLKS = 0x8 };
enum { GWL_STYLE = -16, GWL_EXSTYLE = -20, GWLP_WNDPROC = -4, GWLP_HINSTANCE = -6, GWLP_ID = -12,
       GWLP_USERDATA = -21 };
enum { SW_HIDE = 0, SW_SHOWNORMAL = 1, SW_SHOW = 5, SW_SHOWNA = 8, SW_SHOWDEFAULT = 10 };
enum { SWP_NOSIZE = 1, SWP_NOMOVE = 2, SWP_NOZORDER = 4, SWP_NOACTIVATE = 0x10, SWP_SHOWWINDOW = 0x40,
       SWP_HIDEWINDOW = 0x80 };
enum { RDW_INVALIDATE = 1, RDW_ERASE = 4, RDW_VALIDATE = 8, RDW_UPDATENOW = 0x100, RDW_ALLCHILDREN = 0x80 };
enum { SM_CXSCREEN = 0, SM_CYSCREEN = 1, SM_CXVSCROLL = 2, SM_CYHSCROLL = 3, SM_CYCAPTION = 4, SM_CXBORDER = 5,
       SM_CYBORDER = 6, SM_CXDOUBLECLK = 36, SM_CYDOUBLECLK = 37, SM_CXICON = 11, SM_CYICON = 12,
       SM_CXFRAME = 32, SM_CYFRAME = 33, SM_CMONITORS = 80, SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79,
       SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77, SM_CXSMICON = 49, SM_CYSMICON = 50, SM_CXDRAG = 68,
       SM_CYDRAG = 69, SM_CXFULLSCREEN = 16, SM_CYFULLSCREEN = 17, SM_SWAPBUTTON = 23, SM_MOUSEPRESENT = 19,
       SM_CXMIN = 28, SM_CYMIN = 29, SM_CXMAXIMIZED = 61, SM_CYMAXIMIZED = 62 };
enum { VK_LBUTTON = 1, VK_RBUTTON = 2, VK_MBUTTON = 4, VK_BACK = 8, VK_TAB = 9, VK_RETURN = 13, VK_SHIFT = 0x10,
       VK_CONTROL = 0x11, VK_MENU = 0x12, VK_ESCAPE = 0x1B, VK_SPACE = 0x20 };
enum { MK_LBUTTON = 1, MK_RBUTTON = 2, MK_SHIFT = 4, MK_CONTROL = 8, MK_MBUTTON = 0x10 };
enum { SRCCOPY = 0x00CC0020, SRCPAINT = 0x00EE0086, SRCAND = 0x008800C6, SRCINVERT = 0x00660046,
       SRCERASE = 0x00440328, NOTSRCCOPY = 0x00330008, NOTSRCERASE = 0x001100A6, MERGECOPY = 0x00C000CA,
       MERGEPAINT = 0x00BB0226, PATCOPY = 0x00F00021, PATPAINT = 0x00FB0A09, PATINVERT = 0x005A0049,
       DSTINVERT = 0x00550009, BLACKNESS = 0x00000042, WHITENESS = 0x00FF0062 };
enum { TRANSPARENT_ = 1, OPAQUE_ = 2 };
enum { DT_LEFT = 0, DT_CENTER = 1, DT_RIGHT = 2, DT_VCENTER = 4, DT_BOTTOM = 8, DT_SINGLELINE = 0x20,
       DT_CALCRECT = 0x400, DT_NOCLIP = 0x100, DT_NOPREFIX = 0x800 };
enum { ETO_OPAQUE = 2, ETO_CLIPPED = 4 };
enum { RGN_AND = 1, RGN_OR = 2, RGN_XOR = 3, RGN_DIFF = 4, RGN_COPY = 5 };
enum { NULLREGION = 1, SIMPLEREGION = 2, COMPLEXREGION = 3, ERROR_REGION = 0 };
enum { DIB_RGB_COLORS = 0, BI_RGB = 0, BI_BITFIELDS = 3 };
enum { WHITE_BRUSH = 0, LTGRAY_BRUSH = 1, GRAY_BRUSH = 2, DKGRAY_BRUSH = 3, BLACK_BRUSH = 4, NULL_BRUSH = 5,
       WHITE_PEN = 6, BLACK_PEN = 7, NULL_PEN = 8, SYSTEM_FONT = 13, DEFAULT_GUI_FONT = 17, DEFAULT_PALETTE = 15,
       SYSTEM_FIXED_FONT = 16, DC_BRUSH = 18, DC_PEN = 19 };
enum { HORZSIZE = 4, VERTSIZE = 6, HORZRES = 8, VERTRES = 10, BITSPIXEL = 12, PLANES = 14, NUMCOLORS = 24,
       LOGPIXELSX = 88, LOGPIXELSY = 90, SIZEPALETTE = 104, NUMRESERVED = 106, COLORRES = 108, RASTERCAPS = 38 };
enum { PS_SOLID = 0, PS_NULL = 5 };
enum { COLOR_WINDOW = 5, COLOR_BTNFACE = 15 };
enum { HWND_TOP_ = 0, HWND_BOTTOM_ = 1 };

#endif
