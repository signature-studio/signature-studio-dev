/* shimx 単体テスト (fh3): __CxxFrameHandler3 FuncInfo の funclet walk (MX-45 #4161)。
 * 合成 FuncInfo で期待値を固定する。Python 正本 (mx6_pdata_eh.funclets_fh3) と同じ規則:
 *   unwind action (disp_unwind の 2 番目の DWORD) と catch handler (handler の 4 番目 DWORD) を集める。 */
#include "test_common.h"

static void put32(uint8_t* img, uint32_t at, uint32_t v) {
    for (int i = 0; i < 4; i++) img[at + i] = (uint8_t)(v >> (8 * i));
}

static void t_walk(void) {
    static uint8_t img[0x1000];
    memset(img, 0, sizeof img);
    /* FuncInfo @0x100: magic, maxState=2, dispUnwind=0x200, nTry=1, dispTry=0x300 */
    put32(img, 0x100, 0x19930520u); put32(img, 0x104, 2); put32(img, 0x108, 0x200);
    put32(img, 0x10C, 1); put32(img, 0x110, 0x300);
    /* unwind map: state0 = {prev=-1, action=0x400}, state1 = {prev=0, action=0} (action 0 は除外) */
    put32(img, 0x200, 0xFFFFFFFFu); put32(img, 0x204, 0x400);
    put32(img, 0x208, 0);           put32(img, 0x20C, 0);
    /* try map: tryLow=0 tryHigh=0 catchHigh=0 nCatch=2 dispCatch=0x340 */
    put32(img, 0x300, 0); put32(img, 0x304, 0); put32(img, 0x308, 0);
    put32(img, 0x30C, 2); put32(img, 0x310, 0x340);
    /* handler 0: {adjective,type,fp,handler=0x500}、handler 1: handler=0x400 (unwind と重複 → 1 件) */
    put32(img, 0x340 + 12, 0x500); put32(img, 0x340 + 16 + 12, 0x400);

    uint32_t out[16];
    int n = shimx_fh3_funclets(img, sizeof img, 0x100, out, 16);
    CHECK(n == 2);
    CHECK(out[0] == 0x400 && out[1] == 0x500);

    /* magic 不一致 (FH4 符号化形 0x19930523) は棄却 */
    put32(img, 0x100, 0x19930523u);
    CHECK(shimx_fh3_funclets(img, sizeof img, 0x100, out, 16) == -1);
    put32(img, 0x100, 0x19930520u);

    /* 上限超過 (nCatch > 0x100) は棄却 */
    put32(img, 0x30C, 0x101);
    CHECK(shimx_fh3_funclets(img, sizeof img, 0x100, out, 16) == -1);
    put32(img, 0x30C, 2);

    /* 画像外の FuncInfo は棄却 */
    CHECK(shimx_fh3_funclets(img, sizeof img, 0xFF0, out, 16) == -1);

    /* out_cap 超過: try 間で共有する handler RVA {0x500, 0x600} を 2 try × 2 catch で置く。
     * cap=16 では正確に 2。cap=1 では out は先頭 1 件のみ有効で、戻り値は真の件数 (2) の上界。
     * 現実装は 3 を返すが、契約は「2 以上で cap (1) を超える」のみを保証する。 */
    memset(img, 0, sizeof img);
    put32(img, 0x100, 0x19930520u); put32(img, 0x104, 0); put32(img, 0x108, 0);
    put32(img, 0x10C, 2); put32(img, 0x110, 0x300);
    put32(img, 0x30C, 2); put32(img, 0x310, 0x340);
    put32(img, 0x320, 2); put32(img, 0x324, 0x360);
    put32(img, 0x340 + 12, 0x500); put32(img, 0x350 + 12, 0x600);
    put32(img, 0x360 + 12, 0x500); put32(img, 0x370 + 12, 0x600);
    CHECK(shimx_fh3_funclets(img, sizeof img, 0x100, out, 16) == 2);
    CHECK(out[0] == 0x500 && out[1] == 0x600);
    int n1 = shimx_fh3_funclets(img, sizeof img, 0x100, out, 1);
    CHECK(n1 >= 2);
    CHECK(out[0] == 0x500);
}

/* 合成 FuncInfo → ShxSehScope: IP map {0x100→state0, 0x200→state1, 0x300→state2}、func_end=0x400。
 * try0 = state[0,1] の catch-all (handler target 0x500)、try1 = state[2,2] の typed (ptype 0x5000, target 0x600)。 */
static void t_scopes(void) {
    static uint8_t img[0x1000];
    memset(img, 0, sizeof img);
    put32(img, 0x100, 0x19930520u); put32(img, 0x104, 0);
    put32(img, 0x10C, 2); put32(img, 0x110, 0x200);   /* nTry=2 dispTry=0x200 */
    put32(img, 0x114, 3); put32(img, 0x118, 0x300);   /* nIP=3 dispIP=0x300 */
    /* try0 @0x200: low=0 high=1 nCatch=1 dispHA=0x240 */
    put32(img, 0x200, 0); put32(img, 0x204, 1); put32(img, 0x208, 0);
    put32(img, 0x20C, 1); put32(img, 0x210, 0x240);
    /* try1 @0x214: low=2 high=2 nCatch=1 dispHA=0x250 */
    put32(img, 0x214, 2); put32(img, 0x218, 2); put32(img, 0x21C, 0);
    put32(img, 0x220, 1); put32(img, 0x224, 0x250);
    /* handler0 @0x240: {adj, ptype=0 (catch-all), fp, target=0x500} */
    put32(img, 0x240 + 4, 0); put32(img, 0x240 + 12, 0x500);
    /* handler1 @0x250: {adj, ptype=0x5000 (typed), fp, target=0x600} */
    put32(img, 0x250 + 4, 0x5000); put32(img, 0x250 + 12, 0x600);
    /* IP map @0x300: {ip, state} */
    put32(img, 0x300, 0x100); put32(img, 0x304, 0);
    put32(img, 0x308, 0x200); put32(img, 0x30C, 1);
    put32(img, 0x310, 0x300); put32(img, 0x314, 2);

    ShxSehScope s[8];
    int n = shimx_fh3_scopes(img, sizeof img, 0x100, 0x400, s, 8);
    CHECK(n == 3);
    /* state0 [0x100,0x200) と state1 [0x200,0x300) は try0 (catch-all) に効く */
    CHECK(s[0].begin == 0x100 && s[0].end == 0x200 && s[0].kind == 2 && s[0].target == 0x500);
    CHECK(s[1].begin == 0x200 && s[1].end == 0x300 && s[1].kind == 2 && s[1].target == 0x500);
    /* state2 [0x300,0x400) は try1 (typed: kind=ptype) */
    CHECK(s[2].begin == 0x300 && s[2].end == 0x400 && s[2].kind == 0x5000 && s[2].target == 0x600);

    /* out_cap 超過: 件数は真の件数 (3) を返す */
    CHECK(shimx_fh3_scopes(img, sizeof img, 0x100, 0x400, s, 1) == 3);

    /* IP map が昇順でなければ棄却 */
    put32(img, 0x308, 0x50);
    CHECK(shimx_fh3_scopes(img, sizeof img, 0x100, 0x400, s, 8) == -1);
    put32(img, 0x308, 0x200);

    /* magic 不一致は棄却 */
    put32(img, 0x100, 0x19930523u);
    CHECK(shimx_fh3_scopes(img, sizeof img, 0x100, 0x400, s, 8) == -1);
}

void run_fh3_tests(void) {
    t_walk();
    t_scopes();
}
