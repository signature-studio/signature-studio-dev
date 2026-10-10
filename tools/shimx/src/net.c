/* ネットワーク / 認証系 / MIDI の「常にエラー」スタブ (対象外方針)。
 * - wininet: 接続不可。InternetGetConnectedState=FALSE, Open*=NULL (ERROR_INTERNET_DISCONNECTED)
 * - ws2_32: Windows 固有名のみ。BSD ソケット名 (socket/bind/...) と ntohs 等は Emscripten libc の同名シンボルが
 *   解決する (衝突回避のためここでは定義しない)。WSAStartup は WSASYSNOTREADY を返す。
 * - wintrust/crypt32: 署名検証・証明書は常に「無し」(shimx_set_trust_ok(1) で WinVerifyTrust のみ成功にできる)
 * - mpr: ネットワークリソース無し
 * - winmm MIDI: デバイス 0 台 (weak: Web MIDI 連携側が強定義で上書き可)
 */
#include "shimx_internal.h"

static int g_trust_ok;
void shimx_set_trust_ok(int on) { g_trust_ok = on; }

/* ---- wininet ---- */
static void net_err(void) { SetLastError(ERROR_INTERNET_CANNOT_CONNECT); }
LPVOID InternetOpenW(LPCWSTR agent, DWORD access, LPCWSTR proxy, LPCWSTR bypass, DWORD flags) {
    (void)agent; (void)access; (void)proxy; (void)bypass; (void)flags;
    SetLastError(ERROR_INTERNET_DISCONNECTED); return NULL;
}
BOOL InternetGetConnectedState(LPDWORD flags, DWORD rsv) { (void)rsv; if (flags) *flags = 0; return FALSE; }
BOOL InternetCloseHandle(LPVOID h) { (void)h; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
LPVOID InternetConnectW(LPVOID h, LPCWSTR s, WORD port, LPCWSTR u, LPCWSTR p, DWORD svc, DWORD fl, ULONG_PTR c) {
    (void)h; (void)s; (void)port; (void)u; (void)p; (void)svc; (void)fl; (void)c; net_err(); return NULL;
}
LPVOID InternetOpenUrlW(LPVOID h, LPCWSTR url, LPCWSTR hdr, DWORD hl, DWORD fl, ULONG_PTR c) {
    (void)h; (void)url; (void)hdr; (void)hl; (void)fl; (void)c; net_err(); return NULL;
}
BOOL InternetReadFile(LPVOID h, LPVOID b, DWORD n, LPDWORD r) { (void)h; (void)b; (void)n; if (r) *r = 0; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
BOOL InternetWriteFile(LPVOID h, LPCVOID b, DWORD n, LPDWORD w) { (void)h; (void)b; (void)n; if (w) *w = 0; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
BOOL InternetSetOptionW(LPVOID h, DWORD o, LPVOID b, DWORD n) { (void)h; (void)o; (void)b; (void)n; return TRUE; }
BOOL InternetGetLastResponseInfoW(LPDWORD e, LPWSTR b, LPDWORD n) { if (e) *e = 0; if (n) *n = 0; if (b) b[0] = 0; return TRUE; }
LPVOID HttpOpenRequestW(LPVOID h, LPCWSTR v, LPCWSTR o, LPCWSTR ver, LPCWSTR r, LPCWSTR* a, DWORD fl, ULONG_PTR c) {
    (void)h; (void)v; (void)o; (void)ver; (void)r; (void)a; (void)fl; (void)c; net_err(); return NULL;
}
BOOL HttpSendRequestExW(LPVOID h, LPVOID in, LPVOID out, DWORD fl, ULONG_PTR c) { (void)h; (void)in; (void)out; (void)fl; (void)c; net_err(); return FALSE; }
BOOL HttpEndRequestW(LPVOID h, LPVOID out, DWORD fl, ULONG_PTR c) { (void)h; (void)out; (void)fl; (void)c; net_err(); return FALSE; }
BOOL HttpAddRequestHeadersW(LPVOID h, LPCWSTR hdr, DWORD n, DWORD mod) { (void)h; (void)hdr; (void)n; (void)mod; net_err(); return FALSE; }
BOOL HttpQueryInfoW(LPVOID h, DWORD lvl, LPVOID b, LPDWORD n, LPDWORD i) { (void)h; (void)lvl; (void)b; (void)n; (void)i; net_err(); return FALSE; }
BOOL HttpQueryInfoA(LPVOID h, DWORD lvl, LPVOID b, LPDWORD n, LPDWORD i) { (void)h; (void)lvl; (void)b; (void)n; (void)i; net_err(); return FALSE; }
LPVOID InternetOpenA(LPCSTR agent, DWORD access, LPCSTR proxy, LPCSTR bypass, DWORD flags) {
    (void)agent; (void)access; (void)proxy; (void)bypass; (void)flags; SetLastError(ERROR_INTERNET_DISCONNECTED); return NULL;
}
LPVOID InternetOpenUrlA(LPVOID h, LPCSTR url, LPCSTR hdr, DWORD hl, DWORD fl, ULONG_PTR c) {
    (void)h; (void)url; (void)hdr; (void)hl; (void)fl; (void)c; net_err(); return NULL;
}
LPVOID InternetSetStatusCallbackW(LPVOID h, LPVOID cb) { (void)h; (void)cb; return NULL; }

/* ---- ws2_32 (Windows 固有名のみ) ---- */
int WSAStartup(WORD ver, LPVOID data) {
    (void)ver;
    if (data) memset(data, 0, 8);
    return 10091;   /* WSASYSNOTREADY: ネットワーク不可 */
}
int WSACleanup(void) { return 0; }
int WSAGetLastError(void) { return (int)GetLastError(); }
void WSASetLastError(int e) { SetLastError((DWORD)e); }
int closesocket(uintptr_t s) { (void)s; SetLastError(10038 /* WSAENOTSOCK */); return -1; }
int ioctlsocket(uintptr_t s, LONG cmd, DWORD* arg) { (void)s; (void)cmd; (void)arg; SetLastError(10038); return -1; }
int WSAPoll(LPVOID fds, ULONG n, int timeout) { (void)fds; (void)n; (void)timeout; SetLastError(10050 /* WSAENETDOWN */); return -1; }
uintptr_t WSASocketW(int af, int type, int proto, LPVOID info, DWORD g, DWORD fl) {
    (void)af; (void)type; (void)proto; (void)info; (void)g; (void)fl; SetLastError(10050); return (uintptr_t)-1;
}

/* ---- mpr ---- */
DWORD WNetOpenEnumW(DWORD scope, DWORD type, DWORD usage, LPVOID res, LPHANDLE h) {
    (void)scope; (void)type; (void)usage; (void)res; if (h) *h = 0; return ERROR_NO_NETWORK;
}
DWORD WNetEnumResourceW(HANDLE h, LPDWORD c, LPVOID b, LPDWORD n) { (void)h; (void)b; (void)n; if (c) *c = 0; return ERROR_NO_NETWORK; }
DWORD WNetCloseEnum(HANDLE h) { (void)h; return ERROR_SUCCESS; }
DWORD WNetGetUniversalNameW(LPCWSTR local, DWORD lvl, LPVOID b, LPDWORD n) { (void)local; (void)lvl; (void)b; (void)n; return 2250; /* ERROR_NOT_CONNECTED */ }

/* ---- wintrust / crypt32 ---- */
LONG WinVerifyTrust(HWND w, GUID* action, LPVOID data) { (void)w; (void)action; (void)data; return g_trust_ok ? 0 : (LONG)TRUST_E_NOSIGNATURE; }
BOOL CertCloseStore(LPVOID store, DWORD flags) { (void)store; (void)flags; return TRUE; }
LPVOID CertFindCertificateInStore(LPVOID store, DWORD enc, DWORD flags, DWORD type, const void* para, LPVOID prev) {
    (void)store; (void)enc; (void)flags; (void)type; (void)para; (void)prev; SetLastError(0x80092004u); return NULL;   /* CRYPT_E_NOT_FOUND */
}
BOOL CertFreeCertificateContext(LPVOID c) { (void)c; return TRUE; }
DWORD CertGetNameStringW(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPWSTR out, DWORD n) { (void)c; (void)type; (void)flags; (void)tp; if (out && n) out[0] = 0; return 1; }
DWORD CertGetNameStringA(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPSTR out, DWORD n) { (void)c; (void)type; (void)flags; (void)tp; if (out && n) out[0] = 0; return 1; }
BOOL CryptMsgClose(LPVOID m) { (void)m; return TRUE; }
BOOL CryptMsgGetParam(LPVOID m, DWORD type, DWORD idx, LPVOID d, LPDWORD n) { (void)m; (void)type; (void)idx; (void)d; (void)n; SetLastError(0x80092009u); return FALSE; }
BOOL CryptQueryObject(DWORD t, const void* o, DWORD ex, DWORD ef, DWORD fl, LPDWORD enc, LPDWORD ct, LPDWORD ft, LPVOID* st, LPVOID* msg, const void** ctx) {
    (void)t; (void)o; (void)ex; (void)ef; (void)fl; (void)enc; (void)ct; (void)ft; (void)st; (void)msg; (void)ctx; SetLastError(0x80092009u /* CRYPT_E_NO_MATCH */); return FALSE;
}
BOOL CryptDecodeObject(DWORD enc, LPCSTR type, const BYTE* b, DWORD n, DWORD fl, LPVOID out, LPDWORD cb) {
    (void)enc; (void)type; (void)b; (void)n; (void)fl; (void)out; (void)cb; SetLastError(0x80092002u /* CRYPT_E_BAD_ENCODE */); return FALSE;
}

/* ---- winmm MIDI: デバイス 0 台 (weak) ---- */
#define MMSYSERR_BADDEVICEID 2u
#define MMSYSERR_INVALHANDLE 5u
SHIMX_WEAK UINT midiInGetNumDevs(void) { return 0; }
SHIMX_WEAK UINT midiOutGetNumDevs(void) { return 0; }
SHIMX_WEAK UINT midiInGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n) { (void)id; (void)caps; (void)n; return MMSYSERR_BADDEVICEID; }
SHIMX_WEAK UINT midiOutGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n) { (void)id; (void)caps; (void)n; return MMSYSERR_BADDEVICEID; }
SHIMX_WEAK UINT midiInOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags) { (void)id; (void)cb; (void)inst; (void)flags; if (h) *h = 0; return MMSYSERR_BADDEVICEID; }
SHIMX_WEAK UINT midiOutOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags) { (void)id; (void)cb; (void)inst; (void)flags; if (h) *h = 0; return MMSYSERR_BADDEVICEID; }
SHIMX_WEAK UINT midiInClose(HANDLE h) { (void)h; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutClose(HANDLE h) { (void)h; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInStart(HANDLE h) { (void)h; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInStop(HANDLE h) { (void)h; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInReset(HANDLE h) { (void)h; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInAddBuffer(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInPrepareHeader(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInUnprepareHeader(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutPrepareHeader(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutUnprepareHeader(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutShortMsg(uint64_t h, DWORD msg) { (void)h; (void)msg; return MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutLongMsg(HANDLE h, LPVOID hdr, UINT n) { (void)h; (void)hdr; (void)n; return MMSYSERR_INVALHANDLE; }
static UINT mm_errtext(UINT err, LPWSTR buf, UINT n) {
    const char* t = err == MMSYSERR_BADDEVICEID ? "The specified device ID is out of range." :
                    err == MMSYSERR_INVALHANDLE ? "The specified device handle is invalid." : "MIDI error.";
    if (!buf || !n) return 11;
    UINT i = 0;
    for (; t[i] && i + 1 < n; i++) buf[i] = (WCHAR)t[i];
    buf[i] = 0;
    return 0;
}
SHIMX_WEAK UINT midiInGetErrorTextW(UINT err, LPWSTR buf, UINT n) { return mm_errtext(err, buf, n); }
SHIMX_WEAK UINT midiOutGetErrorTextW(UINT err, LPWSTR buf, UINT n) { return mm_errtext(err, buf, n); }
