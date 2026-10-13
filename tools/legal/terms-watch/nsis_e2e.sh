#!/usr/bin/env bash
# xfer-eula (kind: nsis-license) の検証: 実 makensis (NSIS 3.x, Unicode) で作った合成インストーラからライセンス文を取り出す。
# 実 Xfer インストーラ (plugins-ott 等) は不要。makensis が無ければ apt-get download + dpkg -x で work/ に取得する (root 不要)。
#   bash tools/legal/terms-watch/nsis_e2e.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CLI="$HERE/cli.mjs"
W="$HERE/work/nsis_e2e"
mkdir -p "$W"
rm -rf "$W/run"; mkdir -p "$W/run"
fail=0

if command -v makensis >/dev/null; then MK="$(command -v makensis)"
else
  if [ ! -x "$W/root/usr/bin/makensis" ]; then
    mkdir -p "$W/deb" "$W/root"
    (cd "$W/deb" && apt-get download nsis nsis-common >/dev/null 2>&1 && for d in ./*.deb; do dpkg -x "$d" "$W/root"; done)
  fi
  MK="$W/root/usr/bin/makensis"; export NSISDIR="$W/root/usr/share/nsis"
fi
[ -x "$MK" ] || { echo "makensis を用意できない"; exit 3; }
echo "makensis: $("$MK" -VERSION)"

cd "$W/run"
python3 - <<'PY'
import textwrap
paras = [f"{i}. The Licensee shall use the Software only on devices owned by the Licensee, and is prohibited from reverse engineering, decompiling or disassembling clause {i}. “Quoted” – dashed; 日本語 規約 {i}." for i in range(1, 13)]
open("License.txt", "w", encoding="utf-8").write("\n\n".join(textwrap.fill(p, 60) for p in paras) + "\n")
open("License_mod.txt", "w", encoding="utf-8").write(open("License.txt", encoding="utf-8").read().replace("decompiling", "decompilings", 1))
open("License_ws.txt", "w", encoding="utf-8", newline="").write("\r\n".join(open("License.txt", encoding="utf-8").read().split("\n")).replace(" ", "  "))
def esc(s):
    o = []
    for ch in s:
        c = ord(ch)
        o.append(ch if ch not in "\\{}" and c < 128 else (f"\\u{c - 65536 if c > 32767 else c}?" if c >= 128 else "\\" + ch))
    return "".join(o)
open("License.rtf", "w", encoding="ascii").write("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\pard " + "".join(esc(p) + "\\par\\par " for p in paras) + "}")
PY
build() { # build <out> <license> <compressor>
  mkdir -p "$(dirname "$1")"
  printf 'Unicode true\nSetCompressor %s\nName "TermsWatchTest"\nOutFile "%s"\nRequestExecutionLevel user\nPage license\nPage instfiles\nLicenseData "%s"\nSection "Main"\nSectionEnd\n' "$3" "$PWD/$1" "$PWD/$2" > t.nsi
  "$MK" -V1 t.nsi >/dev/null || { echo "makensis 失敗: $1"; exit 3; }
}
build a/sub/Setup.exe License.txt zlib
build d/Setup.exe License_mod.txt zlib
build e/Setup.exe License_ws.txt zlib
build r/Setup.exe License.rtf zlib
build c/Setup.exe License.txt lzma
build both/a.exe License.txt zlib; cp d/Setup.exe both/d.exe
head -c 300000 /dev/urandom > a/other.exe   # NSIS ではない exe が混ざっていても無視される

export TERMS_WATCH_NOW=2026-10-13T00:00:00Z
unset TERMS_WATCH_XFER_INSTALLER TERMS_WATCH_XFER_EULA
n=0
run() { # run <case> <expected-exit> <ledger-name> <plugins-dir> [extra cli args]
  local name="$1" want="$2" led="$3" dir="$4"; shift 4
  out="$(node "$CLI" check --only xfer-eula --plugins-dir "$dir" --ledger "$W/run/$led.json" --md "$W/run/$led.md" --snapshots "$W/run/snap" "$@" 2>&1)"; code=$?
  n=$((n + 1))
  printf '%-52s expected=%s actual=%s\n' "$name" "$want" "$code"
  [ "$code" = "$want" ] || { fail=1; echo "$out"; }
  echo "$out" | grep -E '^(NEW|CHANGED|UNCHANGED|SKIP|ERROR|PENDING)' | cut -c1-200 | sed 's/^/    /'
}
sha_of() { node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).docs["xfer-eula"].current.sha256)' "$W/run/$1.json"; }

run "A text (基準線 NEW)"                           0 L1 a
run "A text 再実行 (UNCHANGED)"                      0 L1 a
run "D: 1 語改変 → CHANGED"                          1 L1 d
run "A text (別台帳 L2 の基準線 NEW)"                0 L2 a
run "E: 空白/CRLF/折返しのみ改変 → UNCHANGED"        0 L2 e
run "R: RTF 形式の同一本文 → UNCHANGED"              0 L2 r
run "C: LZMA ヘッダ → 未対応で ERROR"                3 L3 c
run "A と D が同じ dir → 内容違いで ERROR"           3 L4 both
run "dir 無し → SKIP (optional なので 0)"            0 L5 "$W/none"
run "dir 無し + --strict → 3"                        3 L5 "$W/none" --strict
TERMS_WATCH_XFER_INSTALLER="$W/run/a/sub/Setup.exe" run "インストーラ直指定 (dir 無し)" 0 L6 "$W/none"
TERMS_WATCH_XFER_INSTALLER="$W/run/c/Setup.exe" run "インストーラ直指定が LZMA → ERROR" 3 L7 "$W/none"
TERMS_WATCH_XFER_EULA="$W/run/License.txt" run "プレーンテキスト直指定 (License.txt)" 0 L8 "$W/none"

echo "--- SHA-256 一致 (Python のインストーラ抽出 / Python の元テキスト / JS 台帳 L2 = A・E・R で不変 / JS 平文直指定 L8) ---"
py="$(python3 "$HERE/crosscheck_nsis.py" a/sub/Setup.exe License.txt)"; echo "$py"
pi="$(echo "$py" | awk '$1=="installer"{print $2}')"; ps="$(echo "$py" | awk '$1=="source"{print $2}')"
js_plain="$(sha_of L8)"; js_l2="$(sha_of L2)"
printf 'js(L2)=%s\njs(L8)=%s\n' "$js_l2" "$js_plain"
[ -n "$pi" ] && [ "$pi" = "$ps" ] && [ "$pi" = "$js_plain" ] && [ "$pi" = "$js_l2" ] || { echo "SHA-256 不一致"; fail=1; }
echo "cases=$n fail=$fail"
exit $fail
