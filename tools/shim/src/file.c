/* file 相当 (§3 #2 の P0 最小面): CreateFileW → Emscripten FS (open) への写影。
 * - パスは Win32 Unicode → UTF-8 変換して FS ルート (/) 基準で open する。
 *   ワークスペースは /flp 等を想定 (テストでも MEMFS 上で検証)。
 * - セキュリティ属性 / share mode / FLAGS_AND_ATTRIBUTES は無視 (単一プロセス内)。
 * - OVERLAPPED (非同期 I/O) は v1 非対応。同期 I/O のみ。
 */
#include "shim.h"
#include "shim_internal.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

/* ---------------------------------------------------------------
 * HANDLE テーブル (thread/event/file 共通)
 * --------------------------------------------------------------- */
ShimSlot g_slots[SHIM_MAX_HANDLES];

/* HANDLE ↔ slot 変換 (HANDLE 値 = index+1, 0 は無効) */
static ShimSlot* slot_from_handle(HANDLE h) {
    size_t idx = (size_t)h;
    if (idx == 0 || idx > SHIM_MAX_HANDLES) return NULL;
    ShimSlot* s = &g_slots[idx - 1];
    if (!s->used) return NULL;
    return s;
}

ShimSlot* shim_alloc_slot(int type) {
    for (int i = 0; i < SHIM_MAX_HANDLES; i++) {
        if (!g_slots[i].used) {
            ShimSlot* s = &g_slots[i];
            memset(s, 0, sizeof(*s));
            s->used = 1;
            s->type = type;
            return s;
        }
    }
    return NULL;
}

void shim_free_slot(ShimSlot* s) {
    s->used = 0;
    s->type = SHIM_TYPE_NONE;
}

ShimSlot* shim_slot_lookup(HANDLE h) {
    return slot_from_handle(h);
}

HANDLE shim_handle_from_slot(ShimSlot* s) {
    return (HANDLE)(1 + (size_t)(s - g_slots));
}

/* ---------------------------------------------------------------
 * UTF-16 → UTF-8 変換 (パス用)。変換後バイト数を返す (-1=エラー)
 * --------------------------------------------------------------- */
static int wchar_path_to_utf8(LPCWSTR w, char* out, size_t outSize) {
    size_t n = 0;
    if (!w) return -1;
    while (*w) {
        uint32_t cp = *w++;
        if (cp >= 0xD800u && cp <= 0xDBFFu) { /* surrogate pair */
            uint16_t lo = *w;
            if (lo < 0xDC00u || lo > 0xDFFFu) return -1;
            w++;
            cp = 0x10000u + ((cp - 0xD800u) << 10) + (lo - 0xDC00u);
        }
        if (cp < 0x80u) {
            if (n + 1 >= outSize) return -1;
            out[n++] = (char)cp;
        } else if (cp < 0x800u) {
            if (n + 2 >= outSize) return -1;
            out[n++] = (char)(0xC0u | (cp >> 6));
            out[n++] = (char)(0x80u | (cp & 0x3Fu));
        } else if (cp < 0x10000u) {
            if (n + 3 >= outSize) return -1;
            out[n++] = (char)(0xE0u | (cp >> 12));
            out[n++] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
            out[n++] = (char)(0x80u | (cp & 0x3Fu));
        } else {
            if (n + 4 >= outSize) return -1;
            out[n++] = (char)(0xF0u | (cp >> 18));
            out[n++] = (char)(0x80u | ((cp >> 12) & 0x3Fu));
            out[n++] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
            out[n++] = (char)(0x80u | (cp & 0x3Fu));
        }
    }
    if (n >= outSize) return -1;
    out[n] = '\0';
    return (int)n;
}

/* ---------------------------------------------------------------
 * open 系トレース (WIN-13 #2905・wasm のみ)。CreateFileW の 1 呼出し = printErr の 1 行
 * "SHIMOPEN {json}"。caller は JS スタックの最初の function_<VA> (lift 関数名)。native では何もしない。
 * --------------------------------------------------------------- */
#ifdef __EMSCRIPTEN__
EM_JS(void, shim_open_trace_js, (const char* fields), {
  var caller = '', frames = [];
  var st = (new Error().stack || '').split('\n');
  for (var i = 1; i < st.length; i++) {
    var name = st[i].replace(/^[ ]*at[ ]+/, '').split(' ')[0];
    if (!name || name === 'Error') continue;
    if (frames.length < 8) frames.push(name);
    if (!caller && /^function_[0-9a-fA-F]+$/.test(name)) caller = name;
  }
  err('SHIMOPEN ' + UTF8ToString(fields) + ',"caller":"' + caller + '","frames":' + JSON.stringify(frames) + '}');
});
static void open_trace(LPCWSTR fileName, DWORD access, DWORD disp, HANDLE h) {
    char path[1024], esc[2400], buf[2800];
    size_t n = 0;
    if (wchar_path_to_utf8(fileName, path, sizeof(path)) < 0) return;
    for (const char* p = path; *p && n + 2 < sizeof(esc); p++) {
        if (*p == '"' || *p == '\\') esc[n++] = '\\';
        esc[n++] = *p;
    }
    esc[n] = '\0';
    int ok = (h != INVALID_HANDLE_VALUE);
    int wr = (access & GENERIC_WRITE) != 0 || disp == CREATE_NEW || disp == CREATE_ALWAYS
          || disp == OPEN_ALWAYS || disp == TRUNCATE_EXISTING;
    snprintf(buf, sizeof(buf), "{\"op\":\"open\",\"path\":\"%s\",\"ok\":%s,\"w\":%s,\"err\":%u,\"access\":\"0x%08x\",\"disp\":%u",
             esc, ok ? "true" : "false", wr ? "true" : "false", (unsigned)(ok ? 0 : GetLastError()),
             (unsigned)access, (unsigned)disp);
    shim_open_trace_js(buf);
}
#endif

/* ---------------------------------------------------------------
 * CreateFileW → open()
 * --------------------------------------------------------------- */
static HANDLE create_file_w(LPCWSTR fileName, DWORD desiredAccess, DWORD shareMode,
                            LPSECURITY_ATTRIBUTES sa, DWORD creationDisposition,
                            DWORD flagsAndAttributes, HANDLE hTemplateFile) {
    (void)sa; (void)shareMode; (void)flagsAndAttributes; (void)hTemplateFile;
    char path[1024];
    if (!fileName || wchar_path_to_utf8(fileName, path, sizeof(path)) < 0) {
        SetLastError(ERROR_INVALID_PARAMETER);
        return INVALID_HANDLE_VALUE;
    }

    int oflags = 0;
    DWORD rd = (desiredAccess & GENERIC_READ) != 0;
    DWORD wr = (desiredAccess & GENERIC_WRITE) != 0;
    if (rd && wr)      oflags |= O_RDWR;
    else if (rd)       oflags |= O_RDONLY;
    else if (wr)       oflags |= O_WRONLY;
    else { SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE; }

    switch (creationDisposition) {
        case CREATE_NEW:        oflags |= O_CREAT | O_EXCL;  break;
        case CREATE_ALWAYS:     oflags |= O_CREAT | O_TRUNC; break;
        case OPEN_EXISTING:     oflags |= 0;                 break;
        case OPEN_ALWAYS:       oflags |= O_CREAT;           break;
        case TRUNCATE_EXISTING: oflags |= O_TRUNC;           break;
        default: SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE;
    }

    int fd = open(path, oflags, 0644);
    if (fd < 0) {
        SetLastError(errno == ENOENT ? ERROR_FILE_NOT_FOUND : (DWORD)errno);
        return INVALID_HANDLE_VALUE;
    }
    ShimSlot* s = shim_alloc_slot(SHIM_TYPE_FILE);
    if (!s) { close(fd); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
    s->fd = fd;
    SetLastError(ERROR_SUCCESS);
    return (HANDLE)(1 + (size_t)(s - g_slots));
}

HANDLE CreateFileW(LPCWSTR fileName, DWORD desiredAccess, DWORD shareMode,
                   LPSECURITY_ATTRIBUTES sa, DWORD creationDisposition,
                   DWORD flagsAndAttributes, HANDLE hTemplateFile) {
    HANDLE h = create_file_w(fileName, desiredAccess, shareMode, sa, creationDisposition, flagsAndAttributes, hTemplateFile);
#ifdef __EMSCRIPTEN__
    if (fileName) open_trace(fileName, desiredAccess, creationDisposition, h);
#endif
    return h;
}

/* ---------------------------------------------------------------
 * Read/Write / seek / size
 * --------------------------------------------------------------- */
static int fd_of(HANDLE h, ShimSlot** outSlot) {
    ShimSlot* s = slot_from_handle(h);
    if (!s || s->type != SHIM_TYPE_FILE) { SetLastError(ERROR_INVALID_FUNCTION); return -1; }
    if (outSlot) *outSlot = s;
    return s->fd;
}

BOOL ReadFile(HANDLE h, LPVOID buf, DWORD bytesToRead, LPDWORD bytesRead,
              LPOVERLAPPED overlapped) {
    (void)overlapped; /* 同期 I/O 前提 */
    if (bytesRead) *bytesRead = 0;
    int fd = fd_of(h, NULL);
    if (fd < 0) return FALSE;
    ssize_t r = read(fd, buf, (size_t)bytesToRead);
    if (r < 0) { SetLastError((DWORD)errno); return FALSE; }
    if (bytesRead) *bytesRead = (DWORD)r;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

BOOL WriteFile(HANDLE h, LPCVOID buf, DWORD bytesToWrite, LPDWORD bytesWritten,
               LPOVERLAPPED overlapped) {
    (void)overlapped;
    if (bytesWritten) *bytesWritten = 0;
    int fd = fd_of(h, NULL);
    if (fd < 0) return FALSE;
    ssize_t r = write(fd, buf, (size_t)bytesToWrite);
    if (r < 0) { SetLastError((DWORD)errno); return FALSE; }
    if (bytesWritten) *bytesWritten = (DWORD)r;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

/* 共通: 64bit seek。失敗時 -1 */
static int64_t seek64(HANDLE h, int64_t dist, DWORD method) {
    int fd = fd_of(h, NULL);
    if (fd < 0) return -1;
    int whence;
    switch (method) {
        case FILE_BEGIN:   whence = SEEK_SET; break;
        case FILE_CURRENT: whence = SEEK_CUR; break;
        case FILE_END:     whence = SEEK_END; break;
        default: SetLastError(ERROR_INVALID_PARAMETER); return -1;
    }
    off_t r = lseek(fd, (off_t)dist, whence);
    if (r < 0) {
        SetLastError(errno == EINVAL ? ERROR_NEGATIVE_SEEK : (DWORD)errno);
        return -1;
    }
    SetLastError(ERROR_SUCCESS);
    return (int64_t)r;
}

DWORD SetFilePointer(HANDLE h, LONG distanceLow, PLONG distanceHigh, DWORD method) {
    int64_t dist = (int64_t)distanceLow;
    if (distanceHigh) dist |= ((int64_t)*distanceHigh) << 32;
    int64_t r = seek64(h, dist, method);
    if (r < 0) return INVALID_SET_FILE_POINTER; /* SetLastError 済み */
    if (distanceHigh) *distanceHigh = (LONG)((uint64_t)r >> 32);
    SetLastError(ERROR_SUCCESS);
    return (DWORD)(uint32_t)(uint64_t)r; /* 下位 32bit (x64 慣例) */
}

BOOL SetFilePointerEx(HANDLE h, LARGE_INTEGER distance,
                      PLARGE_INTEGER newPos, DWORD method) {
    int64_t r = seek64(h, distance.QuadPart, method);
    if (r < 0) return FALSE;
    if (newPos) newPos->QuadPart = r;
    return TRUE;
}

BOOL SetEndOfFile(HANDLE h) {
    int fd = fd_of(h, NULL);
    if (fd < 0) return FALSE;
    off_t cur = lseek(fd, 0, SEEK_CUR);
    if (cur < 0) { SetLastError((DWORD)errno); return FALSE; }
    if (ftruncate(fd, cur) != 0) { SetLastError((DWORD)errno); return FALSE; }
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

static int64_t file_size64(HANDLE h) {
    int fd = fd_of(h, NULL);
    if (fd < 0) return -1;
    struct stat st;
    if (fstat(fd, &st) != 0) { SetLastError((DWORD)errno); return -1; }
    SetLastError(ERROR_SUCCESS);
    return (int64_t)st.st_size;
}

DWORD GetFileSize(HANDLE h, LPDWORD sizeHigh) {
    int64_t r = file_size64(h);
    if (r < 0) return INVALID_SET_FILE_POINTER;
    if (sizeHigh) *sizeHigh = (DWORD)((uint64_t)r >> 32);
    return (DWORD)(uint32_t)(uint64_t)r;
}

BOOL GetFileSizeEx(HANDLE h, PLARGE_INTEGER size) {
    int64_t r = file_size64(h);
    if (r < 0) return FALSE;
    if (size) size->QuadPart = r;
    return TRUE;
}

/* ---------------------------------------------------------------
 * CloseHandle (thread/event/file 共通) と GetLastError/SetLastError
 * --------------------------------------------------------------- */
BOOL CloseHandle(HANDLE h) {
    ShimSlot* s = slot_from_handle(h);
    if (!s) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    switch (s->type) {
        case SHIM_TYPE_FILE:
            close(s->fd);
            shim_free_slot(s);
            break;
        case SHIM_TYPE_EVENT:
            shim_free_slot(s);
            break;
        case SHIM_TYPE_THREAD:
#if defined(__EMSCRIPTEN_PTHREADS__)
            /* Win32 準拠: ハンドルを閉じてもスレッド自体は終了しない。
             * 未 join なら detach して資源を解放する。 */
            if (!s->joined) pthread_detach(s->pt);
#endif
            shim_free_slot(s);
            break;
        default:
            SetLastError(ERROR_INVALID_FUNCTION);
            return FALSE;
    }
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

static DWORD g_last_error = ERROR_SUCCESS;

DWORD GetLastError(void) { return g_last_error; }

void SetLastError(DWORD e) { g_last_error = e; }
