/* trap_harness.c: lift 済み fle_lifted.c の間接 dispatch (ott_dispatch) に VA を 1 つ渡す。
   x87 trap stub なら ott_unsup が abort する (終了 status != 0 + stderr に "trap stub")。 */
#include "fle_cpu.h"
#include <stdlib.h>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    ott_dispatch(strtoull(argv[1], 0, 16));
    return 0;
}
