/* pathmap.c — Win パス → 仮想 FS 写像 (pathreg.h 参照)。
 * - 正規化: pathreg_normalize (Win 形正準化: 区切り / プレフィクス / ドライブレター / '.' '..')
 * - 写像: マウント表 (PathRegMount) を大小無視・最長一致で照合 → vfsTarget + 残り
 * - 未対応は <0 を返し shimx 既定写像 (file.c: C:\x→/c/x, /abs 素通し) に委譲
 * 全操作は起動時設定 + 読み取り専用の表に対する照合なのでロック不要 (add/remove はブート期のみ前提)。
 */
#include "pathreg.h"
#include "pathreg_internal.h"
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>

#define PR_MAX_MOUNTS 64
#define PR_MAX_PREFIX 512

typedef struct {
    char win[PR_MAX_PREFIX];        /* 正準化済み接頭辞 (区切り '\', ドライブ大文字, 末尾 '\' 無し) */
    char target[PR_MAX_PREFIX];     /* FS 側 ('/' 区切り, 末尾 '/' 無し) */
    uint32_t flags;
} PrMount;

static PrMount g_mounts[PR_MAX_MOUNTS];
static int g_nmounts;
static PathRegPaths g_paths;        /* 現在の設定 (監査用) */
static int g_defaults_loaded;

/* 既定マウント表の遅延ロード (モジュール初期化順序に依存しない)。JS 側は add_mount で上書き追加できる */
static void pr_ensure_defaults(void) {
    if (g_defaults_loaded) return;
    g_defaults_loaded = 1;
    PathRegPaths p;
    pathreg_paths_init(&p);
    pathreg_set_paths(&p);
}

/* ---- 文字列ユーティリティ ---- */
static int pr_icase_prefix(const char* path, const char* prefix) {
    /* path が prefix と大小無視で前方一致するか。一致長を返す (非一致 -1) */
    size_t i = 0;
    while (prefix[i]) {
        int a = tolower((unsigned char)path[i]), b = tolower((unsigned char)prefix[i]);
        if (a != b || !path[i]) return -1;
        i++;
    }
    return (int)i;
}

/* 正準化本体: in → out ('\','\\?\' 剥がし, ドライブ大文字, 畳み込み)。out は outCap 以上。
 * 結果の形: UNC "\\srv\share\..." / ドライブ "C:\..." / ルート付き "\foo" (入力が '\\' 始まり) / 相対 "foo\bar"。
 * ".." が根を超える場合は無視 (Win32 相当: ルートに留まる) */
static int pr_canonicalize(const char* in, char* out, size_t outCap) {
    if (!in || !*in || !out || outCap < 4) return -1;
    char buf[PR_MAX_PREFIX * 2];
    size_t n = strlen(in);
    if (n >= sizeof buf) return -1;
    memcpy(buf, in, n + 1);
    for (char* p = buf; *p; p++) if (*p == '/') *p = '\\';

    char* s = buf;
    int unc = 0;
    if (s[0] == '\\' && s[1] == '\\' && (s[2] == '?' || s[2] == '.') && s[3] == '\\') {
        s += 4;
        if (!strncasecmp(s, "UNC\\", 4)) { s += 4; unc = 1; }        /* \\?\UNC\server\share → UNC 形へ */
    }
    if (!unc) unc = (s[0] == '\\' && s[1] == '\\');                  /* 素の UNC \\server\share も UNC 形で保持 */
    if (unc && s[0] == '\\' && s[1] == '\\') s += 2;                 /* 素の UNC の lead \\ は下で書く */
    int rooted = unc || (s[0] == '\\');
    size_t oi = 0;
    if (unc) { out[oi++] = '\\'; out[oi++] = '\\'; }
    else if (rooted) out[oi++] = '\\';
    size_t sepBase = oi;                                              /* 区切り発行は lead の直後から */
    size_t popBase = oi;                                              /* ".." pop の下限 */
    int firstseg = 1;
    while (*s) {
        while (*s == '\\') s++;
        if (!*s) break;
        const char* seg = s;
        while (*s && *s != '\\') s++;
        size_t len = (size_t)(s - seg);
        if (len == 1 && seg[0] == '.') continue;
        if (len == 2 && seg[0] == '.' && seg[1] == '.') {
            if (oi > popBase) {
                while (oi > popBase && out[oi - 1] != '\\') oi--;     /* 末尾セグメントを削る */
                if (oi > popBase) oi--;                               /* 直前の区切りも削る */
            }
            continue;                                                 /* 根を超える ".." は無視 */
        }
        if (oi + len + 2 >= outCap) return -1;
        if (oi > sepBase) out[oi++] = '\\';
        memcpy(out + oi, seg, len); oi += len;
        if (firstseg) {                                               /* ドライブ表記 (X:) は根 → pop で越境させない */
            firstseg = 0;
            if (!unc && oi >= 2 && out[1] == ':') popBase = oi;
        }
    }
    out[oi] = 0;
    /* ドライブ整形式: 大文字化 + 素の "C:" → "C:\" */
    if (out[0] && out[1] == ':' && !unc) {
        out[0] = (char)toupper((unsigned char)out[0]);
        if (!out[2]) { out[2] = '\\'; out[3] = 0; }
    }
    return 0;
}

int pathreg_normalize(const char* winUtf8, char* outWin, size_t outSize) {
    return pr_canonicalize(winUtf8, outWin, outSize);
}

/* ---- マウント表 ---- */
static int pr_add(const char* winPrefix, const char* vfsTarget, uint32_t flags) {
    if (!winPrefix || !*winPrefix || !vfsTarget || !*vfsTarget) return -1;
    if (g_nmounts >= PR_MAX_MOUNTS) return -1;
    PrMount* m = &g_mounts[g_nmounts];
    if (pr_canonicalize(winPrefix, m->win, sizeof m->win) != 0) return -1;
    size_t tl = strlen(vfsTarget);
    while (tl && vfsTarget[tl - 1] == '/') tl--;                    /* 末尾 '/' を除去 */
    if (!tl || tl >= sizeof m->target) return -1;
    memcpy(m->target, vfsTarget, tl); m->target[tl] = 0;
    m->flags = flags;
    g_nmounts++;
    return 0;
}

int pathreg_add_mount(const char* winPrefix, const char* vfsTarget, uint32_t flags) {
    pr_ensure_defaults();
    return pr_add(winPrefix, vfsTarget, flags);
}

int pathreg_remove_mount(const char* winPrefix) {
    pr_ensure_defaults();
    char canon[PR_MAX_PREFIX];
    if (!winPrefix || pr_canonicalize(winPrefix, canon, sizeof canon) != 0) return -1;
    for (int i = 0; i < g_nmounts; i++) {
        if (!strcasecmp(g_mounts[i].win, canon)) {
            memmove(&g_mounts[i], &g_mounts[i + 1], sizeof(PrMount) * (size_t)(g_nmounts - i - 1));
            g_nmounts--;
            return 0;
        }
    }
    return -1;
}

void pathreg_clear_mounts(void) { g_nmounts = 0; }
int  pathreg_mount_count(void) { pr_ensure_defaults(); return g_nmounts; }
int  pathreg_get_mount(int idx, PathRegMount* out) {
    if (idx < 0 || idx >= g_nmounts || !out) return -1;
    out->winPrefix = g_mounts[idx].win;
    out->vfsTarget = g_mounts[idx].target;
    out->flags = g_mounts[idx].flags;
    return 0;
}

void pathreg_paths_init(PathRegPaths* p) {
    if (!p) return;
    memset(p, 0, sizeof *p);
    p->installDir = "C:\\Program Files\\Image-Line\\FL Studio 2026";
    p->vfsInstall = "/fl";
    /* 正規 username (CAB-213 で統一): vreg seed / shimx 内蔵 (env.c/shell.c, CAB-214 で統一済み) /
     * pathreg e2e 契約が全て "C:\Users\webstudio" を採用。予備 profile (user) は CAB-214 follow-up で退役。 */
    p->userProfile = "C:\\Users\\webstudio";
    p->vfsHome = "/c/home";
    p->sharedDataDir = NULL;                                         /* NULL = <profile>\Documents\Image-Line */
    p->vfsSharedData = "/c/home/Documents/Image-Line";
    p->vfsTmp = "/c/tmp";
}

/* プロファイル 1 個分のユーザ領域マウントを追加 (user → home) */
static void pr_add_user_mounts(const char* user, const char* home, const char* sharedData, const char* vfsShared, const char* vfsTmp) {
    if (!user || !*user) return;
    char buf[PR_MAX_PREFIX];
    /* Documents\Image-Line (Shared data) — sharedDataDir 指定があればそれを優先 */
    const char* sd = sharedData;
    if (!sd || !*sd) {
        snprintf(buf, sizeof buf, "%s\\Documents\\Image-Line", user);
        sd = buf;
    }
    pr_add(sd, vfsShared && *vfsShared ? vfsShared : "/c/home/Documents/Image-Line", PATHREG_PERSIST);
    /* %APPDATA% / %LOCALAPPDATA% / %TEMP% */
    snprintf(buf, sizeof buf, "%s\\AppData\\Roaming", user);          pr_add(buf, "/c/home/AppData/Roaming", PATHREG_PERSIST);
    snprintf(buf, sizeof buf, "%s\\AppData\\Local\\Temp\\Image-Line", user); pr_add(buf, vfsTmp && *vfsTmp ? vfsTmp : "/c/tmp", PATHREG_TMP);
    snprintf(buf, sizeof buf, "%s\\AppData\\Local", user);            pr_add(buf, "/c/home/AppData/Local", PATHREG_PERSIST);
    snprintf(buf, sizeof buf, "%s\\AppData\\Roaming\\Image-Line", user); pr_add(buf, "/c/home/AppData/Roaming/Image-Line", PATHREG_PERSIST);
    snprintf(buf, sizeof buf, "%s", user);                            pr_add(buf, home && *home ? home : "/c/home", PATHREG_PERSIST);
}

int pathreg_set_paths(const PathRegPaths* p) {
    if (!p) return -1;
    g_paths = *p;                                                     /* 文字列は呼出側が静的に保持する前提 */
    pathreg_clear_mounts();
    if (p->installDir && *p->installDir)
        pr_add(p->installDir, p->vfsInstall && *p->vfsInstall ? p->vfsInstall : "/fl", PATHREG_RO);
    pr_add_user_mounts(p->userProfile, p->vfsHome, p->sharedDataDir, p->vfsSharedData, p->vfsTmp);
    pr_add("C:", "/c", PATHREG_PERSIST);                              /* 残余のドライブ C (shimx 既定と同じ形) */
    return 0;
}

/* ---- 写像 ---- */
static const PrMount* pr_match(const char* canonWin, size_t* prefixLen) {
    const PrMount* best = NULL;
    size_t bestLen = 0;
    for (int i = 0; i < g_nmounts; i++) {
        size_t pl = strlen(g_mounts[i].win);
        int l = pr_icase_prefix(canonWin, g_mounts[i].win);
        if (l < 0) continue;
        char c = canonWin[l];
        int boundary = (c == '\\' || c == 0 || (pl > 0 && g_mounts[i].win[pl - 1] == '\\'));
        if (!boundary) continue;                                      /* セグメント境界でなければ不一致 */
        if ((size_t)l >= bestLen) { best = &g_mounts[i]; bestLen = (size_t)l; }  /* 同長は後勝ち */
    }
    if (best) *prefixLen = bestLen;
    return best;
}

int pathreg_map(const char* winPathUtf8, char* outPosix, size_t outSize) {
    char canon[PR_MAX_PREFIX * 2];
    if (!winPathUtf8 || !*winPathUtf8 || !outPosix || !outSize) return -1;
    pr_ensure_defaults();
    /* Win 形絶対パス以外 (POSIX 絶対 / 相対) は shimx 既定に委譲 */
    {
        char c0 = winPathUtf8[0];
        int winish = ((c0 >= 'A' && c0 <= 'Z') || (c0 >= 'a' && c0 <= 'z')) && winPathUtf8[1] == ':';
        winish = winish || (c0 == '\\' && winPathUtf8[1] == '\\');
        if (!winish) return -1;
    }
    if (pr_canonicalize(winPathUtf8, canon, sizeof canon) != 0) return -1;
    size_t plen = 0;
    const PrMount* m = pr_match(canon, &plen);
    if (!m) return -1;
    const char* rest = canon + plen;
    if (*rest == '\\') rest++;                                        /* 接頭辞との境界区切りを落とす */
    size_t need = strlen(m->target) + strlen(rest) + 2;
    if (need > outSize) return -1;
    if (*rest) snprintf(outPosix, outSize, "%s/%s", m->target, rest);
    else       snprintf(outPosix, outSize, "%s", m->target);
    for (char* p = outPosix; *p; p++) if (*p == '\\') *p = '/';       /* 残りを '/' 区切りへ (Win はファイル名に '\' を含めない) */
    return 0;
}

int pathreg_unmap(const char* posixPath, char* outWin, size_t outSize) {
    if (!posixPath || posixPath[0] != '/' || !outWin) return -1;
    pr_ensure_defaults();
    const PrMount* best = NULL; size_t bestLen = 0;
    size_t nl = strlen(posixPath);
    for (int i = 0; i < g_nmounts; i++) {
        size_t tl = strlen(g_mounts[i].target);
        if (nl < tl) continue;
        if (strncasecmp(posixPath, g_mounts[i].target, tl) != 0) continue;
        if (posixPath[tl] && posixPath[tl] != '/') continue;
        /* 同長 (同一 target の別名 profile) は先勝ち: 正規 username (webstudio) を返す
         * (CAB-213 username 統一 — 既定表の先頭 = userProfile = 正規)。 */
        if (tl > bestLen) { best = &g_mounts[i]; bestLen = tl; }
    }
    if (!best) return -1;
    const char* rest = posixPath + bestLen;
    char buf[PR_MAX_PREFIX * 2];
    if (*rest) snprintf(buf, sizeof buf, "%s\\%s", best->win, rest + 1);
    else       snprintf(buf, sizeof buf, "%s", best->win);
    /* target 区切りを '\' に戻す */
    for (char* p = buf; *p; p++) if (*p == '/') *p = '\\';
    if (strlen(buf) + 1 > outSize) return -1;
    strcpy(outWin, buf);
    return 0;
}

void pathreg_install(void) {
    shimx_set_path_mapper(pathreg_map);
}
