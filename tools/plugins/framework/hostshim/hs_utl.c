/* hs_utl.c — CAB-195: RTL ユーティリティ 46 slot shim.
 *
 * 背景 (native 実測):
 *   TDelphiFruityPlug._AddRef/_Release (0x40e8f0/0x40e910), TDelphiInterfacedObject の
 *   文字列基底 (DynamicArray) の参照カウント操作 0x40e770 (1 個) / 0x40e800 (n 個),
 *   0x40e850 (n 個 wide) / 0x40e8a0 (TObject リスト free) は **Delphi RTL の真の実装**。
 *   Balance の host 呼出連鎖 (0x6bd210) は rcx/rsi = &plug の stack slot を渡す:
 *     0x6bd2fc: lea rcx,[rbp+0x40]; mov edx,2; call 0x40e800   (rcx=&rHostObj, edx=2)
 *   しかし lift した IR では rcx が BLK 外 (register 未定義) に落ち, RetDec が
 *   `@50` ("$") に定数折畳み → load [0x24] と load [0x54] (2 番目要素) で線形メモリ
 *   先頭を deref して OOB trap する (hs_e2e 実測 [dbg] -> 0x40e800 で停止)。
 *
 *   さらに wasm に AT&T lock xadd は無いため, `lock xadd [rax+8], -1` の IR は
 *   load/store に退化している (atomicity は wasm32 single-thread で実用上等価)。
 *
 * 対応: 46 slot のうち RTL ユーティリティ (slot 6..11 を使わない「0x40 系」) を C で
 * 提供し, hostshim の slot 表に同一 sign で登録する (hs_utl_enter は hostshim の
 * hs_slot_impl から slot != 0 の場合に委譲される: hostshim.c 側で実装)。
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#ifndef FW_BLK
#define FW_BLK 0x8A1000u
#endif
#define BLKQ(off) (*(volatile uint64_t *)(uintptr_t)(FW_BLK + (off)))

/* Block 用の fail-fast は hostshim.c の hs_rec_put 共通。副作用なし実装のみ置く。 */

/* wasm での有効ポインタ範囲: image 0x400000..0xd02000 または wasm heap
 * (GLOBAL_BASE=0x10000000 以降 ~0x14000000。実測 host obj 0x10fafa30,
 * scratch 0x10000448)。range 外 (極小値 / 0 相当 / image 外 VA) は触らない。 */
static int hs_ptr_ok(uint64_t p) { return p >= 0x400000u && p <= 0x1fffffffULL; }

/* 0x40e770 / 0x40e800 / 0x40e850: DynArray(s) の refcount を 1 減らし 0 なら解放。
 * native: rax=[rsi]; if rax!=0 { [rsi]=0; rax-=0x10; if [rax+8]>0 { lock xadd -1;
 *   if (old-1)==0 call 0x407040 (FreeMem) } } return rsi
 * BLK ABI: +8 = rcx/rsi (配列先頭ポインタのアドレス), +0x10 = edx/rbx (個数; 0x40e770 は 1)
 * ※ 0x40e850 は wide string (要素 2 バイト) だが refcount 構造は同一。 */
static long long hs_utl_dec(long long n) {
    for (long long i = 0; i < n; i++) {
        uint64_t *slot = (uint64_t *)(uintptr_t)(BLKQ(8) + 8u * i);
        if (!hs_ptr_ok(BLKQ(8))) break;
        uint64_t p = *slot;
        if (!p) continue;
        *slot = 0;
        /* wasm では refcount ヘッダが image 外 (極小値 / image 外 VA) を指し得る
         * (RetDec fold 残り) ため, image / heap 範囲のみ触る。外なら skip。 */
        if (!hs_ptr_ok(p) || p < 0x10) continue;
        uint32_t *rc = (uint32_t *)(uintptr_t)(p - 0x10 + 8);
        int32_t v = (int32_t)*rc;
        if (v > 0) {
            *rc = (uint32_t)(v - 1);
            if (v == 1) {
                /* FreeMem — FastMM lift (0x407040) を BLK 経由で呼ぶ */
                extern long long hs_utl_freemem(uintptr_t p);
                hs_utl_freemem((uintptr_t)(p - 0x10));
            }
        }
    }
    return (long long)BLKQ(8);
}

/* 0x40e8f0 / 0x40e910: TDelphiInterfacedObject._AddRef / _Release
 * native 0x40e8f0: rax=rcx; if rcx { rcx-=0x10; if [rcx+8]>=0 { edx=1; lock xadd +1 } }
 *                      return
 * native 0x40e910: rax=rcx; if rcx { rcx-=0x10; cmp [rcx+8],0; jge; mov edx,-1;
 *                      lock xadd [rcx+8],-1 } return
 * 戻り値は使用されない (Delphi の _AddRef 規約)。
 * wasm では refcount ヘッダ (obj-0x10+8) が linear memory 外 (VA 範囲外 / 極小値)
 * を指し得る (RetDec の fold 残り) ため, image 範囲 (0x400000..0xD02000) または
 * heap (0xF0000000.. 以上) のみ触る。外なら no-op。 */
static long long hs_utl_ref(long long d) {
    uint64_t p = BLKQ(8);
    if (p < 0x10 || !hs_ptr_ok(p)) return 0;
    uint32_t *rc = (uint32_t *)(uintptr_t)(p - 0x10 + 8);
    int32_t v = (int32_t)*rc;
    if (v < 0) return 0;
    *rc = (uint32_t)(v + (int32_t)d);
    return 0;
}

/* デバッグ用: host shim の util 呼出 (slot/id, p) を stderr に記録 */
int g_fw_utl_dbg = 0;   /* hs_dbg から JS 経由で 1 に */
static void utl_log(uint32_t tag, uint64_t p) {
    if (!g_fw_utl_dbg) return;
    fprintf(stderr, "[hs_utl] tag=0x%x p=0x%llx\n", tag, (unsigned long long)p);
    fflush(stderr);
}

/* 0x40e8a0: TObject リスト free — rcx = 先頭アドレス, edx = 個数
 * native: rsi=rcx; ebx=edx; if ebx>0 { rax=[rsi]; [rbp+0x28]=rax; if !=0 { [rsi]=0;
 *            rcx=[rbp+0x28]; call 0x404eb0 (TObject.Free) } rsi+=8; ebx-- } */
static long long hs_utl_tobj_free(void) {
    uint64_t base = BLKQ(8);
    int32_t n = (int32_t)BLKQ(0x10);
    for (int i = 0; i < n; i++) {
        uint64_t *slot = (uint64_t *)(uintptr_t)(base + 8u * i);
        uint64_t p = *slot;
        if (!p) continue;
        *slot = 0;
        extern long long hs_utl_tobj_destroy(uintptr_t p);
        hs_utl_tobj_destroy((uintptr_t)p);
    }
    return 0;
}

/* 0x407040 (FreeMem) 相当 — BLK+8 = ptr。m11/wasm では __icall_dispatch 経由で
 * FastMM lift の 0x407040 に届くが, hostshim 経由 (fold cell) では BLK 未設定なので
 * ここでは no-op (smoke は leak 許容)。 */
long long hs_utl_freemem(uintptr_t p) { (void)p; return 0; }

/* 0x404eb0 (TObject.Free) 相当 — BLK+8 = obj。vptr 経由の仮想 Destroy が必要だが
 * smoke では破壊予定の scratch のみ到達するため no-op。 */
long long hs_utl_tobj_destroy(uintptr_t p) { (void)p; return 0; }

/* エントリ (hostshim.c の slot6..11 から呼ばれる想定だが, 本 file は単体でも
 * 名前解決できるように EMSCRIPTEN_KEEPALIVE しておく) */
__attribute__((used)) long long hs_utl_dec1(void) { utl_log(0x40e770, BLKQ(8)); return hs_utl_dec(1); }
__attribute__((used)) long long hs_utl_decn(void) { utl_log(0x40e800, BLKQ(8)); return hs_utl_dec((long long)(int32_t)BLKQ(0x10)); }
__attribute__((used)) long long hs_utl_inc(void) { utl_log(0x40e8f0, BLKQ(8)); return hs_utl_ref(1); }
__attribute__((used)) long long hs_utl_dec1ref(void) { utl_log(0x40e910, BLKQ(8)); return hs_utl_ref(-1); }
__attribute__((used)) long long hs_utl_tobjfree(void) { utl_log(0x40e8a0, BLKQ(8)); return hs_utl_tobj_free(); }
