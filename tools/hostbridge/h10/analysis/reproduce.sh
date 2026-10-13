#!/usr/bin/env bash
# reproduce.sh — H10 (#218) の根拠 evidence/* を fl-win64 素材から再生成する.
#   素材: $FL_WIN64_DIR/extracted/block19091_PE.bin (Fruity Wrapper_x64.dll 2.7.0.5653) と block23676_PE.bin (別ビルド)
#   Ghidra 12.1.4 (JDK 21+) 必須: GHIDRA_HOME 未設定なら /opt/ghidra/ghidra_12.1.4_PUBLIC → $RUNNER_TEMP/ghidra/... を探す.
#   初回は fw_a.dll の自動解析 (2m49s 実測, 4 コア) が走る. 以降は解析済 project への読取クエリのみ (1 クエリ 6–9 s).
set -euo pipefail
H10="$(cd -- "$(dirname -- "$0")/.." && pwd)"
HB="$(cd -- "$H10/.." && pwd)"
# shellcheck disable=SC1091
source "$H10/../../shared/env.sh"
W="$H10/work"; G="$W/ghidra"; E="$H10/evidence"; X="$FL_WIN64_DIR/extracted"
mkdir -p "$W" "$G" "$E"
[ -f "$W/fw_a.dll" ] || cp "$X/block19091_PE.bin" "$W/fw_a.dll"
[ -f "$W/fw_b.dll" ] || cp "$X/block23676_PE.bin" "$W/fw_b.dll"
for g in "${GHIDRA_HOME:-}" /opt/ghidra/ghidra_12.1.4_PUBLIC "${RUNNER_TEMP:-/nonexistent}/ghidra/ghidra_12.1.4_PUBLIC"; do
  [ -n "$g" ] && [ -x "$g/support/analyzeHeadless" ] && { export GHIDRA_HOME="$g"; break; }
done
: "${GHIDRA_HOME:?Ghidra 12.1.4 not found}"
if [ -z "${JAVA_HOME:-}" ] && [ -d /usr/lib/jvm/temurin-21-jdk-amd64 ]; then export JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64; fi
[ -n "${JAVA_HOME:-}" ] && export PATH="$JAVA_HOME/bin:$PATH"
if [ ! -d "$G/fw.rep" ]; then
  (cd "$W" && "$GHIDRA_HOME/support/analyzeHeadless" ghidra fw -import fw_a.dll -scriptPath "$HB/ghidra_scripts" \
     -postScript DumpFunctions.java ghidra/functions_fw.csv -max-cpu 4 > ghidra/analyze_fw.log 2>&1)
fi
Q() { "$H10/analysis/gq.sh" "$E/$1" "${@:2}"; }
# --- 状態読込 (FL → Fruity Wrapper SaveRestoreState(load)): version 検査 → record loop
Q fw_state_load.c    decomp 870da0 875af0 875800 8744b0 8744d0
# --- record stream の入出力 (12B header {u32 id,u64 size} / min(size,N) コピー / 文字列エンコード / 次 record へ seek)
Q fw_record_io.c     decomp 74a5b0 74a8e0 74a970 74aa40 74abd0 74a6a0 74a740 44acd0
# --- 状態保存 (record 57 の書出し条件の根拠)
Q fw_state_save.c    decomp 8712b0
# --- plugin ファイルの解決 (Wrapper → FL host msg 7 の問い合わせ書式と応答の解釈)
Q fw_resolve.c       decomp 871fe0 79e540 79e850
# --- plugin 生成 (factory 経由) と LoadPlugin_Finish
Q fw_loadplugin.c    decomp 86e1a0 86e9f0 87c980
# --- TVSTPlugin ctor の呼出元 (hint 引数の供給元) と +0x9c4 (record 57 の実体) の参照
Q fw_ctor_callers.txt refsto 7a9db0 87c980 86e1a0 871fe0 875af0
Q fw_9c4_refs.txt    grepins '\+ 0x9c4\]' 400000 9a0000
Q fw_89c_8a0_refs.txt grepins '\+ 0x8a0\]|\+ 0x89c\]' 800000 9a0000
Q fw_xref_strings.txt xrefstr "SaveRestoreState - load" "LoadPlugin_Finish" "Something went wrong loading the"
# --- FLEngine (block00031_PE.bin) 側: event 212 の flags (0x10 / 0x80) — 解析 10m13s (3 コア) のため REGEN_FLE=1 の時だけ
if [ "${REGEN_FLE:-0}" = 1 ]; then
  [ -f "$W/fle.dll" ] || cp "$X/block00031_PE.bin" "$W/fle.dll"
  mkdir -p "$W/ghidra_fle"
  if [ ! -d "$W/ghidra_fle/fle.rep" ]; then
    (cd "$W" && "$GHIDRA_HOME/support/analyzeHeadless" ghidra_fle fle -import fle.dll -scriptPath "$HB/ghidra_scripts" \
       -postScript DumpFunctions.java ghidra_fle/functions_fle.csv -max-cpu 3 > ghidra_fle/analyze_fle.log 2>&1)
  fi
  QF() { GQ_PROJDIR="$W/ghidra_fle" GQ_PROJECT=fle GQ_PROGRAM=fle.dll "$H10/analysis/gq.sh" "$@"; }
  QF "$E/fle_212_writer_reader.c" decomp aac1e0 aac300 f54900 f3c870
  QF "$W/f46490.c" decomp f46490
  python3 - "$W/f46490.c" "$E/fle_212_reader_excerpt.c" <<'PY'
import sys
src = open(sys.argv[1]).read().splitlines()
i = next(k for k, l in enumerate(src) if 'else if (iVar3 == 0xd4) {' in l)
open(sys.argv[2], 'w').write('=== fle:0xf46490 (.fst/.flp plugin loader) — event 212 (0xd4) case, lines %d..%d of the decompile\n' % (i + 1, i + 261) + '\n'.join(src[i:i + 261]) + '\n')
PY
  QF "$W/aba880.asm" disasm aba880
  grep -B8 -A1 "00ababff" "$W/aba880.asm" > "$E/fle_aba880_call.asm"
fi
echo "[h10 reproduce] evidence → $E"
