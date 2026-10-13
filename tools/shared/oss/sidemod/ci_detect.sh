#!/usr/bin/env bash
# CI-6 (#309): GPL 混入検出テストを emsdk・ネットワーク無しで実行する (Actions の detect-tests ジョブ用)。
#   usage: bash oss/sidemod/ci_detect.sh        rc=0 で全 PASS、1 つでも期待と違えば rc=1
#   1) 陽性: selftest が全ケース OK / build.sh の実引数 (SIDEMOD_GUARD_ONLY=1) が検出をクリーンに通る
#   2) ネガコン: 禁止フラグ表の全件・config.h・license・LAME mpglib・build.sh への注入が「rc=1 ちょうど」で落ちる
#   3) 検出器自身のネガコン: 禁止表から gpl を抜いた / 判定を常に OK にした検出器は selftest・本テストが落ちる
# 「落ちるはずが rc=0」「rc=2 (使い方の誤り) を検出と取り違える」を許さないため、期待 rc を厳密に比較する。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
G="$HERE/check_license_flags.py"
W="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ci_detect.XXXXXX")"
trap 'rm -rf "$W"' EXIT
T0=$(date +%s)
FAIL=0; NPASS=0; NNEG=0
ok() { NPASS=$((NPASS+1)); echo "[ci_detect] PASS $*"; }
ng() { FAIL=1; echo "[ci_detect] FAIL $*"; }

# expect <rc> <name> <cmd...>: 実 rc が期待と一致したときだけ PASS
expect() {
  local want="$1" name="$2"; shift 2
  "$@" >"$W/out.log" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then ok "$name (rc=$rc)"; else ng "$name: rc=$rc, expected $want"; sed 's/^/    | /' "$W/out.log" | head -5; fi
}
# neg <name> <cmd...>: 混入を検出して rc=1 ちょうどで落ちること + "GPL-GUARD FAIL" の出力
neg() {
  local name="$1"; shift
  "$@" >"$W/out.log" 2>&1; local rc=$?
  NNEG=$((NNEG+1))
  if [ "$rc" = 1 ] && grep -q 'GPL-GUARD FAIL' "$W/out.log"; then ok "NEG CAUGHT: $name (rc=1)"
  else ng "NEG MISSED: $name: rc=$rc"; sed 's/^/    | /' "$W/out.log" | head -5; fi
}

GOOD="--prefix=/nonexistent --target-os=none --disable-everything --enable-decoder=flac,mp3 --enable-pic"

echo "=== 1. 陽性 (クリーンな入力は通る) ==="
python3 "$G" selftest >"$W/selftest.log" 2>&1; rc=$?
tail -1 "$W/selftest.log"
n_ok=$(sed -nE 's#^\[selftest\] ([0-9]+)/([0-9]+) ok$#\1#p' "$W/selftest.log")
n_all=$(sed -nE 's#^\[selftest\] ([0-9]+)/([0-9]+) ok$#\2#p' "$W/selftest.log")
if [ "$rc" = 0 ] && [ -n "$n_all" ] && [ "$n_ok" = "$n_all" ] && [ "$n_all" -ge 18 ]; then ok "selftest $n_ok/$n_all"; else ng "selftest rc=$rc ok=$n_ok all=$n_all"; fi
expect 0 "clean ffmpeg configure" python3 "$G" config "$GOOD"
expect 0 "--disable-gpl は禁止ではない" python3 "$G" config "$GOOD --disable-gpl"
expect 0 "clean LAME" python3 "$G" lame "--disable-decoder --disable-shared" -- /dev/null
printf '#define CONFIG_GPL 0\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 0\n' >"$W/clean-config.h"
expect 0 "clean config.h" python3 "$G" configh "$W/clean-config.h"
expect 0 "license LGPL2.1+" python3 "$G" license "LGPL version 2.1 or later"
expect 0 "build.sh の実引数 (SIDEMOD_GUARD_ONLY=1)" env SIDEMOD_GUARD_ONLY=1 bash "$HERE/build.sh"
grep -q 'GPL-GUARD OK' "$W/out.log" && ok "build.sh が GPL-GUARD OK を出力" || ng "build.sh の出力に GPL-GUARD OK が無い"

echo "=== 2. ネガコン: 禁止フラグ表の全件 ==="
python3 - "$G" >"$W/flags.txt" <<'PY'
import importlib.util, sys
s = importlib.util.spec_from_file_location("g", sys.argv[1]); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print("\n".join(sorted(m.FORBIDDEN_FLAGS)))
PY
NFLAGS=$(wc -l <"$W/flags.txt")
[ "$NFLAGS" -ge 30 ] && ok "禁止フラグ表を読めた: $NFLAGS 件" || ng "禁止フラグ表が空/縮小: $NFLAGS 件"
while read -r f; do
  [ -n "$f" ] && neg "--enable-$f" python3 "$G" config "$GOOD --enable-$f"
done <"$W/flags.txt"
neg "--enable-libx265=yes (値付き)" python3 "$G" config "$GOOD --enable-libx265=yes"

echo "=== 3. ネガコン: config.h / license / LAME / artifact ==="
for k in CONFIG_GPL CONFIG_NONFREE CONFIG_VERSION3; do
  sed "s/$k 0/$k 1/" "$W/clean-config.h" >"$W/neg-config.h"
  neg "config.h $k=1" python3 "$G" configh "$W/neg-config.h"
done
neg "config.h にキーが無い" python3 "$G" configh /dev/null
neg "license GPL version 2 or later" python3 "$G" license "GPL version 2 or later"
neg "license LGPL version 3 or later" python3 "$G" license "LGPL version 3 or later"
neg "LAME --disable-decoder 欠落" python3 "$G" lame "--disable-shared" -- /dev/null
neg "LAME --enable-decoder" python3 "$G" lame "--disable-decoder --enable-decoder" -- /dev/null
for s in hip_decode lame_decode decode_header mpglib; do
  printf 'xx %s1 xx' "$s" >"$W/lame-$s.bin"
  neg "LAME binary に $s" python3 "$G" lame "--disable-decoder" -- "$W/lame-$s.bin"
done
printf '\0--prefix=/nonexistent --target-os=none --enable-decoder=flac\0LGPL version 2.1 or later\0' >"$W/ff-clean.bin"
printf '\0--prefix=/nonexistent --enable-gpl --enable-libx264\0GPL version 2 or later\0' >"$W/ff-gpl.bin"
printf 'lame_encode_buffer' >"$W/lame-clean.bin"
expect 0 "artifact clean" python3 "$G" artifact "$W/ff-clean.bin" "$W/lame-clean.bin"
neg "artifact に GPL ffmpeg" python3 "$G" artifact "$W/ff-gpl.bin" "$W/lame-clean.bin"
neg "artifact に license 文字列が無い" python3 "$G" artifact /dev/null "$W/lame-clean.bin"
# rc=2 (使い方の誤り) を検出と取り違えない: neg は rc=1 + GPL-GUARD FAIL を要求するので、引数不足は NEG にならない
expect 2 "引数不足は rc=2 (検出 rc=1 と区別)" python3 "$G" config

echo "=== 4. ネガコン: build.sh の禁止フラグ表 (PR が FF_ARGS / LAME_ARGS に混入させる経路) ==="
for f in --enable-gpl --enable-version3 --enable-nonfree --enable-libx264; do
  neg "build.sh + FF_EXTRA_ARGS=$f" env SIDEMOD_GUARD_ONLY=1 FF_EXTRA_ARGS="$f" bash "$HERE/build.sh"
done
neg "build.sh + LAME_EXTRA_ARGS=--enable-decoder" env SIDEMOD_GUARD_ONLY=1 LAME_EXTRA_ARGS="--enable-decoder" bash "$HERE/build.sh"
# build.sh の FF_ARGS 配列そのものを書き換えたコピー (= 禁止フラグを入れた PR) を実行する
mkdir -p "$W/m/sidemod"; cp "$G" "$W/m/sidemod/check_license_flags.py"   # build.sh は HERE 基準 (ROOT=HERE/../.. = $W/m)
sed 's/--enable-protocol=file --enable-bsf=null --enable-pic/--enable-protocol=file --enable-bsf=null --enable-pic --enable-gpl/' "$HERE/build.sh" >"$W/m/sidemod/build-gpl.sh"
if cmp -s "$HERE/build.sh" "$W/m/sidemod/build-gpl.sh"; then ng "build.sh の FF_ARGS 行が見つからず変異できなかった (テストが古い)"
else neg "build.sh の FF_ARGS に --enable-gpl を書き込んだ PR" env SIDEMOD_GUARD_ONLY=1 bash "$W/m/sidemod/build-gpl.sh"; fi
sed 's/--disable-shared --enable-static --disable-nasm --disable-decoder/--disable-shared --enable-static --disable-nasm/' "$HERE/build.sh" >"$W/m/sidemod/build-lame.sh"
if cmp -s "$HERE/build.sh" "$W/m/sidemod/build-lame.sh"; then ng "build.sh の LAME_ARGS 行が見つからず変異できなかった (テストが古い)"
else neg "build.sh の LAME_ARGS から --disable-decoder を消した PR" env SIDEMOD_GUARD_ONLY=1 bash "$W/m/sidemod/build-lame.sh"; fi

echo "=== 5. 検出器自身のネガコン (検出器が壊れたら本テストが落ちる) ==="
sed 's/"gpl", "nonfree", "version3",//' "$G" >"$W/mut-nogpl.py"
cmp -s "$G" "$W/mut-nogpl.py" && ng "禁止表の変異に失敗 (行が変わった)" || {
  python3 "$W/mut-nogpl.py" selftest >/dev/null 2>&1; r=$?
  NNEG=$((NNEG+1)); [ "$r" = 1 ] && ok "NEG CAUGHT: 禁止表から gpl/nonfree/version3 を抜いた検出器は selftest rc=1" || ng "NEG MISSED: 禁止表変異の selftest rc=$r"; }
sed 's/^    return \[f"forbidden configure flag: {h}" for h in forbidden_in(config)\]/    return []/' "$G" >"$W/mut-noop.py"
cmp -s "$G" "$W/mut-noop.py" && ng "check_config の変異に失敗 (行が変わった)" || {
  python3 "$W/mut-noop.py" selftest >/dev/null 2>&1; r=$?
  NNEG=$((NNEG+1)); [ "$r" = 1 ] && ok "NEG CAUGHT: check_config が常に空を返す検出器は selftest rc=1" || ng "NEG MISSED: check_config 無効化の selftest rc=$r"; }

echo "[ci_detect] checks: PASS=$NPASS (うちネガコン $NNEG 件), elapsed $(( $(date +%s) - T0 )) s, loadavg $(cut -d' ' -f1-3 /proc/loadavg), nproc $(nproc)"
if [ "$FAIL" = 0 ]; then echo "[ci_detect] ALL PASS"; else echo "[ci_detect] FAILED"; fi
exit "$FAIL"
