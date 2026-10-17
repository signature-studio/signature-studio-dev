#!/usr/bin/env bash
# #113 S2 probe: 実物の FL64.exe を wine64 で `/R` 起動し、Render tests の 1 本を WAV 書き出しする。
# 前提: `bash tools/flp/s1_wine_probe.sh` でインストール木 ($RUNNER_TEMP/fl-install) と wineprefix を作成済み。
# 手順: block から FL64.exe / FLEngine_x64.dll を復元 → G03 パッチ (s1_g03_patch.py, oracle ローカルコピーのみ)
#       → 出力 sample rate を 48000 に設定 → `/R` で書き出し → data チャンクの SHA-256 を REPEAT 回求める。
# 使い方: bash tools/flp/s2_render_probe.sh <Render tests の .flp 名> [REPEAT=3]
# 追加試行: S2_REG に 1 行 1 件 `<HKCU 下のキー>|<値名>|<REG_SZ の値>` を入れる (値は WINEPREFIX に残る)。
#   例 (#113 の 16-bit 試行、既定 WFBox=2 のため S2_WFBOX=0 を付ける): S2_WFBOX=0 S2_REG=$'Software\\Image-Line\\FL Studio 26\\General|LastExportedFormats|4' bash tools/flp/s2_render_probe.sh Autogun.flp 1
# 検証用の即値パッチ: S2_PATCH に 1 行 1 件 `<VA hex>|<期待バイト hex>|<新バイト hex>` を入れる (oracle ローカルコピーの FLEngine_x64.dll のみ)。
# レジストリ・トレース: S2_TRACE_REG=1 で WINEDEBUG=+reg にし、開かれたキーを $WORKDIR/s2_reg_keys_<n>.txt に出す。
# thread 状態の採取: S2_THREAD_AT (既定 "60 90" の秒・空白区切り・0 で無効) ごとに $WORKDIR/s2_threads_<n>.tsv へ wine 系プロセスの全 thread を追記する (列: 経過秒・pid・tid・comm・state・utime・stime・wchan・syscall)。
# 実行中の観測: S2_SAMPLE (既定 5 秒・0 で無効) ごとに $WORKDIR/s2_progress_<n>.tsv へ「epoch・WAV バイト数(- は無し)・ログ バイト数・wine 系プロセスの CPU 秒合計・RSS KiB 合計」を追記する。WAV サイズが増え続ければ書き出し中、ログとCPU が止まれば停止の疑い。
# WAV 形式: WAVRenderForm\WFBox = ${S2_WFBOX:-2} (0 = 16-bit / 1 = 24-bit / 2 = 32-bit float、#3052 で実測)、WAVRenderForm\DitherBox = 0 (dither off)。16-bit に戻すには S2_WFBOX=0。
# 出力は $RUNNER_TEMP 配下のみ (commit 対象外)。結果の要約は tools/flp/REPORT_APPENDIX.md §15・§16・§17。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ART="${RUNNER_TEMP:-/tmp}"
EXT="$ART/fl-win64/extracted"
INST="$ART/fl-install"
SRC="${S2_SRC:-$ART/fl-install/Data/System/Render tests}"
WORKDIR="$ART/s2"
NAME="${1:?usage: s2_render_probe.sh <name.flp> [repeat]}"
# thread 状態の採取: 起動からの秒 (既定 "60 90"・0 で無効) に wine 系プロセスの全 thread の state・utime・stime・wchan を追記する。
# 同じ thread の utime が増えていれば spin (CPU を使用中)、増えず wchan が待ちを示していれば待ち。
# 注: stat の列 3・14・15 は comm (括弧内) に空白が無い前提で切る。comm は別に読む。
dump_threads() {
  local out="$1" el="$2" pid t tid
  for pid in $(ps -C wine64-preloader,wine64,FL64.exe -o pid= 2>/dev/null || true); do
    for t in /proc/"$pid"/task/*; do
      [[ -d "$t" ]] || continue
      tid="${t##*/}"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$el" "$pid" "$tid" "$(cat "$t/comm" 2>/dev/null || echo -)" \
        "$(cut -d' ' -f3,14,15 "$t/stat" 2>/dev/null || echo - - -)" "$(cat "$t/wchan" 2>/dev/null || echo -)" "$(cat "$t/syscall" 2>/dev/null | cut -d' ' -f1 || echo -)"
    done
  done >> "$out" || true
}
REPEAT="${2:-3}"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64
if [[ "${S2_TRACE_REG:-0}" == 1 ]]; then export WINEDEBUG="+reg"; else export WINEDEBUG="${S2_WINEDEBUG:--all}"; fi
export PATH="/usr/lib/wine:$PATH"

[[ -d "$INST" ]] || { echo "missing $INST (先に s1_wine_probe.sh)" >&2; exit 2; }
mkdir -p "$WORKDIR"
cp "$SRC/$NAME" "$WORKDIR/"

cp "$EXT"/block00038_* "$INST/FL64.exe"
cp "$EXT"/block00031_* "$INST/FLEngine_x64.dll"
(cd "$INST" && python3 "$ROOT/tools/flp/s1_g03_patch.py" FL64.exe && python3 "$ROOT/tools/flp/s1_g03_patch.py" FLEngine_x64.dll)
while IFS='|' read -r pva pexp pnew; do
  [[ -n "$pva" ]] || continue
  python3 "$ROOT/tools/flp/s2_imm_patch.py" "$INST/FLEngine_x64.dll" "$pva" "$pexp" "$pnew"
done <<< "${S2_PATCH:-}"

wine64 reg add 'HKCU\Software\Image-Line\FL Studio 26\Devices\Audio output' /v 'Sample rate' /t REG_SZ /d 48000 /f >/dev/null 2>&1 || true
wine64 reg add 'HKCU\Software\Image-Line\FL Studio 26\General\WAVRenderForm' /v WFBox /t REG_SZ /d "${S2_WFBOX:-2}" /f >/dev/null 2>&1 || true
wine64 reg add 'HKCU\Software\Image-Line\FL Studio 26\General\WAVRenderForm' /v DitherBox /t REG_SZ /d 0 /f >/dev/null 2>&1 || true
while IFS='|' read -r rkey rname rval; do
  [[ -n "$rkey" ]] || continue
  wine64 reg add "HKCU\\$rkey" /v "$rname" /t REG_SZ /d "$rval" /f >/dev/null 2>&1 || true
done <<< "${S2_REG:-}"
wineserver -k >/dev/null 2>&1 || true
sleep 2

base="${NAME%.flp}"
WINPATH="$(printf '%s' "$WORKDIR" | sed 's#/#\\#g')"
for n in $(seq 1 "$REPEAT"); do
  rm -f "$WORKDIR/$base.wav"
  s=$(date +%s)
  rc=0
  sample="$WORKDIR/s2_progress_$n.tsv"
  : > "$sample"
  # 実行中の観測 (S2_SAMPLE=秒。0 で無効)。5 秒ごとに WAV サイズ・ログ増分・wine 系プロセスの CPU 秒・RSS を記録する。
  # 終了は PID 指定の kill のみ (pkill・kill 0 等は使わない)。
  if [[ "${S2_SAMPLE:-5}" != 0 ]]; then
    (
      while sleep "${S2_SAMPLE:-5}"; do
        w=$(stat -c %s "$WORKDIR/$base.wav" 2>/dev/null || echo -)
        l=$(stat -c %s "$WORKDIR/s2_run_$n.log" 2>/dev/null || echo -)
        p=$(ps -C wine64-preloader,wine64,FL64.exe -o etimes=,cputimes=,rss= 2>/dev/null | awk '{c+=$2; r+=$3} END {printf "%s\t%s", c+0, r+0}' || true)
        printf '%s\t%s\t%s\t%s\n' "$(date +%s)" "$w" "$l" "${p:-0	0}" >> "$sample"
      done
    ) &
    sampler=$!
  fi
  threads="$WORKDIR/s2_threads_$n.tsv"
  : > "$threads"
  if [[ -n "${S2_THREAD_AT:-60 90}" ]]; then
    (
      for at in ${S2_THREAD_AT:-60 90}; do
        sleep_until=$(( s + at ))
        while (( $(date +%s) < sleep_until )); do sleep 1; done
        dump_threads "$threads" "$(( $(date +%s) - s ))"
      done
    ) &
    tdumper=$!
  fi
  (cd "$INST" && timeout "${S2_TIMEOUT:-120}" xvfb-run -a wine64 FL64.exe /R "Z:${WINPATH}\\$NAME" > "$WORKDIR/s2_run_$n.log" 2>&1) || rc=$?
  if [[ -n "${tdumper:-}" ]]; then kill "$tdumper" 2>/dev/null || true; wait "$tdumper" 2>/dev/null || true; unset tdumper; fi
  if [[ -n "${sampler:-}" ]]; then kill "$sampler" 2>/dev/null || true; wait "$sampler" 2>/dev/null || true; unset sampler; fi
  e=$(date +%s)
  cp "$WORKDIR/$base.wav" "$WORKDIR/${base}_run_$n.wav" 2>/dev/null || true
  if [[ "${S2_TRACE_REG:-0}" == 1 ]]; then
    grep -oE 'NtOpenKeyEx \(0x[0-9a-f]+,L"[^"]*"' "$WORKDIR/s2_run_$n.log" | sed 's/.*L"//' | sort | uniq -c > "$WORKDIR/s2_reg_keys_$n.txt" || true
  fi
  python3 - "$WORKDIR/${base}_run_$n.wav" "$n" "$rc" "$((e - s))" <<'EOF'
import hashlib, struct, sys
path, n, rc, sec = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    b = open(path, "rb").read()
except OSError:
    print(f"run={n} rc={rc} sec={sec} wav=missing"); raise SystemExit
i = 12; fmt = data = None
while i + 8 <= len(b):
    cid = b[i:i+4]; sz = struct.unpack("<I", b[i+4:i+8])[0]
    if cid == b"fmt ":
        fmt = struct.unpack("<HHIIHH", b[i+8:i+24])
    if cid == b"data":
        data = b[i+8:i+8+sz]
    i += 8 + sz + (sz & 1)
print(f"run={n} rc={rc} sec={sec} fmt={fmt[0]}/{fmt[1]}ch/{fmt[2]}Hz/{fmt[5]}bit data_bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
EOF
done
