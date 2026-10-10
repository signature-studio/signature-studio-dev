/* winstubs 内部共有 */
#ifndef WS_INTERNAL_H
#define WS_INTERNAL_H

#include "winstubs.h"

extern WsStats g_ws;
extern WsConfig g_ws_cfg;
#define WS_INC(field) __atomic_add_fetch(&g_ws.field, 1u, __ATOMIC_RELAXED)

#ifndef ERROR_CANCELLED
#define ERROR_CANCELLED 1223u
#endif
#define WS_CRYPT_E_NOT_FOUND     0x80092004u
#define WS_CRYPT_E_INVALID_MSG   0x80091004u
#define WS_SEC_E_OK              0

/* ld --wrap の __real_* (= shimx 実装) */
#define WS_REAL(ret, name, args) ret __real_##name args
WS_REAL(LONG, WinVerifyTrust, (HWND, GUID*, LPVOID));
WS_REAL(BOOL, CryptQueryObject, (DWORD, const void*, DWORD, DWORD, DWORD, LPDWORD, LPDWORD, LPDWORD, LPVOID*, LPVOID*, const void**));
WS_REAL(BOOL, CryptMsgGetParam, (LPVOID, DWORD, DWORD, LPVOID, LPDWORD));
WS_REAL(LPVOID, CertFindCertificateInStore, (LPVOID, DWORD, DWORD, DWORD, const void*, LPVOID));
WS_REAL(DWORD, CertGetNameStringW, (LPVOID, DWORD, DWORD, LPVOID, LPWSTR, DWORD));
WS_REAL(DWORD, CertGetNameStringA, (LPVOID, DWORD, DWORD, LPVOID, LPSTR, DWORD));
WS_REAL(HRESULT, SHGetFolderPathW, (HWND, int, HANDLE, DWORD, LPWSTR));
WS_REAL(BOOL, SHGetSpecialFolderPathW, (HWND, LPWSTR, int, BOOL));
WS_REAL(HRESULT, SHGetKnownFolderPath, (const GUID*, DWORD, HANDLE, LPWSTR*));
WS_REAL(DWORD, GetTempPathW, (DWORD, LPWSTR));
WS_REAL(BOOL, CreateProcessW, (LPCWSTR, LPWSTR, LPVOID, LPVOID, BOOL, DWORD, LPVOID, LPCWSTR, LPVOID, void*));
WS_REAL(BOOL, ShellExecuteExW, (void*));
WS_REAL(BOOL, ShellExecuteExA, (void*));
WS_REAL(HMODULE, LoadLibraryW, (LPCWSTR));
WS_REAL(HMODULE, LoadLibraryA, (LPCSTR));
WS_REAL(HMODULE, LoadLibraryExW, (LPCWSTR, HANDLE, DWORD));

void ws_register_procs(void);                 /* ws_ui.c / ws_sys.c の新規 API を GetProcAddress に登録 */
int  ws_shell_hook(const char* verb, const char* file, const char* params);

#endif
