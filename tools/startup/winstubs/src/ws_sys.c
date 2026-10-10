/* G16: OS バージョン (RtlGetVersion)。既知フォルダ / 一時パスの username は shimx 側が webstudio に統一済み (CAB-214) のため wrap 不要。 */
#include "ws_internal.h"

/* ---- RtlGetVersion (ntdll): RTL_OSVERSIONINFOW(276B) / EXW(284B) ---- */
LONG RtlGetVersion(void* vi) {
    uint32_t sz = vi ? *(uint32_t*)vi : 0;
    if (sz != 276 && sz != 284) return (LONG)0xC000000D;           /* STATUS_INVALID_PARAMETER */
    return GetVersionExW((OSVERSIONINFOEXW*)vi) ? 0 : (LONG)0xC000000D;   /* STATUS_SUCCESS */
}
