#!/usr/bin/env bash
# slot_trace.sh — SlateCore.core_64 の closure 131 関数を 1 関数 1 プロセスで走らせ、.data zero-fill 域への
#   実行時アクセス (encoded slot 候補) を集計する (ICALL-59 / #2120)。
#   前提: $FA_DL に plugins-freshair を展開済み (fetch.sh で work/win/Fresh Air ができていること)。
#   出力: work/slot_trace_enc.txt (F 行 = 関数ごとの rc と ACC 件数, ACC 行 = <fn> ACC <addr> <rip> <count>)。
#   用法: bash tools/icall/diff/slot_trace.sh [SLOT_ENC_INIT=1 を付けると enc(NULL)=cookie を事前に敷く]
#   SLOT_T2_INIT=1 を併せると、T2 の 34 entry も enc(NULL)=cookie で敷く (CRT 初期化 0x18105ea78 の終状態)。既定は敷かない。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/../.."
FA="$T/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
MAP="$T/icall/work/rt_freshair-core/map.json"
BIN="$T/icall/work/slot_trace"
OUT="$T/icall/work/slot_trace_enc.txt"
ERR="$T/icall/work/slot_trace_err.txt"
ERR_OUT="$T/icall/work/slot_trace_fatal.txt"
gcc -O1 -g -o "$BIN" "$HERE/slot_trace.c" "$T/ott/native/ms_call.S" -lm || exit 1
: > "$OUT"; : > "$ERR_OUT"
for va in $(python3 -c "import json,sys;print(' '.join(k[2:] for k in json.load(open(sys.argv[1]))['func_map']))" "$MAP"); do
  r="$(SLOT_ENC_INIT="${SLOT_ENC_INIT:-}" timeout 10 "$BIN" "$FA" "$va" 2>"$ERR")"; rc=$?
  echo "F $va rc=$rc $(echo "$r" | grep -c ACC)" >> "$OUT"
  grep -E 'fatal|regs|heap_args' "$ERR" | sed "s/^/$va /" >> "$ERR_OUT"
  echo "$r" | grep ACC | sed "s/^/$va /" >> "$OUT"
done
python3 - "$OUT" <<'PY'
import sys
known = {0x1813068d0,0x1813068f8,0x181306900,0x181306908,0x181306910,0x1813072b0,0x1813073f0,0x1813073f8,
         0x181307400,0x181307408,0x181307410,0x181307418}
rc, acc = {}, set()
for l in open(sys.argv[1]):
    p = l.split()
    if p[:1] == ['F']: rc[p[2]] = rc.get(p[2], 0) + 1
    elif len(p) >= 4 and p[1] == 'ACC': acc.add(int(p[2], 16))
print('funcs', sum(rc.values()), 'exit', dict(sorted(rc.items())))
print('distinct zero-fill addrs', len(acc), ' '.join(hex(a) for a in sorted(acc)))
print('known 12 hit', len(acc & known), 'miss', len(known - acc))
# T1 (module handle 表, 20 entry)・T2 (encoded 関数ポインタ表, 34 entry) の index 別読出し (静的な終点は REPORT_APPENDIX_2225 §2.5)
TABLES = {'T1': (0x181307100, 0x1813071a0, 20), 'T2': (0x1813071a0, 0x1813072b0, 34)}
idx = {}
for l in open(sys.argv[1]):
    p = l.split()
    if len(p) >= 5 and p[1] == 'ACC':
        a = int(p[2], 16)
        for name, (lo, hi, n) in TABLES.items():
            if lo <= a < hi: idx.setdefault(name, {}).setdefault((a - lo) // 8, set()).add((hex(a), '0x' + p[3]))
for name, (lo, hi, n) in TABLES.items():
    hit = idx.get(name, {})
    for i in sorted(hit): print(name, 'index', i, sorted(hit[i]))
    top = max(hit) if hit else None
    print(name, 'static entry', n, 'distinct read', len(hit), 'max read', top, 'static max', n - 1,
          'gap', (n - 1 - top) if top is not None else 'n/a (no read)')
PY
