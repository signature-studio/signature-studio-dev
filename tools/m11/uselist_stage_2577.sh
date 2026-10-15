#!/usr/bin/env bash
# #2577: RetDec drc.ll の uselistorder 並びの差が入る段を二分する (REPORT_APPENDIX_2577 §21)。
#   G1: バックエンド最適化を止める (--backend-no-opts)・全 150 range・3 回 (バックエンド段を除いても差が残るか)
#   G2: 150 range を半分に分ける: A=1-75, B=76-150, B1=76-112, B2=113-150 (各 4 回)
#   G3: 差の出た単独 range 0x409c80-0x409ed8 (B の 111 番目。function_409c80) を
#       on=ASLR 有効 / off=ASLR 無効 (setarch -R) / tc=ASLR 無効 + glibc.malloc.tcache_count=0 で各 4 回
# 使い方: M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_stage_2577.sh
# 前提: work/boot_ranges.txt (work-m11)。出力は work/uselist_2577/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source ../shared/env.sh   # FL_WIN64_DIR
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
RETDEC_BIN="${RETDEC:-$(command -v retdec-decompiler || true)}"
[ -n "$RETDEC_BIN" ] || RETDEC_BIN="${RETDEC_ROOT:-}/bin/retdec-decompiler"
[ -x "$RETDEC_BIN" ] || { echo "FAIL: retdec-decompiler 無し (RETDEC か PATH・RETDEC_ROOT で指定)" >&2; exit 1; }
[ -f "$PE" ] || { echo "FAIL: PE 無し: $PE" >&2; exit 1; }
[ -f work/boot_ranges.txt ] || { echo "FAIL: work/boot_ranges.txt 無し (work-m11 を展開)" >&2; exit 1; }
OUT="$HERE/work/uselist_2577"
rm -rf "$OUT"; mkdir -p "$OUT/tmp"
export TMPDIR="$OUT/tmp"
ALL="$(tr ',' '\n' < work/boot_ranges.txt | sed -n '1,150p')"
A="$(sed -n '1,75p' <<< "$ALL" | paste -sd, -)"
B="$(sed -n '76,150p' <<< "$ALL" | paste -sd, -)"
B1="$(sed -n '76,112p' <<< "$ALL" | paste -sd, -)"
B2="$(sed -n '113,150p' <<< "$ALL" | paste -sd, -)"
ALL="$(paste -sd, <<< "$ALL")"
SINGLE="0x409c80-0x409ed8"
SUM="$OUT/summary.tsv"
printf 'group\tlabel\trc\tsec\tload1\tll_md5\tll_nodirective_md5\tdirectives\n' > "$SUM"

run() { # run <group> <label> <ranges> <mode: plain|noopts|on|off|tc> [<extra arg>]
  local group="$1" label="$2" rng="$3" mode="$4" wrap="" tun="" rc=0 t0 t1 extra=""
  case "$mode" in
    noopts) extra="--backend-no-opts" ;;
    off)    wrap="setarch x86_64 -R" ;;
    tc)     wrap="setarch x86_64 -R"; tun="glibc.malloc.tcache_count=0" ;;
  esac
  local load; load="$(cut -d' ' -f1 /proc/loadavg)"
  t0="$(date +%s.%N)"
  env ${tun:+GLIBC_TUNABLES=$tun} $wrap "$RETDEC_BIN" "$PE" -o "$OUT/$label.c" \
    --select-ranges "$rng" --select-decode-only --timeout 250 $extra > "$OUT/$label.log" 2>&1 || rc=$?
  t1="$(date +%s.%N)"
  local ll="$OUT/$label.ll" md5="-" nd="-" dir="-"
  if [ -f "$ll" ]; then
    md5="$(md5sum < "$ll" | cut -c1-8)"
    nd="$(grep -v 'uselistorder' "$ll" | md5sum | cut -c1-8)"
    dir="$(grep -c 'uselistorder' "$ll" || true)"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$group" "$label" "$rc" \
    "$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", b-a}')" "$load" "$md5" "$nd" "$dir" >> "$SUM"
}

for i in 1 2 3; do run G1 "G1-noopts$i" "$ALL" noopts; done
for i in 1 2 3 4; do
  run G2-A  "G2-A$i"   "$A"  plain
  run G2-B  "G2-B$i"   "$B"  plain
  run G2-B1 "G2-B1-$i" "$B1" plain
  run G2-B2 "G2-B2-$i" "$B2" plain
done
for m in on off tc; do
  for i in 1 2 3 4; do run "G3-$m" "G3-$m$i" "$SINGLE" "$m"; done
done

# G4: 出力名の長さだけを変える (相対名 9 字と 17 字)。ASLR 無効・env -i・各 2 回。
#     --backend-no-opts と --print-after-all (stderr 全体の md5) も同じ 2 条件で比べる。
G4="$OUT/g4"; mkdir -p "$G4"
g4run() { # g4run <len> <tag> [extra arg]
  local n="$1" tag="$2" extra="${3:-}" name base
  name="$(printf 'q%.0s' $(seq 1 $((n-2)))).c"; base="${name%.c}"
  rm -f "$G4/$base.ll"
  ( cd "$G4" && env -i PATH=/usr/bin:/bin TMPDIR="$OUT/tmp" setarch x86_64 -R timeout 250 "$RETDEC_BIN" "$PE" \
      -o "$name" --select-ranges "$SINGLE" --select-decode-only --timeout 100 $extra > "$G4/$base.$tag.log" 2> "$G4/$base.$tag.err" ) || true
  printf 'G4\t%s\tlen=%s\tll=%s\terr_md5=%s\n' "$tag" "$n" "$(md5sum < "$G4/$base.ll" 2>/dev/null | cut -c1-8)" \
    "$(md5sum < "$G4/$base.$tag.err" | cut -c1-8)" >> "$G4/g4.tsv"
}
: > "$G4/g4.tsv"
for i in 1 2; do for n in 9 17; do g4run "$n" "plain$i"; done; done
for i in 1 2; do for n in 9 17; do g4run "$n" "noopts$i" "--backend-no-opts"; done; done
for n in 9 17; do g4run "$n" "printall" "--print-after-all"; done
echo "== G4 (出力名の長さ・ASLR 無効・env -i。ll=.ll の md5、err_md5=stderr 全体の md5)"
cat "$G4/g4.tsv"

echo "== summary (group / label / rc / sec / load1 / ll md5 / 指示行を除いた md5 / 指示行数)"
cat "$SUM"
echo "== distinct .ll md5 per group"
awk -F'\t' 'NR>1 && $6!="-" {k=$1"\t"$6; if(!(k in s)){s[k]=1; c[$1]++}} END{for(g in c) printf "%s\t%d\n", g, c[g]}' "$SUM" | sort
echo "== distinct md5 excluding directives per group (1 なら差は指示行だけ)"
awk -F'\t' 'NR>1 && $7!="-" {k=$1"\t"$7; if(!(k in s)){s[k]=1; c[$1]++}} END{for(g in c) printf "%s\t%d\n", g, c[g]}' "$SUM" | sort
if [ -f "$OUT/G3-on1.ll" ] && [ -f "$OUT/G3-off1.ll" ]; then
  echo "== G3 on1 と off1 の差 (指示行)"
  diff "$OUT/G3-on1.ll" "$OUT/G3-off1.ll" || true
fi
