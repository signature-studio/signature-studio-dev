/* scenarios_kh.c — CAB-56 SnapinMasterDsp ハーネス用 scenario 登録 (native_ref_kh バイナリ用)。
 * 既存 scenarios.c に触れないための独立エントリ (scen_khmaster.h は自己完結)。 */
#include "ctxfuzz.h"
#include "scen_khmaster.h"
Scenario SCEN_LIST[] = {
    {"khmrel", trial_khmrel, 12},
    {"khmaster", trial_khmaster, 12},
    {"khmring", trial_khmring, 10},
    {0, 0, 0},
};
