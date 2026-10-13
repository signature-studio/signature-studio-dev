/* SHX-T12 (#789): file API の構造化トレース。1 行 1 イベントの JSON Lines。
 *   SHIMX_TRACE_FILE=<path> (初期化時に読む) または shimx_set_trace_file(path)。
 * stderr の SHX_TRACE (自由文) とは独立。出力先が無ければ何も書かない。
 */
#include "shimx_internal.h"

volatile int g_shx_ftrace_on = 0;
static shx_mutex_t g_ftr_lk;
static FILE* g_ftr_fp;
static uint64_t g_ftr_seq;

static void put_str(FILE* f, const char* s) {
    if (!s) { fputs("null", f); return; }
    fputc('"', f);
    for (const unsigned char* p = (const unsigned char*)s; *p; p++) {
        if (*p == '"' || *p == '\\') fprintf(f, "\\%c", *p);
        else if (*p < 0x20) fprintf(f, "\\u%04x", *p);
        else fputc(*p, f);
    }
    fputc('"', f);
}

static int ftrace_open(const char* path) {
    int rc = 0;
    shx_mutex_lock(&g_ftr_lk);
    if (g_ftr_fp) fclose(g_ftr_fp);
    g_ftr_fp = NULL;
    g_shx_ftrace_on = 0;
    if (path && *path) {
        g_ftr_fp = fopen(path, "w");
        if (g_ftr_fp) { g_ftr_seq = 0; g_shx_ftrace_on = 1; }
        else rc = -1;
    }
    shx_mutex_unlock(&g_ftr_lk);
    return rc;
}

void shx_ftrace_open_env(void) {
    const char* p = getenv("SHIMX_TRACE_FILE");
    if (p && *p) ftrace_open(p);
}

int shimx_set_trace_file(const char* path) { shx_ensure_init(); return ftrace_open(path); }

void shx_ftrace_emit(const ShxFtrEv* ev) {
    char gbuf[4096], nbuf[1024];
    const char* guest = ev->guest;
    const char* name = ev->name;
    if (!g_shx_ftrace_on) return;
    if (!guest && ev->guestw && shimx_utf16_to_utf8(ev->guestw, -1, gbuf, sizeof gbuf) >= 0) guest = gbuf;
    if (!name && ev->namew && shimx_utf16_to_utf8(ev->namew, -1, nbuf, sizeof nbuf) >= 0) name = nbuf;
    shx_mutex_lock(&g_ftr_lk);
    FILE* f = g_ftr_fp;
    if (f) {
        fprintf(f, "{\"seq\":%llu,\"api\":", (unsigned long long)g_ftr_seq++);
        put_str(f, ev->api);
        fputs(",\"guest\":", f); put_str(f, guest);
        fputs(",\"posix\":", f); put_str(f, ev->posix);
        fputs(",\"name\":", f); put_str(f, name);
        if (ev->has_open) fprintf(f, ",\"access\":\"0x%08x\",\"disp\":%u,\"flags\":\"0x%08x\"",
                                  (unsigned)ev->access, (unsigned)ev->disp, (unsigned)ev->flags);
        else fputs(",\"access\":null,\"disp\":null,\"flags\":null", f);
        fprintf(f, ",\"write\":%s,\"ok\":%s,\"err\":%u", ev->write ? "true" : "false",
                ev->ok ? "true" : "false", (unsigned)(ev->ok ? 0 : ev->err));
        if (ev->has_attr) fprintf(f, ",\"attr\":\"0x%08x\"}\n", (unsigned)ev->attr);
        else fputs(",\"attr\":null}\n", f);
        fflush(f);
    }
    shx_mutex_unlock(&g_ftr_lk);
}
