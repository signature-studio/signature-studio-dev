/* gui_lift_main.c — lifted PE の起動グルー (関数 VA 表を登録して PE entry を呼ぶ) */
#include <stdint.h>
#include "gui_api.h"
extern const GuiFnMap gui_lift_fnmap[];
extern const int gui_lift_fnmap_n;
extern int64_t gui_lift_entry(void);
int main(void) {
  gui_register_fnmap(gui_lift_fnmap, gui_lift_fnmap_n);
  gui_lift_entry();
  return 0;
}
