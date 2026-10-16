#!/usr/bin/env bash
# #5044 (ICALL-108) 受入 2: 180cbb930 の直接・間接呼出し先が r13 を書かないことの静的確認。
# 使い方: tools/icall/r13_callee_check.sh <SlateCore.core_64 のパス> <出力 dsm (work/ 配下)>
#         tools/icall/r13_callee_check.sh --selftest   (判定関数の期待値確認のみ)
# dsm は objdump -d -M intel の全量。初回のみ生成し、以降は再利用する。
set -euo pipefail

# 宛先 (第 1 オペランド) が r13/r13b/r13w/r13d の命令を数える (ニーモニックは限定しない)。
# 書込みではない cmp/test/push/call/jmp/jcc は除外する。xchg は両オペランドを見る。
# push r13 / pop r13 は保存・復元として別に数える (r13_saves)。
r13_writes() {
  awk -F'\t' 'NF>=3 {
      ins=$3; sub(/^ +/,"",ins); m=ins; sub(/ .*/,"",m)
      rest=ins; sub(/^[^ ]+ */,"",rest)
      split(rest,ops,","); d=ops[1]; gsub(/ /,"",d)
      if (m ~ /^(cmp|test|push|call|jmp|j[a-z]+)$/) next
      if (d ~ /^r13[bwd]?$/ || (m=="xchg" && rest ~ /(^|[ ,])r13[bwd]?($|[ ,])/)) n++
    } END {print n+0}'
}
r13_saves() {
  awk -F'\t' -v op="$1" 'NF>=3 {
      ins=$3; sub(/^ +/,"",ins); m=ins; sub(/ .*/,"",m); rest=ins; sub(/^[^ ]+ */,"",rest)
      gsub(/ /,"",rest)
      if (m==op && rest ~ /^r13[bwd]?$/) n++
    } END {print n+0}'
}

if [ "${1:-}" = "--selftest" ]; then
  # 期待値: 書込み 3 件 (bsf r13,rax / mov r13b,al / pop r13)、push r13 1 件、pop r13 1 件。
  # 非書込み (cmp / test / 格納先が r13 のメモリ参照) は数えない。
  T=$(mktemp)
  printf '  1:\t00 00\tbsf    r13,rax\n  2:\t00 00\tmov    r13b,al\n  3:\t00 00\tpop    r13\n  4:\t00 00\tcmp    r13,rax\n  5:\t00 00\tpush   r13\n  6:\t00 00\ttest   r13,r13\n  7:\t00 00\tmov    QWORD PTR [r13+0x8],rax\n' > "$T"
  w=$(r13_writes < "$T"); p=$(r13_saves push < "$T"); q=$(r13_saves pop < "$T")
  rm -f "$T"
  echo "selftest: 書込み ${w} 件 (期待 3) / push r13 ${p} 件 (期待 1) / pop r13 ${q} 件 (期待 1)"
  [ "$w" = 3 ] && [ "$p" = 1 ] && [ "$q" = 1 ]
  exit $?
fi

F="${1:?SlateCore.core_64 のパスを指定}"; DSM="${2:?dsm の出力先を指定}"
[ -s "$DSM" ] || timeout 600 objdump -d -M intel "$F" > "$DSM"
# 関数本体: 開始アドレス行から、ret の直後に int3 パディングが来る所までを切り出す
body() {
  awk -v s="$1" '
    !on && $1 == s":" {on=1}
    on && prev_ret && /\tint3/ {exit}
    on {print; prev_ret = ($0 ~ /\tret/)}
  ' "$DSM"
}
for a in 180cbb930 180cbcd90 180cb9890; do
  printf '%-10s r13 書込み %s 件 (push r13: %s / pop r13: %s)\n' "$a" \
    "$(body "$a" | r13_writes)" "$(body "$a" | r13_saves push)" "$(body "$a" | r13_saves pop)"
done
echo "間接呼出し 180cbba21 [rax+0x8] / 180cbba36 [rax+0x10]: 具象型は静的に未特定"
echo "control block 格納 (+0xa80) の箇所数: $(grep -cE 'mov +QWORD PTR \[r[a-z0-9]+\+0xa80\],' "$DSM")"
