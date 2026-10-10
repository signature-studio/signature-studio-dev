/* IPP shim: lift 側 FLEngine が解決する dsp_ippv2 の 420 名関数表 + MS x64 レジスタブロック thunk。
   呼出規約の契約 (tools/icall/icall_rewrite.py の memory-ABI ブロックと同一配置 + スタック引数ポインタ +0x48 の拡張):
     +0x00 target(GetProcAddress が返した値)  +0x08 rcx +0x10 rdx +0x18 r8 +0x20 r9  +0x28..+0x40 xmm0..3 (下位 64bit, float は下位 32bit)
     +0x48 stk (= call 時点の rsp+0x20 = 第 5 引数スロットのアドレス)  +0x80 rax(戻り)  +0x88 xmm0(戻り) */
#pragma once
#include <stdint.h>
#include <stddef.h>

/* ゲストポインタ(レジスタ/スタック上の 64bit 値) <-> ホストポインタ変換。既定は恒等 (lift 側のゲストアドレス = wasm32 リニアメモリ番地: m11/lowbase 方式)。
   ゲスト VA にベースオフセットを持つ方式ならリンク時に -DIPP_GUEST_PTR(w)=... -DIPP_TO_GUEST(p)=... で差し替える。 */
#ifndef IPP_GUEST_PTR
#define IPP_GUEST_PTR(w) ((uintptr_t)(w))
#endif
#ifndef IPP_TO_GUEST
#define IPP_TO_GUEST(p) ((uint64_t)(uintptr_t)(p))
#endif

typedef struct IppBlk {
  uint64_t target;
  uint64_t gp[4];      /* rcx rdx r8 r9 */
  uint64_t xmm[4];     /* xmm0..3 */
  uint64_t stk;        /* 第 5 引数以降へのポインタ (64bit 語の配列) */
  uint64_t _rsv[6];
  uint64_t rax;
  uint64_t xmm0ret;
} IppBlk;
_Static_assert(offsetof(IppBlk, gp) == 0x08 && offsetof(IppBlk, xmm) == 0x28 && offsetof(IppBlk, stk) == 0x48 &&
               offsetof(IppBlk, rax) == 0x80 && offsetof(IppBlk, xmm0ret) == 0x88, "IppBlk layout must match icall_rewrite BLK");

typedef struct IppShimEntry {
  const char *name;
  void (*blk)(IppBlk *);   /* 実装済み: 型付き実装を呼ぶ thunk / 未実装: NULL (fail-soft stub は dispatch が処理) */
  const char *conf;        /* 署名確度 A / B+ / B- (REPORT.md §2) */
  uint8_t impl;
  int8_t nargs;            /* -1 = 署名不明 */
  const char *sig;         /* C プロトタイプ文字列 */
} IppShimEntry;
extern const IppShimEntry ipp_shim_table[];   /* 名前昇順 (strcmp) */
extern const int ipp_shim_table_count;        /* 420 */

enum { IPP_SHIM_SOFT = 0, IPP_SHIM_STRICT = 1 };

/* ---- GetProcAddress / LoadLibrary 相当 ---- */
int      ipp_shim_find(const char *name);                 /* 表 index or -1。"legacy90" 接頭辞は剥がして引く */
uint64_t ipp_shim_cookie(int idx);                        /* GetProcAddress が FL に返す値 (非 0。表要素のアドレス) */
uint64_t ipp_shim_getproc(const char *name);              /* name -> cookie / 0 */
uint64_t ipp_shim_load_library_w(const uint16_t *wname);  /* "dsp_ippv2[_x64][.dll|.dylib]" (パス・大小無視) なら module handle, 他は 0 */
uint64_t ipp_shim_get_proc_address(uint64_t hmod, const char *name);
int      ipp_shim_owns(uint64_t target);                  /* target が本 shim の cookie か */
/* b->target が本 shim の cookie なら実行して 1, そうでなければ 0 (b は不変)。icall dispatch から呼ぶ */
int      ipp_shim_dispatch(IppBlk *b);

/* ---- fail-soft / 採取 ---- */
void     ipp_shim_set_mode(int mode);                     /* SOFT(既定): 未実装は rax=0/xmm0=0 を返し数える。STRICT: 未実装で trap */
int      ipp_shim_get_mode(void);
uint32_t ipp_shim_calls(int idx);                         /* 関数別呼出回数 (実装済み・stub 共通) */
uint32_t ipp_shim_stub_calls_total(void);
int      ipp_shim_stub_distinct(void);                     /* 呼ばれた stub の種類数 */
int      ipp_shim_stub_first(int k);                       /* k 番目に初めて呼ばれた stub の表 index (範囲外 -1) */
int      ipp_shim_last_stub(void);                         /* 直近に呼ばれた stub の index (無ければ -1) */
void     ipp_shim_reset(void);
