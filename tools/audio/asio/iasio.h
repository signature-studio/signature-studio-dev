/* iasio.h — IASIO COM アダプタ (win64 ABI ⇄ flasio_*)。CAB-97 [AU-1]。
 *
 * 実測根拠 (tools/audio/INVENTORY.md §2-§3 / CAB-9 検収):
 * - FLEngine は IASIO を vtable 呼出するラッパ 19 本 (0xc53da0–0xc53ff0, getErrorMessage/future 未使用)
 * - FL が渡す ASIOCallbacks 4 関数 (bufferSwitch 0xc57420 / sampleRateDidChange 0xc576b0 /
 *   asioMessage 0xc576c0 / bufferSwitchTimeInfo 0xc56ae0 = 本体)
 * - ILWASAPI2ASIO vtable = 24 スロット (0x1800657e0) = IUnknown 3 + IASIO 21 (FL 呼出 19 + 未使用 2)
 * - CLSID {188135E1-7171-3434-854F-01A3C71F3DF9}、FLEngine 側参照 +0x7aa18
 * - レジストリは小文字 software\asio + 値名 clsid (FLEngine 内 UTF-16 文字列実測)
 *
 * ABI 規約 (shimx ole.c IStream/IMalloc と同一):
 * - vtable / オブジェクト先頭 / ASIOCallbacks / ASIOBufferInfo.buffers のポインタは
 *   **8 バイトスロット** (win64 レイアウト)。wasm32 関数ポインタをゼロ拡張で格納する。
 * - lifted FLEngine からの間接呼出しは hostbridge の呼出規約ブリッジ (i64↔i32) を要する
 *   (CAB-33 接続時に確認。shimx REPORT §3-8 同項)。
 * - ASIOChannelInfo / ASIOClockSource / ASIOTime はポインタを持たないため C ネイティブ
 *   (flasio.h) と win64 で同一レイアウト (sizeof 実測は com_test で static_assert)。
 */
#ifndef FLA_IASIO_H
#define FLA_IASIO_H
#include <stdint.h>
#include <stddef.h>
#include "flasio.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- HRESULT / CLSCTX (win32 値) ---- */
typedef int32_t HRESULT;
#define IAS_S_OK                  ((HRESULT)0)
#define IAS_S_FALSE               ((HRESULT)1)
#define IAS_E_NOINTERFACE         ((HRESULT)0x80004002u)
#define IAS_E_POINTER             ((HRESULT)0x80004003u)
#define IAS_CLASS_E_NOAGGREGATION ((HRESULT)0x80040110u)
#define IAS_REGDB_E_CLASSNOTREG   ((HRESULT)0x80040154u)
#define IAS_CLSCTX_INPROC_SERVER  0x1u

/* ---- GUID (win64: 16B) ---- */
typedef struct { uint32_t Data1; uint16_t Data2, Data3; uint8_t Data4[8]; } IASIO_GUID;
int iasio_guid_parse(const char *s, IASIO_GUID *g);            /* "{XXXXXXXX-...-XXXX}" 38 文字 */
int iasio_guid_format(const IASIO_GUID *g, char out[39]);      /* 大文字正規形 + NUL */
int iasio_guid_eq(const IASIO_GUID *a, const IASIO_GUID *b);

#define IAS_GUID_CLSID_ILWASAPI2ASIO \
    { 0x188135E1u, 0x7171, 0x3434, { 0x85, 0x4F, 0x01, 0xA3, 0xC7, 0x1F, 0x3D, 0xF9 } }  /* 実測 */
#define IAS_GUID_IID_IASIO \
    { 0x48D0C522u, 0x75FA, 0x11D3, { 0x9D, 0x4B, 0x00, 0xC0, 0x4F, 0x6E, 0xA7, 0xAE } }  /* ASIO SDK 2.x (FLEngine 実測値ではない — REPORT §1) */
#define IAS_GUID_IID_IUNKNOWN \
    { 0x00000000u, 0x0000, 0x0000, { 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46 } }
#define IAS_GUID_IID_ICLASSFACTORY \
    { 0x00000001u, 0x0000, 0x0000, { 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46 } }

/* ---- win64 形状の構造体 (ポインタ = 8B スロット) ---- */
#pragma pack(push, 8)
typedef struct { int32_t isInput, channelNum; uint64_t buffers[2]; } ASIOBufferInfo64;   /* 24B */
typedef struct {   /* FL が渡す ASIOCallbacks (win64: 4 × 8B = 32B, 実測 Delphi 初期化 0xc5e360) */
    uint64_t bufferSwitch;             /* (long doubleBufferIndex, ASIOBool directProcess) */
    uint64_t sampleRateDidChange;      /* (double sRate) */
    uint64_t asioMessage;              /* (long selector, long value, void *message, double *opt) → long */
    uint64_t bufferSwitchTimeInfo;     /* (ASIOTime *params, long doubleBufferIndex, ASIOBool directProcess) → ASIOTime* */
} ASIOCallbacks64;
#pragma pack(pop)

typedef ASIOSamples ASIOTimeStamp;     /* ASIO SDK で同形 (hi/lo) — flasio_get_sample_position の第2引数と同一 */

/* ---- vtable: 24 スロット × 8B (ILWASAPI2ASIO 0x1800657e0 実測と同数) ---- */
typedef struct { uint64_t slot[24]; } IASIOVtbl;
enum {  /* 標準 IASIO 順 (FL の固定 index ラッパ 0xc53da0.. が前提とする並び) */
    IAS_SLOT_QUERYINTERFACE = 0, IAS_SLOT_ADDREF = 1, IAS_SLOT_RELEASE = 2,
    IAS_SLOT_INIT = 3, IAS_SLOT_GETDRIVERNAME = 4, IAS_SLOT_GETDRIVERVERSION = 5,
    IAS_SLOT_GETERRORMESSAGE = 6, IAS_SLOT_GETCHANNELS = 7, IAS_SLOT_GETLATENCIES = 8,
    IAS_SLOT_GETBUFFERSIZE = 9, IAS_SLOT_CANSAMPLERATE = 10, IAS_SLOT_GETSAMPLERATE = 11,
    IAS_SLOT_SETSAMPLERATE = 12, IAS_SLOT_GETCLOCKSOURCES = 13, IAS_SLOT_SETCLOCKSOURCE = 14,
    IAS_SLOT_GETSAMPLEPOSITION = 15, IAS_SLOT_GETCHANNELINFO = 16, IAS_SLOT_CREATEBUFFERS = 17,
    IAS_SLOT_DISPOSEBUFFERS = 18, IAS_SLOT_CONTROLPANEL = 19, IAS_SLOT_FUTURE = 20,
    IAS_SLOT_OUTPUTREADY = 21, IAS_SLOT_START = 22, IAS_SLOT_STOP = 23
};
typedef struct { uint64_t slot[5]; } IASFactoryVtbl;   /* IClassFactory: QI/AddRef/Release/CreateInstance/LockServer */

/* ---- C 側呼出ヘルパ (8B スロットを実 deref して呼ぶ = COM 経由の呼出そのもの) ---- */
const uint64_t *iasio_vtbl(const void *obj);           /* obj 先頭 8B スロット → vtable */
#define IAS_VT(obj) iasio_vtbl(obj)

HRESULT  iasio_QueryInterface(void *self, const IASIO_GUID *iid, void **out);
uint32_t iasio_AddRef(void *self);
uint32_t iasio_Release(void *self);
ASIOBool  iasio_init(void *self, void *sysHandle);
void      iasio_getDriverName(void *self, char name[32]);
ASIOLong  iasio_getDriverVersion(void *self);
ASIOError iasio_getErrorMessage(void *self, char str[124]);
ASIOError iasio_getChannels(void *self, ASIOLong *numIn, ASIOLong *numOut);
ASIOError iasio_getLatencies(void *self, ASIOLong *latIn, ASIOLong *latOut);
ASIOError iasio_getBufferSize(void *self, ASIOLong *minS, ASIOLong *maxS, ASIOLong *prefS, ASIOLong *gran);
ASIOError iasio_canSampleRate(void *self, double rate);
ASIOError iasio_getSampleRate(void *self, double *rate);
ASIOError iasio_setSampleRate(void *self, double rate);
ASIOError iasio_getClockSources(void *self, ASIOClockSource *clocks, ASIOLong *num);
ASIOError iasio_setClockSource(void *self, ASIOLong reference);
ASIOError iasio_getSamplePosition(void *self, ASIOSamples *sPos, ASIOTimeStamp *tStamp);
ASIOError iasio_getChannelInfo(void *self, ASIOChannelInfo *info);
ASIOError iasio_createBuffers(void *self, ASIOBufferInfo64 *infos, ASIOLong numChannels, ASIOLong bufferSize, ASIOCallbacks64 *callbacks);
ASIOError iasio_disposeBuffers(void *self);
ASIOError iasio_controlPanel(void *self);
ASIOError iasio_future(void *self, ASIOLong selector, void *opt);
ASIOError iasio_outputReady(void *self);
ASIOError iasio_start(void *self);
ASIOError iasio_stop(void *self);

/* ---- COM 登録の代替 (レジストリ / CLSID 解決) ----
 * FLEngine の実フロー (実測): RegOpenKeyEx(HKLM, "software\asio") → RegEnumKeyEx →
 * RegQueryValueEx("clsid") → CLSIDFromString → CoCreateInstance(CLSID, IID_IASIO)。
 * 本実装では CoCreateInstance 相当を iasio_co_create_instance で提供し、shimx 側の
 * CoCreateInstance (現状 REGDB_E_CLASSNOTREG スタブ) からフォワードする 1 箇所を入口とする。 */
/* 登録: software\asio\<名>\clsid + SOFTWARE\Classes\CLSID\{...}\InprocServer32 を書く
 * (ILWASAPI2ASIO の DllRegisterServer 相当。既定バックエンド = 内蔵 vreg)。 */
HRESULT iasio_dll_register_server(const char *inproc_server_path /* NULL = 既定名 */);
HRESULT iasio_dll_unregister_server(void);
/* CLSID 解決 → IASIO (または IID 指定の IUnknown)。outer 非対応 (CLASS_E_NOAGGREGATION)。 */
HRESULT iasio_co_create_instance(const IASIO_GUID *clsid, void *outer, uint32_t ctx, const IASIO_GUID *iid, void **out);
HRESULT iasio_co_get_class_object(const IASIO_GUID *clsid, uint32_t ctx, void *reserved, const IASIO_GUID *iid, void **out);
/* FLEngine 列挙の代替 (PoC ハーネス用。実 FL 結合後は shimx Reg* の直接呼出に置換)。n は in/out。 */
int iasio_enum_asio_drivers(char names[][32], IASIO_GUID *clsids, uint32_t *n);

/* ---- レジストリバックエンド (内蔵 vreg が既定。shimx 結合は iasio_shimx_register()) ----
 * パスは UTF-8 でルート込み: "HKLM\software\asio" (大小無視)。戻り 0 = 成功。 */
typedef struct {
    int  (*open)(const char *path, uint32_t *hkey);
    int  (*enum_sub)(uint32_t hkey, uint32_t idx, char *name, uint32_t cap);
    int  (*query_sz)(uint32_t hkey, const char *name, char *out, uint32_t cap);
    void (*close)(uint32_t hkey);
} iasio_reg_backend_t;
void iasio_reg_set_backend(const iasio_reg_backend_t *b);   /* NULL = 内蔵 vreg */
const iasio_reg_backend_t *iasio_vreg_backend(void);        /* 内蔵 vreg のバックエンド実装 */

/* 内蔵 vreg (mini レジストリ: software\asio 形状, 大小無視, フラット保存) */
void iasio_vreg_reset(void);
int  iasio_vreg_set_sz(const char *path, const char *name, const char *utf8);
int  iasio_vreg_get_sz(const char *path, const char *name, char *out, uint32_t cap);
int  iasio_vreg_enum_sub(const char *path, uint32_t idx, char *out, uint32_t cap);

/* shimx 結合 (iasio_shimx.c。tools/shimx をリンクしたビルドでのみ使用可):
 * shimx のメモリレジストリへ登録し、Reg* 読出しをバックエンドに取る。 */
int iasio_shimx_register(void);
void iasio_shimx_unregister(void);

/* ---- 8B スロット ⇄ C ネイティブ変換 (flasio_* 受渡し) ---- */
void iasio_callbacks64_import(const ASIOCallbacks64 *src, ASIOCallbacks *dst);
void iasio_callbacks64_export(const ASIOCallbacks *src, ASIOCallbacks64 *dst);
void iasio_binfo64_import(const ASIOBufferInfo64 *src, ASIOLong n, ASIOBufferInfo *dst);   /* n ≤ 16 */
void iasio_binfo64_export(const ASIOBufferInfo *src, ASIOLong n, ASIOBufferInfo64 *dst);

/* ---- 統計 (テスト用) ---- */
typedef struct {
    uint32_t qi_total, qi_ok, qi_fail, addref_total, release_total;
    uint32_t created, alive, factory_alive, co_create_ok, co_create_fail;
    uint32_t cb64_import, cb64_export, binfo64_ops, reg_seeds;
} iasio_stats_t;
void iasio_get_stats(iasio_stats_t *s);

#ifdef __cplusplus
}
#endif
#endif
