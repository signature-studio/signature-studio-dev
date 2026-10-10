/* D: UI/OS 付随 + user32 ポンプ系の stub。いずれも weak (tools/gui / CAB-102 の強定義が優先)。
 * ポンプ系は「呼出カウントのみ」: RING ABI 結線 (PeekMessage/GetMessage/MsgWait/SetTimer...) は CAB-102 が担当し、
 * ここでは未結線ビルドでも起動を止めない (GetMessageW=0 → ループ即終了, PeekMessageW=FALSE) 最小の値だけを返す。
 */
#include "ws_internal.h"

#define WEAK SHIMX_WEAK

/* ---- G06: 単一インスタンス検査 ---- */
WEAK HWND FindWindowW(LPCWSTR cls, LPCWSTR title) {
    (void)cls; (void)title; WS_INC(find_window);
    SetLastError(1407u /* ERROR_CANNOT_FIND_WND_CLASS: 実機で未登録クラスを問い合わせたときと同じ */);
    return 0;
}
WEAK HWND FindWindowExW(HWND parent, HWND after, LPCWSTR cls, LPCWSTR title) {
    (void)parent; (void)after; (void)cls; (void)title; WS_INC(find_window);
    SetLastError(1407u);
    return 0;
}

/* ---- uxtheme ---- */
WEAK HRESULT BufferedPaintInit(void) { WS_INC(bufferedpaint); return S_OK; }
WEAK HRESULT BufferedPaintUnInit(void) { WS_INC(bufferedpaint); return S_OK; }

/* ---- アイコン: リソースは lift 後の .rsrc から。それまでは非 NULL ダミー ---- */
WEAK HANDLE LoadIconW(HANDLE inst, LPCWSTR name) { (void)inst; (void)name; WS_INC(loadicon); return (HANDLE)0x00010001u; }

/* ---- GetSystemMetrics: キャンバス寸法 + Windows 10 (100% DPI) 既定の近似値 ---- */
WEAK int GetSystemMetrics(int idx) {
    const int w = g_ws_cfg.screen_w ? g_ws_cfg.screen_w : 1920, h = g_ws_cfg.screen_h ? g_ws_cfg.screen_h : 1080;
    WS_INC(sysmetrics);
    switch (idx) {
        case 0: case 16: case 78: return w;                        /* CXSCREEN / CXFULLSCREEN / CXVIRTUALSCREEN */
        case 1: case 79: return h;                                 /* CYSCREEN / CYVIRTUALSCREEN */
        case 17: return h - 40 - 23;                               /* CYFULLSCREEN */
        case 2: case 3: case 9: case 10: case 20: case 21: return 17;
        case 4: return 23;  case 5: case 6: return 1;  case 7: case 8: return 3;
        case 11: case 12: case 13: case 14: return 32;
        case 15: return 20; case 19: case 75: case 81: case 80: return 1;  /* MOUSEPRESENT / MOUSEWHEELPRESENT / SAMEDISPLAYFORMAT / CMONITORS */
        case 28: case 34: return 136; case 29: case 35: return 39;
        case 30: return 36; case 31: return 22;
        case 32: case 33: return 8;
        case 36: case 37: return 4; case 38: case 39: return 75;
        case 43: return 3; case 45: case 46: return 2;
        case 47: return 160; case 48: return 24;
        case 49: case 50: return 16;
        case 59: return w + 16; case 60: return h - 40 + 16;
        case 61: return w + 16; case 62: return h + 16;
        case 76: case 77: return 0;
        default: return 0;
    }
}

static void fill_logfont(uint8_t* lf) {
    static const char face[] = "Segoe UI";
    memset(lf, 0, 92);
    *(int32_t*)(lf + 0) = -12;                 /* lfHeight (9pt @96dpi) */
    *(int32_t*)(lf + 16) = 400;                /* lfWeight */
    lf[23] = 1;                                /* DEFAULT_CHARSET */
    for (size_t i = 0; i < sizeof face; i++) ((uint16_t*)(lf + 28))[i] = (uint16_t)(unsigned char)face[i];
}

WEAK BOOL SystemParametersInfoW(UINT action, UINT ui, PVOID pv, UINT win) {
    (void)win; WS_INC(spi);
    const int w = g_ws_cfg.screen_w ? g_ws_cfg.screen_w : 1920, h = g_ws_cfg.screen_h ? g_ws_cfg.screen_h : 1080;
    uint8_t* p = (uint8_t*)pv;
    switch (action) {
        case 0x30:  /* SPI_GETWORKAREA */
            if (!p) break;
            ((int32_t*)p)[0] = 0; ((int32_t*)p)[1] = 0; ((int32_t*)p)[2] = w; ((int32_t*)p)[3] = h - 40;
            return TRUE;
        case 0x29:  /* SPI_GETNONCLIENTMETRICS */
            if (!p || ui < 504) break;
            memset(p, 0, ui);
            *(uint32_t*)p = ui;
            ((int32_t*)p)[1] = 1; ((int32_t*)p)[2] = 17; ((int32_t*)p)[3] = 17; ((int32_t*)p)[4] = 22; ((int32_t*)p)[5] = 22;
            fill_logfont(p + 24);
            ((int32_t*)(p + 116))[0] = 22; ((int32_t*)(p + 116))[1] = 22; fill_logfont(p + 124);
            ((int32_t*)(p + 216))[0] = 22; ((int32_t*)(p + 216))[1] = 20;
            fill_logfont(p + 224); fill_logfont(p + 316); fill_logfont(p + 408);
            *(int32_t*)(p + 500) = 4;
            return TRUE;
        case 0x1F:  /* SPI_GETICONTITLELOGFONT */
            if (!p || ui < 92) break;
            fill_logfont(p);
            return TRUE;
        case 0x68: if (!p) break; *(UINT*)p = 3; return TRUE;                  /* WHEELSCROLLLINES */
        case 0x26: if (!p) break; *(BOOL*)p = 1; return TRUE;                  /* DRAGFULLWINDOWS */
        case 0x16: if (!p) break; *(UINT*)p = 1; return TRUE;                  /* KEYBOARDDELAY */
        case 0x0A: if (!p) break; *(UINT*)p = 31; return TRUE;                 /* KEYBOARDSPEED */
        case 0x6A: case 0x66: if (!p) break; *(UINT*)p = 400; return TRUE;     /* MENUSHOWDELAY / MOUSEHOVERTIME */
        case 0x62: case 0x64: if (!p) break; *(UINT*)p = 4; return TRUE;       /* MOUSEHOVERWIDTH / HEIGHT */
        default: break;
    }
    SetLastError(ERROR_INVALID_PARAMETER);       /* fail-soft: 未知の action は FALSE (trap しない) */
    return FALSE;
}

/* ---- user32 ポンプ系: 呼出カウントのみ (CAB-102 が強定義で置換) ---- */
#define PUMP() WS_INC(pump_calls)
WEAK BOOL PeekMessageW(LPVOID msg, HWND h, UINT lo, UINT hi, UINT rm) { (void)msg; (void)h; (void)lo; (void)hi; (void)rm; PUMP(); return FALSE; }
WEAK LONG GetMessageW(LPVOID msg, HWND h, UINT lo, UINT hi) { (void)msg; (void)h; (void)lo; (void)hi; PUMP(); return 0; }   /* 0 = WM_QUIT */
WEAK BOOL TranslateMessage(const void* msg) { (void)msg; PUMP(); return FALSE; }
WEAK LONG DispatchMessageW(const void* msg) { (void)msg; PUMP(); return 0; }
WEAK BOOL PostMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp) { (void)h; (void)m; (void)wp; (void)lp; PUMP(); return TRUE; }
WEAK LRESULT_T SendMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp) { (void)h; (void)m; (void)wp; (void)lp; PUMP(); return 0; }
WEAK void PostQuitMessage(int code) { (void)code; PUMP(); }
WEAK UINT_PTR_T SetTimer(HWND h, UINT_PTR_T id, UINT ms, LPVOID fn) { (void)h; (void)ms; (void)fn; PUMP(); return id ? id : 1; }
WEAK BOOL KillTimer(HWND h, UINT_PTR_T id) { (void)h; (void)id; PUMP(); return TRUE; }
WEAK BOOL WaitMessage(void) { PUMP(); return TRUE; }

/* ---- GetProcAddress への登録 (shimx の組込み表に無い新規 API) ---- */
static HMODULE mod(const char* n) {
    WCHAR w[64]; int i = 0;
    for (; n[i] && i < 63; i++) w[i] = (WCHAR)(unsigned char)n[i];
    w[i] = 0;
    return GetModuleHandleW(w);
}
void ws_register_procs(void) {
    HMODULE nt = mod("ntdll.dll"), u32 = mod("user32.dll"), ux = mod("uxtheme.dll");
    extern LONG RtlGetVersion(void*);
#define REG(m, n) shimx_proc_register(m, #n, 0, (void*)n)
    REG(nt, RtlGetVersion);
    REG(u32, FindWindowW); REG(u32, FindWindowExW); REG(u32, LoadIconW); REG(u32, GetSystemMetrics); REG(u32, SystemParametersInfoW);
    REG(u32, PeekMessageW); REG(u32, GetMessageW); REG(u32, TranslateMessage); REG(u32, DispatchMessageW);
    REG(u32, PostMessageW); REG(u32, SendMessageW); REG(u32, PostQuitMessage); REG(u32, SetTimer); REG(u32, KillTimer); REG(u32, WaitMessage);
    REG(ux, BufferedPaintInit); REG(ux, BufferedPaintUnInit);
    /* shimx は wtsapi32.dll を「システム DLL」と見なさず LoadLibrary が失敗する → 動的束縛 (Delphi) が空振りしないよう薄く登録 */
    HMODULE wts = shimx_module_register("wtsapi32.dll", 0, "C:\\Windows\\System32\\wtsapi32.dll");
    REG(wts, WTSRegisterSessionNotification); REG(wts, WTSUnRegisterSessionNotification);
    /* crypt32: shimx の組込み GetProcAddress 表に無い (静的 import でなく動的束縛された場合の備え) */
    HMODULE c32 = mod("crypt32.dll");
    REG(c32, CryptQueryObject); REG(c32, CryptMsgGetParam); REG(c32, CertFindCertificateInStore);
    REG(c32, CertGetNameStringW); REG(c32, CertGetNameStringA);
    REG(c32, CertFreeCertificateContext); REG(c32, CertCloseStore); REG(c32, CryptMsgClose);
#undef REG
}
