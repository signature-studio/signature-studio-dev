/*
 * flpy.c — FL Studio 組込 Python (3.12.1) の wasm 埋込みランタイム。
 *
 * - CPython を static link (libpython3.12.a)。stock python.js (main) ではなく、ホストから呼べる最小 C ABI を export。
 * - `_flhost` (builtin C module): Python → ホスト(JS/FLEngine) の唯一の境界。flapi 各関数は fn_id で識別。
 * - 引数/戻り値は 16B スロットの tagged union (tag u8 @+0, payload @+8)。構造化戻り値は JSON ('J')。
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <emscripten.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef FLPY_STATIC
/* PY-2 (#83): FLEngine 側 provider (fl_api_call) を同一 wasm に静的リンクする。JS import も JSON 往復も無い。
 * fl_slot と本ファイルの 16B スロットは同一レイアウト (provider/fl_api.h の _Static_assert)。 */
#include "fl_api.h"
static unsigned g_trace_on;
static unsigned long g_host_calls;
#define TRACE_MAX 65536
static unsigned short g_trace_fn[TRACE_MAX];
static unsigned char g_trace_argc[TRACE_MAX];
static inline int flhost_call(int fn_id, const unsigned char *argv, int argc, unsigned char *ret) {
    if (g_trace_on && g_host_calls < TRACE_MAX) { g_trace_fn[g_host_calls] = (unsigned short)fn_id; g_trace_argc[g_host_calls] = (unsigned char)argc; }
    g_host_calls++;
    return fl_api_call(fn_id, (const fl_slot *)argv, argc, (fl_slot *)ret);
}
EMSCRIPTEN_KEEPALIVE void flpy_trace_reset(unsigned on) { g_trace_on = on; g_host_calls = 0; }
EMSCRIPTEN_KEEPALIVE unsigned long flpy_host_calls(void) { return g_host_calls; }
EMSCRIPTEN_KEEPALIVE unsigned flpy_trace_len(void) { return g_host_calls < TRACE_MAX ? (unsigned)g_host_calls : TRACE_MAX; }
EMSCRIPTEN_KEEPALIVE const unsigned short *flpy_trace_fn(void) { return g_trace_fn; }
EMSCRIPTEN_KEEPALIVE const unsigned char *flpy_trace_argc(void) { return g_trace_argc; }
#else
/* flhost_lib.js が提供するホスト import。戻り値 0=ok。ret は 16B スロット。 */
extern int flhost_call(int fn_id, const unsigned char *argv, int argc, unsigned char *ret);
#endif

enum { T_NONE = 'N', T_BOOL = 'B', T_INT = 'I', T_DBL = 'D', T_STR = 'S', T_BYTES = 'Y', T_JSON = 'J', T_ERR = 'E', T_CB = 'F' };

/* PY-12 (#587): _flhost の状態は module state (インタプリタごと)。static 変数に持つとサブインタプリタ間で共有・上書きされる。 */
typedef struct {
    PyObject *HostError;
    PyObject *json_loads;
    PyObject *cbs;      /* callable handle table: id -> callable (Python→FL→Python 非同期コールバック用) */
    long cb_counter;
} flhost_state;

static char g_last_error[4096];  /* ホスト向け診断バッファ (インタプリタ非依存・スレッド無し) */

static flhost_state *flhost_get_state(PyObject *m) {
    return (flhost_state *)PyModule_GetState(m);
}

static PyObject *flhost_call_py(PyObject *self, PyObject *args) {
    flhost_state *st = flhost_get_state(self);
    if (!st) return NULL;
    int fn_id;
    PyObject *tup;
    if (!PyArg_ParseTuple(args, "iO!", &fn_id, &PyTuple_Type, &tup)) return NULL;
    Py_ssize_t n = PyTuple_GET_SIZE(tup);
    if (n > 32) { PyErr_SetString(PyExc_TypeError, "too many arguments (max 32)"); return NULL; }
    unsigned char argv[32 * 16];
    memset(argv, 0, sizeof(argv));
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *o = PyTuple_GET_ITEM(tup, i);
        unsigned char *s = argv + i * 16;
        if (o == Py_None) { s[0] = T_NONE; }
        else if (PyBool_Check(o)) { s[0] = T_BOOL; *(int64_t *)(s + 8) = (o == Py_True); }
        else if (PyLong_Check(o)) {
            int ovf = 0;
            long long v = PyLong_AsLongLongAndOverflow(o, &ovf);
            if (ovf) { PyErr_SetString(PyExc_OverflowError, "int too large for host call"); return NULL; }
            s[0] = T_INT; *(int64_t *)(s + 8) = v;
        } else if (PyFloat_Check(o)) { s[0] = T_DBL; *(double *)(s + 8) = PyFloat_AS_DOUBLE(o); }
        else if (PyUnicode_Check(o)) {
            Py_ssize_t len; const char *u = PyUnicode_AsUTF8AndSize(o, &len);
            if (!u) return NULL;
            s[0] = T_STR; *(uint32_t *)(s + 8) = (uint32_t)(uintptr_t)u; *(uint32_t *)(s + 12) = (uint32_t)len;
        } else if (PyBytes_Check(o)) {
            s[0] = T_BYTES; *(uint32_t *)(s + 8) = (uint32_t)(uintptr_t)PyBytes_AS_STRING(o);
            *(uint32_t *)(s + 12) = (uint32_t)PyBytes_GET_SIZE(o);
        } else if (PyCallable_Check(o)) {
            long id = ++st->cb_counter;
            PyObject *key = PyLong_FromLong(id);
            if (!key || PyDict_SetItem(st->cbs, key, o) < 0) { Py_XDECREF(key); return NULL; }
            Py_DECREF(key);
            s[0] = T_CB; *(int64_t *)(s + 8) = id;
        } else {
            PyErr_Format(PyExc_TypeError, "unsupported argument type for host call: %s", Py_TYPE(o)->tp_name);
            return NULL;
        }
    }
    unsigned char ret[16];
    memset(ret, 0, sizeof(ret));
    int rc = flhost_call(fn_id, argv, (int)n, ret);
    if (rc != 0) { PyErr_Format(st->HostError, "host call %d failed rc=%d", fn_id, rc); return NULL; }
    PyObject *out = NULL;
    uint32_t p = *(uint32_t *)(ret + 8), l = *(uint32_t *)(ret + 12);
    switch (ret[0]) {
    case 0:
    case T_NONE: Py_RETURN_NONE;
    case T_BOOL: out = PyBool_FromLong((long)*(int64_t *)(ret + 8)); break;
    case T_INT: out = PyLong_FromLongLong(*(int64_t *)(ret + 8)); break;
    case T_DBL: out = PyFloat_FromDouble(*(double *)(ret + 8)); break;
    case T_STR: out = PyUnicode_DecodeUTF8((const char *)(uintptr_t)p, l, "replace"); free((void *)(uintptr_t)p); break;
    case T_BYTES: out = PyBytes_FromStringAndSize((const char *)(uintptr_t)p, l); free((void *)(uintptr_t)p); break;
    case T_JSON: {
        PyObject *s = PyUnicode_DecodeUTF8((const char *)(uintptr_t)p, l, "replace");
        free((void *)(uintptr_t)p);
        if (!s) return NULL;
        out = PyObject_CallFunctionObjArgs(st->json_loads, s, NULL);
        Py_DECREF(s);
        break;
    }
    case T_ERR: {
        int code = (int)*(int32_t *)(ret + 4);
        PyObject *msg = PyUnicode_DecodeUTF8((const char *)(uintptr_t)p, l, "replace");
        free((void *)(uintptr_t)p);
        PyObject *ex = Py_BuildValue("(iN)", code, msg);
        PyErr_SetObject(st->HostError, ex);
        Py_XDECREF(ex);
        return NULL;
    }
    default: PyErr_Format(st->HostError, "bad host return tag %d", ret[0]); return NULL;
    }
    return out;
}

static PyMethodDef flhost_methods[] = {
    {"call", flhost_call_py, METH_VARARGS, "call(fn_id, args_tuple) -> object  (Python -> host boundary)"},
    {NULL, NULL, 0, NULL}};

static int flhost_exec(PyObject *m) {
    flhost_state *st = flhost_get_state(m);
    if (!st) return -1;
    st->HostError = PyErr_NewException("_flhost.HostError", PyExc_Exception, NULL);
    if (!st->HostError) return -1;
    if (PyModule_AddObjectRef(m, "HostError", st->HostError) < 0) return -1;
    st->cbs = PyDict_New();
    if (!st->cbs) return -1;
    if (PyModule_AddObjectRef(m, "_cbs", st->cbs) < 0) return -1;
    PyObject *json = PyImport_ImportModule("json");
    if (!json) return -1;
    st->json_loads = PyObject_GetAttrString(json, "loads");
    Py_DECREF(json);
    return st->json_loads ? 0 : -1;
}

static int flhost_traverse(PyObject *m, visitproc visit, void *arg) {
    flhost_state *st = flhost_get_state(m);
    if (st) { Py_VISIT(st->HostError); Py_VISIT(st->json_loads); Py_VISIT(st->cbs); }
    return 0;
}

static int flhost_clear(PyObject *m) {
    flhost_state *st = flhost_get_state(m);
    if (st) { Py_CLEAR(st->HostError); Py_CLEAR(st->json_loads); Py_CLEAR(st->cbs); }
    return 0;
}

static void flhost_free(void *m) { flhost_clear((PyObject *)m); }

static PyModuleDef_Slot flhost_slots[] = {
    {Py_mod_exec, flhost_exec},
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {0, NULL}};
static struct PyModuleDef flhost_def = {PyModuleDef_HEAD_INIT, "_flhost", "FL host boundary", (Py_ssize_t)sizeof(flhost_state), flhost_methods, flhost_slots, flhost_traverse, flhost_clear, flhost_free};
PyMODINIT_FUNC PyInit__flhost(void) { return PyModuleDef_Init(&flhost_def); }

/* ---------------- ホスト向け export ---------------- */

static void set_err_from_python(const char *ctx) {
    PyObject *t, *v, *tb;
    PyErr_Fetch(&t, &v, &tb);
    PyErr_NormalizeException(&t, &v, &tb);
    if (tb && v) PyException_SetTraceback(v, tb);
    snprintf(g_last_error, sizeof g_last_error, "%s: (error)", ctx);
    PyObject *trace = PyImport_ImportModule("traceback");
    PyObject *lines = trace && v ? PyObject_CallMethod(trace, "format_exception", "OOO", t, v, tb ? tb : Py_None) : NULL;
    PyObject *joined = lines ? PyUnicode_Join(PyUnicode_FromString(""), lines) : NULL;
    const char *u = joined ? PyUnicode_AsUTF8(joined) : NULL;
    if (u) snprintf(g_last_error, sizeof g_last_error, "%s:\n%s", ctx, u);
    else if (v) {
        PyObject *s = PyObject_Str(v);
        const char *su = s ? PyUnicode_AsUTF8(s) : NULL;
        snprintf(g_last_error, sizeof g_last_error, "%s: %s: %s", ctx, t ? ((PyTypeObject *)t)->tp_name : "?", su ? su : "?");
        Py_XDECREF(s);
    }
    Py_XDECREF(joined); Py_XDECREF(lines); Py_XDECREF(trace);
    Py_XDECREF(t); Py_XDECREF(v); Py_XDECREF(tb);
    PyErr_Clear();
}

static wchar_t *to_w(const char *s) { return Py_DecodeLocale(s, NULL); }

EMSCRIPTEN_KEEPALIVE int flpy_init(const char *syspath_colon) {
    if (Py_IsInitialized()) return 0;
    if (PyImport_AppendInittab("_flhost", PyInit__flhost) < 0) { snprintf(g_last_error, sizeof g_last_error, "AppendInittab failed"); return -1; }
    PyPreConfig pre;
    PyPreConfig_InitIsolatedConfig(&pre);
    pre.utf8_mode = 1;
    PyStatus pst = Py_PreInitialize(&pre);
    if (PyStatus_Exception(pst)) { snprintf(g_last_error, sizeof g_last_error, "PreInit: %s", pst.err_msg ? pst.err_msg : "?"); return -1; }
    PyConfig cfg;
    PyConfig_InitIsolatedConfig(&cfg);
    cfg.install_signal_handlers = 0;
    cfg.use_environment = 0;
    cfg.write_bytecode = 0;
    PyStatus st = PyConfig_SetString(&cfg, &cfg.home, L"/usr/local");
    if (PyStatus_Exception(st)) goto fail;
    cfg.module_search_paths_set = 1;
    const char *base[] = {"/usr/local/lib/python312.zip", "/usr/local/lib/python3.12", "/fl/Lib"};
    for (int i = 0; i < 3; i++) {
        wchar_t *w = to_w(base[i]);
        st = PyWideStringList_Append(&cfg.module_search_paths, w);
        PyMem_RawFree(w);
        if (PyStatus_Exception(st)) goto fail;
    }
    if (syspath_colon && *syspath_colon) {
        char *dup = strdup(syspath_colon);
        for (char *tok = strtok(dup, ":"); tok; tok = strtok(NULL, ":")) {
            wchar_t *w = to_w(tok);
            st = PyWideStringList_Append(&cfg.module_search_paths, w);
            PyMem_RawFree(w);
            if (PyStatus_Exception(st)) { free(dup); goto fail; }
        }
        free(dup);
    }
    st = Py_InitializeFromConfig(&cfg);
    PyConfig_Clear(&cfg);
    if (PyStatus_Exception(st)) {
        snprintf(g_last_error, sizeof g_last_error, "Py_InitializeFromConfig: %s", st.err_msg ? st.err_msg : "?");
        return -1;
    }
    return 0;
fail:
    snprintf(g_last_error, sizeof g_last_error, "PyConfig: %s", st.err_msg ? st.err_msg : "?");
    PyConfig_Clear(&cfg);
    return -1;
}

EMSCRIPTEN_KEEPALIVE int flpy_run(const char *src, const char *filename) {
    PyObject *main_mod = PyImport_AddModule("__main__");
    if (!main_mod) { set_err_from_python("run"); return -1; }
    PyObject *globals = PyModule_GetDict(main_mod);
    PyObject *code = Py_CompileString(src, filename ? filename : "<flpy>", Py_file_input);
    if (!code) { set_err_from_python("compile"); return -1; }
    PyObject *r = PyEval_EvalCode(code, globals, globals);
    Py_DECREF(code);
    if (!r) { set_err_from_python("exec"); return -1; }
    Py_DECREF(r);
    return 0;
}

/* target = "module:func"  args_json = JSON array / object / "" -> malloc'ed JSON {"ok":..}|{"err":..}  (flpy_free で解放) */
EMSCRIPTEN_KEEPALIVE char *flpy_call_json(const char *target, const char *args_json) {
    PyObject *rt = PyImport_ImportModule("fl_rt");
    char *out = NULL;
    if (!rt) { set_err_from_python("import fl_rt"); return strdup("{\"err\":\"fl_rt import failed\"}"); }
    PyObject *r = PyObject_CallMethod(rt, "call_json", "ss", target, args_json ? args_json : "");
    Py_DECREF(rt);
    if (!r) { set_err_from_python("call_json"); return strdup("{\"err\":\"call_json raised\"}"); }
    const char *u = PyUnicode_AsUTF8(r);
    out = strdup(u ? u : "{\"err\":\"non-utf8\"}");
    Py_DECREF(r);
    return out;
}

/* ---------------- PY-6 (#76): サブインタプリタ可否の検証用 export ----------------
 * code を新しいサブインタプリタの __main__ で実行し、その __main__.result (str) を返す → インタプリタを破棄して元に戻る。
 * mode: 0 = isolated (_PyInterpreterConfig_INIT: 独立 obmalloc / 単相初期化 ext 拒否 / OWN_GIL)
 *       1 = isolated + SHARED_GIL (wasm はスレッド無しなので OWN_GIL が成立するかの切り分け用)
 *       2 = legacy (_PyInterpreterConfig_LEGACY_INIT: main と obmalloc/GIL を共有、ext 制限なし)
 * 戻り値: malloc'ed JSON {"ok":true,"result":..} | {"ok":false,"stage":..,"err":..} (flpy_free で解放)。
 * 本番経路 (flpy_run / flpy_call_json) はこの関数を使わない。 */
static char *json_reply(int ok, const char *stage, const char *text) {
    PyObject *d = PyDict_New();
    PyDict_SetItemString(d, "ok", ok ? Py_True : Py_False);
    if (stage) { PyObject *o = PyUnicode_FromString(stage); PyDict_SetItemString(d, "stage", o); Py_DECREF(o); }
    if (text) { PyObject *o = PyUnicode_DecodeUTF8(text, (Py_ssize_t)strlen(text), "replace"); PyDict_SetItemString(d, ok ? "result" : "err", o); Py_DECREF(o); }
    PyObject *dumps = NULL, *out = NULL;
    PyObject *js = PyImport_ImportModule("json");
    if (js) dumps = PyObject_GetAttrString(js, "dumps");
    if (dumps) out = PyObject_CallFunctionObjArgs(dumps, d, NULL);
    const char *u = out ? PyUnicode_AsUTF8(out) : NULL;
    char *r = strdup(u ? u : "{\"ok\":false,\"err\":\"json_reply failed\"}");
    Py_XDECREF(out); Py_XDECREF(dumps); Py_XDECREF(js); Py_DECREF(d);
    PyErr_Clear();
    return r;
}

EMSCRIPTEN_KEEPALIVE char *flpy_subinterp_run(const char *code, int mode) {
    PyThreadState *main_ts = PyThreadState_Get();
    PyInterpreterConfig cfg = mode == 2 ? (PyInterpreterConfig)_PyInterpreterConfig_LEGACY_INIT : (PyInterpreterConfig)_PyInterpreterConfig_INIT;
    if (mode == 1) cfg.gil = PyInterpreterConfig_SHARED_GIL;
    PyThreadState *sub = NULL;
    PyStatus st = Py_NewInterpreterFromConfig(&sub, &cfg);
    if (PyStatus_Exception(st) || !sub) {
        PyThreadState_Swap(main_ts);
        return json_reply(0, "new_interpreter", st.err_msg ? st.err_msg : "Py_NewInterpreterFromConfig failed");
    }
    char *text = NULL;
    int ok = 0;
    PyObject *main_mod = PyImport_AddModule("__main__");
    PyObject *globals = main_mod ? PyModule_GetDict(main_mod) : NULL;
    PyObject *co = globals ? Py_CompileString(code, "<subinterp>", Py_file_input) : NULL;
    PyObject *r = co ? PyEval_EvalCode(co, globals, globals) : NULL;
    if (!r) {
        set_err_from_python("subinterp");
        text = strdup(g_last_error);
    } else {
        Py_DECREF(r);
        PyObject *res = PyDict_GetItemString(globals, "result");
        const char *u = res ? PyUnicode_AsUTF8(res) : NULL;
        text = strdup(u ? u : "");
        ok = 1;
    }
    Py_XDECREF(co);
    Py_EndInterpreter(sub);
    PyThreadState_Swap(main_ts);
    char *reply = json_reply(ok, ok ? NULL : "exec", text);  /* 応答は元の (main) インタプリタで組み立てる */
    free(text);
    return reply;
}

EMSCRIPTEN_KEEPALIVE const char *flpy_last_error(void) { return g_last_error; }
EMSCRIPTEN_KEEPALIVE void flpy_free(void *p) { free(p); }
EMSCRIPTEN_KEEPALIVE int flpy_finalize(void) { return Py_FinalizeEx(); }

#ifdef FLPY_STATIC
#include <time.h>
/* 境界単体のコスト: Python を経由せず C から fl_api_call(fn_id, 引数なし) を n 回。戻り S/J/E の本体は free する。返り値 = 合計 ns */
EMSCRIPTEN_KEEPALIVE double flpy_bench_c(int fn_id, int n) {
    fl_slot ret;
    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);
    for (int i = 0; i < n; i++) {
        memset(&ret, 0, sizeof ret);
        fl_api_call(fn_id, NULL, 0, &ret);
        if (ret.tag == 'S' || ret.tag == 'J' || ret.tag == 'E') free((void *)(uintptr_t)ret.v.s.ptr);
    }
    clock_gettime(CLOCK_MONOTONIC, &b);
    return (double)(b.tv_sec - a.tv_sec) * 1e9 + (double)(b.tv_nsec - a.tv_nsec);
}
#endif

#if defined(FLPY_STATIC) && defined(FLPY_PTHREAD)
/* PY-80 (#2856): 別スレッドから Python を実行する経路 (FL が束縛する PyThreadState_New / PyEval_RestoreThread /
 * PyEval_SaveThread で GIL を受け渡す)。各 pthread が自分の thread state を作って GIL を取り、flpy_call_json を 1 回呼ぶ。
 * 戻り値は各スレッドの call_json 結果を並べた JSON 配列 ([{"ok":..}|{"err":..}, ...])。flpy_free で解放。 */
#include <pthread.h>
#define FLPY_MT_MAX 8
#define FLPY_MT_NORESULT "{\"err\":\"thread result missing\"}"
typedef struct { PyInterpreterState *interp; const char *target; const char *args; char *out; } flpy_mt_job;
static const char *flpy_mt_out(const flpy_mt_job *j) { return j->out ? j->out : FLPY_MT_NORESULT; }

static void *flpy_mt_worker(void *p) {
    flpy_mt_job *j = (flpy_mt_job *)p;
    PyThreadState *ts = PyThreadState_New(j->interp);
    PyEval_RestoreThread(ts);
    j->out = flpy_call_json(j->target, j->args);
    PyThreadState_Clear(ts);
    PyThreadState_DeleteCurrent();
    return NULL;
}

EMSCRIPTEN_KEEPALIVE char *flpy_mt_call(int nthreads, const char *target, const char *args) {
    if (nthreads < 1) nthreads = 1;
    if (nthreads > FLPY_MT_MAX) nthreads = FLPY_MT_MAX;
    pthread_t th[FLPY_MT_MAX];
    flpy_mt_job jobs[FLPY_MT_MAX];
    int started[FLPY_MT_MAX] = {0};
    PyInterpreterState *interp = PyInterpreterState_Get();
    PyThreadState *main_ts = PyEval_SaveThread();
    for (int i = 0; i < nthreads; i++) {
        jobs[i] = (flpy_mt_job){interp, target, args, NULL};
        started[i] = pthread_create(&th[i], NULL, flpy_mt_worker, &jobs[i]) == 0;
    }
    for (int i = 0; i < nthreads; i++) if (started[i]) pthread_join(th[i], NULL);
    PyEval_RestoreThread(main_ts);
    /* out が NULL のスレッドは未開始 (pthread_create 失敗) か strdup 失敗。代用 JSON を並べ、解放は確保できた分だけ */
    size_t len = 3;
    for (int i = 0; i < nthreads; i++) len += strlen(flpy_mt_out(&jobs[i])) + 1;
    char *buf = malloc(len);
    if (!buf) {
        for (int i = 0; i < nthreads; i++) free(jobs[i].out);
        return NULL;
    }
    char *w = buf;
    *w++ = '[';
    for (int i = 0; i < nthreads; i++) {
        if (i) *w++ = ',';
        const char *s = flpy_mt_out(&jobs[i]);
        size_t n = strlen(s);
        memcpy(w, s, n);
        w += n;
        free(jobs[i].out);
    }
    *w++ = ']';
    *w = 0;
    return buf;
}
#endif
