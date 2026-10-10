#!/usr/bin/env python3
"""fw_cab129.py — alloca 縮退 (CAB-129) の targeted IR 修復.

m11 で実証された欠陥クラス: RetDec が `rep stosq` ×N (レコード初期化) の宛先フレームを
`alloca i64` (8B) に潰す → フィールド書込みが wasm shadow stack を破壊 (m11: 44bb70 の
0x188=392B レコードで unit #18 が OOB; C 転記実験で 392B 配列化すると消えた = 実証済)。

本 pass は同一判定を IR 静的に行い, 露出関数の縮退 alloca を fill サイズへ拡大する:
  1. 関数内の `call void @__asm_rep_stosq*(ptr dest, ... i64 LEN)` と大容量
     `llvm.memset...(ptr dest, ..., i64 LEN>64)` を収集
  2. dest を SSA で逆向きに辿り (reg2mem reload → store された値 → alloca) 元 alloca を特定
  3. その alloca の型サイズ < LEN なら `alloca [K x i64], align 8` (K=ceil(LEN/8)) に拡大
     (ポインタ使用はopaque/typedを問わず先頭アドレス互換; フィールド GEP は alloca 先頭 base のため無影響)

  python3 fw_cab129.py IN.ll OUT.ll [--report r.json]
"""
import argparse, json, re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report')
    ap.add_argument('--max-grow', type=int, default=1 << 20, help='拡大上限 (安全弁)')
    a = ap.parse_args()
    lines = open(a.src, errors='replace').read().split('\n')
    out = list(lines)
    fixed = []
    # 関数スライス
    starts = [i for i, l in enumerate(lines) if l.startswith('define ')]
    starts.append(len(lines))
    for si in range(len(starts) - 1):
        lo, hi = starts[si], starts[si + 1]
        body = lines[lo:hi]
        head = body[0]
        # 1. 大容量 fill 収集
        fills = []
        for j, l in enumerate(body):
            m = re.search(r'call void @__asm_rep_stosq\w*\(([^)]*)\)', l)
            if m:
                cargs = [x.strip() for x in m.group(1).split(',') if x.strip()]
                if len(cargs) >= 3:
                    d0 = cargs[0]
                    if '%' in d0:
                        d0 = d0[d0.rindex('%'):]
                    ln = cargs[-1].split()[-1]
                    if ln.lstrip('-').isdigit():
                        fills.append((j, d0, int(ln) * 8))
                continue
            m = re.search(r'call void @llvm\.memset[^,]*\(([^,]+), [^,]+, (i64 (\d+)|i64 %[\w.-]+)', l)
            if m and m.group(3) and int(m.group(3)) > 64:
                fills.append((j, m.group(1).strip(), int(m.group(3))))
        if not fills:
            continue
        # 2. alloca 行索引 (def 行番号 → サイズ)
        alloca_sz = {}
        for j, l in enumerate(body):
            m = re.match(r'\s*(%[\w.-]+) = alloca ([^,]+)', l)
            if m:
                ty = m.group(2).strip()
                sz = 0
                ma = re.match(r'\[(\d+) x ([\w]+)\]', ty)
                if ma:
                    base = {'i64': 8, 'i32': 4, 'i16': 2, 'i8': 1, 'double': 8, 'float': 4, 'ptr': 4}.get(ma.group(2), 0)
                    sz = base * int(ma.group(1))
                else:
                    sz = {'i64': 8, 'i32': 4, 'i16': 2, 'i8': 1, 'double': 8, 'float': 4, 'ptr': 4}.get(ty, 0)
                alloca_sz[j] = (m.group(1), sz, ty)
        # SSA name → def 行
        defrow = {}
        for j, l in enumerate(body):
            m = re.match(r'\s*(%[\w.-]+) = ', l)
            if m and m.group(1) not in defrow:
                defrow[m.group(1)] = j
        # 3. dest を逆向きに辿る
        changed = set()
        for j, dest, need in fills:
            seen = 0
            cur = dest
            # 直接 alloca ポインタ or reg2mem 経由 (最大 6 hop)
            while seen < 6:
                seen += 1
                dm = re.match(r'%([\w.-]+)$', cur)
                if not dm:
                    break
                nm = '%' + dm.group(1)
                dj = defrow.get(nm)
                if dj is None:
                    break
                dl = body[dj]
                am = re.match(r'\s*(%[\w.-]+) = alloca ', dl)
                if am:
                    for aj, (an, asz, aty) in alloca_sz.items():
                        if an == am.group(1) and asz < need and need <= a.max_grow:
                            # 拡大 (K x i64)
                            k = (need + 7) // 8
                            body[dj] = re.sub(r'= alloca [^,]+(, align \d+)?',
                                              '= alloca [%d x i64], align 8' % k, dl, count=1)
                            changed.add((am.group(1), asz, need))
                            break
                    break
                # bitcast 経路: %v = bitcast ptr %X to ptr → %X を追う
                bm = re.match(r'\s*(?:%[\w.-]+) = bitcast \w+ (%[\w.-]+) to', dl)
                if bm:
                    cur = bm.group(1)
                    continue
                # reg2mem reload: %v = load ptr, ptr %X.reg2mem → store 行を探す
                lm = re.match(r'\s*(%[\w.-]+) = load \w+, (?:ptr|%[\w.-]+\*) (%[\w.-]+)', dl)
                if lm:
                    src_slot = lm.group(2)
                    st = None
                    for k2 in range(dj - 1, max(-1, dj - 400), -1):
                        sm = re.match(r'\s*store (?:ptr|%[\w.-]+) (%[\w.-]+), (?:ptr|%[\w.-]+\*) ' +
                                      re.escape(src_slot) + r'\s*$', body[k2])
                        if sm:
                            st = sm.group(1)
                            break
                    if st:
                        cur = st
                        continue
                break
        if changed:
            out[lo:hi] = body
            fixed.append({'fn': re.search(r'@function_([0-9a-f]+)', head).group(1), 'grown': sorted(changed)})
    open(a.dst, 'w').write('\n'.join(out))
    if a.report:
        json.dump(fixed, open(a.report, 'w'), indent=1)
    print('[cab129] grown allocas: %d functions %s' % (len(fixed), [f['fn'] for f in fixed]))


if __name__ == '__main__':
    main()
