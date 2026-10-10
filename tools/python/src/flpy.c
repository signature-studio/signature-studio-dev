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

/* flhost_lib.js が提供するホスト import。戻り値 0=ok。ret は 16B スロット。 */
extern int flhost_call(int fn_id, const unsigned char *argv, int argc, unsigned char *ret);

enum { T_NONE = 'N', T_BOOL = 'B', T_INT = 'I', T_DBL = 'D', T_STR = 'S', T_BYTES = 'Y', T_JSON = 'J', T_ERR = 'E', T_CB = 'F' };

static PyObject *HostError;
static PyObject *json_loads;
static PyObject *g_cbs;      /* callable handle table: id -> callable (Python→FL→Python 非同期コールバック用) */
static long g_cb_counter;
static char g_last_error[4096];

static PyObject *flhost_call_py(PyObject *self, PyObject *args) {
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
            long id = ++g_cb_counter;
            PyObject *key = PyLong_FromLong(id);
            if (!key || PyDict_SetItem(g_cbs, key, o) < 0) { Py_XDECREF(key); return NULL; }
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
    if (rc != 0) { PyErr_Format(HostError, "host call %d failed rc=%d", fn_id, rc); return NULL; }
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
        out = PyObject_CallFunctionObjArgs(json_loads, s, NULL);
        Py_DECREF(s);
        break;
    }
    case T_ERR: {
        int code = (int)*(int32_t *)(ret + 4);
        PyObject *msg = PyUnicode_DecodeUTF8((const char *)(uintptr_t)p, l, "replace");
        free((void *)(uintptr_t)p);
        PyObject *ex = Py_BuildValue("(iN)", code, msg);
        PyErr_SetObject(HostError, ex);
        Py_XDECREF(ex);
        return NULL;
    }
    default: PyErr_Format(HostError, "bad host return tag %d", ret[0]); return NULL;
    }
    return out;
}

static PyMethodDef flhost_methods[] = {
    {"call", flhost_call_py, METH_VARARGS, "call(fn_id, args_tuple) -> object  (Python -> host boundary)"},
    {NULL, NULL, 0, NULL}};

static int flhost_exec(PyObject *m) {
    HostError = PyErr_NewException("_flhost.HostError", PyExc_Exception, NULL);
    if (!HostError) return -1;
    Py_INCREF(HostError);
    if (PyModule_AddObject(m, "HostError", HostError) < 0) return -1;
    g_cbs = PyDict_New();
    if (!g_cbs) return -1;
    Py_INCREF(g_cbs);
    if (PyModule_AddObject(m, "_cbs", g_cbs) < 0) return -1;
    PyObject *json = PyImport_ImportModule("json");
    if (!json) return -1;
    json_loads = PyObject_GetAttrString(json, "loads");
    Py_DECREF(json);
    return json_loads ? 0 : -1;
}

static PyModuleDef_Slot flhost_slots[] = {{Py_mod_exec, flhost_exec}, {0, NULL}};
static struct PyModuleDef flhost_def = {PyModuleDef_HEAD_INIT, "_flhost", "FL host boundary", 0, flhost_methods, flhost_slots, NULL, NULL, NULL};
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

EMSCRIPTEN_KEEPALIVE const char *flpy_last_error(void) { return g_last_error; }
EMSCRIPTEN_KEEPALIVE void flpy_free(void *p) { free(p); }
EMSCRIPTEN_KEEPALIVE int flpy_finalize(void) { return Py_FinalizeEx(); }
