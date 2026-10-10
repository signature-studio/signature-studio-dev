/* iasio.c — IASIO COM オブジェクト実装 (vtable + IUnknown + IASIO 21 スロット)。
 * 役割: lifted FLEngine が COM (vtable 固定 index) 経由で ASIO ドライバとして取得・操作できる
 * オブジェクトを提供し、実体は検収済み flasio_* (tools/audio/src/flasio.c) へ委譲する。
 * - vtable = 24 × 8B スロット (ILWASAPI2ASIO 0x1800657e0 実測と同数・標準 IASIO 順)
 * - IUnknown: QueryInterface (IID_IUnknown / IID_IASIO) / AddRef / Release (0 で自己解放)
 * - FL 未使用の getErrorMessage / future はスロット互換のため実装 (実測: FL は呼ばない)
 * - CreateBuffers は win64 形状 (ASIOBufferInfo64 / ASIOCallbacks64) を受けて flasio_create_buffers
 *   (C ネイティブ形状) へ変換委譲。ASIOTime / ChannelInfo / ClockSource は形状同一のため素通し。
 */
#include "iasio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ST32(x, v) __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)
#define LD32(x)    __atomic_load_n(&(x), __ATOMIC_SEQ_CST)

static const IASIO_GUID g_clsid    = IAS_GUID_CLSID_ILWASAPI2ASIO;
static const IASIO_GUID g_iid_unk  = IAS_GUID_IID_IUNKNOWN;
static const IASIO_GUID g_iid_asio = IAS_GUID_IID_IASIO;
static const IASIO_GUID g_iid_cf   = IAS_GUID_IID_ICLASSFACTORY;

typedef struct iasio_obj {
    uint64_t vtbl;                 /* +0: vtable ポインタ (8B スロット, shimx 規約) */
    uint32_t refs;                 /* 参照カウント (生成時 1) */
    uint32_t magic;                /* 0x49415331 'IAS1' — デバッグ用 */
} iasio_obj_t;

typedef struct iasio_factory {
    uint64_t vtbl;                 /* IClassFactory vtable (5 スロット) */
    uint32_t refs;
    uint32_t magic;
} iasio_factory_t;

static iasio_stats_t g_stats;
static char g_last_error[124] = "FL Studio ASIO (webstudio iasio adapter)";

/* ---------------- 8B スロット ⇄ C ネイティブ変換 ---------------- */
void iasio_callbacks64_import(const ASIOCallbacks64 *src, ASIOCallbacks *dst) {
    dst->bufferSwitch         = (void (*)(ASIOLong, ASIOBool))(uintptr_t)src->bufferSwitch;
    dst->sampleRateDidChange  = (void (*)(double))(uintptr_t)src->sampleRateDidChange;
    dst->asioMessage          = (ASIOLong (*)(ASIOLong, ASIOLong, void *, double *))(uintptr_t)src->asioMessage;
    dst->bufferSwitchTimeInfo = (ASIOTime *(*)(ASIOTime *, ASIOLong, ASIOBool))(uintptr_t)src->bufferSwitchTimeInfo;
    g_stats.cb64_import++;
}
void iasio_callbacks64_export(const ASIOCallbacks *src, ASIOCallbacks64 *dst) {
    dst->bufferSwitch         = (uint64_t)(uintptr_t)src->bufferSwitch;
    dst->sampleRateDidChange  = (uint64_t)(uintptr_t)src->sampleRateDidChange;
    dst->asioMessage          = (uint64_t)(uintptr_t)src->asioMessage;
    dst->bufferSwitchTimeInfo = (uint64_t)(uintptr_t)src->bufferSwitchTimeInfo;
    g_stats.cb64_export++;
}
void iasio_binfo64_import(const ASIOBufferInfo64 *src, ASIOLong n, ASIOBufferInfo *dst) {
    for (ASIOLong i = 0; i < n; i++) {
        dst[i].isInput = src[i].isInput; dst[i].channelNum = src[i].channelNum;
        dst[i].buffers[0] = (void *)(uintptr_t)src[i].buffers[0];
        dst[i].buffers[1] = (void *)(uintptr_t)src[i].buffers[1];
    }
    g_stats.binfo64_ops++;
}
void iasio_binfo64_export(const ASIOBufferInfo *src, ASIOLong n, ASIOBufferInfo64 *dst) {
    for (ASIOLong i = 0; i < n; i++) {
        dst[i].isInput = src[i].isInput; dst[i].channelNum = src[i].channelNum;
        dst[i].buffers[0] = (uint64_t)(uintptr_t)src[i].buffers[0];
        dst[i].buffers[1] = (uint64_t)(uintptr_t)src[i].buffers[1];
    }
    g_stats.binfo64_ops++;
}

/* ---------------- IUnknown ---------------- */
static HRESULT vt_QueryInterface(void *self, const IASIO_GUID *iid, void **out) {
    iasio_obj_t *o = (iasio_obj_t *)self;
    g_stats.qi_total++;
    if (!out) return IAS_E_POINTER;
    *out = NULL;
    if (!iasio_guid_eq(iid, &g_iid_unk) && !iasio_guid_eq(iid, &g_iid_asio)) { g_stats.qi_fail++; return IAS_E_NOINTERFACE; }
    *out = self;
    ST32(o->refs, LD32(o->refs) + 1);
    g_stats.qi_ok++; g_stats.addref_total++;
    return IAS_S_OK;
}
static uint32_t vt_AddRef(void *self) {
    iasio_obj_t *o = (iasio_obj_t *)self;
    uint32_t r = LD32(o->refs) + 1;
    ST32(o->refs, r);
    g_stats.addref_total++;
    return r;
}
static uint32_t vt_Release(void *self) {
    iasio_obj_t *o = (iasio_obj_t *)self;
    uint32_t r = LD32(o->refs) - 1;
    ST32(o->refs, r);
    g_stats.release_total++;
    if (r == 0) { g_stats.alive--; free(o); }   /* stdlib free — flaudio と同一アロケータ */
    return r;
}

/* ---------------- IASIO → flasio_* 委譲 (this は同一性のみに使用) ---------------- */
static ASIOBool vt_init(void *self, void *sysHandle) {
    (void)self;
    ASIOBool r = flasio_init(sysHandle);
    if (!r) snprintf(g_last_error, sizeof g_last_error, "Init failed");
    else g_last_error[0] = 0;
    return r;
}
static void vt_getDriverName(void *self, char name[32]) { (void)self; flasio_get_driver_name(name); }
static ASIOLong vt_getDriverVersion(void *self) { (void)self; return flasio_get_driver_version(); }
static ASIOError vt_getErrorMessage(void *self, char str[124]) {   /* FL 未使用 (実測)。最終エラー文字列を返す */
    (void)self;
    if (!str) return ASE_InvalidParameter;
    snprintf(str, 124, "%s", g_last_error[0] ? g_last_error : "No error");
    return ASE_OK;
}
static ASIOError vt_getChannels(void *self, ASIOLong *a, ASIOLong *b) { (void)self; return flasio_get_channels(a, b); }
static ASIOError vt_getLatencies(void *self, ASIOLong *a, ASIOLong *b) { (void)self; return flasio_get_latencies(a, b); }
static ASIOError vt_getBufferSize(void *self, ASIOLong *a, ASIOLong *b, ASIOLong *c, ASIOLong *d) {
    (void)self; return flasio_get_buffer_size(a, b, c, d);
}
static ASIOError vt_canSampleRate(void *self, double r) { (void)self; return flasio_can_sample_rate(r); }
static ASIOError vt_getSampleRate(void *self, double *r) { (void)self; return flasio_get_sample_rate(r); }
static ASIOError vt_setSampleRate(void *self, double r) { (void)self; return flasio_set_sample_rate(r); }
static ASIOError vt_getClockSources(void *self, ASIOClockSource *cs, ASIOLong *n) { (void)self; return flasio_get_clock_sources(cs, n); }
static ASIOError vt_setClockSource(void *self, ASIOLong ref) { (void)self; return flasio_set_clock_source(ref); }
static ASIOError vt_getSamplePosition(void *self, ASIOSamples *sp, ASIOTimeStamp *ts) {
    (void)self; return flasio_get_sample_position(sp, ts);
}
static ASIOError vt_getChannelInfo(void *self, ASIOChannelInfo *ci) { (void)self; return flasio_get_channel_info(ci); }
static ASIOError vt_createBuffers(void *self, ASIOBufferInfo64 *infos, ASIOLong n, ASIOLong B, ASIOCallbacks64 *cb64) {
    (void)self;
    if (!infos || !cb64 || n <= 0 || n > 16) return ASE_InvalidParameter;
    ASIOBufferInfo tmp[16]; ASIOCallbacks cb;
    iasio_binfo64_import(infos, n, tmp);
    iasio_callbacks64_import(cb64, &cb);
    ASIOError e = flasio_create_buffers(tmp, n, B, &cb);
    if (e == ASE_OK) iasio_binfo64_export(tmp, n, infos);   /* バッファポインタを 8B スロットへ返す */
    else snprintf(g_last_error, sizeof g_last_error, "CreateBuffers failed (%d)", e);
    return e;
}
static ASIOError vt_disposeBuffers(void *self) { (void)self; return flasio_dispose_buffers(); }
static ASIOError vt_controlPanel(void *self) { (void)self; return flasio_control_panel(); }
static ASIOError vt_future(void *self, ASIOLong sel, void *opt) { (void)self; return flasio_future(sel, opt); }   /* 実測: FL 未使用, ILWASAPI 既定 -998 */
static ASIOError vt_outputReady(void *self) { (void)self; return flasio_output_ready(); }                         /* 実測: -1000 */
static ASIOError vt_start(void *self) { (void)self; return flasio_start(); }
static ASIOError vt_stop(void *self) { (void)self; return flasio_stop(); }

/* vtable (24 スロット, 標準 IASIO 順)。静的単一定義 — COM オブジェクトは状態を self 側に持つ。
 * wasm では関数ポインタ→整数の静的初期化が定数にならないため constructor で実行時初期化する。 */
static IASIOVtbl g_vtbl;
static IASFactoryVtbl g_cfvt;

__attribute__((constructor)) static void iasio_vtables_init(void) {
    g_vtbl.slot[IAS_SLOT_QUERYINTERFACE]     = (uint64_t)(uintptr_t)vt_QueryInterface;
    g_vtbl.slot[IAS_SLOT_ADDREF]             = (uint64_t)(uintptr_t)vt_AddRef;
    g_vtbl.slot[IAS_SLOT_RELEASE]            = (uint64_t)(uintptr_t)vt_Release;
    g_vtbl.slot[IAS_SLOT_INIT]               = (uint64_t)(uintptr_t)vt_init;
    g_vtbl.slot[IAS_SLOT_GETDRIVERNAME]      = (uint64_t)(uintptr_t)vt_getDriverName;
    g_vtbl.slot[IAS_SLOT_GETDRIVERVERSION]   = (uint64_t)(uintptr_t)vt_getDriverVersion;
    g_vtbl.slot[IAS_SLOT_GETERRORMESSAGE]    = (uint64_t)(uintptr_t)vt_getErrorMessage;
    g_vtbl.slot[IAS_SLOT_GETCHANNELS]        = (uint64_t)(uintptr_t)vt_getChannels;
    g_vtbl.slot[IAS_SLOT_GETLATENCIES]       = (uint64_t)(uintptr_t)vt_getLatencies;
    g_vtbl.slot[IAS_SLOT_GETBUFFERSIZE]      = (uint64_t)(uintptr_t)vt_getBufferSize;
    g_vtbl.slot[IAS_SLOT_CANSAMPLERATE]      = (uint64_t)(uintptr_t)vt_canSampleRate;
    g_vtbl.slot[IAS_SLOT_GETSAMPLERATE]      = (uint64_t)(uintptr_t)vt_getSampleRate;
    g_vtbl.slot[IAS_SLOT_SETSAMPLERATE]      = (uint64_t)(uintptr_t)vt_setSampleRate;
    g_vtbl.slot[IAS_SLOT_GETCLOCKSOURCES]    = (uint64_t)(uintptr_t)vt_getClockSources;
    g_vtbl.slot[IAS_SLOT_SETCLOCKSOURCE]     = (uint64_t)(uintptr_t)vt_setClockSource;
    g_vtbl.slot[IAS_SLOT_GETSAMPLEPOSITION]  = (uint64_t)(uintptr_t)vt_getSamplePosition;
    g_vtbl.slot[IAS_SLOT_GETCHANNELINFO]     = (uint64_t)(uintptr_t)vt_getChannelInfo;
    g_vtbl.slot[IAS_SLOT_CREATEBUFFERS]      = (uint64_t)(uintptr_t)vt_createBuffers;
    g_vtbl.slot[IAS_SLOT_DISPOSEBUFFERS]     = (uint64_t)(uintptr_t)vt_disposeBuffers;
    g_vtbl.slot[IAS_SLOT_CONTROLPANEL]       = (uint64_t)(uintptr_t)vt_controlPanel;
    g_vtbl.slot[IAS_SLOT_FUTURE]             = (uint64_t)(uintptr_t)vt_future;
    g_vtbl.slot[IAS_SLOT_OUTPUTREADY]        = (uint64_t)(uintptr_t)vt_outputReady;
    g_vtbl.slot[IAS_SLOT_START]              = (uint64_t)(uintptr_t)vt_start;
    g_vtbl.slot[IAS_SLOT_STOP]               = (uint64_t)(uintptr_t)vt_stop;
}

const uint64_t *iasio_vtbl(const void *obj) { return (const uint64_t *)(uintptr_t)*(const uint64_t *)obj; }

/* C 側 typed 呼出ヘルパ — すべて 8B スロットの実 deref 経由 (COM 経由呼出そのもの) */
#define VT(self) iasio_vtbl(self)
HRESULT  iasio_QueryInterface(void *s, const IASIO_GUID *i, void **o) { return ((HRESULT (*)(void *, const IASIO_GUID *, void **))(uintptr_t)VT(s)[IAS_SLOT_QUERYINTERFACE])(s, i, o); }
uint32_t iasio_AddRef(void *s) { return ((uint32_t (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_ADDREF])(s); }
uint32_t iasio_Release(void *s) { return ((uint32_t (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_RELEASE])(s); }
ASIOBool  iasio_init(void *s, void *h) { return ((ASIOBool (*)(void *, void *))(uintptr_t)VT(s)[IAS_SLOT_INIT])(s, h); }
void      iasio_getDriverName(void *s, char n[32]) { ((void (*)(void *, char *))(uintptr_t)VT(s)[IAS_SLOT_GETDRIVERNAME])(s, n); }
ASIOLong  iasio_getDriverVersion(void *s) { return ((ASIOLong (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_GETDRIVERVERSION])(s); }
ASIOError iasio_getErrorMessage(void *s, char str[124]) { return ((ASIOError (*)(void *, char *))(uintptr_t)VT(s)[IAS_SLOT_GETERRORMESSAGE])(s, str); }
ASIOError iasio_getChannels(void *s, ASIOLong *a, ASIOLong *b) { return ((ASIOError (*)(void *, ASIOLong *, ASIOLong *))(uintptr_t)VT(s)[IAS_SLOT_GETCHANNELS])(s, a, b); }
ASIOError iasio_getLatencies(void *s, ASIOLong *a, ASIOLong *b) { return ((ASIOError (*)(void *, ASIOLong *, ASIOLong *))(uintptr_t)VT(s)[IAS_SLOT_GETLATENCIES])(s, a, b); }
ASIOError iasio_getBufferSize(void *s, ASIOLong *a, ASIOLong *b, ASIOLong *c, ASIOLong *d) { return ((ASIOError (*)(void *, ASIOLong *, ASIOLong *, ASIOLong *, ASIOLong *))(uintptr_t)VT(s)[IAS_SLOT_GETBUFFERSIZE])(s, a, b, c, d); }
ASIOError iasio_canSampleRate(void *s, double r) { return ((ASIOError (*)(void *, double))(uintptr_t)VT(s)[IAS_SLOT_CANSAMPLERATE])(s, r); }
ASIOError iasio_getSampleRate(void *s, double *r) { return ((ASIOError (*)(void *, double *))(uintptr_t)VT(s)[IAS_SLOT_GETSAMPLERATE])(s, r); }
ASIOError iasio_setSampleRate(void *s, double r) { return ((ASIOError (*)(void *, double))(uintptr_t)VT(s)[IAS_SLOT_SETSAMPLERATE])(s, r); }
ASIOError iasio_getClockSources(void *s, ASIOClockSource *c, ASIOLong *n) { return ((ASIOError (*)(void *, ASIOClockSource *, ASIOLong *))(uintptr_t)VT(s)[IAS_SLOT_GETCLOCKSOURCES])(s, c, n); }
ASIOError iasio_setClockSource(void *s, ASIOLong r) { return ((ASIOError (*)(void *, ASIOLong))(uintptr_t)VT(s)[IAS_SLOT_SETCLOCKSOURCE])(s, r); }
ASIOError iasio_getSamplePosition(void *s, ASIOSamples *p, ASIOTimeStamp *t) { return ((ASIOError (*)(void *, ASIOSamples *, ASIOTimeStamp *))(uintptr_t)VT(s)[IAS_SLOT_GETSAMPLEPOSITION])(s, p, t); }
ASIOError iasio_getChannelInfo(void *s, ASIOChannelInfo *c) { return ((ASIOError (*)(void *, ASIOChannelInfo *))(uintptr_t)VT(s)[IAS_SLOT_GETCHANNELINFO])(s, c); }
ASIOError iasio_createBuffers(void *s, ASIOBufferInfo64 *i, ASIOLong n, ASIOLong b, ASIOCallbacks64 *c) { return ((ASIOError (*)(void *, ASIOBufferInfo64 *, ASIOLong, ASIOLong, ASIOCallbacks64 *))(uintptr_t)VT(s)[IAS_SLOT_CREATEBUFFERS])(s, i, n, b, c); }
ASIOError iasio_disposeBuffers(void *s) { return ((ASIOError (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_DISPOSEBUFFERS])(s); }
ASIOError iasio_controlPanel(void *s) { return ((ASIOError (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_CONTROLPANEL])(s); }
ASIOError iasio_future(void *s, ASIOLong sel, void *opt) { return ((ASIOError (*)(void *, ASIOLong, void *))(uintptr_t)VT(s)[IAS_SLOT_FUTURE])(s, sel, opt); }
ASIOError iasio_outputReady(void *s) { return ((ASIOError (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_OUTPUTREADY])(s); }
ASIOError iasio_start(void *s) { return ((ASIOError (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_START])(s); }
ASIOError iasio_stop(void *s) { return ((ASIOError (*)(void *))(uintptr_t)VT(s)[IAS_SLOT_STOP])(s); }

/* ---------------- オブジェクト / クラスファクトリ / CLSID 解決 ---------------- */
static void *iasio_create_instance(void) {
    iasio_obj_t *o = (iasio_obj_t *)calloc(1, sizeof *o);
    if (!o) return NULL;
    o->vtbl = (uint64_t)(uintptr_t)&g_vtbl;
    o->refs = 1; o->magic = 0x49415331u;
    g_stats.created++; g_stats.alive++;
    return o;
}

/* IClassFactory: QI(IID_IUnknown/IID_IClassFactory) / CreateInstance / LockServer */
static HRESULT cf_QueryInterface(void *self, const IASIO_GUID *iid, void **out) {
    iasio_factory_t *f = (iasio_factory_t *)self;
    if (!out) return IAS_E_POINTER;
    *out = NULL;
    if (!iasio_guid_eq(iid, &g_iid_unk) && !iasio_guid_eq(iid, &g_iid_cf)) return IAS_E_NOINTERFACE;
    *out = self; ST32(f->refs, LD32(f->refs) + 1);
    return IAS_S_OK;
}
static uint32_t cf_AddRef(void *self) { iasio_factory_t *f = (iasio_factory_t *)self; ST32(f->refs, LD32(f->refs) + 1); return LD32(f->refs); }
static uint32_t cf_Release(void *self) {
    iasio_factory_t *f = (iasio_factory_t *)self;
    uint32_t r = LD32(f->refs) - 1; ST32(f->refs, r);
    if (r == 0) { g_stats.factory_alive--; free(f); }
    return r;
}
static HRESULT cf_CreateInstance(void *self, void *outer, const IASIO_GUID *iid, void **out) {
    (void)self;
    if (!out) return IAS_E_POINTER;
    *out = NULL;
    if (outer) return IAS_CLASS_E_NOAGGREGATION;   /* ILWASAPI2ASIO は集約非対応 (単独 in-process) */
    iasio_obj_t *o = (iasio_obj_t *)iasio_create_instance();
    if (!o) return (HRESULT)0x8007000Eu;           /* E_OUTOFMEMORY */
    HRESULT hr = vt_QueryInterface(o, iid, out);
    vt_Release(o);                                  /* 初期参照を QI の成功に移譲 */
    return hr;
}
static HRESULT cf_LockServer(void *self, int fLock) { (void)self; (void)fLock; return IAS_S_OK; }

__attribute__((constructor)) static void iasio_cfvt_init(void) {
    g_cfvt.slot[0] = (uint64_t)(uintptr_t)cf_QueryInterface;
    g_cfvt.slot[1] = (uint64_t)(uintptr_t)cf_AddRef;
    g_cfvt.slot[2] = (uint64_t)(uintptr_t)cf_Release;
    g_cfvt.slot[3] = (uint64_t)(uintptr_t)cf_CreateInstance;
    g_cfvt.slot[4] = (uint64_t)(uintptr_t)cf_LockServer;
}

HRESULT iasio_co_get_class_object(const IASIO_GUID *clsid, uint32_t ctx, void *reserved, const IASIO_GUID *iid, void **out) {
    (void)reserved;
    if (!out) return IAS_E_POINTER;
    *out = NULL;
    if (ctx && !(ctx & IAS_CLSCTX_INPROC_SERVER)) return IAS_REGDB_E_CLASSNOTREG;   /* in-process のみ提供 */
    if (!clsid || !iasio_guid_eq(clsid, &g_clsid)) { g_stats.co_create_fail++; return IAS_REGDB_E_CLASSNOTREG; }
    iasio_factory_t *f = (iasio_factory_t *)calloc(1, sizeof *f);
    if (!f) return (HRESULT)0x8007000Eu;
    f->vtbl = (uint64_t)(uintptr_t)&g_cfvt;
    f->refs = 1; f->magic = 0x49414346u;   /* 'IACF' */
    g_stats.factory_alive++;
    HRESULT hr = cf_QueryInterface(f, iid, out);
    cf_Release(f);
    return hr;
}

HRESULT iasio_co_create_instance(const IASIO_GUID *clsid, void *outer, uint32_t ctx, const IASIO_GUID *iid, void **out) {
    void *cf = NULL;
    HRESULT hr = iasio_co_get_class_object(clsid, ctx, NULL, &g_iid_cf, &cf);
    if (hr != IAS_S_OK) return hr;
    const IASFactoryVtbl *fvt = (const IASFactoryVtbl *)(uintptr_t)*(const uint64_t *)cf;
    hr = ((HRESULT (*)(void *, void *, const IASIO_GUID *, void **))(uintptr_t)fvt->slot[3])(cf, outer, iid, out);
    if (hr == IAS_S_OK) g_stats.co_create_ok++;
    ((uint32_t (*)(void *))(uintptr_t)fvt->slot[2])(cf);
    return hr;
}

/* ---------------- レジストリ (バックエンド = 内蔵 vreg 既定) ---------------- */
static const iasio_reg_backend_t *g_reg_backend;
void iasio_reg_set_backend(const iasio_reg_backend_t *b) { g_reg_backend = b; }

static const char k_asio_root[] = "HKLM\\software\\asio";                 /* FLEngine 実測 (小文字, 大小無視) */
static const char k_driver_name[] = "FL Studio ASIO";                     /* ILWASAPI2ASIO 実測のドライバ名 */
static const char k_clsid_str[] = "{188135E1-7171-3434-854F-01A3C71F3DF9}"; /* 実測 CLSID */

/* 登録値の正 (register_server が書く内容)。shimx backend 時は iasio_shimx.c が同一内容を
 * shimx のレジストリへ書く (iasio_shimx_register() が seed + backend 設定を行う)。 */
HRESULT iasio_dll_register_server(const char *inproc_server_path) {
    if (g_reg_backend) return IAS_S_OK;   /* shimx backend: 書込済み (iasio_shimx_register())。読出しは backend 経由 */
    char path[160], clsid_key[96];
    snprintf(path, sizeof path, "%s\\%s", k_asio_root, k_driver_name);
    if (iasio_vreg_set_sz(path, "clsid", k_clsid_str) != 0) return (HRESULT)0x8007000Eu;   /* 実測: 値名 clsid */
    if (iasio_vreg_set_sz(path, "", k_driver_name) != 0) return (HRESULT)0x8007000Eu;      /* 既定値 = 表示名 (ASIO 仕様) */
    snprintf(clsid_key, sizeof clsid_key, "HKLM\\SOFTWARE\\Classes\\CLSID\\%s", k_clsid_str);
    if (iasio_vreg_set_sz(clsid_key, "", k_driver_name) != 0) return (HRESULT)0x8007000Eu;
    snprintf(clsid_key, sizeof clsid_key, "HKLM\\SOFTWARE\\Classes\\CLSID\\%s\\InprocServer32", k_clsid_str);
    if (iasio_vreg_set_sz(clsid_key, "", inproc_server_path ? inproc_server_path : "ILWASAPI2ASIO_x64.dll") != 0)
        return (HRESULT)0x8007000Eu;
    g_stats.reg_seeds++;
    return IAS_S_OK;
}

HRESULT iasio_dll_unregister_server(void) {
    if (g_reg_backend) return IAS_E_POINTER;   /* shimx 側は RegDeleteKeyA を直接 (iasio_shimx.c) */
    iasio_vreg_reset();
    return IAS_S_OK;
}

int iasio_enum_asio_drivers(char names[][32], IASIO_GUID *clsids, uint32_t *n) {
    const iasio_reg_backend_t *b = g_reg_backend ? g_reg_backend : iasio_vreg_backend();
    uint32_t hk = 0;
    if (b->open(k_asio_root, &hk) != 0) return -1;
    char name[64], clsid_s[64];
    uint32_t count = 0, max = n ? *n : 0;
    for (uint32_t i = 0; b->enum_sub(hk, i, name, sizeof name) == 0; i++) {
        uint32_t hk2 = 0;
        char sub[160];
        snprintf(sub, sizeof sub, "%s\\%s", k_asio_root, name);
        if (b->open(sub, &hk2) != 0) continue;
        int has = b->query_sz(hk2, "clsid", clsid_s, sizeof clsid_s) == 0;   /* 実測: 値名 clsid */
        b->close(hk2);
        if (!has) continue;
        IASIO_GUID g;
        if (iasio_guid_parse(clsid_s, &g) != 0) continue;
        if (count < max) {
            if (names) snprintf(names[count], 32, "%s", name);
            if (clsids) clsids[count] = g;
        }
        count++;
    }
    b->close(hk);
    if (n) *n = count;
    return 0;
}

/* ---------------- GUID 文字列 ---------------- */
int iasio_guid_parse(const char *s, IASIO_GUID *g) {
    if (!s || !g) return -1;
    char t[48]; int n = 0;
    while (s[n] && n < 46) { t[n] = s[n]; n++; }
    t[n] = 0;
    unsigned a, b, c, d[8];
    if (n != 38 || t[0] != '{' || t[37] != '}' ||
        sscanf(t, "{%8x-%4x-%4x-%2x%2x-%2x%2x%2x%2x%2x%2x}", &a, &b, &c, &d[0], &d[1], &d[2], &d[3], &d[4], &d[5], &d[6], &d[7]) != 11)
        return -1;
    g->Data1 = a; g->Data2 = (uint16_t)b; g->Data3 = (uint16_t)c;
    for (int i = 0; i < 8; i++) g->Data4[i] = (uint8_t)d[i];
    return 0;
}
int iasio_guid_format(const IASIO_GUID *g, char out[39]) {
    if (!g || !out) return -1;
    snprintf(out, 39, "{%08X-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}",
             g->Data1, g->Data2, g->Data3, g->Data4[0], g->Data4[1], g->Data4[2], g->Data4[3], g->Data4[4], g->Data4[5], g->Data4[6], g->Data4[7]);
    return 0;
}

int iasio_guid_eq(const IASIO_GUID *a, const IASIO_GUID *b) { return a && b && memcmp(a, b, sizeof(IASIO_GUID)) == 0; }

void iasio_get_stats(iasio_stats_t *s) { *s = g_stats; }
