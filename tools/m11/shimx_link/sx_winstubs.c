/* sx_winstubs.c — M11 shimx リンクへの winstubs 結線 (#223 / CAB-96 §8-2)。
 *
 * build.sh が tools/startup/winstubs/src/*.c を同リンクに入れ、wrap_list.txt を -Wl,--wrap=<api> として渡す。
 * 本ファイルは link 側の 1 ファイル:
 *   - constructor (priority 102 = sx_cbboot の既定優先度より先) で winstubs_init(0) を 1 回呼ぶ
 *     (engine モジュール登録 / 環境 seed / trust_ok / ShellExecute hook / GetProcAddress 表)。
 *     m11_boot_enter より前に必ず実行されるので、THostInstance 構築前という要件を満たす。
 *   - __asm_cpuid の実体は m11_simd2.py が winstubs_cpuid を呼ぶ形で生成 (m11_simd.c)。
 *   - sx_ws_probe_*: 同一 wasm 内から --wrap 経由のシンボルを叩く検査口 (ws_e2e.mjs が呼ぶ)。
 *     lift 側が __wrap_<api> に束縛されていることの実測に使う (export 名は wrap されないので JS 側から直接は叩けない)。
 */
#include <emscripten.h>
#include <string.h>
#include "../../startup/winstubs/src/winstubs.h"

typedef struct { unsigned a, b, c, d; } sx_cpuid_t;
extern sx_cpuid_t __asm_cpuid(unsigned leaf);   /* lift 側 helper (m11_simd.c): winstubs_cpuid へ橋渡し */

__attribute__((constructor(102))) static void sx_ws_boot(void) { winstubs_init(0); }

/* ---- G05: lift 側 helper 経由 ---- */
EMSCRIPTEN_KEEPALIVE unsigned sx_ws_probe_cpuid(unsigned leaf, int reg) {
    sx_cpuid_t r = __asm_cpuid(leaf);
    return reg == 0 ? r.a : reg == 1 ? r.b : reg == 2 ? r.c : r.d;
}

/* ---- G03: 署名チェーン (VERIFY → Query → MsgGetParam → Find → NameString → CLOSE) を --wrap 経由で ---- */
EMSCRIPTEN_KEEPALIVE int sx_ws_probe_g03(int use_engine) {
    HMODULE m = use_engine ? winstubs_engine_module() : 0;   /* 0 = 呼出元 EXE */
    WCHAR path[260]; GetModuleFileNameW(m, path, 260);
    unsigned char wtd[128] = { 0 }; GUID act = { 0 };
    LONG v = WinVerifyTrust(0, &act, wtd);
    DWORD enc, ct, ft; void *hs = 0, *hm = 0;
    int ok = (v == 0) && CryptQueryObject(1, path, 0x400, 2, 0, &enc, &ct, &ft, &hs, &hm, NULL);
    DWORD len = 0;
    if (ok) ok = CryptMsgGetParam(hm, 6, 0, NULL, &len) && len >= 0x80;
    void* si = ok ? LocalAlloc(0x40, len) : NULL;
    if (ok) ok = si && CryptMsgGetParam(hm, 6, 0, si, &len);
    void* ctx = ok ? CertFindCertificateInStore(hs, enc, 0, 0xb0000, si, NULL) : NULL;
    int match = 0;
    if (ctx) {
        char cn[64] = { 0 };
        DWORD n = CertGetNameStringA(ctx, 4, 0, NULL, NULL, 0);
        if (n && n < sizeof cn) { CertGetNameStringA(ctx, 4, 0, NULL, cn, n); match = !strcmp(cn, "Image Line NV"); }
        CertFreeCertificateContext(ctx);
    }
    if (si) LocalFree(si);
    if (hs) CertCloseStore(hs, 0);
    if (hm) CryptMsgClose(hm);
    LONG c = WinVerifyTrust(0, &act, wtd);
    return match && v == 0 && c == 0;
}

/* ---- G12: CreateProcessW は試行されても成功 0。WebView2Loader.dll は NULL/126 ---- */
EMSCRIPTEN_KEEPALIVE int sx_ws_probe_g12(void) {
    static const WCHAR exe[] = { 'i','l','b','r','i','d','g','e','.','e','x','e', 0 };
    static const WCHAR wv[] = { 'W','e','b','V','i','e','w','2','L','o','a','d','e','r','.','d','l','l', 0 };
    unsigned char si[104] = { 0 }; PROCESS_INFORMATION64 pi;
    BOOL cp = CreateProcessW(exe, NULL, NULL, NULL, 0, 0, NULL, NULL, si, &pi);
    HMODULE h = LoadLibraryW(wv);
    return (cp ? 1 : 0) | (h ? 2 : 0) | ((int)GetLastError() << 8);
}

/* ---- 統計 / ログ (lift 実機の観測口) ---- */
EMSCRIPTEN_KEEPALIVE unsigned sx_ws_stat(int i) {
    const WsStats* s = winstubs_stats();
    switch (i) {
        case 0: return s->verify_trust;  case 1: return s->crypt_query;   case 2: return s->cert_name;
        case 3: return s->cpuid;         case 4: return s->createprocess_attempts; case 5: return s->createprocess_success;
        case 6: return s->loadlib_calls; case 7: return s->loadlib_miss;  case 8: return s->loadlib_blocked;
        case 9: return s->pump_calls;    case 10: return s->find_window;  case 11: return s->sysmetrics;
        case 12: return s->shell_calls;
        default: return 0;
    }
}
EMSCRIPTEN_KEEPALIVE const char* sx_ws_loadlib_miss(int i) { return winstubs_loadlib_miss(i); }
