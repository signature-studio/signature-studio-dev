/* iasio_vreg.c — 内蔵 mini レジストリ (vreg)。FLEngine が読む形状だけを模す:
 * - キー = パス文字列 (ルート込み, 例 "HKLM\software\asio\FL Studio ASIO")、大小無視、'\' 区切り
 * - 値 = (名前, REG_SZ 文字列)。名前 "" は既定値。実測の値名 clsid (小文字) も大小無視で照合
 * - サブキー列挙 = パス直下の子要素の登場順 (重複排除)
 * 本物のレジストリ実装 (shimx advapi32) への差替えは iasio_reg_set_backend() で行う
 * (iasio_shimx.c が shimx の Reg* で実装)。本実装は PoC ハーネス / 単体テスト用。 */
#include "iasio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#define IAS_VREG_MAX 64
typedef struct { char path[160]; char name[64]; char val[128]; } vreg_ent;
static vreg_ent g_ent[IAS_VREG_MAX];
static int g_n;

static int cieq(const char *a, const char *b) {   /* 大小無視比較 ('/' は比較しない) */
    while (*a && *b) { if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0; a++; b++; }
    return *a == 0 && *b == 0;
}
static void norm_slash(char *s) { for (; *s; s++) if (*s == '/') *s = '\\'; }

void iasio_vreg_reset(void) { g_n = 0; }

int iasio_vreg_set_sz(const char *path, const char *name, const char *utf8) {
    if (!path || !utf8) return -1;
    char p[160], nm[64];
    snprintf(p, sizeof p, "%s", path); norm_slash(p);
    snprintf(nm, sizeof nm, "%s", name ? name : "");
    for (int i = 0; i < g_n; i++) {
        if (cieq(g_ent[i].path, p) && cieq(g_ent[i].name, nm)) {
            snprintf(g_ent[i].val, sizeof g_ent[i].val, "%s", utf8);
            return 0;
        }
    }
    if (g_n >= IAS_VREG_MAX) return -1;
    snprintf(g_ent[g_n].path, sizeof g_ent[g_n].path, "%s", p);
    snprintf(g_ent[g_n].name, sizeof g_ent[g_n].name, "%s", nm);
    snprintf(g_ent[g_n].val, sizeof g_ent[g_n].val, "%s", utf8);
    g_n++;
    return 0;
}

int iasio_vreg_get_sz(const char *path, const char *name, char *out, uint32_t cap) {
    if (!path || !out) return -1;
    char p[160], nm[64];
    snprintf(p, sizeof p, "%s", path); norm_slash(p);
    snprintf(nm, sizeof nm, "%s", name ? name : "");
    for (int i = 0; i < g_n; i++)
        if (cieq(g_ent[i].path, p) && cieq(g_ent[i].name, nm)) { snprintf(out, cap, "%s", g_ent[i].val); return 0; }
    return -1;
}

int iasio_vreg_enum_sub(const char *path, uint32_t idx, char *out, uint32_t cap) {
    if (!path || !out) return -1;
    char p[160];
    snprintf(p, sizeof p, "%s", path); norm_slash(p);
    size_t pl = strlen(p);
    while (pl && p[pl - 1] == '\\') p[--pl] = 0;   /* 末尾 \ 除去 */
    uint32_t seen = 0;
    for (int i = 0; i < g_n; i++) {
        const char *e = g_ent[i].path;
        size_t el = strlen(e);
        if (el <= pl + 1) continue;
        if (strncasecmp(e, p, pl) != 0 || e[pl] != '\\') continue;
        const char *rest = e + pl + 1;
        if (strchr(rest, '\\')) continue;           /* 直下のみ */
        /* 既出の子名は数えない (登場順・重複排除。同一子が別の値名から複数回
         * 登場する場合 (既定値 + clsid 等) と、より深いパス ('\\' 続き) の両方を重複扱い) */
        int dup = 0;
        for (int j = 0; j < i; j++) {
            if (strncasecmp(g_ent[j].path, p, pl) == 0 && g_ent[j].path[pl] == '\\') {
                const char *restj = g_ent[j].path + pl + 1;
                size_t rl = strlen(rest);
                if (strncasecmp(restj, rest, rl) == 0 && (restj[rl] == '\\' || restj[rl] == 0)) { dup = 1; break; }
            }
        }
        if (dup) continue;
        if (seen++ == idx) {
            const char *end = strchr(rest, '\\');
            snprintf(out, cap, "%.*s", end ? (int)(end - rest) : (int)strlen(rest), rest);
            return 0;
        }
    }
    return -1;
}

/* ---- バックエンド実装 (iasio_reg_set_backend(NULL) でこれに戻る) ----
 * ハンドル = (open 済みパスのスロット index + 1)。PoC 用の単純表。 */
#define IAS_VREG_HMAX 8
static char g_hk_path[IAS_VREG_HMAX][160];
static int g_hk_used[IAS_VREG_HMAX];

static int vb_open(const char *path, uint32_t *hkey) {
    char p[160];
    if (!path) return -1;
    snprintf(p, sizeof p, "%s", path); norm_slash(p);
    size_t pl = strlen(p);
    while (pl && p[pl - 1] == '\\') p[--pl] = 0;
    int exists = 0;
    for (int i = 0; i < g_n && !exists; i++)
        if (strncasecmp(g_ent[i].path, p, pl) == 0 && (g_ent[i].path[pl] == 0 || g_ent[i].path[pl] == '\\')) exists = 1;
    if (!exists) return -1;
    for (int s = 0; s < IAS_VREG_HMAX; s++) {
        if (!g_hk_used[s]) {
            snprintf(g_hk_path[s], sizeof g_hk_path[s], "%s", p);
            g_hk_used[s] = 1;
            if (hkey) *hkey = (uint32_t)(s + 1);
            return 0;
        }
    }
    return -1;
}
static int vb_enum(uint32_t hk, uint32_t idx, char *name, uint32_t cap) {
    if (!hk || hk > IAS_VREG_HMAX) return -1;
    return iasio_vreg_enum_sub(g_hk_path[hk - 1], idx, name, cap);
}
static int vb_query(uint32_t hk, const char *name, char *out, uint32_t cap) {
    if (!hk || hk > IAS_VREG_HMAX) return -1;
    return iasio_vreg_get_sz(g_hk_path[hk - 1], name, out, cap);
}
static void vb_close(uint32_t hk) {
    if (hk && hk <= IAS_VREG_HMAX) g_hk_used[hk - 1] = 0;
}

const iasio_reg_backend_t *iasio_vreg_backend(void) {
    static const iasio_reg_backend_t b = { vb_open, vb_enum, vb_query, vb_close };
    return &b;
}
