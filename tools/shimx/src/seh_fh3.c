/* MX-45 (#4161): __CxxFrameHandler3 の FuncInfo (x64 RVA 形) から funclet (catch 本体・cleanup action) の RVA を取る。
 *
 * Python 正本: tools/targets/massivex/dsp/scripts/mx6_pdata_eh.py funclets_fh3 と、上限棄却を加えた
 * mx39_funclet_reach.py fh3_funclets_capped (上限: maxState 0x1000 / nTry 0x1000 / nCatch 0x100)。
 * 画像は RVA で引ける平坦なバッファ (img[rva] = そのバイト)。範囲外の読みは 0 とする (Python の 0 埋めと同じ)。
 */
#include "shimx.h"

#define SHX_FH3_CAP_STATE  0x1000u
#define SHX_FH3_CAP_TRY    0x1000u
#define SHX_FH3_CAP_CATCH  0x100u

/* 4 byte 読みが画像末尾を跨ぐ場合は、範囲外の byte を 0 として読む */
static uint32_t fh3_rd32(const uint8_t* img, uint32_t img_size, uint32_t rva) {
    uint32_t v = 0;
    for (uint32_t i = 0; i < 4; i++) {
        uint64_t p = (uint64_t)rva + i;
        v |= (p < img_size ? (uint32_t)img[p] : 0u) << (8 * i);
    }
    return v;
}

static int fh3_add(uint32_t* out, uint32_t out_cap, uint32_t* n, uint32_t v) {
    for (uint32_t i = 0; i < *n && i < out_cap; i++)
        if (out[i] == v) return 0;
    if (*n < out_cap) out[*n] = v;
    (*n)++;
    return 1;
}

int shimx_fh3_funclets(const uint8_t* img, uint32_t img_size, uint32_t fi_rva,
                       uint32_t* out, uint32_t out_cap) {
    if (!img || (uint64_t)fi_rva + 36 > img_size) return -1;
    uint32_t magic = fh3_rd32(img, img_size, fi_rva);
    if (magic != 0x19930520u && magic != 0x19930521u && magic != 0x19930522u) return -1;
    uint32_t max_state = fh3_rd32(img, img_size, fi_rva + 4);
    uint32_t disp_unwind = fh3_rd32(img, img_size, fi_rva + 8);
    uint32_t n_try = fh3_rd32(img, img_size, fi_rva + 12);
    uint32_t disp_try = fh3_rd32(img, img_size, fi_rva + 16);
    if (max_state > SHX_FH3_CAP_STATE || n_try > SHX_FH3_CAP_TRY) return -1;

    uint32_t n = 0;
    for (uint32_t i = 0; i < max_state; i++) {
        uint32_t act = fh3_rd32(img, img_size, disp_unwind + 8u * i + 4u);
        if (act) fh3_add(out, out_cap, &n, act);
    }
    for (uint32_t t = 0; t < n_try; t++) {
        uint32_t tb = disp_try + 20u * t;
        uint32_t n_catch = fh3_rd32(img, img_size, tb + 12);
        if (n_catch > SHX_FH3_CAP_CATCH) return -1;
        uint32_t disp_ha = fh3_rd32(img, img_size, tb + 16);
        for (uint32_t h = 0; h < n_catch; h++)
            fh3_add(out, out_cap, &n, fh3_rd32(img, img_size, disp_ha + 16u * h + 12u));
    }
    return (int)n;
}

/* FH3 の unwind map と IP-to-state map から kind 0 (cleanup action) の ShxSehScope 表を作る (MX-57 #4928)。
 * unwind map の entry s は {toState(prev), action RVA} の 8 byte。IP 範囲 [ip[i], ip[i+1]) の state s から
 * prev を辿り、action を持つ state をすべて内側から順に同じ範囲で出す (seh_run_pads は表順に pc を含む scope を実行する)。
 * 戻り値は件数 (超過も真の件数)。FuncInfo 不正は -1。 */
int shimx_fh3_unwind_scopes(const uint8_t* img, uint32_t img_size, uint32_t fi_rva, uint32_t func_end_rva,
                            ShxSehScope* out, uint32_t out_cap) {
    if (!img || (uint64_t)fi_rva + 36 > img_size) return -1;
    uint32_t magic = fh3_rd32(img, img_size, fi_rva);
    if (magic != 0x19930520u && magic != 0x19930521u && magic != 0x19930522u) return -1;
    uint32_t max_state = fh3_rd32(img, img_size, fi_rva + 4);
    uint32_t disp_unwind = fh3_rd32(img, img_size, fi_rva + 8);
    uint32_t n_ip = fh3_rd32(img, img_size, fi_rva + 20);
    uint32_t disp_ip = fh3_rd32(img, img_size, fi_rva + 24);
    if (max_state > SHX_FH3_CAP_STATE || n_ip > SHX_FH3_CAP_STATE) return -1;
    for (uint32_t i = 1; i < n_ip; i++)
        if (fh3_rd32(img, img_size, disp_ip + 8u * i) < fh3_rd32(img, img_size, disp_ip + 8u * (i - 1)))
            return -1;

    uint32_t n = 0;
    for (uint32_t i = 0; i < n_ip; i++) {
        int32_t state = (int32_t)fh3_rd32(img, img_size, disp_ip + 8u * i + 4);
        uint32_t begin = fh3_rd32(img, img_size, disp_ip + 8u * i);
        uint32_t end = (i + 1 < n_ip) ? fh3_rd32(img, img_size, disp_ip + 8u * (i + 1)) : func_end_rva;
        if (end <= begin) continue;
        for (int32_t cur = state; cur >= 0 && (uint32_t)cur < max_state;) {
            uint32_t ub = disp_unwind + 8u * (uint32_t)cur;
            uint32_t act = fh3_rd32(img, img_size, ub + 4);
            if (act) {
                if (n < out_cap) {
                    out[n].begin = begin;
                    out[n].end = end;
                    out[n].kind = 0;
                    out[n].target = act;
                }
                n++;
            }
            int32_t prev = (int32_t)fh3_rd32(img, img_size, ub);
            if (prev >= cur) break;
            cur = prev;
        }
    }
    return (int)n;
}

/* FH3 の try map と IP-to-state map から ShxSehScope 表を作る (MX-57 #4928)。
 * IP map は {Ip RVA, State} の 8 byte 昇順。entry i の状態は [ip[i], ip[i+1]) (最後は func_end) に効く。
 * try t の [tryLow, tryHigh] に入る状態の範囲ごとに、handler を 1 件ずつ scope にする:
 *   pType == 0 → catch-all (kind 2)、それ以外 → typed (kind = pType の RVA)。target = dispOfHandler。
 * 未検証: unwind map (kind 0/1 の pad 領域) は扱わない。nested try の照合順は handler 順のまま。 */
int shimx_fh3_scopes(const uint8_t* img, uint32_t img_size, uint32_t fi_rva, uint32_t func_end_rva,
                     ShxSehScope* out, uint32_t out_cap) {
    if (!img || (uint64_t)fi_rva + 36 > img_size) return -1;
    uint32_t magic = fh3_rd32(img, img_size, fi_rva);
    if (magic != 0x19930520u && magic != 0x19930521u && magic != 0x19930522u) return -1;
    uint32_t n_try = fh3_rd32(img, img_size, fi_rva + 12);
    uint32_t disp_try = fh3_rd32(img, img_size, fi_rva + 16);
    uint32_t n_ip = fh3_rd32(img, img_size, fi_rva + 20);
    uint32_t disp_ip = fh3_rd32(img, img_size, fi_rva + 24);
    if (n_try > SHX_FH3_CAP_TRY || n_ip > SHX_FH3_CAP_STATE) return -1;
    for (uint32_t i = 1; i < n_ip; i++)
        if (fh3_rd32(img, img_size, disp_ip + 8u * i) < fh3_rd32(img, img_size, disp_ip + 8u * (i - 1)))
            return -1;

    uint32_t n = 0;
    for (uint32_t t = 0; t < n_try; t++) {
        uint32_t tb = disp_try + 20u * t;
        int32_t low = (int32_t)fh3_rd32(img, img_size, tb);
        int32_t high = (int32_t)fh3_rd32(img, img_size, tb + 4);
        uint32_t n_catch = fh3_rd32(img, img_size, tb + 12);
        if (n_catch > SHX_FH3_CAP_CATCH) return -1;
        uint32_t disp_ha = fh3_rd32(img, img_size, tb + 16);
        for (uint32_t i = 0; i < n_ip; i++) {
            int32_t state = (int32_t)fh3_rd32(img, img_size, disp_ip + 8u * i + 4);
            if (state < low || state > high) continue;
            uint32_t begin = fh3_rd32(img, img_size, disp_ip + 8u * i);
            uint32_t end = (i + 1 < n_ip) ? fh3_rd32(img, img_size, disp_ip + 8u * (i + 1)) : func_end_rva;
            if (end <= begin) continue;
            for (uint32_t h = 0; h < n_catch; h++) {
                uint32_t ptype = fh3_rd32(img, img_size, disp_ha + 16u * h + 4);
                uint32_t target = fh3_rd32(img, img_size, disp_ha + 16u * h + 12);
                if (n < out_cap) {
                    out[n].begin = begin;
                    out[n].end = end;
                    out[n].kind = ptype ? ptype : 2u;
                    out[n].target = target;
                }
                n++;
            }
        }
    }
    return (int)n;
}
