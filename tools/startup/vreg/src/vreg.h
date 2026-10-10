/* vreg 公開ヘッダ: shimx.h に無い追加面 (tools/startup/vreg/src/reg.c が定義)。 */
#ifndef VREG_H
#define VREG_H
#include "shimx.h"

/* ---- 運用フック ---- */
uint32_t vreg_generation(void);                          /* 変更世代 (値/キーの作成・削除・更新で増加) */
void     vreg_set_notify(void (*cb)(uint32_t gen));      /* 変更通知 (Reg* を呼んだスレッドで、内部ロック解放後に同期呼出) */
char*    vreg_export_root(int root);                     /* 0=HKCR 1=HKCU 2=HKLM 3=HKU 4=HKCC を .reg 形式 (UTF-8, LF) で。free() すること */
void     vreg_clear_root(int root);                      /* 指定ルート配下を空にする (seed 再投入前に使用) */
void     vreg_clear_all(void);                           /* 全ルートを空にする (shimx 内蔵 seed も消す) */

/* ---- advapi32 追加 API (shimx.h 未宣言分) ---- */
LSTATUS RegGetValueA(HKEY k, LPCSTR sub, LPCSTR name, DWORD flags, LPDWORD type, PVOID data, LPDWORD cb);
LSTATUS RegEnumKeyW(HKEY k, DWORD idx, LPWSTR name, DWORD cch);
LSTATUS RegDeleteTreeW(HKEY k, LPCWSTR sub);
LSTATUS RegSetKeyValueW(HKEY k, LPCWSTR sub, LPCWSTR name, DWORD type, LPCVOID data, DWORD cb);
LSTATUS RegDeleteKeyValueW(HKEY k, LPCWSTR sub, LPCWSTR name);
LSTATUS RegQueryInfoKeyA(HKEY k, LPSTR cls, LPDWORD cchCls, LPDWORD rsv, LPDWORD nSub, LPDWORD maxSub, LPDWORD maxCls,
                         LPDWORD nVal, LPDWORD maxValName, LPDWORD maxValData, LPDWORD secDesc, FILETIME* lw);

/* ---- probe.c (テスト/e2e 専用): FL(Delphi TRegistry) と同じ呼出パターンで叩く UTF-8 ヘルパ。戻り値は Win32 エラー(0=成功) ---- */
int  vreg_probe_key_exists(const char* hive, const char* key);
int  vreg_probe_value_exists(const char* hive, const char* key, const char* name);
int  vreg_probe_read_str(const char* hive, const char* key, const char* name, char* out, int cap, unsigned* type_out);
long vreg_probe_read_int(const char* hive, const char* key, const char* name, long def);
int  vreg_probe_read_bool(const char* hive, const char* key, const char* name, int def);
int  vreg_probe_write_str(const char* hive, const char* key, const char* name, const char* val);
int  vreg_probe_write_int(const char* hive, const char* key, const char* name, long v);
int  vreg_probe_write_dword(const char* hive, const char* key, const char* name, unsigned v);
int  vreg_probe_delete_value(const char* hive, const char* key, const char* name);
int  vreg_probe_create_key(const char* hive, const char* key);
int  vreg_probe_delete_key(const char* hive, const char* key);
int  vreg_probe_enum(const char* hive, const char* key, int kind, char* out, int cap);
#endif
