#ifndef GLUE_H
#define GLUE_H
/* glue.h — startup-glue 公開 API (CAB-101 / ST-T1, 親 CAB-22)。
 *
 * 役割 (実 FL lift コード未到達のため「結線規約 + 単体 e2e」を先行実施):
 *   1. THostInstance 構造体 + vtbl 3 slot の逐語実装 (stub_plan §2 / STARTUP.md S03)。
 *      layout は win64 実物と同じオフセットを wasm32 でも維持する (明示パディング)。
 *   2. CreateFruityInstance の呼出規約 (ハンドシェイク 0xC0 / 0xEDE95A) とスタブ。
 *      FL boot 貫通前は glue_set_create_fruity_instance() で差し替え、貫通後は
 *      m11 の export 解決結果をそのまま登録する (登録口は変わらない)。
 *   3. 初期化順序規約: 各段階を独立に呼べる API と、順序違反を検出する検査。
 *
 * ビルド: shimx + winstubs + pump + pathreg + vreg のソースと一緒に本 dir の src/glue.c を
 *   リンクする (host/build.sh 参照)。tools/startup/{vreg,pump,winstubs} と tools/shimx は
 *   読取専用 (本 dir からは include とコンパイル参照のみ)。
 */
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * 1. THostInstance — win64 実物と同一の 0x38 B layout (stub_plan §2)
 *
 *   +0x00 vtbl (3 slot) / +0x08 version=1 / +0x0c flags / +0x10 hwnd_parent
 *   +0x18 title="FL Studio" / +0x20,+0x28 = &zero_page / +0x30 cmdline buf[0x8000]
 *
 * wasm32 はポインタが 4B のため、**フィールドのオフセットを win64 と同じに保つ**ことを
 * 優先して明示パディングを置く (pump の WMSG 48B 維持と同じ方針)。
 * ================================================================ */
#define GLUE_HOST_SIZE        0x38u
#define GLUE_HOST_VERSION     1u
#define GLUE_HOST_TITLE       "FL Studio"
#define GLUE_CMDLINE_CAP      0x8000u

/* host フラグ (STARTUP.md §0) */
#define GLUE_FLAG_PLUGIN      0x1u   /* bit0: ラッパ/プラグインモード (cmdline 解析・署名確認スキップ) */
#define GLUE_FLAG_UNK1        0x2u   /* bit1: 不明 (DAT_015e01b0 に格納) */
#define GLUE_FLAG_NO_SPLASH   0x4u   /* bit2: スプラッシュ抑止 */
#define GLUE_FLAG_NO_SOUND    0x8u   /* bit3: 起動音抑止 */

/* vtbl 3 slot の逐語仕様 (FL64.exe 逆アセンブル, stub_plan §2):
 *   slot0 `0x140007520(this,a,b,c)`: a,b,c を int32→int64 符号拡張し this->vtbl[2] へ tail-call
 *   slot1 `0x140007530(this)`: ret (何もしない)
 *   slot2 `0x140007540(this,a,b,c)`: a-=2 後、(a==1 && (uint64)b<=1) ? 1 : 0
 * wasm32 では int64 を 1 引数で運べないため、引数は int32 で受ける (符号拡張は
 * lift 後の実引数 marshalling で確定させる。ST-T1 の trace で確認する未確定点)。 */
#pragma pack(push, 1)
typedef struct GlueHostVtbl {
    void* (*slot0)(void* self, int32_t a, int32_t b, int32_t c);   /* 0x140007520 */
    void  (*slot1)(void* self);                                    /* 0x140007530 */
    void* (*slot2)(void* self, int32_t a, int32_t b, int32_t c);   /* 0x140007540 */
} GlueHostVtbl;

typedef struct GlueHostInstance {
    void*            vtbl;        /* +0x00 */
    uint32_t         pad_04;      /* +0x04 (win64 の 8B アライン合わせ) */
    uint32_t         version;     /* +0x08 = 1 */
    uint32_t         flags;       /* +0x0c = 0 */
    uint64_t         hwnd_parent; /* +0x10 = 0 (plugin モード時の親) */
    const char*      title;       /* +0x18 = "FL Studio" */
    uint32_t         pad_1c;      /* +0x1c */
    void*            p20;         /* +0x20 = &zero_page */
    uint32_t         pad_24;      /* +0x24 */
    void*            p28;         /* +0x28 = &zero_page */
    uint32_t         pad_2c;      /* +0x2c */
    char*            cmdline;     /* +0x30 → buf[0x8000] */
    uint32_t         pad_34;      /* +0x34 (size 0x38) */
} GlueHostInstance;
#pragma pack(pop)

/* host 構造体が規約どおりのオフセットであることをコンパイル時に固定する */
typedef char glue_static_assert_vtbl_off   [(offsetof(GlueHostInstance, vtbl)       == 0x00) ? 1 : -1];
typedef char glue_static_assert_ver_off    [(offsetof(GlueHostInstance, version)     == 0x08) ? 1 : -1];
typedef char glue_static_assert_flags_off  [(offsetof(GlueHostInstance, flags)       == 0x0c) ? 1 : -1];
typedef char glue_static_assert_hwnd_off   [(offsetof(GlueHostInstance, hwnd_parent) == 0x10) ? 1 : -1];
typedef char glue_static_assert_title_off  [(offsetof(GlueHostInstance, title)       == 0x18) ? 1 : -1];
typedef char glue_static_assert_p20_off    [(offsetof(GlueHostInstance, p20)         == 0x20) ? 1 : -1];
typedef char glue_static_assert_p28_off    [(offsetof(GlueHostInstance, p28)         == 0x28) ? 1 : -1];
typedef char glue_static_assert_cmd_off    [(offsetof(GlueHostInstance, cmdline)     == 0x30) ? 1 : -1];
typedef char glue_static_assert_size_off   [(sizeof(GlueHostInstance)                == 0x38) ? 1 : -1];

/* ================================================================
 * 2. CreateFruityInstance 呼出規約 + スタブ
 *
 *   CreateFruityInstance(0xC0, 0xEDE95A, THostInstance*, void** iface)  (rcx,rdx,r8,r9)
 *   既定値は host(THostInstance*) と iface(void**) の 2 引数形 (mac / 将来の wasm 直呼出)。
 * ================================================================ */
#define GLUE_HSHAKE_A   0xC0u
#define GLUE_HSHAKE_B   0xEDE95Au

/* FL boot 未到達時のスタブ。ハンドシェイク不遵守は負値で返す (native は -2/-3)。
 * iface には Destroy スロットを持つスタブ iface を書き込む。 */
int glue_stub_create_fruity_instance(void* host, void** iface);

/* 本番は m11 export 解決結果を登録する (boot 貫通前はスタブのまま) */
void  glue_set_create_fruity_instance(int (*fn)(void* host, void** iface));
int   (*glue_get_create_fruity_instance(void))(void*, void**);
int   glue_create_fruity_instance_called(void);   /* 呼出回数 (スタブ検証用) */
void* glue_last_iface(void);                      /* 直近の *iface (検証用) */

/* ハンドシェイク定数付きの 4 引数呼出 (native と同じ引数形を再現する規約関数) */
int  glue_call_engine_entry(uint32_t a, uint32_t b, void* host, void** iface);

/* ================================================================
 * 3. 初期化順序規約
 *
 * 既定順 (ST-T1): mount 表 → vreg import/flush フック → pump RING 起動 →
 *                 wvfs mount → DllMain 前フック → DllMain → host 構築 →
 *                 CreateFruityInstance → 後フック → 終了処理。
 * 各段階は独立に呼べる。順序違反は GLUE_EORDER を返し違反カウンタを増やす。
 * ================================================================ */
#define GLUE_OK      0
#define GLUE_EARG   (-1)
#define GLUE_EORDER  (-100)   /* 初期化順序違反 */
#define GLUE_EBOOT   (-101)   /* ハンドシェイク/version 不一致 */

typedef enum GlueStageId {
    GLUE_STAGE_FIRST = 0,
    GLUE_STAGE_PATHS = 0,     /* 0: mount 表 (pathreg_set_paths + pathreg_install) */
    GLUE_STAGE_REGISTRY,      /* 1: vreg import/flush フック (seed import + 基準 hash) */
    GLUE_STAGE_PUMP,          /* 2: pump RING 起動 (wait mode + clock calibration 要求) */
    GLUE_STAGE_VFS,           /* 3: wvfs mount 表の整合 (/c/home・/c/tmp・/fl) */
    GLUE_STAGE_PRE_DLLMAIN,   /* 4: DllMain 前フック (cmdline 投入・host 準備) */
    GLUE_STAGE_DLLMAIN,       /* 5: DllMain / unit initialization (m11 closure) */
    GLUE_STAGE_HOST,          /* 6: THostInstance 構築 */
    GLUE_STAGE_BOOT,          /* 7: CreateFruityInstance 呼出 */
    GLUE_STAGE_POST,          /* 8: 後フック (iface 検証・run 入口) */
    GLUE_STAGE_SHUTDOWN,      /* 9: 終了処理 (flush/syncfs/trace dump) */
    GLUE_STAGE_LAST = GLUE_STAGE_SHUTDOWN,
    GLUE_STAGE_COUNT
} GlueStageId;

/* 段階 API (独立に呼べる。戻り GLUE_OK / 負値) */
int glue_stage_paths(const char* username);          /* username = "webstudio" 等 (既定と同じ) */
int glue_stage_registry(void);                        /* seed import + flush 基準 mark */
int glue_stage_pump(int wait_mode);                   /* -1 で既定モード */
int glue_stage_vfs(void);
int glue_stage_pre_dllmain(const char* cmdline);
int glue_stage_dllmain(void);
int glue_stage_host(void);
int glue_stage_boot(void);
int glue_stage_post(void);
int glue_stage_shutdown(void);

/* 順序規約の検査 */
int  glue_stage_is_done(int stage);
int  glue_stage_next(void);              /* 次に期待される段階 (-1 = 全て完了) */
int  glue_order_violations(void);        /* 累積違反回数 */
int  glue_stage_name(int stage, char* out, int cap);   /* 表示名 */
int  glue_run_all(const char* username); /* 既定順に全段階 (e2e 用) */
void glue_reset(void);                   /* テスト用リセット */

/* ---- 検査/ホスト用の参照口 ---- */
GlueHostInstance* glue_host_instance(void);   /* glue_stage_host() 後の THostInstance */
int               glue_host_addr(void);       /* 同上の wasm 内アドレス (JS から host を指す) */
const char*       glue_username(void);
const char*       glue_cmdline(void);
int               glue_pump_mode_req(void);   /* glue_stage_pump() に渡した mode (-1=既定) */
int               glue_pump_calib_req(void);  /* host が clock calibration を行う要求 (1) */

/* ================================================================
 * 4. trace (順序突合・C:\Users\<user> 残存検査の対象)
 * ================================================================ */
#define GLUE_TRACE_LINE_CAP  192
#define GLUE_TRACE_MAX_LINES 64
int  glue_trace_count(void);
int  glue_trace_line(int i, char* out, int cap);   /* i 行目を複写 (戻り=文字長/-1) */
int  glue_trace_contains(const char* needle);      /* 1=含む / 0=含まない (部分一致) */
void glue_trace_clear(void);
void glue_trace_dump(void);                        /* stdout に全行 */
int  glue_trace_dropped(void);                     /* あふれて落とした行数 */

/* G12 検証口 (ST-T10): ShellExecuteW(verb,file,params) を呼び戻りの HINSTANCE 値を返す。
 * `fldiagnostic /restartfl` は 2 を返し winstubs_restart_requested() が 1 になる */
int  glue_probe_shell_execute(const char* verb, const char* file, const char* params);

#ifdef __cplusplus
}
#endif
#endif /* GLUE_H */
