#include <stdlib.h>
#include <string.h>
#include "fl_api.h"

static void set_tag(fl_call *c, char tag) { memset(c->ret, 0, sizeof *c->ret); c->ret->tag = (uint8_t)tag; }

/* S/J/E の本体は malloc して所有権を呼出し側に渡す (flpy.c が読んだ後 free する) */
static void put_str(fl_call *c, char tag, const char *s) {
    size_t n = strlen(s);
    char *p = malloc(n + 1);
    memcpy(p, s, n + 1);
    set_tag(c, tag);
    c->ret->v.s.ptr = (uint32_t)(uintptr_t)p;
    c->ret->v.s.len = (uint32_t)n;
}

int fl_err(fl_call *c, int code, const char *msg) {
    put_str(c, 'E', msg);
    c->ret->code = code;
    return code;
}
int fl_ret_none(fl_call *c) { set_tag(c, 'N'); return 0; }
int fl_ret_i(fl_call *c, int64_t v) { set_tag(c, 'I'); c->ret->v.i = v; return 0; }
int fl_ret_b(fl_call *c, int v) { set_tag(c, 'B'); c->ret->v.i = v ? 1 : 0; return 0; }
int fl_ret_d(fl_call *c, double v) { set_tag(c, 'D'); c->ret->v.d = v; return 0; }
int fl_ret_s(fl_call *c, const char *s) { put_str(c, 'S', s); return 0; }
int fl_ret_json(fl_call *c, const char *json) { put_str(c, 'J', json); return 0; }

#define WRONG(c) fl_err((c), FL_E_WRONG_PARAM, "Wrong number of function parameters or wrong parameter type")

int fl_a_int(fl_call *c, int i, int64_t def, int64_t *out) {
    if (i >= c->n || c->a[i].tag == 'N') { *out = def; return 0; }
    switch (c->a[i].tag) {
    case 'I': case 'B': *out = c->a[i].v.i; return 0;
    default: return WRONG(c);
    }
}
int fl_a_dbl(fl_call *c, int i, double def, double *out) {
    if (i >= c->n || c->a[i].tag == 'N') { *out = def; return 0; }
    switch (c->a[i].tag) {
    case 'D': *out = c->a[i].v.d; return 0;
    case 'I': case 'B': *out = (double)c->a[i].v.i; return 0;
    default: return WRONG(c);
    }
}
int fl_a_str(fl_call *c, int i, const char **out) {
    if (i >= c->n || c->a[i].tag != 'S') return WRONG(c);
    *out = (const char *)(uintptr_t)c->a[i].v.s.ptr;
    return 0;
}
int fl_a_cb(fl_call *c, int i, int64_t *out) {
    if (i >= c->n || c->a[i].tag != 'F') return WRONG(c);
    *out = c->a[i].v.i;
    return 0;
}

static int type_ok(char want, uint8_t tag) {
    if (tag == 'N') return 1; /* None は既定値扱い (handler 側の def) */
    switch (want) {
    case 'i': return tag == 'I' || tag == 'B';
    case 'b': return tag == 'B' || tag == 'I';
    case 'f': return tag == 'D' || tag == 'I' || tag == 'B';
    case 's': return tag == 'S';
    default: return 1;
    }
}

int fl_api_call(int fn_id, const fl_slot *argv, int argc, fl_slot *ret) {
    if (fn_id < 0 || fn_id >= fl_table_n || argc < 0 || (argc && !argv) || !ret) return 2;
    for (int i = 0; i < argc; i++)
        if (!strchr("NBIDSYF", argv[i].tag)) return 2;
    const fl_desc *d = &fl_table[fn_id];
    fl_call c = {argv, argc, ret};
    if (!d->h) {
        char msg[160];
        strcpy(msg, "Unspecified error (not implemented: ");
        strncat(msg, d->mod, 40); strcat(msg, "."); strncat(msg, d->name, 60); strcat(msg, ")");
        fl_err(&c, FL_E_UNSPECIFIED, msg);
        return 0;
    }
    if (d->np >= 0) {
        if (argc < d->nmin || argc > d->np) { WRONG(&c); return 0; }
        for (int i = 0; i < argc; i++)
            if (!type_ok(d->ptypes[i], argv[i].tag)) { WRONG(&c); return 0; }
    }
    d->h(&c);
    return 0;
}
