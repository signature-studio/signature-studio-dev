#!/usr/bin/env python3
"""fw_retw.py — lifted define の各 ret に「戻り値 → BLK+0x80/+0x88 store」を挿入する (CAB-195).

背景 (icall ABI の既定): icall_rewrite は全 call site (direct 含む) の後ろに
`mov rax,[BLK+0x80]; movsd xmm0,[BLK+0x88]` (abi_ret_load) を置く。間接 call は
__icall_dispatch が f() の wasm 戻り値を BLK+0x80 に store するが、**direct call は
誰も BLK+0x80 に書かない** (lifted define は `ret i64 %v` で wasm 戻り値として返すのみ。
icall_rewrite の abi_ret_store は機械語では 256 ret しか適用されておらず、lift IR には
BLK+0x80 への store が 0 個 — fw_flat4_canon3.ll 実測)。その結果 direct call の戻り値は
呼び出し側が読む BLK+0x80 に流れず、CreatePlugInstance→ctor 連鎖の版チェック (al) 等が
垃圾値になる (CAB-195 で実測)。

本 pass は各 define の全 `ret` 直前に戻り値の BLK store を挿入する:
  ret i64/i32/i16/i8/i1 %v → zext i64 して BLK+0x80
  ret ptr %v              → ptr のまま BLK+0x80 (memory は untyped)
  ret i128 %v             → low64 を BLK+0x80 と BLK+0x88 に (fw_table.py w_ wrapper と同一規約)
  ret double/float %v     → BLK+0x88 (xmm0 戻り規約)
  ret void                → 何もしない (呼び出し側は rax を使わない)

  python3 fw_retw.py in.ll out.ll --blk 0x8A1000 [--report json]
          [--only-range LO:HI ...]

スコープ (--only-range): store 挿入を define VA の範囲に限定する。既定は全 define。
  CAB-195 実測: 全 define への適用は framework smoke の unit init #16 経路 (誤
  decode mosaic 領域) で分岐が変わり OOB trap、0x6b8000..0x6c2000 への適用でも
  unit 17 以降へ進んで stack overflow した (fw_run.mjs で再現、canon3 は PASS)。
  ゆえに plugin 連鎖の検証ビルド (hostshim/hs_e2e.sh) では、消費が実測された
  戻り値 (--only-range 0x6be800:0x6be801 = TTestPlug.Create の戻り TFruityPlug*)
  に限定して適用する。
"""
import argparse, re, json

RT = {'i64': 'i64', 'i32': 'i32', 'i16': 'i16', 'i8': 'i8', 'i1': 'i1'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--blk', type=lambda x: int(x, 0), default=0x8A1000)
    ap.add_argument('--report')
    ap.add_argument('--only-range', action='append', default=[],
                    help='define VA 範囲 LO:HI (16進可) — この範囲の define のみ store を挿入')
    a = ap.parse_args()
    RANGES = []
    for r in a.only_range:
        lo, _, hi = r.partition(':')
        RANGES.append((int(lo, 0), int(hi, 0)))
    RAX = a.blk + 0x80
    XMM = a.blk + 0x88
    uid = [0]

    def store(val, addr, ty='i64'):
        return '  store %s %s, ptr inttoptr (i64 %d to ptr), align 8' % (ty, val, addr)

    out = []
    n_ins = 0
    n_skip = 0
    by = {}
    cur = None
    curva = None
    with open(a.src, errors='replace') as f:
        for line in f:
            if line.startswith('define '):
                cur = line.split('@')[1].split('(')[0] if '@' in line else '?'
                mv2 = re.match(r'define \S+ @function_([0-9a-f]+)\(', line)
                curva = int(mv2.group(1), 16) if mv2 else None
            m = re.match(r'^(\s*)ret (i128|i64|i32|i16|i8|i1|ptr|float|double|void)(?: (.*?))?(\s*)$', line.rstrip('\n'))
            if not m or line.lstrip().startswith('declare'):
                out.append(line.rstrip('\n'))
                continue
            if RANGES and (curva is None or not any(lo <= curva < hi for lo, hi in RANGES)):
                out.append(line.rstrip('\n'))
                n_skip += 1
                continue
            ind, ty, val = m.group(1), m.group(2), (m.group(3) or '').strip()
            # metadata suffix を分離 (先 token 以降の全て)
            meta = ''
            mv = re.match(r'^([^,\s]+)(.*)$', val)
            if mv:
                val, meta = mv.group(1), mv.group(2)
            if ty == 'void' or val == '' or val.startswith('void'):
                out.append(line.rstrip('\n'))
                continue
            ins = []
            if ty == 'i128':
                uid[0] += 1
                lo = '%%fwretlo%d' % uid[0]
                ins.append('  %s = trunc i128 %s to i64' % (lo, val))
                ins.append(store(lo, RAX))
                ins.append(store(lo, XMM))
            elif ty in RT:
                if ty == 'i64':
                    ins.append(store(val, RAX))
                else:
                    uid[0] += 1
                    z = '%%fwretz%d' % uid[0]
                    ins.append('  %s = zext %s %s to i64' % (z, ty, val))
                    ins.append(store(z, RAX))
            elif ty == 'ptr':
                ins.append(store(val, RAX, 'ptr'))
            elif ty == 'double':
                ins.append(store(val, XMM, 'double'))
            elif ty == 'float':
                ins.append(store(val, XMM, 'float'))
            out.extend(ins)
            out.append(ind + 'ret ' + ty + (' ' + val if val else '') + meta)
            n_ins += 1
            by[ty] = by.get(ty, 0) + 1
    open(a.dst, 'w').write('\n'.join(out) + '\n')
    rep = {'rets_patched': n_ins, 'rets_skipped_out_of_range': n_skip, 'ranges': ['%x:%x' % (lo, hi) for lo, hi in RANGES],
           'by_type': by, 'blk_rax': RAX, 'blk_xmm': XMM}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[retw] rets patched %d (skipped %d out of range) %s -> %s' % (n_ins, n_skip, by, a.dst))


if __name__ == '__main__':
    main()
