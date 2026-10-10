/* 自動生成: scripts/gen_stub_protos.py — 手編集禁止 (shimx.h 未宣言の公開関数の prototype) */
#ifndef SHIMX_STUBS_H
#define SHIMX_STUBS_H
#ifdef __cplusplus
extern "C" {
#endif
BOOL CertCloseStore(LPVOID store, DWORD flags);
LPVOID CertFindCertificateInStore(LPVOID store, DWORD enc, DWORD flags, DWORD type, const void* para, LPVOID prev);
BOOL CertFreeCertificateContext(LPVOID c);
DWORD CertGetNameStringA(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPSTR out, DWORD n);
DWORD CertGetNameStringW(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPWSTR out, DWORD n);
BOOL ClosePrinter(HANDLE h);
BOOL CryptDecodeObject(DWORD enc, LPCSTR type, const BYTE* b, DWORD n, DWORD fl, LPVOID out, LPDWORD cb);
BOOL CryptMsgClose(LPVOID m);
BOOL CryptMsgGetParam(LPVOID m, DWORD type, DWORD idx, LPVOID d, LPDWORD n);
BOOL CryptQueryObject(DWORD t, const void* o, DWORD ex, DWORD ef, DWORD fl, LPDWORD enc, LPDWORD ct, LPDWORD ft, LPVOID* st, LPVOID* msg, const void** ctx);
LONG DocumentPropertiesW(HWND w, HANDLE h, LPWSTR dev, LPVOID out, LPVOID in, DWORD mode);
BOOL EnumPrintersW(DWORD flags, LPWSTR name, DWORD level, LPBYTE buf, DWORD n, LPDWORD needed, LPDWORD returned);
BOOL GetDefaultPrinterW(LPWSTR buf, LPDWORD n);
LPVOID InternetOpenA(LPCSTR agent, DWORD access, LPCSTR proxy, LPCSTR bypass, DWORD flags);
LPVOID InternetOpenUrlA(LPVOID h, LPCSTR url, LPCSTR hdr, DWORD hl, DWORD fl, ULONG_PTR c);
LPVOID InternetSetStatusCallbackW(LPVOID h, LPVOID cb);
BOOL OpenPrinterW(LPWSTR name, LPHANDLE h, LPVOID def);
BOOL PropVariantToBooleanWithDefault(const void* pv, BOOL def);
HRESULT PropVariantToFileTime(const void* pv, int type, FILETIME* ft);
const WCHAR* PropVariantToStringWithDefault(const void* pv, const WCHAR* def);
HRESULT PropVariantToVariant(const void* pv, void* v);
HRESULT VariantToPropVariant(const void* v, void* pv);
int WSACleanup(void);
int WSAGetLastError(void);
int WSAPoll(LPVOID fds, ULONG n, int timeout);
void WSASetLastError(int e);
uintptr_t WSASocketW(int af, int type, int proto, LPVOID info, DWORD g, DWORD fl);
int WSAStartup(WORD ver, LPVOID data);
BOOL WTSRegisterSessionNotification(HWND w, DWORD flags);
BOOL WTSUnRegisterSessionNotification(HWND w);
UINT acmDriverClose(HANDLE h, DWORD flags);
UINT acmDriverDetailsA(HANDLE h, LPVOID d, DWORD flags);
UINT acmDriverEnum(LPVOID cb, ULONG_PTR dw, DWORD flags);
UINT acmDriverOpen(LPHANDLE h, HANDLE id, DWORD flags);
UINT acmFormatChooseW(LPVOID p);
UINT acmFormatSuggest(HANDLE h, LPVOID src, LPVOID dst, DWORD n, DWORD flags);
UINT acmMetrics(uint64_t h, UINT metric, LPVOID out);
UINT acmStreamClose(HANDLE h, DWORD flags);
UINT acmStreamConvert(HANDLE h, LPVOID hdr, DWORD flags);
UINT acmStreamMessage(HANDLE h, UINT msg, ULONG_PTR a, ULONG_PTR b);
UINT acmStreamOpen(LPHANDLE h, HANDLE drv, LPVOID src, LPVOID dst, LPVOID flt, ULONG_PTR cb, ULONG_PTR inst, DWORD flags);
UINT acmStreamPrepareHeader(HANDLE h, LPVOID hdr, DWORD flags);
UINT acmStreamSize(HANDLE h, DWORD n, LPDWORD out, DWORD flags);
UINT acmStreamUnprepareHeader(HANDLE h, LPVOID hdr, DWORD flags);
int closesocket(uintptr_t s);
int ioctlsocket(uintptr_t s, LONG cmd, DWORD* arg);
UINT midiInAddBuffer(HANDLE h, LPVOID hdr, UINT n);
UINT midiInClose(HANDLE h);
UINT midiInGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n);
UINT midiInGetErrorTextW(UINT err, LPWSTR buf, UINT n);
UINT midiInGetNumDevs(void);
UINT midiInOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags);
UINT midiInPrepareHeader(HANDLE h, LPVOID hdr, UINT n);
UINT midiInReset(HANDLE h);
UINT midiInStart(HANDLE h);
UINT midiInStop(HANDLE h);
UINT midiInUnprepareHeader(HANDLE h, LPVOID hdr, UINT n);
UINT midiOutClose(HANDLE h);
UINT midiOutGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n);
UINT midiOutGetErrorTextW(UINT err, LPWSTR buf, UINT n);
UINT midiOutGetNumDevs(void);
UINT midiOutLongMsg(HANDLE h, LPVOID hdr, UINT n);
UINT midiOutOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags);
UINT midiOutPrepareHeader(HANDLE h, LPVOID hdr, UINT n);
UINT midiOutShortMsg(uint64_t h, DWORD msg);
UINT midiOutUnprepareHeader(HANDLE h, LPVOID hdr, UINT n);
#ifdef __cplusplus
}
#endif
#endif
