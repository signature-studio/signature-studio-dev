#!/usr/bin/env bash
# M11-N20 (#565): WNDCLASS 静的実体の WNDPROC を closure に加える (自動生成)。
#   PE の WNDCLASS 走査 (m11_wndclass_scan.py) → closure 外 WNDPROC + call/jmp 閉包の ranges → RetDec lift (boot5) → gen_ir2 → 検査
#   bash tools/m11/m11_wndseed.sh        (所要: lift 約 2 分 + gen_ir2 約 30 秒。boot0..4 が work/ にあること)
# 前提: capstone / pefile (python3)、/opt/retdec、PE (FL_WIN64_DIR/extracted/block00031_PE.bin。m11_gen_ir2.sh と同じ /home/ubuntu/... 固定パスにも symlink 要)
set -euo pipefail
cd "$(dirname "$0")"
PE="${PE:-${FL_WIN64_DIR:-/home/ubuntu/work/analysis/win64}/extracted/block00031_PE.bin}"
[ -f "$PE" ] || { echo "[wndseed] PE 無し: $PE" >&2; exit 2; }
for i in 0 1 2 3 4; do [ -f work/boot$i.lift.ll ] || { echo "[wndseed] work/boot$i.lift.ll 無し (work-m11 素材)" >&2; exit 2; }; done
mkdir -p results
# 基準は常に boot0..4 (boot5 取込後に再実行しても同じ ranges になる = 冪等)
python3 m11_wndclass_scan.py --pe "$PE" --json-out results/wndclass_scan.json --ranges-out work/boot_ranges_wnd.txt -q
bash m11_lift.sh work/boot_ranges_wnd.txt boot5 900
bash m11_gen_ir2.sh
python3 m11_wndclass_scan.py --pe "$PE" --check --min-instances 11
