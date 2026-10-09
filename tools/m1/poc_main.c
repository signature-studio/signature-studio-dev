/* M1 極小 PoC プログラム (ELF と x86_64 PE の両方に同一ソースをコンパイルする)。
 * toolchain_setup.md E2E-1/E2E-2 の実績プログラムと同じもの。 */
#include <stdio.h>
int main(void) { printf("hello from e2e, answer=%d\n", 42); return 0; }
