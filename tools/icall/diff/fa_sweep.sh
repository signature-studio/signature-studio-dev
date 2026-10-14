#!/usr/bin/env bash
# fa_sweep.sh — Fresh Air SlateCore closure の全関数 (work/rt_freshair-core/map.json の func_map) を
#   fa_cmp.py で 1 関数ずつ別プロセス実行する (native の SIGSEGV で全体が落ちないように)。
#   出力: work/fa_route/sweep.jsonl (1 行 1 関数)。判定集計は REPORT_APPENDIX_*.md 側で行う。
#   用法: bash tools/icall/diff/fa_sweep.sh [N] [timeout秒]
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/../.."
N="${1:-8}"; TO="${2:-60}"
MAP="$HERE/../work/rt_freshair-core/map.json"
OUT="$HERE/../work/fa_route/sweep.jsonl"; : > "$OUT"
for va in $(python3 -c "import json,sys;print(' '.join(k[2:] for k in json.load(open(sys.argv[1]))['func_map']))" "$MAP"); do
  line="$(timeout "$TO" python3 "$HERE/fa_cmp.py" "$va" --n "$N" 2>/dev/null | tail -1)"
  if [ -z "$line" ]; then line="{\"va\": \"0x$va\", \"status\": \"crash_or_timeout\"}"; fi
  echo "$line" >> "$OUT"
done
python3 - "$OUT" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
rows = [r[0] if isinstance(r, list) else r for r in rows]
ok = [r for r in rows if r.get('status') is None and r.get('n') and r['mismatch'] == 0 and r['native_err'] == 0 and r['wasm_err'] == 0]
bad = [r for r in rows if r not in ok]
print('funcs', len(rows), 'bit-match', len(ok), 'other', len(bad))
PY
