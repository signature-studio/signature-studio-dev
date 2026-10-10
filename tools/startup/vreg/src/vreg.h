/* vreg 公開ヘッダ: shimx.h に無い追加面 = probe.c (テスト専用ヘルパ) のみ。 */
#ifndef VREG_H
#define VREG_H
#include "shimx.h"

/* 運用フック (vreg_generation 等) と advapi32 追加 6 API は shimx.h に宣言済み (正本は shimx/src/reg.c, CAB-214)。 */

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
