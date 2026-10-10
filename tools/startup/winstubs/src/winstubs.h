/* winstubs: 起動 critical Win32 API の fail-soft 差分層 (CAB-96)。
 *
 * tools/shimx の実装を土台に、startup stub_plan.md §5 (A/B/D) の戻り値表と食い違う API だけを
 *   (1) ld --wrap=<api> による薄い委譲 (__wrap_<api> → 必要時 __real_<api> = shimx 実装)
 *   (2) shimx に無い API の新規 (weak) 定義
 * で補う。shimx のソースは 1 行も変更しない。リンク時は src/*.c に加えて
 * tools/startup/winstubs/wrap_list.txt の各行を -Wl,--wrap=<api> として渡すこと (winstubs.sh 参照)。
 */
#ifndef WINSTUBS_H
#define WINSTUBS_H

#include "../../../shimx/src/shimx.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WS_CPU_SSE2 0   /* 既定: SSE2 まで広告 (tools/m11 の __asm_* SIMD helper 到達範囲と一致) */
#define WS_CPU_PLAN 1   /* stub_plan §5: SSE3/SSSE3/SSE4.1/4.2/POPCNT (AVX2 は常に立てない) */

typedef struct WsConfig {
    int trust;            /* 1: G03 署名検証チェーン (WinVerifyTrust..CertGetNameStringW) を「検証しない shim」として通す */
    int cpu_profile;      /* WS_CPU_* */
    const char* user;     /* 仮想ユーザ名 (既定 "webstudio" = vreg_seed.json の _known_folders) */
    int screen_w, screen_h;   /* GetSystemMetrics(SM_CXSCREEN/CYSCREEN) / SPI_GETWORKAREA (既定 1920x1080) */
} WsConfig;

typedef struct WsStats {
    uint32_t verify_trust, crypt_query, crypt_msg_param, cert_find, cert_name;      /* G03 */
    uint32_t cpuid, find_window;                                                    /* G05/G06 */
    uint32_t createprocess_attempts, createprocess_success;                         /* G12 */
    uint32_t shell_calls, shell_ok, shell_fnf, shell_cancel, shell_url, shell_restartfl;
    uint32_t loadlib_calls, loadlib_miss, loadlib_blocked;
    uint32_t bufferedpaint, loadicon, sysmetrics, spi;                              /* D */
    uint32_t pump_calls;                                                            /* user32 ポンプ系 (CAB-102 が実体を結線) */
} WsStats;

void winstubs_defaults(WsConfig* cfg);
void winstubs_init(const WsConfig* cfg);          /* NULL = 既定。多重呼出し可 (最後の cfg が有効) */
const WsStats* winstubs_stats(void);
void winstubs_stats_reset(void);

HMODULE winstubs_engine_module(void);             /* GetModuleFileNameW(h) が FLEngine_x64.dll の絶対パスを返す h */
int  winstubs_restart_requested(void);            /* `fldiagnostic /restartfl` を ShellExecute が検知した (G12: glue がページ再ロード) */
void winstubs_set_open_url_cb(void (*cb)(const char* url));   /* ShellExecute "open" http(s):// を受ける (ユーザ操作中のみ実開封する側で判断) */
const char* winstubs_loadlib_miss(int i);         /* LoadLibrary 失敗名ログ (最大 32 件, 重複なし)。i >= 件数なら NULL */

/* cpuid 命令の返値表 (lift 側 __asm_cpuid の実体から呼ぶ)。out = {eax, ebx, ecx, edx} */
void winstubs_cpuid(uint32_t leaf, uint32_t sub, uint32_t out[4]);

/* ShellExecute 分類 (テスト用に公開): 1=成功扱い(33) 2=ERROR_FILE_NOT_FOUND(2) 3=UAC キャンセル(1223 / ShellExecuteEx のみ) */
int  winstubs_shell_classify(const char* verb, const char* file, const char* params, int is_ex);

#ifdef __cplusplus
}
#endif
#endif
