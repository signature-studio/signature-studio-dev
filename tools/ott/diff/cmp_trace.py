"""cmp_trace.py nat.json wasm.json [--all]: entry trace の最初の乖離を報告。
   VA 同一 + 引数 (image ptr 正規化) 比較。native の hook は wasm 側 C 実装関数も含み得るので, 両側 hook 集合の積に限定。"""
import sys, json
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
def nq(h):
    q = int(h, 16)
    if 0x180000000 <= q < 0x180400000: q -= 0x150000000
    return q
A = [(int(r[0], 16), [nq(x) for x in r[1:5]]) for r in a['trace']]
B = [(int(r[0], 16), [nq(x) for x in r[1:5]]) for r in b['trace']]
# wasm VA は 0x18xxxxxxx (整数) そのまま
print('nat records', len(A), 'wasm records', len(B))
inter = {v for v, _ in A} & {v for v, _ in B}
A2 = [(i, v, g) for i, (v, g) in enumerate(A) if v in inter]; B2 = [(i, v, g) for i, (v, g) in enumerate(B) if v in inter]
print('common funcs', len(inter), 'nat common records', len(A2), 'wasm common records', len(B2))
nshow = 0
for k in range(min(len(A2), len(B2))):
    ia, va, ga = A2[k]; ib, vb, gb = B2[k]
    if va != vb:
        print(f'  SEQ DIVERGE at common#{k}: nat #{ia} fn={va:#x} args={[hex(x) for x in ga]}  wasm #{ib} fn={vb:#x} args={[hex(x) for x in gb]}')
        for t in range(max(0,k-6), k): print('    prev', hex(A2[t][1]), [hex(x) for x in A2[t][2]])
        break
    # 引数: 戻り先に依存しない整数引数のみ。ptr 不一致は heap 同一なので厳密比較
    if ga != gb:
        nshow += 1
        if nshow <= 12:
            print(f'  ARG DIFF common#{k} fn={va:#x}: nat={[hex(x) for x in ga]} wasm={[hex(x) for x in gb]}  (nat#{ia} wasm#{ib})')
else:
    print('sequences equal over common prefix; arg diffs:', nshow)
