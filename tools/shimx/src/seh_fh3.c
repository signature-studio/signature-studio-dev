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
