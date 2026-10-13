#!/usr/bin/env bash
# m11_simd2.py の rep_stosb_memset を実行で検証する (#538)。
#   bash tools/plugins/lift/passes/test_rep_stosb.sh [<m11_simd2.py>]   既定は同ディレクトリの m11_simd2.py
# declare だけの .ll から helper C を生成 → emcc → node で実行し、memset の結果をバイト単位で照合する。
# 1 件でも不一致なら exit 1。 ネガコン: `--negctl` は origin/main の旧 m11_simd2.py (stub) を渡して「FAIL すること」を確認し、
#   FAIL しなければ exit 1 (= 検査が緩い)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
source "$ROOT/tools/shared/env.sh"
: "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
if [ "${1:-}" = "--negctl" ]; then
  OLD="$(mktemp -d "$RUNNER_TEMP/stosb_old.XXXXXX")"
  git -C "$ROOT" show origin/main:tools/plugins/lift/passes/m11_simd2.py > "$OLD/m11_simd2.py" || exit 2
  if bash "$0" "$OLD/m11_simd2.py" > "$OLD/out.log" 2>&1; then
    echo "[test_rep_stosb] negctl FAIL: 旧 stub 版が PASS した (検査が緩い)"; exit 1
  fi
  echo "[test_rep_stosb] negctl OK: 旧 stub 版は FAIL ($(grep -c MISMATCH "$OLD/out.log") 件の不一致)"; exit 0
fi
GEN="${1:-$HERE/m11_simd2.py}"
W="$(mktemp -d "$RUNNER_TEMP/stosb_test.XXXXXX")"
cat > "$W/t.ll" <<'LL'
declare void @__asm_rep_stosb_memset(ptr, i8, i64) local_unnamed_addr
LL
python3 "$GEN" "$W/t.ll" 2> "$W/simd.log" | sed 's#"\.\./msimd11_core\.h"#"msimd11_core.h"#' > "$W/t_simd.c" || { echo "[test_rep_stosb] generator failed"; exit 1; }
cat > "$W/main.c" <<'C'
#include <stdio.h>
#include <string.h>
#include <stdint.h>
extern void __asm_rep_stosb_memset(void*, uint32_t, uint64_t);
static int bad = 0;
static void chk(const char* name, uint32_t b, uint64_t c, size_t off) {
    uint8_t buf[64], ref[64];
    memset(buf, 0x5a, sizeof buf); memset(ref, 0x5a, sizeof ref);
    __asm_rep_stosb_memset(buf + off, b, c);
    memset(ref + off, (int)(b & 0xff), c);   /* rep stosb の意味: AL を c バイト */
    if (memcmp(buf, ref, sizeof buf)) { printf("MISMATCH %s\n", name); bad++; }
    else printf("ok %s\n", name);
}
int main(void) {
    chk("zero-fill 49B", 0, 49, 3);
    chk("0xab x 17B", 0xab, 17, 5);
    chk("upper bits garbage (0x1ab)", 0x1ab, 9, 0);
    chk("count 0 (no write)", 0xff, 0, 8);
    chk("count 1", 0x7f, 1, 63);
    chk("full 64B", 0xcc, 64, 0);
    return bad ? 1 : 0;
}
C
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
TMPDIR="$W" emcc -w -O0 -I "$ROOT/tools/m11" -msimd128 "$W/t_simd.c" "$W/main.c" -o "$W/t.js" > "$W/emcc.log" 2>&1 || { cat "$W/emcc.log"; echo "[test_rep_stosb] emcc failed"; exit 1; }
node "$W/t.js" 2>&1 | tee "$W/run.log"
rc=${PIPESTATUS[0]}
[ "$rc" = 0 ] && echo "[test_rep_stosb] PASS" || echo "[test_rep_stosb] FAIL rc=$rc"
exit "$rc"
