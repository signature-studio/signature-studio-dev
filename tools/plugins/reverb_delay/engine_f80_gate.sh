#!/usr/bin/env bash
# engine_f80_subset.sh の gate (判定のみ・emcc を呼ばない)。 stub (python / re.split) と別の算法 (awk) で
# 「本体 (define 行〜対応する } 行) に x86_fp80 を含む define の名前集合」を求め、 f80_excluded.tsv の名前集合と一致することを見る。
#   bash tools/plugins/reverb_delay/engine_f80_gate.sh <FULL.ll> <SUB.ll> <EXCL.tsv> <emcc_c_rc>
# PASS: emcc_c_rc=0 かつ define 数が除外数だけ減る かつ 除外集合 = 本体に f80 を含む define 集合 かつ SUB.ll の本体 f80 が 0。 不合格なら exit 1。
set -uo pipefail
FULL="$1"; SUB="$2"; TSV="$3"; RC="$4"
f80_names() { awk '
  /^define / { inb = 1; f = 0; n = $0; sub(/^[^@]*@/, "", n); sub(/\(.*/, "", n) }
  inb && /x86_fp80/ { f = 1 }
  inb && /^}$/ { if (f) print n; inb = 0 }' "$1" | sort; }
tsv_names() { tail -n +2 "$1" | cut -f1 | sort; }
NFULL=$(grep -c '^define' "$FULL")
NSUB=$(grep -c '^define' "$SUB")
NEX=$(($(wc -l < "$TSV") - 1))
NF80=$(f80_names "$FULL" | wc -l)
NF80SUB=$(f80_names "$SUB" | wc -l)
SETEQ=diff
cmp -s <(f80_names "$FULL") <(tsv_names "$TSV") && SETEQ=same
GATE=FAIL
[ "$RC" -eq 0 ] && [ "$NSUB" -eq $((NFULL - NEX)) ] && [ "$NF80SUB" -eq 0 ] && [ "$SETEQ" = same ] && GATE=PASS
echo "f80_excluded=$NEX,define_full=$NFULL,define_sub=$NSUB,f80_body_full=$NF80,f80_body_sub=$NF80SUB,excl_set_eq_f80_body=$SETEQ,emcc_c_rc=$RC,gate=$GATE"
[ "$GATE" = PASS ]
