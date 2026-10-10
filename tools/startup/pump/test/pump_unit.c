/* pump_unit.c — pump shim 単体テスト (C 単独、ST ビルド想定 / HOSTED・NONE・SPIN を切替検証)。
 *
 * 出力: "Tnn\tpass|fail 詳細" の KV 行。runner (host/run_e2e.mjs) が全行を検査する。
 * MT 固有 (futex 実待ち) は e2e 側で検証するため、ここでは待機「しない」経路と
 * キュー・タイマ・フィルタ・優先順の論理を検証する。
 */
#include "../src/pump_internal.h"
#include "../src/pump_api.h"
#include <stdlib.h>

static int g_fails;
static void rep(int id, int ok, const char* note) {
    printf("T%02d\t%s%c%s\n", id, ok ? "pass" : "fail", ok ? ' ' : ' ', note ? note : "");
    if (!ok) g_fails++;
}
#define CHECK(id, cond, note) rep(id, !!(cond), note)

static int eq(uint64_t a, uint64_t b) { return a == b; }

/* ---- テスト用 wndproc / timerproc ---- */
static uint64_t g_proc_hits;
static int64_t test_wndproc(void* hwnd, uint32_t msg, uint64_t wp, uint64_t lp) {
    (void)hwnd; (void)lp;
    g_proc_hits += 1;
    return (int64_t)(msg + wp);
}
static uint32_t g_tproc_hits;
static void test_tproc(void* hwnd, uint32_t msg, uint64_t id, uint32_t now) {
    (void)hwnd; (void)msg; (void)now;
    g_tproc_hits += (uint32_t)id;
}

int main(void) {
    winstubs_init(0);
    pump_set_wait_mode(PUMP_WAIT_HOSTED);
    pstash_clear();
    pump_stats_reset_e();

    /* T01: WMSG は Win64 MSG 48B */
    CHECK(1, sizeof(WMSG) == 48, "sizeof(WMSG) != 48");

    /* T02: ring 初期化 (magic/capacity/seq) */
    CHECK(2, g_pring.hdr[PR_H_MAGIC] == (int32_t)PR_MAGIC, "magic");
    CHECK(3, g_pring.hdr[PR_H_CAPACITY] == (int32_t)PR_CAP_DEFAULT, "capacity");
    CHECK(4, g_pring.slot[0][PR_S_SEQ] == 0 && g_pring.slot[PR_CAP_DEFAULT - 1][PR_S_SEQ] == (int32_t)(PR_CAP_DEFAULT - 1), "seq init");

    /* T05: PostMessageW → GetMessageW の往復 (同じスレッド内) */
    {
        WMSG m; memset(&m, 0, sizeof m);
        CHECK(5, PostMessageW((HWND)0x1111, PWM_MOUSEMOVE, 0xAABB, 0xCDDCCCDDu), "PostMessageW false");
        LONG r = GetMessageW(&m, 0, 0, 0);
        CHECK(6, r == 1, "GetMessageW ret");
        CHECK(7, m.message == PWM_MOUSEMOVE && m.hwnd == 0x1111, "msg/hwnd");
        CHECK(8, m.wParam == 0xAABB && m.lParam == 0xCDDCCCDDu, "wp/lp");
        CHECK(9, m.time != 0, "time 未設定");
        /* 空 → HOSTED は -1 */
        CHECK(10, GetMessageW(&m, 0, 0, 0) == -1, "空で -1 でない");
    }

    /* T11: PeekMessage PM_NOREMOVE で消えない / PM_REMOVE で消える */
    {
        WMSG m;
        PostMessageW(0, PWM_CHAR, 7, 8);
        CHECK(11, PeekMessageW(&m, 0, 0, 0, PPM_NOREMOVE) == TRUE, "peek no-remove");
        CHECK(12, PeekMessageW(&m, 0, 0, 0, PPM_NOREMOVE) == TRUE, "peek 2 回目 (残っている)");
        CHECK(13, PeekMessageW(&m, 0, 0, 0, PPM_REMOVE) == TRUE, "peek remove");
        CHECK(14, PeekMessageW(&m, 0, 0, 0, PPM_REMOVE) == FALSE, "peek 空");
        CHECK(15, eq(m.message, PWM_CHAR) && m.wParam == 7, "peek 取得内容");
    }

    /* T16: フィルタ (msg 範囲) — 不一致先頭は stash 退避され、後続で復元される */
    {
        WMSG m;
        PostMessageW((HWND)0x22, PWM_MOUSEMOVE, 1, 1);   /* 範囲外 → stash */
        PostMessageW((HWND)0x22, PWM_KEYDOWN, 2, 2);     /* 範囲内 */
        CHECK(16, PeekMessageW(&m, 0, PWM_KEYDOWN, PWM_SYSKEYUP, PPM_REMOVE) == TRUE, "フィルタ取得失敗");
        CHECK(17, m.message == PWM_KEYDOWN && m.wParam == 2, "フィルタで KEYDOWN が先に取れる");
        CHECK(18, PeekMessageW(&m, 0, 0, 0, PPM_REMOVE) == TRUE && m.message == PWM_MOUSEMOVE && m.wParam == 1,
              "stash 復元失敗");
        /* hwnd フィルタ: 別 hwnd は見えない */
        PostMessageW((HWND)0x33, PWM_CHAR, 3, 3);
        CHECK(19, PeekMessageW(&m, (HWND)0x44, 0, 0, PPM_NOREMOVE) == FALSE, "hwnd フィルタ無効");
        PeekMessageW(&m, 0, 0, 0, PPM_REMOVE);
    }

    /* T20: 優先順 — 投稿 → QUIT → PAINT → TIMER の順 (投稿と QUIT が同時) */
    {
        WMSG m;
        PostMessageW(0, PWM_CHAR, 11, 0);
        pquit_post(42);
        GetMessageW(&m, 0, 0, 0);
        CHECK(20, m.message == PWM_CHAR, "投稿が QUIT より先");
        LONG r = GetMessageW(&m, 0, 0, 0);
        CHECK(21, r == 0 && m.message == PWM_QUIT && m.wParam == 42, "WM_QUIT 取得");
        /* QUIT は消費済み → 次は空 */
        CHECK(22, GetMessageW(&m, 0, 0, 0) == -1, "QUIT は 1 回だけ");
    }

    /* T23: PAINT — InvalidateRect → WM_PAINT (低優先: 投稿の後) */
    {
        WMSG m;
        PostMessageW((HWND)0x55, PWM_CHAR, 1, 0);
        InvalidateRect((HWND)0x55, 0, TRUE);
        InvalidateRect((HWND)0x55, 0, TRUE);   /* 重複は 1 件に合流 */
        CHECK(23, GetMessageW(&m, 0, 0, 0) == 1 && m.message == PWM_CHAR, "投稿優先");
        CHECK(24, GetMessageW(&m, 0, 0, 0) == 1 && m.message == PWM_PAINT && m.hwnd == 0x55, "WM_PAINT 合成");
        CHECK(25, GetMessageW(&m, 0, 0, 0) == -1, "PAINT は合流 (1 件)");
    }

    /* T26: NONE モード — GetMessage はブロックしない (空即 -1)。時間上限で検証 */
    {
        pump_set_wait_mode(PUMP_WAIT_NONE);
        WMSG m;
        double t0 = pnow();
        LONG r = GetMessageW(&m, 0, 0, 0);
        double dt = pnow() - t0;
        CHECK(26, r == -1 && dt < 1.0, "NONE でブロックした (dt が大きい)");
        pump_set_wait_mode(PUMP_WAIT_HOSTED);
    }

    /* T27: SetTimer/KillTimer — id 採番・再設定・kill */
    {
        UINT_PTR_T a = SetTimer(0, 5, 10, 0);
        CHECK(27, a == 5, "SetTimer 既存 id");
        UINT_PTR_T b = SetTimer(0, 0, 10, 0);   /* 自動採番 */
        CHECK(28, b != 0 && b != 5, "SetTimer 自動 id");
        CHECK(29, KillTimer(0, b) == TRUE, "KillTimer true");
        CHECK(30, KillTimer(0, b) == FALSE, "KillTimer 二重目 false");
        KillTimer(0, 5);
        CHECK(31, ptimer_count() == 0, "タイマ残存");
    }

    /* T32: タイマ合成 — due 到来で WM_TIMER (HOSTED step 経由) */
    {
        WMSG m;
        SetTimer((HWND)0x66, 9, 10, 0);
        /* due を待つ (sleep 禁止のためビジーウェイト: 最大 200ms) */
        double t0 = pnow();
        while (pnow() - t0 < 200.0) {
            int r = pump_step(&m);
            if (r == 1 && m.message == PWM_TIMER) break;
        }
        CHECK(32, m.message == PWM_TIMER && m.hwnd == 0x66 && m.wParam == 9, "WM_TIMER 合成");
        /* 次の due は interval (10ms) 後 → wait_ms ヒントは (0, interval] */
        {
            double hint = pump_wait_ms();
            CHECK(33, hint > 0.0 && hint <= 11.0, "pump_wait_ms ヒント異常");
        }
        KillTimer((HWND)0x66, 9);
    }

    /* T34: TIMERPROC 付き SetTimer → DispatchMessage が proc を呼ぶ */
    {
        WMSG m;
        g_tproc_hits = 0;
        SetTimer((HWND)0x77, 3, 10, (LPVOID)test_tproc);
        double t0 = pnow();
        while (pnow() - t0 < 200.0) {
            if (pump_step(&m) == 1 && m.message == PWM_TIMER) break;
        }
        LONG dr = DispatchMessageW(&m);
        CHECK(34, g_tproc_hits == 3, "TIMERPROC 未呼出");
        CHECK(35, dr == 0, "DispatchMessageW(WM_TIMER) 戻り値");
        KillTimer((HWND)0x77, 3);
    }

    /* T36: wndproc 登録 → DispatchMessage / SendMessage が呼ぶ */
    {
        WMSG m;
        g_proc_hits = 0;
        pwnd_register((void*)0x88, test_wndproc);
        PostMessageW((HWND)0x88, PWM_CHAR, 5, 0);
        pump_step(&m);
        LONG dr = DispatchMessageW(&m);
        CHECK(36, g_proc_hits == 1, "wndproc 未呼出");
        CHECK(37, dr == (LONG)(PWM_CHAR + 5), "wndproc 戻り値");
        LRESULT_T sr = SendMessageW((HWND)0x88, 0x1234, 2, 0);
        CHECK(38, sr == (LRESULT_T)(uint32_t)(0x1234 + 2), "SendMessage 直接呼出");
        /* 未登録 hwnd は fail-soft */
        CHECK(39, SendMessageW((HWND)0x99, 1, 1, 1) == 0, "未登録 SendMessage 0");
    }

    /* T40: PostThreadMessageW — tid 無視で UI キューへ */
    {
        WMSG m;
        CHECK(40, PostThreadMessageW(777, PWM_APP_RUNTIME_STOP, 1, 2) == TRUE, "PostThreadMessageW false");
        CHECK(41, pump_step(&m) == 1 && m.message == PWM_APP_RUNTIME_STOP && m.wParam == 1, "thread msg 取得");
    }

    /* T42: ctrl 要求 — HOSTED ではブロックせず pending、応答書込み後に service で完了 */
    {
        /* 要求を積む (応答はまだ無い → pending -1) */
        double ret = 0;
        int rc = pump_ctrl_request(PCTRL_OP_ECHO, 0x5A5A, 0, &ret, 0);
        CHECK(42, rc == -1, "HOSTED で即完了してしまった");
        /* ホスト相当: 応答メールボックスに直接書く (req_id は in-flight のもの) */
        /* req_id は内部カウンタ — 外部からは addr 経由で読むテストにする (ここでは統計で確認) */
        CHECK(43, g_pstat.ctrl_req >= 1, "ctrl_req 計数");
    }

    /* T44: 統計の最低整合 */
    CHECK(44, g_pstat.pops >= 1 && g_pstat.pushes >= 1, "pops/pushes 計数");
    CHECK(45, g_pstat.hosted_empty >= 1, "hosted_empty 計数");
    CHECK(46, g_pstat.dispatched >= 2, "dispatched 計数");

    /* T47: winstubs 統計の踏襲 (g_ws.pump_calls が増えている) */
    CHECK(47, g_ws.pump_calls > 0, "g_ws.pump_calls 未加算 (winstubs リンク確認)");

    /* T48: GetProcAddress (動的束縛) も強定義に解決されている (winstubs ws_register_procs が
     * (void*)GetMessageW を登録するため、リンク時に本 TU の強定義へ解決されるはず) */
    {
        WCHAR u32n[16]; for (int i = 0; i < 16; i++) u32n[i] = 0;
        u32n[0] = 'u'; u32n[1] = 's'; u32n[2] = 'e'; u32n[3] = 'r'; u32n[4] = '3'; u32n[5] = '2'; u32n[6] = '.'; u32n[7] = 'd'; u32n[8] = 'l'; u32n[9] = 'l';
        HMODULE u32 = GetModuleHandleW(u32n);
        void* p1 = (void*)GetProcAddress(u32, "GetMessageW");
        void* p2 = (void*)GetMessageW;
        CHECK(48, p1 != 0 && p1 == p2, "GetProcAddress が強定義に一致しない");
    }

    printf("%s\t%s\n", "unit", g_fails ? "FAILED" : "ALL PASS");
    return g_fails ? 1 : 0;
}
