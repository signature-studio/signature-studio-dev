/* side_compat.h (side_build.sh の -include): SIDE_MODULE は main の stderr の global を GOT で受けられないため、
 * 診断出力の stderr を side_host.c の side_stderr() (main 側の関数) に置き換える。 */
#include <stdio.h>
FILE *side_stderr(void);
#define stderr (side_stderr())
