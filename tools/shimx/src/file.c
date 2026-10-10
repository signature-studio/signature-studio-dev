/* パス写像 (Win → Emscripten FS) / ファイル I/O / ディレクトリ / 属性。
 *
 * パス写像 (shimx_path_to_posix):
 *   C:\foo\bar   → /c/foo/bar     (ドライブ文字は小文字ディレクトリ)
 *   \\srv\share\x → /unc/srv/share/x
 *   \\?\C:\x     → /c/x           (プレフィクス除去)
 *   /abs/path    → そのまま (M4 互換: POSIX 絶対パスは素通し)
 *   相対パス     → Win カレントディレクトリ (既定 C:\) 基準
 *   '.' '..' を畳み込む。FS 側で見つからなければ大小文字無視で再探索 (Windows は case-insensitive)。
 * 上書き: shimx_set_path_mapper() で VFS 連携 (戻り <0 なら既定写像にフォールバック)。
 */
#include "shimx_internal.h"
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include <strings.h>
#include <utime.h>
#include <ctype.h>

static shimx_path_mapper_fn g_mapper;
static char g_cwd[1024] = "C:\\";          /* Win 形式 */
static int g_ci = 1;
static shx_mutex_t g_path_lk;

void shimx_set_path_mapper(shimx_path_mapper_fn fn) { g_mapper = fn; }

static DWORD errno_to_win(int e, int parentMissing) {
    switch (e) {
        case ENOENT: return parentMissing ? ERROR_PATH_NOT_FOUND : ERROR_FILE_NOT_FOUND;
        case ENOTDIR: return ERROR_PATH_NOT_FOUND;
        case EEXIST: return ERROR_FILE_EXISTS;
        case EACCES: case EPERM: case EISDIR: case EROFS: return ERROR_ACCESS_DENIED;
        case ENOMEM: return ERROR_NOT_ENOUGH_MEMORY;
        case ENOSPC: return 112;
        case EMFILE: case ENFILE: return ERROR_TOO_MANY_OPEN_FILES;
        case EBADF: return ERROR_INVALID_HANDLE;
        case EINVAL: return ERROR_INVALID_PARAMETER;
        case ENOTEMPTY: return ERROR_DIR_NOT_EMPTY;
        case ENAMETOOLONG: return 206;
        case EBUSY: return ERROR_SHARING_VIOLATION;
        default: return 31;   /* ERROR_GEN_FAILURE */
    }
}

/* '.' '..' を畳み、重複 '/' を除去 (別バッファへ書いてから戻す: in-place だと終端 NUL を潰す) */
static void collapse(char* p) {
    size_t len = strlen(p);
    char* o = (char*)malloc(len + 2);
    char* out = o;
    int abs = (p[0] == '/');
    if (abs) *out++ = '/';
    char* base = out;
    const char* in = abs ? p + 1 : p;
    while (*in) {
        const char* seg = in;
        while (*in && *in != '/') in++;
        size_t n = (size_t)(in - seg);
        if (*in == '/') in++;
        if (n == 0 || (n == 1 && seg[0] == '.')) continue;
        if (n == 2 && seg[0] == '.' && seg[1] == '.') {
            if (out > base) {
                out--;                                   /* 直前の '/' */
                while (out > base && out[-1] != '/') out--;
            }
            continue;
        }
        memcpy(out, seg, n);
        out += n;
        *out++ = '/';
    }
    if (out > base && out[-1] == '/') out--;
    *out = 0;
    if (!*o) { o[0] = abs ? '/' : '.'; o[1] = 0; }
    strcpy(p, o);
    free(o);
}

int shimx_path_to_posix(const char* in, char* out, size_t outSize) {
    char buf[2048];
    shx_ensure_init();
    if (!in || !*in) return -1;
    if (g_mapper) {
        int r = g_mapper(in, out, outSize);
        if (r >= 0) return 0;
    }
    size_t n = strlen(in);
    if (n >= sizeof buf - 1024) return -1;
    memcpy(buf, in, n + 1);
    for (char* p = buf; *p; p++) if (*p == '\\') *p = '/';
    char* s = buf;
    char uncbuf[2100];
    if (!strncmp(s, "//?/", 4) || !strncmp(s, "//./", 4)) {
        s += 4;
        if (!strncasecmp(s, "UNC/", 4)) { snprintf(uncbuf, sizeof uncbuf, "//%s", s + 4); s = uncbuf; }
    }
    char res[2200];
    if (((s[0] >= 'A' && s[0] <= 'Z') || (s[0] >= 'a' && s[0] <= 'z')) && s[1] == ':') {
        char d = (char)tolower((unsigned char)s[0]);
        const char* rest = s + 2;
        snprintf(res, sizeof res, "/%c/%s", d, *rest == '/' ? rest + 1 : rest);
    } else if (s[0] == '/' && s[1] == '/') {
        snprintf(res, sizeof res, "/unc/%s", s + 2);
    } else if (s[0] == '/') {
        snprintf(res, sizeof res, "%s", s);
    } else {
        /* 相対: Win cwd (C:\x\y) を posix 化して連結 */
        char cwd[1100];
        shx_mutex_lock(&g_path_lk);
        snprintf(cwd, sizeof cwd, "%s", g_cwd);
        shx_mutex_unlock(&g_path_lk);
        char cposix[1100];
        for (char* p = cwd; *p; p++) if (*p == '\\') *p = '/';
        if (cwd[1] == ':') snprintf(cposix, sizeof cposix, "/%c/%s", tolower((unsigned char)cwd[0]), cwd[2] == '/' ? cwd + 3 : cwd + 2);
        else if (cwd[0] == '/' && cwd[1] == '/') snprintf(cposix, sizeof cposix, "/unc/%s", cwd + 2);
        else snprintf(cposix, sizeof cposix, "%s", cwd);
        snprintf(res, sizeof res, "%s/%s", cposix, s);
    }
    collapse(res);
    if (strlen(res) + 1 > outSize) return -1;
    strcpy(out, res);
    return 0;
}

/* posix → Win 形式 (逆写像)。out は十分なサイズ */
static void posix_to_win(const char* p, char* out, size_t sz) {
    if (p[0] == '/' && ((p[1] >= 'a' && p[1] <= 'z')) && (p[2] == '/' || p[2] == 0)) {
        snprintf(out, sz, "%c:%s", toupper((unsigned char)p[1]), p[2] ? p + 2 : "/");
    } else if (!strncmp(p, "/unc/", 5)) {
        snprintf(out, sz, "//%s", p + 5);
    } else snprintf(out, sz, "%s", p);
    if (out[1] == ':' || out[0] == '/') {
        if (out[1] == ':' || !strncmp(out, "//", 2)) for (char* q = out; *q; q++) if (*q == '/') *q = '\\';
    }
}

/* 大小文字無視の再解決: 見つからない成分を readdir で探して path を書き換える */
static void ci_fix(char* path, size_t sz) {
    struct stat st;
    if (!g_ci || stat(path, &st) == 0) return;
    char cur[2048] = "/";
    char* p = path;
    while (*p == '/') p++;
    while (*p) {
        char* e = p; while (*e && *e != '/') e++;
        char comp[512]; size_t cl = (size_t)(e - p);
        if (cl >= sizeof comp) return;
        memcpy(comp, p, cl); comp[cl] = 0;
        char cand[2600];
        snprintf(cand, sizeof cand, "%s%s%s", cur, cur[1] ? "/" : "", comp);
        if (stat(cand, &st) != 0) {
            DIR* d = opendir(cur);
            int found = 0;
            if (d) {
                struct dirent* de;
                while ((de = readdir(d))) {
                    if (!strcasecmp(de->d_name, comp)) {
                        snprintf(cand, sizeof cand, "%s%s%s", cur, cur[1] ? "/" : "", de->d_name);
                        found = 1; break;
                    }
                }
                closedir(d);
            }
            if (!found) return;      /* 残りは未存在: 以降は触らない */
        }
        size_t cn = strlen(cand);
        if (cn >= sizeof cur) return;
        memcpy(cur, cand, cn + 1);
        p = e; while (*p == '/') p++;
    }
    if (strlen(cur) < sz) strcpy(path, cur);
}

int shx_wpath_to_posix(LPCWSTR w, char* out, size_t outSize) {
    char tmp[2048];
    if (!w || shimx_utf16_to_utf8(w, -1, tmp, sizeof tmp) < 0 || shimx_path_to_posix(tmp, out, outSize) < 0) {
        SetLastError(ERROR_INVALID_NAME);   /* Win: ERROR_INVALID_PARAMETER/INVALID_NAME */
        return -1;
    }
    ci_fix(out, outSize);
    return 0;
}
int shx_apath_to_posix(LPCSTR a, char* out, size_t outSize) {
    WCHAR w[1100];
    int n = MultiByteToWideChar(CP_ACP, 0, a, -1, w, 1100);
    if (n <= 0) { SetLastError(ERROR_INVALID_NAME); return -1; }
    return shx_wpath_to_posix(w, out, outSize);
}

int shx_wcopy_out(const WCHAR* src, int srcLen, LPWSTR dst, DWORD dstCch) {
    if (!dst || dstCch < (DWORD)srcLen + 1) return srcLen + 1;   /* 必要バッファ長 (NUL 含む) */
    memcpy(dst, src, (size_t)srcLen * 2);
    dst[srcLen] = 0;
    return srcLen;
}
static int copy_utf8_out(const char* s, LPWSTR dst, DWORD cch) {
    int n = shimx_utf8_to_utf16(s, -1, NULL, 0);
    if (n < 0) n = 0;
    WCHAR* t = (WCHAR*)malloc(((size_t)n + 1) * 2);
    shimx_utf8_to_utf16(s, -1, t, (size_t)n + 1);
    t[n] = 0;
    int r = shx_wcopy_out(t, n, dst, cch);
    free(t);
    return r;
}

/* ---------------------------------------------------------------
 * 初期化 (std handle / ドライブルート)
 * --------------------------------------------------------------- */
static HANDLE g_std[3];
void shx_init_std_handles(void) {
    for (int i = 0; i < 3; i++) {
        ShxObj* o = shx_obj_new(OBJ_FILE);
        o->fd = i; o->is_std = 1; o->access = i == 0 ? GENERIC_READ : GENERIC_WRITE;
        g_std[i] = shx_handle_new(o);
    }
    mkdir("/c", 0755);
}

HANDLE GetStdHandle(DWORD which) {
    shx_ensure_init();
    int i = which == STD_INPUT_HANDLE ? 0 : which == STD_OUTPUT_HANDLE ? 1 : which == STD_ERROR_HANDLE ? 2 : -1;
    if (i < 0) { SetLastError(ERROR_INVALID_HANDLE); return INVALID_HANDLE_VALUE; }
    return g_std[i];
}
BOOL SetStdHandle(DWORD which, HANDLE h) {
    int i = which == STD_INPUT_HANDLE ? 0 : which == STD_OUTPUT_HANDLE ? 1 : which == STD_ERROR_HANDLE ? 2 : -1;
    if (i < 0) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    g_std[i] = h;
    return TRUE;
}

void shx_file_destroy(ShxObj* o) {
    if (o->fd >= 0 && !o->is_std) close(o->fd);
    free(o->path);
}

/* ---------------------------------------------------------------
 * CreateFile
 * --------------------------------------------------------------- */
static HANDLE create_file_posix(const char* path, DWORD access, DWORD disp, DWORD flagsAttr) {
    int oflags = 0;
    int rd = (access & (GENERIC_READ | GENERIC_ALL)) != 0;
    int wr = (access & (GENERIC_WRITE | GENERIC_ALL)) != 0;
    if (!rd && !wr) rd = 1;               /* access=0 (属性照会用) */
    oflags |= (rd && wr) ? O_RDWR : (wr ? O_WRONLY : O_RDONLY);
    struct stat st;
    int exists = (stat(path, &st) == 0);
    if (exists && S_ISDIR(st.st_mode)) {
        if (!(flagsAttr & FILE_FLAG_BACKUP_SEMANTICS) || disp != OPEN_EXISTING) {
            SetLastError(ERROR_ACCESS_DENIED);
            return INVALID_HANDLE_VALUE;
        }
        ShxObj* o = shx_obj_new(OBJ_FILE);
        if (!o) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
        o->is_dir = 1; o->path = strdup(path);
        HANDLE h = shx_handle_new(o);
        if (!h) return INVALID_HANDLE_VALUE;
        SetLastError(ERROR_SUCCESS);
        return h;
    }
    switch (disp) {
        case CREATE_NEW:        oflags |= O_CREAT | O_EXCL;  break;
        case CREATE_ALWAYS:     oflags |= O_CREAT | O_TRUNC; break;
        case OPEN_EXISTING:     break;
        case OPEN_ALWAYS:       oflags |= O_CREAT;           break;
        case TRUNCATE_EXISTING: oflags |= O_TRUNC; if (!wr) { SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE; } break;
        default: SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE;
    }
    int fd = open(path, oflags, 0644);
    if (fd < 0) {
        int e = errno;
        SHX_TRACE("CreateFile open(%s) failed errno=%d", path, e);
        int parentMissing = 0;
        if (e == ENOENT) {
            char par[2048]; snprintf(par, sizeof par, "%s", path);
            char* sl = strrchr(par, '/');
            if (sl && sl != par) { *sl = 0; struct stat ps; parentMissing = (stat(par, &ps) != 0); }
        }
        if (e == EEXIST && disp == CREATE_NEW) { SetLastError(ERROR_FILE_EXISTS); return INVALID_HANDLE_VALUE; }
        SetLastError(errno_to_win(e, parentMissing));
        return INVALID_HANDLE_VALUE;
    }
    ShxObj* o = shx_obj_new(OBJ_FILE);
    if (!o) { close(fd); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
    o->fd = fd; o->access = access; o->path = strdup(path);
    HANDLE h = shx_handle_new(o);
    if (!h) { close(fd); return INVALID_HANDLE_VALUE; }
    SetLastError((exists && (disp == CREATE_ALWAYS || disp == OPEN_ALWAYS)) ? ERROR_ALREADY_EXISTS : ERROR_SUCCESS);
    return h;
}

HANDLE CreateFileW(LPCWSTR fileName, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                   DWORD disp, DWORD flagsAttr, HANDLE tmpl) {
    (void)share; (void)sa; (void)tmpl;
    shx_ensure_init();
    char path[2048];
    if (fileName && fileName[0] == 'N' && fileName[1] == 'U' && fileName[2] == 'L' && !fileName[3]) strcpy(path, "/dev/null");
    else if (shx_wpath_to_posix(fileName, path, sizeof path) < 0) return INVALID_HANDLE_VALUE;
    return create_file_posix(path, access, disp, flagsAttr);
}
HANDLE CreateFileA(LPCSTR fileName, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                   DWORD disp, DWORD flagsAttr, HANDLE tmpl) {
    (void)share; (void)sa; (void)tmpl;
    shx_ensure_init();
    char path[2048];
    if (shx_apath_to_posix(fileName, path, sizeof path) < 0) return INVALID_HANDLE_VALUE;
    return create_file_posix(path, access, disp, flagsAttr);
}

/* ---------------------------------------------------------------
 * Read / Write / seek / size
 * --------------------------------------------------------------- */
static ShxObj* file_ref(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return NULL; }
    if (o->fd < 0) { shx_unref(o); SetLastError(ERROR_INVALID_HANDLE); return NULL; }
    return o;
}

BOOL ReadFile(HANDLE h, LPVOID buf, DWORD n, LPDWORD out, LPOVERLAPPED ov) {
    (void)ov;
    if (out) *out = 0;
    ShxObj* o = file_ref(h);
    if (!o) return FALSE;
    ssize_t r = read(o->fd, buf, n);
    int e = errno;
    shx_unref(o);
    if (r < 0) { SetLastError(errno_to_win(e, 0)); return FALSE; }
    if (out) *out = (DWORD)r;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}
BOOL WriteFile(HANDLE h, LPCVOID buf, DWORD n, LPDWORD out, LPOVERLAPPED ov) {
    (void)ov;
    if (out) *out = 0;
    ShxObj* o = file_ref(h);
    if (!o) return FALSE;
    ssize_t r = write(o->fd, buf, n);
    int e = errno;
    shx_unref(o);
    if (r < 0) { SetLastError(errno_to_win(e, 0)); return FALSE; }
    if (out) *out = (DWORD)r;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

static int64_t seek64(HANDLE h, int64_t dist, DWORD method) {
    ShxObj* o = file_ref(h);
    if (!o) return -1;
    int whence = method == FILE_BEGIN ? SEEK_SET : method == FILE_CURRENT ? SEEK_CUR : method == FILE_END ? SEEK_END : -1;
    if (whence < 0) { shx_unref(o); SetLastError(ERROR_INVALID_PARAMETER); return -1; }
    off_t r = lseek(o->fd, (off_t)dist, whence);
    int e = errno;
    shx_unref(o);
    if (r < 0) { SetLastError(e == EINVAL ? ERROR_NEGATIVE_SEEK : errno_to_win(e, 0)); return -1; }
    SetLastError(ERROR_SUCCESS);
    return (int64_t)r;
}
DWORD SetFilePointer(HANDLE h, LONG lo, PLONG hi, DWORD method) {
    int64_t dist = (int64_t)lo;
    if (hi) dist = (int64_t)(((uint64_t)(uint32_t)*hi << 32) | (uint32_t)lo);
    int64_t r = seek64(h, dist, method);
    if (r < 0) return INVALID_SET_FILE_POINTER;
    if (hi) *hi = (LONG)((uint64_t)r >> 32);
    SetLastError(ERROR_SUCCESS);
    return (DWORD)(uint64_t)r;
}
BOOL SetFilePointerEx(HANDLE h, LARGE_INTEGER dist, PLARGE_INTEGER np, DWORD method) {
    int64_t r = seek64(h, dist.QuadPart, method);
    if (r < 0) return FALSE;
    if (np) np->QuadPart = r;
    return TRUE;
}
BOOL SetEndOfFile(HANDLE h) {
    ShxObj* o = file_ref(h);
    if (!o) return FALSE;
    off_t cur = lseek(o->fd, 0, SEEK_CUR);
    int ok = (cur >= 0 && ftruncate(o->fd, cur) == 0);
    int e = errno;
    shx_unref(o);
    if (!ok) { SetLastError(errno_to_win(e, 0)); return FALSE; }
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}
static int64_t fsize64(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return -1; }
    struct stat st; int r;
    if (o->fd >= 0) r = fstat(o->fd, &st); else r = o->path ? stat(o->path, &st) : -1;
    int e = errno;
    shx_unref(o);
    if (r != 0) { SetLastError(errno_to_win(e, 0)); return -1; }
    SetLastError(ERROR_SUCCESS);
    return (int64_t)st.st_size;
}
DWORD GetFileSize(HANDLE h, LPDWORD hi) {
    int64_t r = fsize64(h);
    if (r < 0) return INVALID_FILE_SIZE;
    if (hi) *hi = (DWORD)((uint64_t)r >> 32);
    return (DWORD)(uint64_t)r;
}
BOOL GetFileSizeEx(HANDLE h, PLARGE_INTEGER size) {
    int64_t r = fsize64(h);
    if (r < 0) return FALSE;
    if (size) size->QuadPart = r;
    return TRUE;
}
DWORD GetFileType(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FILE_TYPE_UNKNOWN; }
    DWORD t = o->is_std ? FILE_TYPE_CHAR : FILE_TYPE_DISK;
    shx_unref(o);
    SetLastError(ERROR_SUCCESS);
    return t;
}
BOOL FlushFileBuffers(HANDLE h) {
    ShxObj* o = file_ref(h);
    if (!o) return FALSE;
    if (!o->is_std) fsync(o->fd);
    shx_unref(o);
    return TRUE;
}

/* ---- FILETIME 変換 (st → FILETIME) ---- */
static void st_to_ft(time_t t, FILETIME* ft) {
    uint64_t v = ((uint64_t)t + 11644473600ull) * 10000000ull;
    ft->dwLowDateTime = (DWORD)v; ft->dwHighDateTime = (DWORD)(v >> 32);
}
static time_t ft_to_t(const FILETIME* ft) {
    uint64_t v = ((uint64_t)ft->dwHighDateTime << 32) | ft->dwLowDateTime;
    return (time_t)(v / 10000000ull) - 11644473600ll;
}
static DWORD attrs_of(const struct stat* st) {
    DWORD a = S_ISDIR(st->st_mode) ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_ARCHIVE;
    if (!(st->st_mode & 0200)) a |= FILE_ATTRIBUTE_READONLY;
    return a;
}
BOOL GetFileInformationByHandle(HANDLE h, BY_HANDLE_FILE_INFORMATION* info) {
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o || !info) { if (o) shx_unref(o); SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    struct stat st; int r;
    if (o->fd >= 0) r = fstat(o->fd, &st); else r = o->path ? stat(o->path, &st) : -1;
    int e = errno;
    shx_unref(o);
    if (r != 0) { SetLastError(errno_to_win(e, 0)); return FALSE; }
    memset(info, 0, sizeof(*info));
    info->dwFileAttributes = attrs_of(&st);
    st_to_ft(st.st_ctime, &info->ftCreationTime);
    st_to_ft(st.st_atime, &info->ftLastAccessTime);
    st_to_ft(st.st_mtime, &info->ftLastWriteTime);
    info->dwVolumeSerialNumber = 0x57454253;
    info->nFileSizeHigh = (DWORD)((uint64_t)st.st_size >> 32);
    info->nFileSizeLow = (DWORD)st.st_size;
    info->nNumberOfLinks = st.st_nlink ? (DWORD)st.st_nlink : 1;
    info->nFileIndexHigh = (DWORD)((uint64_t)st.st_ino >> 32);
    info->nFileIndexLow = (DWORD)st.st_ino;
    return TRUE;
}
BOOL GetFileTime(HANDLE h, FILETIME* c, FILETIME* a, FILETIME* w) {
    BY_HANDLE_FILE_INFORMATION i;
    if (!GetFileInformationByHandle(h, &i)) return FALSE;
    if (c) *c = i.ftCreationTime;
    if (a) *a = i.ftLastAccessTime;
    if (w) *w = i.ftLastWriteTime;
    return TRUE;
}
BOOL SetFileTime(HANDLE h, const FILETIME* c, const FILETIME* a, const FILETIME* w) {
    (void)c;
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    struct stat st;
    int ok = (o->path && stat(o->path, &st) == 0);
    if (ok) {
        struct utimbuf ub;
        ub.actime = a ? ft_to_t(a) : st.st_atime;
        ub.modtime = w ? ft_to_t(w) : st.st_mtime;
        utime(o->path, &ub);       /* best effort (MEMFS 非対応でも成功扱い) */
    }
    shx_unref(o);
    if (!ok) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    return TRUE;
}
BOOL LockFile(HANDLE h, DWORD a, DWORD b, DWORD c, DWORD d) { (void)a; (void)b; (void)c; (void)d; return shx_ref(h, OBJ_FILE) ? TRUE : FALSE; }
BOOL UnlockFile(HANDLE h, DWORD a, DWORD b, DWORD c, DWORD d) { return LockFile(h, a, b, c, d); }
BOOL LockFileEx(HANDLE h, DWORD f, DWORD r, DWORD c, DWORD d, LPOVERLAPPED ov) { (void)f; (void)r; (void)ov; return LockFile(h, 0, 0, c, d); }
BOOL UnlockFileEx(HANDLE h, DWORD r, DWORD c, DWORD d, LPOVERLAPPED ov) { (void)r; (void)ov; return LockFile(h, 0, 0, c, d); }

DWORD GetFinalPathNameByHandleW(HANDLE h, LPWSTR out, DWORD n, DWORD flags) {
    (void)flags;
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o || !o->path) { if (o) shx_unref(o); SetLastError(ERROR_INVALID_HANDLE); return 0; }
    char w[2200], full[2300];
    posix_to_win(o->path, w, sizeof w);
    snprintf(full, sizeof full, "\\\\?\\%s", w);
    shx_unref(o);
    return (DWORD)copy_utf8_out(full, out, n);
}

BOOL CreateSymbolicLinkW(LPCWSTR l, LPCWSTR t, DWORD f) { (void)l; (void)t; (void)f; SetLastError(ERROR_PRIVILEGE_NOT_HELD); return FALSE; }
BOOL DeviceIoControl(HANDLE h, DWORD c, LPVOID i, DWORD in, LPVOID o, DWORD on, LPDWORD r, LPOVERLAPPED ov) {
    (void)h; (void)c; (void)i; (void)in; (void)o; (void)on; (void)ov; if (r) *r = 0; SetLastError(ERROR_INVALID_FUNCTION); return FALSE;
}
BOOL ReadDirectoryChangesW(HANDLE h, LPVOID b, DWORD n, BOOL s, DWORD f, LPDWORD r, LPOVERLAPPED ov, LPVOID cr) {
    (void)h; (void)b; (void)n; (void)s; (void)f; (void)ov; (void)cr; if (r) *r = 0; SetLastError(ERROR_NOT_SUPPORTED); return FALSE;
}
BOOL PeekNamedPipe(HANDLE h, LPVOID b, DWORD n, LPDWORD r, LPDWORD a, LPDWORD l) {
    (void)h; (void)b; (void)n; (void)r; (void)a; (void)l; SetLastError(109 /* ERROR_BROKEN_PIPE */); return FALSE;
}
BOOL AreFileApisANSI(void) { return TRUE; }

/* ---------------------------------------------------------------
 * 削除 / コピー / 移動 / ディレクトリ
 * --------------------------------------------------------------- */
BOOL DeleteFileW(LPCWSTR p) {
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return FALSE;
    struct stat st;
    if (stat(px, &st) == 0 && S_ISDIR(st.st_mode)) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
    if (unlink(px) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    return TRUE;
}
BOOL DeleteFileA(LPCSTR p) {
    char px[2048]; if (shx_apath_to_posix(p, px, sizeof px) < 0) return FALSE;
    if (unlink(px) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    return TRUE;
}
BOOL CopyFileW(LPCWSTR from, LPCWSTR to, BOOL failIfExists) {
    char a[2048], b[2048];
    if (shx_wpath_to_posix(from, a, sizeof a) < 0 || shx_wpath_to_posix(to, b, sizeof b) < 0) return FALSE;
    struct stat st;
    if (stat(a, &st) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    if (S_ISDIR(st.st_mode)) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
    int fi = open(a, O_RDONLY);
    if (fi < 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    int fo = open(b, O_WRONLY | O_CREAT | (failIfExists ? O_EXCL : O_TRUNC), 0644);
    if (fo < 0) {
        int e = errno; close(fi);
        SetLastError(e == EEXIST ? ERROR_FILE_EXISTS : errno_to_win(e, e == ENOENT));
        return FALSE;
    }
    char buf[16384]; ssize_t r; int ok = 1;
    while ((r = read(fi, buf, sizeof buf)) > 0) if (write(fo, buf, (size_t)r) != r) { ok = 0; break; }
    if (r < 0) ok = 0;
    close(fi); close(fo);
    if (!ok) { SetLastError(112); return FALSE; }
    return TRUE;
}
BOOL MoveFileExW(LPCWSTR from, LPCWSTR to, DWORD flags) {
    char a[2048], b[2048];
    if (shx_wpath_to_posix(from, a, sizeof a) < 0 || shx_wpath_to_posix(to, b, sizeof b) < 0) return FALSE;
    struct stat st;
    if (stat(a, &st) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    if (stat(b, &st) == 0) {
        if (!(flags & MOVEFILE_REPLACE_EXISTING)) { SetLastError(ERROR_ALREADY_EXISTS); return FALSE; }
    }
    if (rename(a, b) != 0) { SetLastError(errno_to_win(errno, 1)); return FALSE; }
    return TRUE;
}
BOOL MoveFileW(LPCWSTR from, LPCWSTR to) { return MoveFileExW(from, to, 0); }

BOOL CreateDirectoryW(LPCWSTR p, LPSECURITY_ATTRIBUTES sa) {
    (void)sa;
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return FALSE;
    if (mkdir(px, 0755) != 0) {
        int e = errno;
        SetLastError(e == EEXIST ? ERROR_ALREADY_EXISTS : errno_to_win(e, e == ENOENT));
        return FALSE;
    }
    return TRUE;
}
BOOL RemoveDirectoryW(LPCWSTR p) {
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return FALSE;
    if (rmdir(px) != 0) { SetLastError(errno == ENOTDIR ? ERROR_PATH_NOT_FOUND : errno_to_win(errno, 0)); return FALSE; }
    return TRUE;
}

DWORD GetFileAttributesW(LPCWSTR p) {
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return INVALID_FILE_ATTRIBUTES;
    struct stat st;
    if (stat(px, &st) != 0) {
        char par[2048]; snprintf(par, sizeof par, "%s", px);
        char* sl = strrchr(par, '/'); int pm = 0;
        if (sl && sl != par) { *sl = 0; struct stat ps; pm = (stat(par, &ps) != 0); }
        SetLastError(errno_to_win(errno, pm));
        return INVALID_FILE_ATTRIBUTES;
    }
    SetLastError(ERROR_SUCCESS);
    return attrs_of(&st);
}
DWORD GetFileAttributesA(LPCSTR p) {
    WCHAR w[1100];
    if (MultiByteToWideChar(CP_ACP, 0, p, -1, w, 1100) <= 0) return INVALID_FILE_ATTRIBUTES;
    return GetFileAttributesW(w);
}
BOOL GetFileAttributesExW(LPCWSTR p, uint64_t level, LPVOID info) {
    if (level != GetFileExInfoStandard || !info) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return FALSE;
    struct stat st;
    if (stat(px, &st) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    WIN32_FILE_ATTRIBUTE_DATA* d = (WIN32_FILE_ATTRIBUTE_DATA*)info;
    d->dwFileAttributes = attrs_of(&st);
    st_to_ft(st.st_ctime, &d->ftCreationTime);
    st_to_ft(st.st_atime, &d->ftLastAccessTime);
    st_to_ft(st.st_mtime, &d->ftLastWriteTime);
    d->nFileSizeHigh = (DWORD)((uint64_t)st.st_size >> 32);
    d->nFileSizeLow = (DWORD)st.st_size;
    return TRUE;
}
BOOL SetFileAttributesW(LPCWSTR p, DWORD attr) {
    char px[2048]; if (shx_wpath_to_posix(p, px, sizeof px) < 0) return FALSE;
    struct stat st;
    if (stat(px, &st) != 0) { SetLastError(errno_to_win(errno, 0)); return FALSE; }
    mode_t m = st.st_mode & 07777;
    if (attr & FILE_ATTRIBUTE_READONLY) m &= ~0222; else m |= 0200;
    chmod(px, m);
    return TRUE;
}

/* ---------------------------------------------------------------
 * フルパス / 一時ファイル / カレントディレクトリ / ドライブ
 * --------------------------------------------------------------- */
static void to_canon_win(const char* in, char* out, size_t sz) {
    /* 入力 (Win or POSIX 形式) → 正規化した絶対パス。POSIX 絶対形式の入力は POSIX のまま返す */
    char t[2200], px[2048];
    int posixStyle = (in[0] == '/' && in[1] != '/' && !strchr(in, '\\'));
    if (shimx_path_to_posix(in, px, sizeof px) < 0) { snprintf(out, sz, "%s", in); return; }
    if (posixStyle) { snprintf(out, sz, "%s", px); return; }
    posix_to_win(px, t, sizeof t);
    snprintf(out, sz, "%s", t);
}

DWORD GetFullPathNameW(LPCWSTR p, DWORD n, LPWSTR buf, LPWSTR* filePart) {
    char in[2048], out[2300];
    if (!p || !*p || shimx_utf16_to_utf8(p, -1, in, sizeof in) < 0) { SetLastError(ERROR_INVALID_NAME); return 0; }
    to_canon_win(in, out, sizeof out);
    WCHAR* w = shx_wcsdup_utf8(out);
    int len = shx_wstr_len(w);
    DWORD r;
    if (!buf || n < (DWORD)len + 1) { r = (DWORD)len + 1; }
    else {
        memcpy(buf, w, ((size_t)len + 1) * 2);
        r = (DWORD)len;
        if (filePart) {
            int i = len;
            while (i > 0 && buf[i - 1] != '\\' && buf[i - 1] != '/') i--;
            *filePart = (i < len) ? buf + i : NULL;
        }
    }
    free(w);
    return r;
}
DWORD GetFullPathNameA(LPCSTR p, DWORD n, LPSTR buf, LPSTR* filePart) {
    WCHAR wi[1100], wo[1100];
    if (MultiByteToWideChar(CP_ACP, 0, p, -1, wi, 1100) <= 0) return 0;
    LPWSTR fp = NULL;
    DWORD r = GetFullPathNameW(wi, 1100, wo, &fp);
    if (!r || r >= 1100) return r;
    int need = WideCharToMultiByte(CP_ACP, 0, wo, -1, NULL, 0, NULL, NULL);
    if (!buf || n < (DWORD)need) return (DWORD)need;
    WideCharToMultiByte(CP_ACP, 0, wo, -1, buf, (int)n, NULL, NULL);
    if (filePart) *filePart = fp ? buf + WideCharToMultiByte(CP_ACP, 0, wo, (int)(fp - wo), NULL, 0, NULL, NULL) : NULL;
    return (DWORD)(need - 1);
}

static void mkdirs(const char* path) {
    char t[2048]; snprintf(t, sizeof t, "%s", path);
    for (char* p = t + 1; *p; p++) if (*p == '/') { *p = 0; mkdir(t, 0755); *p = '/'; }
    mkdir(t, 0755);
}
DWORD GetTempPathW(DWORD n, LPWSTR buf) {
    shx_ensure_init();
    char px[2048];
    const char* tmp = "C:\\Users\\webstudio\\AppData\\Local\\Temp\\";
    shimx_path_to_posix(tmp, px, sizeof px);
    mkdirs(px);
    return (DWORD)copy_utf8_out(tmp, buf, n);
}
DWORD GetTempPathA(DWORD n, LPSTR buf) {
    const char* tmp = "C:\\Users\\webstudio\\AppData\\Local\\Temp\\";
    DWORD len = (DWORD)strlen(tmp);
    if (!buf || n < len + 1) return len + 1;
    memcpy(buf, tmp, len + 1);
    return len;
}
UINT GetTempFileNameW(LPCWSTR dir, LPCWSTR prefix, UINT unique, LPWSTR out) {
    char d[1100], pf[16] = {0};
    if (!dir || shimx_utf16_to_utf8(dir, -1, d, sizeof d) < 0 || !out) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    for (int i = 0; prefix && prefix[i] && i < 3; i++) pf[i] = (char)prefix[i];
    size_t dl = strlen(d);
    while (dl && (d[dl - 1] == '\\' || d[dl - 1] == '/')) d[--dl] = 0;
    static volatile uint32_t ctr = 0x1234;
    for (int tries = 0; tries < 4096; tries++) {
        UINT u = unique ? unique : (UINT)(__atomic_add_fetch(&ctr, 1, __ATOMIC_SEQ_CST) & 0xFFFF);
        if (!u) continue;
        char name[1300], px[2048];
        snprintf(name, sizeof name, "%s\\%s%X.tmp", d, pf, u);
        if (shimx_path_to_posix(name, px, sizeof px) < 0) { SetLastError(ERROR_INVALID_NAME); return 0; }
        struct stat st;
        if (unique) {
            copy_utf8_out(name, out, MAX_PATH);
            return u;
        }
        if (stat(px, &st) == 0) continue;
        int fd = open(px, O_WRONLY | O_CREAT | O_EXCL, 0644);
        if (fd < 0) { SetLastError(errno_to_win(errno, 1)); return 0; }
        close(fd);
        copy_utf8_out(name, out, MAX_PATH);
        return u;
    }
    SetLastError(ERROR_FILE_EXISTS);
    return 0;
}

DWORD GetCurrentDirectoryW(DWORD n, LPWSTR buf) {
    char c[1100];
    shx_mutex_lock(&g_path_lk); snprintf(c, sizeof c, "%s", g_cwd); shx_mutex_unlock(&g_path_lk);
    return (DWORD)copy_utf8_out(c, buf, n);
}
BOOL SetCurrentDirectoryW(LPCWSTR p) {
    char in[1100], px[2048], full[1300];
    if (!p || shimx_utf16_to_utf8(p, -1, in, sizeof in) < 0 || shimx_path_to_posix(in, px, sizeof px) < 0) { SetLastError(ERROR_INVALID_NAME); return FALSE; }
    ci_fix(px, sizeof px);
    struct stat st;
    if (stat(px, &st) != 0 || !S_ISDIR(st.st_mode)) { SetLastError(ERROR_FILE_NOT_FOUND); return FALSE; }
    to_canon_win(in, full, sizeof full);
    shx_mutex_lock(&g_path_lk); snprintf(g_cwd, sizeof g_cwd, "%s", full); shx_mutex_unlock(&g_path_lk);
    return TRUE;
}

DWORD GetLogicalDrives(void) { return 0x4; }   /* C: のみ */
DWORD GetLogicalDriveStringsW(DWORD n, LPWSTR buf) {
    if (n < 5) return 5;
    buf[0] = 'C'; buf[1] = ':'; buf[2] = '\\'; buf[3] = 0; buf[4] = 0;
    return 4;
}
UINT GetDriveTypeW(LPCWSTR root) {
    if (!root || ((root[0] == 'C' || root[0] == 'c') && root[1] == ':')) return DRIVE_FIXED;
    return DRIVE_NO_ROOT_DIR;
}
BOOL GetVolumeInformationW(LPCWSTR root, LPWSTR label, DWORD labelN, LPDWORD serial,
                           LPDWORD maxComp, LPDWORD flags, LPWSTR fsName, DWORD fsN) {
    (void)root;
    if (label && labelN) copy_utf8_out("WebStudio", label, labelN);
    if (serial) *serial = 0x57454253;
    if (maxComp) *maxComp = 255;
    if (flags) *flags = 0x7;        /* CASE_SENSITIVE_SEARCH | CASE_PRESERVED | UNICODE_ON_DISK */
    if (fsName && fsN) copy_utf8_out("NTFS", fsName, fsN);
    return TRUE;
}
BOOL GetDiskFreeSpaceW(LPCWSTR root, LPDWORD spc, LPDWORD bps, LPDWORD freeC, LPDWORD totC) {
    (void)root;
    if (spc) *spc = 8;
    if (bps) *bps = 512;
    if (freeC) *freeC = 0x1000000;
    if (totC) *totC = 0x2000000;
    return TRUE;
}
BOOL GetDiskFreeSpaceA(LPCSTR root, LPDWORD spc, LPDWORD bps, LPDWORD freeC, LPDWORD totC) {
    return GetDiskFreeSpaceW(NULL, spc, bps, freeC, totC); (void)root;
}
DWORD QueryDosDeviceW(LPCWSTR dev, LPWSTR target, DWORD n) {
    if (dev && dev[0] && dev[1] == ':') {
        const char* t = "\\Device\\HarddiskVolume1";
        DWORD len = (DWORD)strlen(t);
        if (n < len + 2) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        for (DWORD i = 0; i <= len; i++) target[i] = (WCHAR)t[i];
        target[len + 1] = 0;
        return len + 2;
    }
    SetLastError(ERROR_FILE_NOT_FOUND);
    return 0;
}
BOOL SetVolumeLabelW(LPCWSTR root, LPCWSTR label) { (void)root; (void)label; return TRUE; }

/* shell32 PathCleanupSpec: 無効文字を '-' に置換。戻り: PCS_REPLACEDCHAR(1) */
BOOL PathCleanupSpec(LPWSTR path, LPWSTR spec) {
    (void)path;
    int changed = 0;
    if (!spec) return 0;
    for (WCHAR* p = spec; *p; p++)
        if (*p < 32 || *p == '\\' || *p == '/' || *p == ':' || *p == '*' || *p == '?' || *p == '"' || *p == '<' || *p == '>' || *p == '|') { *p = '-'; changed = 1; }
    return changed ? 1 : 0;
}

/* ---------------------------------------------------------------
 * FindFirstFile / FindNextFile
 * --------------------------------------------------------------- */
static int wild_match(const char* p, const char* s) {
    while (*p) {
        if (*p == '*') {
            while (*p == '*') p++;
            if (!*p) return 1;
            for (;; s++) { if (wild_match(p, s)) return 1; if (!*s) return 0; }
        }
        if (!*s) return 0;
        if (*p != '?' && tolower((unsigned char)*p) != tolower((unsigned char)*s)) return 0;
        p++; s++;
    }
    return !*s;
}
static int name_cmp(const void* a, const void* b) {
    const char* x = *(char* const*)a; const char* y = *(char* const*)b;
    int dx = !strcmp(x, ".") ? 0 : !strcmp(x, "..") ? 1 : 2, dy = !strcmp(y, ".") ? 0 : !strcmp(y, "..") ? 1 : 2;
    if (dx != dy) return dx - dy;
    return strcasecmp(x, y);
}
void shx_find_destroy(ShxObj* o) {
    for (int i = 0; i < o->find_n; i++) free(o->find_list[i]);
    free(o->find_list); free(o->find_pat); free(o->path);
}

static BOOL find_fill(ShxObj* o, WIN32_FIND_DATAW* fd) {
    if (o->find_i >= o->find_n) { SetLastError(ERROR_NO_MORE_FILES); return FALSE; }
    const char* name = o->find_list[o->find_i++];
    char full[2600]; struct stat st;
    snprintf(full, sizeof full, "%s/%s", o->path, name);
    memset(fd, 0, sizeof(*fd));
    if (stat(full, &st) == 0) {
        fd->dwFileAttributes = attrs_of(&st);
        st_to_ft(st.st_ctime, &fd->ftCreationTime);
        st_to_ft(st.st_atime, &fd->ftLastAccessTime);
        st_to_ft(st.st_mtime, &fd->ftLastWriteTime);
        fd->nFileSizeHigh = S_ISDIR(st.st_mode) ? 0 : (DWORD)((uint64_t)st.st_size >> 32);
        fd->nFileSizeLow = S_ISDIR(st.st_mode) ? 0 : (DWORD)st.st_size;
    } else fd->dwFileAttributes = FILE_ATTRIBUTE_NORMAL;
    int n = shimx_utf8_to_utf16(name, -1, fd->cFileName, MAX_PATH - 1);
    fd->cFileName[n < 0 ? 0 : n] = 0;
    return TRUE;
}

HANDLE FindFirstFileExW(LPCWSTR pat, int infoLevel, LPVOID fd, int searchOp, LPVOID filter, DWORD flags) {
    (void)infoLevel; (void)searchOp; (void)filter; (void)flags;
    shx_ensure_init();
    char in[2048], px[2048];
    if (!pat || !*pat || shimx_utf16_to_utf8(pat, -1, in, sizeof in) < 0) { SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE; }
    /* ディレクトリ部とパターン部を分離 (Win 区切りで) */
    size_t l = strlen(in);
    const char* base = in;
    for (size_t i = l; i > 0; i--) if (in[i - 1] == '\\' || in[i - 1] == '/') { base = in + i; break; }
    char dirpart[2048], patpart[512];
    size_t dl = (size_t)(base - in);
    if (dl) { memcpy(dirpart, in, dl); dirpart[dl] = 0; if (dl > 1 && !(dl == 3 && dirpart[1] == ':')) dirpart[dl - 1] = 0; } else strcpy(dirpart, ".");
    snprintf(patpart, sizeof patpart, "%s", base);
    if (!*patpart) { SetLastError(ERROR_FILE_NOT_FOUND); return INVALID_HANDLE_VALUE; }
    if (shimx_path_to_posix(dirpart, px, sizeof px) < 0) { SetLastError(ERROR_PATH_NOT_FOUND); return INVALID_HANDLE_VALUE; }
    ci_fix(px, sizeof px);
    DIR* d = opendir(px);
    if (!d) { SetLastError(errno == ENOENT || errno == ENOTDIR ? ERROR_PATH_NOT_FOUND : errno_to_win(errno, 0)); return INVALID_HANDLE_VALUE; }
    char** list = NULL; int cnt = 0, cap = 0;
    int isRoot = (!strcmp(px, "/"));
    struct dirent* de;
    int star_dot_star = (!strcmp(patpart, "*.*"));
    while ((de = readdir(d))) {
        const char* nm = de->d_name;
        if (isRoot && (!strcmp(nm, ".") || !strcmp(nm, ".."))) continue;
        int m = star_dot_star ? 1 : wild_match(patpart, nm);
        if (!m) continue;
        if (cnt == cap) { cap = cap ? cap * 2 : 32; list = (char**)realloc(list, (size_t)cap * sizeof(char*)); }
        list[cnt++] = strdup(nm);
    }
    closedir(d);
    if (!cnt) { free(list); SetLastError(ERROR_FILE_NOT_FOUND); return INVALID_HANDLE_VALUE; }
    qsort(list, (size_t)cnt, sizeof(char*), name_cmp);
    ShxObj* o = shx_obj_new(OBJ_FIND);
    if (!o) { for (int i = 0; i < cnt; i++) free(list[i]); free(list); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
    o->find_list = list; o->find_n = cnt; o->find_i = 0; o->path = strdup(px); o->find_pat = strdup(patpart);
    find_fill(o, (WIN32_FIND_DATAW*)fd);
    HANDLE h = shx_handle_new(o);
    if (!h) return INVALID_HANDLE_VALUE;
    SetLastError(ERROR_SUCCESS);
    return h;
}
HANDLE FindFirstFileW(LPCWSTR pat, WIN32_FIND_DATAW* fd) { return FindFirstFileExW(pat, 0, fd, 0, NULL, 0); }
BOOL FindNextFileW(HANDLE h, WIN32_FIND_DATAW* fd) {
    ShxObj* o = shx_ref(h, OBJ_FIND);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    BOOL r = find_fill(o, fd);
    shx_unref(o);
    return r;
}
BOOL FindClose(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_FIND);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    shx_unref(o);
    return CloseHandle(h);
}

/* ---------------------------------------------------------------
 * FileMapping: マッピング毎の共有バッファ方式 (inventory 制限参照)
 * --------------------------------------------------------------- */
extern HANDLE shx_named_create(int type, ShxObj* fresh, char* name);
extern HANDLE shx_named_open(int type, char* name);

typedef struct MapView { void* ptr; ShxObj* map; size_t len; int used; } MapView;
#define SHX_MAX_VIEWS 256
static MapView g_views[SHX_MAX_VIEWS];

static void map_writeback(ShxObj* m) {
    if (m->map_fd >= 0 && (m->map_prot & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE)) && m->map_base) {
        ssize_t r = pwrite(m->map_fd, m->map_base, m->map_size, 0);
        (void)r;
    }
}
void shx_map_destroy(ShxObj* o) {
    map_writeback(o);
    if (o->map_fd >= 0) close(o->map_fd);
    free(o->map_base);
}

static HANDLE create_mapping(HANDLE file, DWORD prot, DWORD hi, DWORD lo, char* name) {
    shx_ensure_init();
    uint64_t size = ((uint64_t)hi << 32) | lo;
    ShxObj* o = shx_obj_new(OBJ_MAPPING);
    if (!o) { free(name); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    o->map_prot = prot;
    if (file == INVALID_HANDLE_VALUE || file == 0) {
        if (!size) { shx_unref(o); free(name); SetLastError(ERROR_INVALID_PARAMETER); return 0; }
        o->map_anon = 1; o->map_size = (size_t)size;
        o->map_base = calloc(1, o->map_size);
        if (!o->map_base) { shx_unref(o); free(name); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    } else {
        ShxObj* f = file_ref(file);
        if (!f) { shx_unref(o); free(name); return 0; }
        struct stat st;
        if (fstat(f->fd, &st) != 0) { shx_unref(f); shx_unref(o); free(name); SetLastError(ERROR_INVALID_HANDLE); return 0; }
        if (!size) size = (uint64_t)st.st_size;
        if (!size) { shx_unref(f); shx_unref(o); free(name); SetLastError(ERROR_FILE_INVALID); return 0; }
        o->map_fd = dup(f->fd);
        shx_unref(f);
        o->map_size = (size_t)size;
        if ((uint64_t)st.st_size < size && (prot & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE))) ftruncate(o->map_fd, (off_t)size);
        o->map_base = calloc(1, o->map_size);
        if (!o->map_base) { shx_unref(o); free(name); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
        ssize_t r = pread(o->map_fd, o->map_base, o->map_size, 0);
        (void)r;
    }
    return shx_named_create(OBJ_MAPPING, o, name);
}
HANDLE CreateFileMappingW(HANDLE file, LPSECURITY_ATTRIBUTES sa, DWORD prot, DWORD hi, DWORD lo, LPCWSTR name) {
    (void)sa; return create_mapping(file, prot, hi, lo, shx_wname(name));
}
HANDLE CreateFileMappingA(HANDLE file, LPSECURITY_ATTRIBUTES sa, DWORD prot, DWORD hi, DWORD lo, LPCSTR name) {
    (void)sa; return create_mapping(file, prot, hi, lo, shx_aname(name));
}
HANDLE OpenFileMappingW(DWORD access, BOOL inherit, LPCWSTR name) {
    (void)access; (void)inherit; return shx_named_open(OBJ_MAPPING, shx_wname(name));
}
LPVOID MapViewOfFile(HANDLE m, DWORD access, DWORD offHi, DWORD offLo, SIZE_T n) {
    (void)access;
    ShxObj* o = shx_ref(m, OBJ_MAPPING);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return NULL; }
    uint64_t off = ((uint64_t)offHi << 32) | offLo;
    if (off >= o->map_size) { shx_unref(o); SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    size_t len = n ? n : (size_t)(o->map_size - off);
    if (off + len > o->map_size) { shx_unref(o); SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    void* p = (char*)o->map_base + off;
    shx_lock();
    int slot = -1;
    for (int i = 0; i < SHX_MAX_VIEWS; i++) if (!g_views[i].used) { slot = i; break; }
    if (slot >= 0) { g_views[slot].used = 1; g_views[slot].ptr = p; g_views[slot].map = o; g_views[slot].len = len; }
    shx_unlock();
    if (slot < 0) { shx_unref(o); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    SetLastError(ERROR_SUCCESS);
    return p;                      /* o の参照はビューが保持 */
}
BOOL FlushViewOfFile(LPCVOID p, SIZE_T n) {
    (void)n;
    ShxObj* m = NULL;
    shx_lock();
    for (int i = 0; i < SHX_MAX_VIEWS; i++) if (g_views[i].used && g_views[i].ptr == p) { m = g_views[i].map; break; }
    if (m) __atomic_add_fetch(&m->refs, 1, __ATOMIC_SEQ_CST);
    shx_unlock();
    if (!m) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    map_writeback(m);
    shx_unref(m);
    return TRUE;
}
BOOL UnmapViewOfFile(LPCVOID p) {
    ShxObj* m = NULL;
    shx_lock();
    for (int i = 0; i < SHX_MAX_VIEWS; i++) if (g_views[i].used && g_views[i].ptr == p) { m = g_views[i].map; g_views[i].used = 0; break; }
    shx_unlock();
    if (!m) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    map_writeback(m);
    shx_unref(m);
    return TRUE;
}
