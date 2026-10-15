/* com_test.c — IASIO COM アダプタ テストハーネス (CAB-97)。
 *
 * mode=check      : COM 面の静的検証 126 項目 (node 実行。AudioContext 不使用 — fla_open に到達しない)
 *                   - win64 レイアウト static_assert (BufferInfo64=24B/buffers@8, Callbacks64=32B, ASIOTime=148B)
 *                   - FL 側 asioMessage 応答表 (検収実測値) の検証
 *                   - IUnknown / IClassFactory / CLSID 解決 / slot index 監査 (生 slot vs typed 呼出)
 *                   - vreg 登録 → FLEngine フロー (software\asio 列挙 → clsid → CoCreateInstance)
 *                   - shimx 実レジストリ経由 (FLASIO_COM_SHIMX=1)
 *                   - 19 メソッド + getErrorMessage/future の戻り値 (検収実測値照合)
 * mode=ramp|sine  : FLEngine 呼出を模した実行 (headless Chrome + FlAudioShim)。
 *                   COM 取得 → CreateBuffers(win64 形状) → bufferSwitch(TimeInfo) 連鎖 →
 *                   実行中に getLatencies/getSamplePosition/outputReady を COM 経由で照合。
 *
 * 引数: mode=ramp|sine|check buf=256 secs=5 sr=48000
 * 結果: check は stdout へ JSON。ramp/sine は g_result + g_done (page.mjs 流儀)。 */
#include "iasio.h"
#include "flaudio.h"
#include <emscripten.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef FLASIO_COM_SHIMX
#include "shimx.h"
#endif

/* ---- win64 レイアウト保証 (FL 実測: ASIOCallbacks 4 関数, ASIOTime 0x94=148B) ---- */
_Static_assert(sizeof(ASIOBufferInfo64) == 24, "ASIOBufferInfo64 win64 = 24B");
_Static_assert(offsetof(ASIOBufferInfo64, buffers) == 8, "ASIOBufferInfo64.buffers @8");
_Static_assert(sizeof(ASIOCallbacks64) == 32, "ASIOCallbacks64 win64 = 4 x 8B");
_Static_assert(sizeof(ASIOTime) == 148, "ASIOTime = 148B (FL 0x94 実測)");
_Static_assert(sizeof(ASIOChannelInfo) == 52, "ASIOChannelInfo ポインタ無し = C/native 同一");
_Static_assert(sizeof(ASIOClockSource) == 48, "ASIOClockSource ポインタ無し = C/native 同一");
_Static_assert(sizeof(IASIOVtbl) == 192, "IASIO vtable = 24 slots x 8B");
_Static_assert(sizeof(IASFactoryVtbl) == 40, "IClassFactory vtable = 5 slots x 8B");

static char g_result[16384];
static uint32_t g_done;
EMSCRIPTEN_KEEPALIVE uint32_t *com_test_done_ptr(void) { return &g_done; }
EMSCRIPTEN_KEEPALIVE char *com_test_result_ptr(void) { return g_result; }

static const IASIO_GUID k_clsuid   = IAS_GUID_CLSID_ILWASAPI2ASIO;
static const IASIO_GUID k_iid_unk  = IAS_GUID_IID_IUNKNOWN;
static const IASIO_GUID k_iid_asio = IAS_GUID_IID_IASIO;

/* ---- 判定収集 ---- */
#define MAX_CHECKS 128
static struct { char name[44]; char got[48]; char want[48]; int ok; } g_ck[MAX_CHECKS];
static int g_nck;
static void ck_num(const char *name, long long got, long long want) {
    if (g_nck >= MAX_CHECKS) return;
    snprintf(g_ck[g_nck].name, sizeof g_ck[0].name, "%s", name);
    snprintf(g_ck[g_nck].got, sizeof g_ck[0].got, "%lld", got);
    snprintf(g_ck[g_nck].want, sizeof g_ck[0].want, "%lld", want);
    g_ck[g_nck].ok = got == want; g_nck++;
}
static void ck_str(const char *name, const char *got, const char *want) {
    if (g_nck >= MAX_CHECKS) return;
    snprintf(g_ck[g_nck].name, sizeof g_ck[0].name, "%s", name);
    snprintf(g_ck[g_nck].got, sizeof g_ck[0].got, "%.40s", got);
    snprintf(g_ck[g_nck].want, sizeof g_ck[0].want, "%.40s", want);
    g_ck[g_nck].ok = strcmp(g_ck[g_nck].got, g_ck[g_nck].want) == 0; g_nck++;
}
#define CK(name, expr) ck_num(name, (long long)((expr) ? 1 : 0), 1)
#define CKV(name, got, want) ck_num(name, (long long)(got), (long long)(want))

/* ---- パラメータ ---- */
static struct { char mode[12]; uint32_t buf, sr; double secs; } P = { "check", 256, 48000, 5 };

/* ================= オーディオ生成 (fla_test.c と同一のランプ/正弦) ================= */
static float *g_obuf[2][2], *g_ibuf[2][2];
static uint64_t g_n;
static uint32_t g_sr_run;

static void gen_block(ASIOLong idx) {
    uint32_t B = P.buf;
    float *o0 = g_obuf[idx][0], *o1 = g_obuf[idx][1];
    const float *i0 = g_ibuf[idx][0], *i1 = g_ibuf[idx][1];
    if (!o0) return;
    for (uint32_t k = 0; k < B; k++) {
        uint64_t n = g_n + k;
        if (P.mode[0] == 'r') {                       /* ramp: (n & 0xFFFFFF)+1 / 反転 — fla_test 同一 */
            o0[k] = (float)((n & 0xFFFFFFu) + 1);
            o1[k] = -(float)((n & 0xFFFFFFu) + 1);
        } else {                                      /* sine 440/660Hz */
            o0[k] = (float)(0.5 * sin(2.0 * M_PI * 440.0 * (double)n / (double)P.sr));
            o1[k] = (float)(0.5 * sin(2.0 * M_PI * 660.0 * (double)n / (double)P.sr));
        }
        (void)i0; (void)i1;                           /* 入力は COM 実行では未使用 (in は CAB-191) */
    }
    g_n += B;
}

/* ---- FL 側ホストモック (検収実測の ASIOCallbacks 挙動) ----
 * asioMessage 応答表 (INVENTORY §2 実測 / CAB-9 検収独立確認):
 *   1 (SelectorSupported) : value ∈ [2..8] → 1
 *   2 (EngineVersion)     : 2
 *   3,4,5 (Reset/BufferSizeChange/Resync) : dialog (0x425210, id 0x55f) 後 1
 *   6 (LatenciesChanged)  : 内部コマンド 0x17 発行後 1
 *   7 (SupportsTimeInfo)  : 1 → ドライバは bufferSwitchTimeInfo を使う
 *   8 (TimeCode)          : 0、その他 0 */
static struct { uint32_t calls, dialogs, cmd17, bs, bsti, srate; } g_host;
static int16_t g_sellog[16][2]; static int g_sellog_n;
static uint32_t g_ti_last, g_ti_bad, g_ti_n;

static void host_bufferSwitch(ASIOLong idx, ASIOBool direct) { (void)direct; g_host.bs++; gen_block(idx); }
static void host_sampleRateDidChange(double r) { (void)r; g_host.srate++; }
static ASIOTime *host_bufferSwitchTimeInfo(ASIOTime *t, ASIOLong idx, ASIOBool direct) {
    g_host.bsti++;
    uint32_t pos = (uint32_t)(((uint64_t)t->timeInfo.samplePosition.hi << 32) | t->timeInfo.samplePosition.lo);
    if (g_ti_n && pos < g_ti_last) g_ti_bad++;            /* 位置の単調性 */
    if (t->timeInfo.sampleRate != (double)g_sr_run) g_ti_bad++;
    g_ti_last = pos; g_ti_n++;
    host_bufferSwitch(idx, direct);
    return NULL;
}
static ASIOLong host_asioMessage(ASIOLong sel, ASIOLong val, void *msg, double *opt) {
    (void)msg; (void)opt;
    g_host.calls++;
    if (g_sellog_n < 16) { g_sellog[g_sellog_n][0] = (int16_t)sel; g_sellog[g_sellog_n][1] = (int16_t)val; g_sellog_n++; }
    switch (sel) {
    case 1: return (val >= 2 && val <= 8) ? 1 : 0;
    case 2: return 2;
    case 3: case 4: case 5: g_host.dialogs++; return 1;
    case 6: g_host.cmd17++; return 1;
    case 7: return 1;
    case 8: return 0;
    default: return 0;
    }
}
static ASIOCallbacks64 host_callbacks64(void) {
    ASIOCallbacks64 cb;
    cb.bufferSwitch = (uint64_t)(uintptr_t)host_bufferSwitch;
    cb.sampleRateDidChange = (uint64_t)(uintptr_t)host_sampleRateDidChange;
    cb.asioMessage = (uint64_t)(uintptr_t)host_asioMessage;
    cb.bufferSwitchTimeInfo = (uint64_t)(uintptr_t)host_bufferSwitchTimeInfo;
    return cb;
}

static void wait_ms(double ms) {
    static uint32_t dummy;
    __builtin_wasm_memory_atomic_wait32((int *)&dummy, 0, (int64_t)(ms * 1e6));
}

/* ================= mode=check (node) ================= */
static void check_hostmsg_table(void) {
    CKV("hostmsg_sel1_v2", host_asioMessage(1, 2, NULL, NULL), 1);
    CKV("hostmsg_sel1_v7", host_asioMessage(1, 7, NULL, NULL), 1);
    CKV("hostmsg_sel1_v8", host_asioMessage(1, 8, NULL, NULL), 1);
    CKV("hostmsg_sel1_v9", host_asioMessage(1, 9, NULL, NULL), 0);
    CKV("hostmsg_sel1_v1", host_asioMessage(1, 1, NULL, NULL), 0);
    CKV("hostmsg_sel2", host_asioMessage(2, 0, NULL, NULL), 2);
    CKV("hostmsg_sel3_dialog", host_asioMessage(3, 0, NULL, NULL), 1);
    CKV("hostmsg_sel4_dialog", host_asioMessage(4, 0, NULL, NULL), 1);
    CKV("hostmsg_sel5_dialog", host_asioMessage(5, 0, NULL, NULL), 1);
    CKV("hostmsg_dialogs_3", g_host.dialogs, 3);
    CKV("hostmsg_sel6_cmd17", host_asioMessage(6, 0, NULL, NULL), 1);
    CKV("hostmsg_cmd17_1", g_host.cmd17, 1);
    CKV("hostmsg_sel7_timeinfo", host_asioMessage(7, 0, NULL, NULL), 1);
    CKV("hostmsg_sel8_timecode", host_asioMessage(8, 0, NULL, NULL), 0);
    CKV("hostmsg_sel9_other", host_asioMessage(9, 0, NULL, NULL), 0);
}

static void check_com_lifecycle(void) {
    void *drv = NULL;
    static const IASIO_GUID iid_bad = { 0xDEADBEEFu, 0x1234, 0x5678, { 1, 2, 3, 4, 5, 6, 7, 8 } };
    static const IASIO_GUID clsid_bad = { 0x0BAD0BADu, 0x1111, 0x2222, { 9, 8, 7, 6, 5, 4, 3, 2 } };

    iasio_stats_t st; iasio_get_stats(&st);
    uint32_t created0 = st.created, alive0 = st.alive;
    CKV("cocreate_iunknown_hr", iasio_co_create_instance(&k_clsuid, NULL, IAS_CLSCTX_INPROC_SERVER, &k_iid_unk, &drv), IAS_S_OK);
    CK("cocreate_ptr_nonnull", drv != 0);
    void *same = NULL;
    CKV("qi_unknown_same_hr", iasio_QueryInterface(drv, &k_iid_unk, &same), IAS_S_OK);
    CKV("qi_unknown_same_ptr", same == drv, 1);
    if (same) iasio_Release(drv);   /* QI 参照の解放 (COM 規約: QI は AddRef する) */
    same = NULL;
    CKV("qi_iasio_same_hr", iasio_QueryInterface(drv, &k_iid_asio, &same), IAS_S_OK);
    CKV("qi_iasio_same_ptr", same == drv, 1);
    if (same) iasio_Release(drv);
    same = (void *)1;
    CKV("qi_bad_hr", iasio_QueryInterface(drv, &iid_bad, &same), IAS_E_NOINTERFACE);
    CKV("qi_bad_null", same == NULL, 1);
    CKV("addref_2", iasio_AddRef(drv), 2);
    CKV("release_1", iasio_Release(drv), 1);

    /* 19 メソッド + 未使用 2 の戻り値 (検収実測値) */
    CKV("init_ok", iasio_init(drv, NULL), 1);
    char name[32]; iasio_getDriverName(drv, name);
    ck_str("getDriverName", name, "FL Studio ASIO");
    CKV("getDriverVersion_ge1", iasio_getDriverVersion(drv) >= 1, 1);
    char emsg[124] = { 0 };
    CKV("getErrorMessage_ok", iasio_getErrorMessage(drv, emsg), ASE_OK);
    CK("getErrorMessage_nonempty", emsg[0] != 0);
    ASIOLong nin = 0, nout = 0;
    CKV("getChannels_hr", iasio_getChannels(drv, &nin, &nout), ASE_OK);
    CKV("getChannels_in2", nin, 2);
    CKV("getChannels_out2", nout, 2);
    ASIOLong mn = 0, mx = 0, pref = 0, gran = 1;
    CKV("getBufferSize_hr", iasio_getBufferSize(drv, &mn, &mx, &pref, &gran), ASE_OK);
    CKV("getBufferSize_min_0x100", mn, 0x100);     /* ILWASAPI 実測: min 256 */
    CKV("getBufferSize_max_0x1000", mx, 0x1000);   /* ILWASAPI 実測: max 4096 */
    CKV("getBufferSize_pref_0x200", pref, 0x200);  /* 未作成時の既定 512 */
    CKV("getBufferSize_gran_0", gran, 0);          /* ILWASAPI 実測: granularity 0 */
    CKV("canSampleRate_44100", iasio_canSampleRate(drv, 44100.0), ASE_OK);
    CKV("canSampleRate_12345", iasio_canSampleRate(drv, 12345.0), ASE_NoClock);
    double sr = 0;
    CKV("getSampleRate_hr", iasio_getSampleRate(drv, &sr), ASE_OK);
    CKV("getSampleRate_48000", (int)sr, 48000);
    CKV("setSampleRate_44100", iasio_setSampleRate(drv, 44100.0), ASE_OK);
    iasio_getSampleRate(drv, &sr);
    CKV("setSampleRate_roundtrip", (int)sr, 44100);
    CKV("setSampleRate_12345", iasio_setSampleRate(drv, 12345.0), ASE_NoClock);
    CKV("setSampleRate_back_48000", iasio_setSampleRate(drv, 48000.0), ASE_OK);
    ASIOClockSource cs; ASIOLong ncs = 0;
    memset(&cs, 0, sizeof cs);
    CKV("getClockSources_hr", iasio_getClockSources(drv, &cs, &ncs), ASE_OK);
    CKV("getClockSources_n1", ncs, 1);
    ck_str("getClockSources_name", cs.name, "Internal");
    CKV("getClockSources_current", cs.isCurrentSource, 1);
    CKV("setClockSource_0", iasio_setClockSource(drv, 0), ASE_OK);
    CKV("setClockSource_1", iasio_setClockSource(drv, 1), ASE_InvalidParameter);
    ASIOChannelInfo ci; memset(&ci, 0, sizeof ci); ci.channel = 0; ci.isInput = 0;
    CKV("getChannelInfo_hr", iasio_getChannelInfo(drv, &ci), ASE_OK);
    CKV("getChannelInfo_type_0x13", ci.type, 0x13);   /* 実測: ASIOSTFloat32LSB (19) */
    CKV("getChannelInfo_group0", ci.channelGroup, 0);
    ck_str("getChannelInfo_name", ci.name, "Out 1");
    ci.channel = 7;
    CKV("getChannelInfo_ch7", iasio_getChannelInfo(drv, &ci), ASE_InvalidParameter);
    ASIOLong lat_in = 9, lat_out = 9;
    CKV("getLatencies_hr", iasio_getLatencies(drv, &lat_in, &lat_out), ASE_OK);
    CKV("getLatencies_precreate_0", lat_in == 0 && lat_out == 0, 1);
    ASIOSamples sp, ts;
    CKV("getSamplePosition_stopped", iasio_getSamplePosition(drv, &sp, &ts), ASE_SPNotAdvancing);
    CKV("outputReady_notpresent", iasio_outputReady(drv), ASE_NotPresent);   /* 実測 -1000 */
    CKV("future_invalidparam", iasio_future(drv, 1, NULL), ASE_InvalidParameter);   /* ILWASAPI 既定 -998 */
    CKV("controlPanel_notpresent", iasio_controlPanel(drv), ASE_NotPresent);   /* UI 未登録 (AU-5 #192 以降の仕様) */
    CKV("start_nobuf", iasio_start(drv), ASE_InvalidMode);
    CKV("stop_idle", iasio_stop(drv), ASE_OK);
    CKV("dispose_nocreate", iasio_disposeBuffers(drv), ASE_InvalidMode);

    /* CreateBuffers 無効引数 (fla_open に到達しない範囲 = node で安全) */
    ASIOBufferInfo64 infos[2] = { { 0, 0, { 0, 0 } }, { 0, 1, { 0, 0 } } };
    ASIOCallbacks64 cb = host_callbacks64();
    CKV("createBuffers_size100", iasio_createBuffers(drv, infos, 2, 100, &cb), ASE_InvalidMode);
    CKV("createBuffers_size8192", iasio_createBuffers(drv, infos, 2, 8192, &cb), ASE_InvalidMode);
    ASIOBufferInfo64 badch[1] = { { 0, 5, { 0, 0 } } };
    CKV("createBuffers_badch5", iasio_createBuffers(drv, badch, 1, 256, &cb), ASE_InvalidMode);
    CKV("createBuffers_nullinfo", iasio_createBuffers(drv, NULL, 2, 256, &cb), ASE_InvalidParameter);
    CKV("createBuffers_nullcb", iasio_createBuffers(drv, infos, 2, 256, NULL), ASE_InvalidParameter);

    /* slot index 監査: 生 slot 呼出 (FL の固定 index ラッパ前提) vs typed 呼出の一致 */
    const uint64_t *vt = IAS_VT(drv);
    ASIOLong a1 = 0, b1 = 0, a2 = 0, b2 = 0;
    ((ASIOError (*)(void *, ASIOLong *, ASIOLong *))(uintptr_t)vt[IAS_SLOT_GETCHANNELS])(drv, &a1, &b1);
    iasio_getChannels(drv, &a2, &b2);
    CKV("slot7_getChannels", a1 == a2 && b1 == b2, 1);
    ASIOLong m1[4] = { 0, 0, 0, 9 }, m2[4] = { 0, 0, 0, 9 };
    ((ASIOError (*)(void *, ASIOLong *, ASIOLong *, ASIOLong *, ASIOLong *))(uintptr_t)vt[IAS_SLOT_GETBUFFERSIZE])(drv, &m1[0], &m1[1], &m1[2], &m1[3]);
    iasio_getBufferSize(drv, &m2[0], &m2[1], &m2[2], &m2[3]);
    CKV("slot9_getBufferSize", memcmp(m1, m2, sizeof m1) == 0, 1);
    CKV("slot21_outputReady", ((ASIOError (*)(void *))(uintptr_t)vt[IAS_SLOT_OUTPUTREADY])(drv), ASE_NotPresent);
    CKV("slot20_future", ((ASIOError (*)(void *, ASIOLong, void *))(uintptr_t)vt[IAS_SLOT_FUTURE])(drv, 1, NULL), ASE_InvalidParameter);
    CKV("slot23_stop", ((ASIOError (*)(void *))(uintptr_t)vt[IAS_SLOT_STOP])(drv), ASE_OK);
    CKV("slot3_init", ((ASIOBool (*)(void *, void *))(uintptr_t)vt[IAS_SLOT_INIT])(drv, NULL), 1);
    CKV("slot6_getErrorMessage", ((ASIOError (*)(void *, char *))(uintptr_t)vt[IAS_SLOT_GETERRORMESSAGE])(drv, emsg), ASE_OK);

    /* 解放 (0 で自己解放) */
    CKV("release_to_0", iasio_Release(drv), 0);
    iasio_get_stats(&st);
    CKV("alive_back_to_0", st.alive, alive0);
    CKV("created_plus1", st.created, created0 + 1);

    /* IClassFactory (CoGetClassObject 相当)。クラスオブジェクトは IID_IUnknown/IID_IClassFactory
     * のみ受付 (COM 標準)。IID_IASIO 要求は E_NOINTERFACE を明示検証する。 */
    static const IASIO_GUID k_iid_cf = IAS_GUID_IID_ICLASSFACTORY;
    void *cf = NULL;
    CKV("co_get_class_object_iid_iasio", iasio_co_get_class_object(&k_clsuid, 0, NULL, &k_iid_asio, &cf), IAS_E_NOINTERFACE);
    cf = NULL;
    CKV("co_get_class_object_hr", iasio_co_get_class_object(&k_clsuid, 0, NULL, &k_iid_cf, &cf), IAS_S_OK);
    CK("cf_ptr_nonnull", cf != 0);
    void *d2 = NULL;
    CKV("cf_CreateInstance_hr", cf ? ((HRESULT (*)(void *, void *, const IASIO_GUID *, void **))(uintptr_t)IAS_VT(cf)[3])(cf, NULL, &k_iid_asio, &d2) : IAS_E_POINTER, IAS_S_OK);
    CK("cf_CreateInstance_ptr", d2 != 0);
    void *d3 = (void *)1;
    CKV("cf_noaggregation", cf ? ((HRESULT (*)(void *, void *, const IASIO_GUID *, void **))(uintptr_t)IAS_VT(cf)[3])(cf, (void *)cf, &k_iid_asio, &d3) : IAS_E_POINTER, IAS_CLASS_E_NOAGGREGATION);
    CKV("cf_lockserver", cf ? ((HRESULT (*)(void *, int))(uintptr_t)IAS_VT(cf)[4])(cf, 1) : IAS_E_POINTER, IAS_S_OK);
    if (cf) CKV("cf_release", iasio_Release(cf), 0);
    if (d2) iasio_Release(d2);

    /* CLSID 解決の失敗系 */
    CKV("cocreate_badclsid", iasio_co_create_instance(&clsid_bad, NULL, IAS_CLSCTX_INPROC_SERVER, &k_iid_asio, &d3), IAS_REGDB_E_CLASSNOTREG);
    CKV("cocreate_badctx", iasio_co_create_instance(&k_clsuid, NULL, 0x4u /* LOCAL_SERVER */, &k_iid_asio, &d3), IAS_REGDB_E_CLASSNOTREG);
    d3 = (void *)1;
    CKV("cocreate_noaggregation", iasio_co_create_instance(&k_clsuid, (void *)8, IAS_CLSCTX_INPROC_SERVER, &k_iid_asio, &d3), IAS_CLASS_E_NOAGGREGATION);
}

static void check_registry(void) {
    /* GUID 文字列 */
    IASIO_GUID g; char s[64];
    ck_str("guid_parse_fmt", iasio_guid_parse("{188135E1-7171-3434-854F-01A3C71F3DF9}", &g) == 0 && iasio_guid_format(&g, s) == 0 ? s : "?", "{188135E1-7171-3434-854F-01A3C71F3DF9}");
    CKV("guid_lowercase_parse", iasio_guid_parse("{188135e1-7171-3434-854f-01a3c71f3df9}", &g), 0);
    CKV("guid_bad_nobrace", iasio_guid_parse("188135E1-7171-3434-854F-01A3C71F3DF9", &g) != 0, 1);

    /* vreg 登録 → FLEngine フロー (software\asio 列挙 → clsid → CoCreateInstance) */
    iasio_vreg_reset();
    iasio_reg_set_backend(NULL);
    CKV("register_server_hr", iasio_dll_register_server(NULL), IAS_S_OK);
    char sub[64];
    CKV("vreg_enum_asio_n1", iasio_vreg_enum_sub("HKLM\\software\\asio", 0, sub, sizeof sub), 0);
    ck_str("vreg_enum_asio_name", sub, "FL Studio ASIO");
    CKV("vreg_enum_asio_idx1_empty", iasio_vreg_enum_sub("HKLM\\software\\asio", 1, sub, sizeof sub) != 0, 1);
    char clsid_s[64];
    CKV("vreg_query_clsid", iasio_vreg_get_sz("HKLM\\software\\asio\\FL Studio ASIO", "clsid", clsid_s, sizeof clsid_s), 0);
    ck_str("vreg_clsid_value", clsid_s, "{188135E1-7171-3434-854F-01A3C71F3DF9}");
    char ips[64];
    CKV("vreg_inprocserver", iasio_vreg_get_sz("HKLM\\SOFTWARE\\Classes\\CLSID\\{188135E1-7171-3434-854F-01A3C71F3DF9}\\InprocServer32", "", ips, sizeof ips), 0);
    ck_str("vreg_inprocserver_value", ips, "ILWASAPI2ASIO_x64.dll");
    CKV("vreg_case_insensitive", iasio_vreg_get_sz("hklm\\SOFTWARE\\Asio\\fl studio asio", "CLSID", clsid_s, sizeof clsid_s), 0);

    /* 列挙ヘルパ + 解決 → vtable 呼出まで一気通貫 */
    char names[4][32]; IASIO_GUID gids[4]; uint32_t n = 4;
    CKV("enum_drivers_hr", iasio_enum_asio_drivers(names, gids, &n), 0);
    CKV("enum_drivers_n", n, 1);
    ck_str("enum_drivers_name", names[0], "FL Studio ASIO");
    ck_str("enum_drivers_clsid", iasio_guid_format(&gids[0], s) == 0 ? s : "?", "{188135E1-7171-3434-854F-01A3C71F3DF9}");
    void *drv = NULL;
    CKV("enum_to_cocreate_hr", iasio_co_create_instance(&gids[0], NULL, IAS_CLSCTX_INPROC_SERVER, &k_iid_asio, &drv), IAS_S_OK);
    CK("enum_to_cocreate_init", iasio_init(drv, NULL) == 1);
    iasio_Release(drv);

    /* 8B スロット変換の往復 */
    ASIOCallbacks64 cb64 = host_callbacks64();
    ASIOCallbacks cb;
    iasio_callbacks64_import(&cb64, &cb);
    ASIOCallbacks64 cb64b;
    iasio_callbacks64_export(&cb, &cb64b);
    CKV("cb64_roundtrip", memcmp(&cb64, &cb64b, sizeof cb64) == 0, 1);
    ASIOBufferInfo64 bi64[2] = { { 1, 3, { 0x1234, 0x5678 } }, { 0, 1, { 0xAAAA, 0xBBBB } } };
    ASIOBufferInfo bi[2];
    iasio_binfo64_import(bi64, 2, bi);
    ASIOBufferInfo64 bi64b[2];
    iasio_binfo64_export(bi, 2, bi64b);
    CKV("binfo64_roundtrip", memcmp(bi64, bi64b, sizeof bi64) == 0, 1);
}

#ifdef FLASIO_COM_SHIMX
static void check_shimx(void) {
    /* shimx 実レジストリ (lifted FLEngine が advapi32 Reg* で読むものと同一実体) への登録と読出し */
    CKV("shimx_register", iasio_shimx_register(), 0);
    iasio_stats_t st; iasio_get_stats(&st);
    uint32_t seeds0 = st.reg_seeds;
    CKV("shimx_register_server_noop", iasio_dll_register_server(NULL), IAS_S_OK);   /* backend 設定済 → vreg 書込 skip */
    iasio_get_stats(&st);
    CKV("shimx_vreg_write_skipped", st.reg_seeds, seeds0);

    /* FLEngine の実フロー: shimx Reg* で software\asio を列挙 → clsid → CoCreateInstance */
    HKEY hk = 0;
    CKV("shimx_open_software_asio", RegOpenKeyExA(HKEY_LOCAL_MACHINE, "software\\asio", 0, KEY_READ, &hk), ERROR_SUCCESS);
    char name[64]; DWORD cch = sizeof name;
    CKV("shimx_enum_key", RegEnumKeyExA(hk, 0, name, &cch, NULL, NULL, NULL, NULL), ERROR_SUCCESS);
    ck_str("shimx_enum_name", name, "FL Studio ASIO");
    HKEY hk2 = 0;
    CKV("shimx_open_driver_key", RegOpenKeyExA(HKEY_LOCAL_MACHINE, "software\\asio\\FL Studio ASIO", 0, KEY_READ, &hk2), ERROR_SUCCESS);
    char val[64]; DWORD type = 0, cb = sizeof val;
    CKV("shimx_query_clsid", RegQueryValueExA(hk2, "clsid", NULL, &type, (BYTE *)val, &cb), ERROR_SUCCESS);
    CKV("shimx_query_type_regsz", type, REG_SZ);
    ck_str("shimx_clsid_value", val, "{188135E1-7171-3434-854F-01A3C71F3DF9}");
    RegCloseKey(hk); RegCloseKey(hk2);

    /* backend 経由の列挙 + 解決 → IASIO */
    char names[4][32]; IASIO_GUID gids[4]; uint32_t n = 4;
    CKV("shimx_enum_drivers", iasio_enum_asio_drivers(names, gids, &n), 0);
    CKV("shimx_enum_drivers_n", n, 1);
    void *drv = NULL;
    CKV("shimx_cocreate_hr", iasio_co_create_instance(&gids[0], NULL, IAS_CLSCTX_INPROC_SERVER, &k_iid_asio, &drv), IAS_S_OK);
    CK("shimx_cocreate_init", iasio_init(drv, NULL) == 1);
    iasio_Release(drv);
    iasio_shimx_unregister();
}
#endif

static int run_check(char *j, size_t jn) {
    g_nck = 0; g_sellog_n = 0;
    memset(&g_host, 0, sizeof g_host);
    check_hostmsg_table();
    check_com_lifecycle();
    check_registry();
#ifdef FLASIO_COM_SHIMX
    check_shimx();
#endif
    int fail = 0;
    for (int i = 0; i < g_nck; i++) if (!g_ck[i].ok) fail++;
    size_t w = 0;
    #define P(...) w += (size_t)snprintf(j + w, jn > w ? jn - w : 0, __VA_ARGS__)
    P("{\"api\":\"com_check\",\"n\":%d,\"fail\":%d,\"all_ok\":%s,\"checks\":[", g_nck, fail, fail ? "false" : "true");
    for (int i = 0; i < g_nck; i++)
        P("%s{\"name\":\"%s\",\"ok\":%s,\"got\":\"%s\",\"want\":\"%s\"}", i ? "," : "", g_ck[i].name, g_ck[i].ok ? "true" : "false", g_ck[i].got, g_ck[i].want);
    P("]}");
    #undef P
    return fail ? 1 : 0;
}

/* ================= mode=ramp|sine (headless Chrome, FlAudioShim 必要) =================
 * FLEngine 側呼出を模した一連: 登録 → 列挙 → CoCreateInstance → init → CreateBuffers(win64 形状)
 * → Start → bufferSwitch(TimeInfo) 連鎖 (生成は本モック = FL の 2353B 本体に相当) → Stop → Release。 */
static int run_com(char *j, size_t jn) {
    g_n = 0; g_ti_last = 0; g_ti_bad = 0; g_ti_n = 0; g_sellog_n = 0;
    memset(&g_host, 0, sizeof g_host);
    g_sr_run = P.sr;
    memset(g_obuf, 0, sizeof g_obuf); memset(g_ibuf, 0, sizeof g_ibuf);

    iasio_vreg_reset();
    iasio_reg_set_backend(NULL);
    HRESULT hr_reg = iasio_dll_register_server(NULL);
    char names[4][32]; IASIO_GUID gids[4]; uint32_t n = 4;
    int hr_enum = iasio_enum_asio_drivers(names, gids, &n);
    void *drv = NULL;
    HRESULT hr_cc = n ? iasio_co_create_instance(&gids[0], NULL, IAS_CLSCTX_INPROC_SERVER, &k_iid_asio, &drv) : IAS_REGDB_E_CLASSNOTREG;
    if (hr_reg != IAS_S_OK || hr_enum != 0 || hr_cc != IAS_S_OK) {
        snprintf(j, jn, "{\"error\":\"cocreate\",\"hr_reg\":%d,\"hr_enum\":%d,\"hr_cc\":%d}", hr_reg, hr_enum, hr_cc);
        return 1;
    }
    ASIOBool binit = iasio_init(drv, NULL);
    ASIOLong nin = 0, nout = 0;
    iasio_getChannels(drv, &nin, &nout);
    ASIOLong mn = 0, mx = 0, pref0 = 0, gran = 0;
    iasio_getBufferSize(drv, &mn, &mx, &pref0, &gran);
    if (P.sr != 48000) iasio_setSampleRate(drv, (double)P.sr);

    ASIOBufferInfo64 infos[4]; int ni = 0;
    for (int c = 0; c < 2; c++) { infos[ni].isInput = 0; infos[ni].channelNum = c; infos[ni].buffers[0] = infos[ni].buffers[1] = 0; ni++; }
    ASIOCallbacks64 cb64 = host_callbacks64();
    ASIOError ecr = iasio_createBuffers(drv, infos, ni, (ASIOLong)P.buf, &cb64);
    if (binit != 1 || ecr != ASE_OK) { snprintf(j, jn, "{\"error\":\"createBuffers\",\"code\":%d}", ecr); return 1; }
    for (int i = 0; i < ni; i++)      /* 戻されたバッファポインタ (8B スロット) を C 側へ */
        for (int b = 0; b < 2; b++) g_obuf[b][infos[i].channelNum] = (float *)(uintptr_t)infos[i].buffers[b];
    ASIOLong lat_in0 = 0, lat_out0 = 0;
    iasio_getLatencies(drv, &lat_in0, &lat_out0);
    ASIOChannelInfo ci; memset(&ci, 0, sizeof ci); ci.channel = 0; ci.isInput = 0;
    iasio_getChannelInfo(drv, &ci);
    ASIOLong mn2 = 0, mx2 = 0, pref1 = 0, gran2 = 0;
    iasio_getBufferSize(drv, &mn2, &mx2, &pref1, &gran2);   /* 作成後: pref = B */

    if (iasio_start(drv) != ASE_OK) { snprintf(j, jn, "{\"error\":\"start\"}"); return 1; }
    double t0 = emscripten_get_now();
    int ns = 0, mono = 1; double lastpos = -1; ASIOLong or_code = 9999;
    while (emscripten_get_now() - t0 < P.secs * 1000.0) {
        wait_ms(250);
        ASIOSamples sp, ts;
        if (iasio_getSamplePosition(drv, &sp, &ts) == ASE_OK) {
            double pos = (double)(((uint64_t)sp.hi << 32) | sp.lo);
            if (pos < lastpos) mono = 0;
            lastpos = pos; ns++;
        }
        if (or_code == 9999 && emscripten_get_now() - t0 > P.secs * 500.0) or_code = iasio_outputReady(drv);
    }
    double elapsed = emscripten_get_now() - t0;
    flasio_stats_t st;
    flasio_get_stats(&st);
    ASIOLong lat_in = 0, lat_out = 0;
    iasio_getLatencies(drv, &lat_in, &lat_out);
    iasio_stop(drv);
    iasio_disposeBuffers(drv);
    uint32_t refs_last = iasio_Release(drv);
    iasio_stats_t cst;
    iasio_get_stats(&cst);

    size_t w = 0;
    #define Q(...) w += (size_t)snprintf(j + w, jn > w ? jn - w : 0, __VA_ARGS__)
    Q("{\"api\":\"com\",\"mode\":\"%s\",\"buf\":%u,\"depth\":%u,\"sr\":%u,\"secs_wall\":%.3f,"
      "\"reported\":{\"nin\":%d,\"nout\":%d,\"min\":%d,\"max\":%d,\"pref\":%d,\"gran\":%d,\"pref_created\":%d,"
      "\"lat_in\":%d,\"lat_out\":%d,\"lat_in0\":%d,\"lat_out0\":%d,\"ch_type\":%d},"
      "\"stats\":{\"cb_count\":%u,\"cb_late\":%u,\"cb_max_us\":%u,\"cb_avg_us\":%u,\"underruns\":%u,\"silence_frames\":%u,"
      "\"in_overruns\":%u,\"in_underflows\":%u,\"min_fill\":%u,\"avg_fill\":%u,\"wake_count\":%u,\"wait_timeouts\":%u,"
      "\"ring_frames\":%u,\"quanta\":%u,\"reset_requests\":%u,\"wake_hist\":[%u,%u,%u,%u,%u,%u],"
      "\"latency_changes\":%u,\"T\":%u,\"burst_obs\":%u,\"timeinfo_cb\":%u,"
      "\"seg_max_us\":{\"in_read\":%u,\"memset\":%u,\"bufferswitch\":%u,\"out_write\":%u}},"
      "\"timeinfo\":{\"calls\":%u,\"bad\":%u},\"clock\":{\"samples\":%d,\"monotonic\":%d},\"produced_frames\":%llu,"
      "\"com\":{\"hr_register\":%d,\"hr_enum\":%d,\"enum_n\":%u,\"driver\":\"%s\",\"hr_cocreate\":%d,"
      "\"refs_last\":%u,\"alive\":%u,\"qi_ok\":%u,\"created\":%u,\"host_bs\":%u,\"host_bsti\":%u,"
      "\"dialogs\":%u,\"cmd17\":%u,\"srate_changes\":%u,\"output_ready\":%d,\"msglog_n\":%d,\"sellog\":[",
      P.mode, P.buf, st.depth, P.sr, elapsed / 1000.0,
      nin, nout, mn, mx, pref0, gran, pref1, lat_in, lat_out, lat_in0, lat_out0, ci.type,
      st.cb_count, st.cb_late, st.cb_max_us, st.cb_avg_us, st.underruns, st.silence_frames,
      st.in_overruns, st.in_underflows, st.min_fill, st.avg_fill,
      st.wake_count, st.wait_timeouts, st.ring_frames, st.quanta, st.reset_requests,
      st.wake_hist[0], st.wake_hist[1], st.wake_hist[2], st.wake_hist[3], st.wake_hist[4], st.wake_hist[5],
      st.latency_changes, st.T, st.burst_obs, st.timeinfo_cb,
      st.seg_max_us[0], st.seg_max_us[1], st.seg_max_us[2], st.seg_max_us[3],
      g_host.bsti, g_ti_bad, ns, mono, (unsigned long long)g_n,
      hr_reg, hr_enum, n, names[0], hr_cc,
      refs_last, cst.alive, cst.qi_ok, cst.created, g_host.bs, g_host.bsti,
      g_host.dialogs, g_host.cmd17, g_host.srate, or_code, g_sellog_n);
    for (int i = 0; i < g_sellog_n; i++) Q("%s[%d,%d]", i ? "," : "", g_sellog[i][0], g_sellog[i][1]);
    Q("]}}");   /* sellog 配列 / com オブジェクト / 外側オブジェクトの順に閉じる */
    #undef Q
    return 0;
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        char *a = argv[i], *v = strchr(a, '=');
        if (!v) continue;
        *v++ = 0;
        if (!strcmp(a, "mode")) snprintf(P.mode, sizeof P.mode, "%.11s", v);
        else if (!strcmp(a, "buf")) P.buf = (uint32_t)atoi(v);
        else if (!strcmp(a, "secs")) P.secs = atof(v);
        else if (!strcmp(a, "sr")) P.sr = (uint32_t)atoi(v);
    }
    int rc;
    if (!strcmp(P.mode, "check")) {
        rc = run_check(g_result, sizeof g_result);
        printf("%s\n", g_result);
        fflush(stdout);
    } else {
        rc = run_com(g_result, sizeof g_result);
    }
    __atomic_store_n(&g_done, rc ? 2 : 1, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&g_done, 0x7fffffff);
    return 0;
}
