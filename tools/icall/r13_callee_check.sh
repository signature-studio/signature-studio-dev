#!/usr/bin/env bash
# #5044 (ICALL-108) 受入 2: 180cbb930 の直接・間接呼出し先が r13 を書かないことの静的確認。
# 使い方: tools/icall/r13_callee_check.sh <SlateCore.core_64 のパス> <出力 dsm (work/ 配下)>
# dsm は objdump -d -M intel の全量。初回のみ生成し、以降は再利用する。
set -euo pipefail
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
# r13 を書く命令の数 (宛先オペランドが r13/r13d、または xchg で r13 を入れ替える)
r13_writes() {
  awk -F'\t' 'NF>=3 {
      ins=$3; sub(/^ +/,"",ins); m=ins; sub(/ .*/,"",m); rest=substr(ins,length(m)+2)
      split(rest,ops,","); d=ops[1]; gsub(/ /,"",d)
      if (m ~ /^(mov|movzx|movsx|movsxd|lea|pop|xor|add|sub|and|or|inc|dec|neg|not|shl|shr|sar|imul|cmov|set|bswap)/ && (d=="r13" || d=="r13d")) n++
      if (m=="xchg" && (ops[1] ~ /r13/ || ops[2] ~ /r13/)) n++
    } END {print n+0}'
}
for a in 180cbb930 180cbcd90 180cb9890; do
  printf '%-10s r13 書込み %s 件\n' "$a" "$(body "$a" | r13_writes)"
done
echo "間接呼出し 180cbba21 [rax+0x8] / 180cbba36 [rax+0x10]: 具象型は静的に未特定"
echo "control block 格納 (+0xa78 / +0xa80) の箇所数: $(grep -cE 'mov +QWORD PTR \[r[a-z0-9]+\+0xa80\],' "$DSM")"
