/* gui_ft.h — FreeType ベースのテキストエンジン (GUI-9 #186)。gui_ft.c を shim にリンクし gui_set_text_engine(gui_ft_engine()) で有効化。
 * 未登録なら gui_gdi.c は内蔵 8x8 フォントへフォールバックする (既存 e2e の挙動)。
 * 方針 (#186 PM 判断): Windows 標準フォントは同梱しない。face 名 -> OSS フォントの alias 表で吸収し、表示差は許容。 */
#ifndef GUI_FT_H
#define GUI_FT_H
#include <stddef.h>
#include <stdint.h>
#include "gui_internal.h"

/* face 登録 (ASCII 名・大小無視)。data は呼出側が寿命を保証。戻り値 = index (<0 失敗)。最初に登録した face が未解決名の既定 */
int gui_ft_register_face(const char *name, const uint8_t *data, size_t size);
/* 遅延取得 (VFS #22 想定): 最初に open された時点で load を呼ぶ。成功で 1 (data/size を設定)。失敗した face は 8x8 へフォールバック */
typedef int (*GuiFtLoader)(const char *name, const uint8_t **data, size_t *size, void *user);
int gui_ft_register_lazy(const char *name, GuiFtLoader load, void *user);
/* Windows の face 名 (Segoe UI / Tahoma 等) -> 登録済み face の代替。0 = ok */
int gui_ft_alias(const char *alias, const char *target);
void gui_ft_reset(void);   /* テスト用: 登録を全消去 */
const GuiTextEngine *gui_ft_engine(void);

#endif
