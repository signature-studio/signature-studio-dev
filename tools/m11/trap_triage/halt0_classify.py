#!/usr/bin/env python3
"""halt0 unit を Error() 呼出元 (wasm 名前付き frame) で分類し件数表を出す独立集計 (#417).
使い方: python3 halt0_classify.py <per-unit.json> [...]   (survey_units.mjs の出力)
注意: frame は wasm-function[index] で、index は build ごとに変わる。JSON は「それを出力した時点の wasm」でのみ名前解決できる
      (古い JSON を現在の wasm で引くと別名に化ける)。分類は survey 直後に実行すること。
frame 列 (frames[0]=Halt0 側) から 409730 / 412a60 の直上 frame を「Error() 呼出元」とし, 原因クラスへ写像する。"""
import json, re, sys, os, collections
ns = {'__file__': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'annotate.py')}
sys.argv, argv = ['x', 'x'], sys.argv
exec(open(ns['__file__']).read().split('per = json.load')[0], ns)
names = ns['names']
def nm(f):
    m = re.search(r'wasm-function\[(\d+)\]', f)
    return names.get(int(m.group(1)), '?').replace('function_', '') if m else f
CLS = {  # Error() 呼出元 -> 原因 (実測で確認した範囲のみ。DEFECTS.md への採番はしない)
    '40a1c0': 'FP 例外送出: GetMXCSR (40a3b0) が 0 を返す (IR は `__asm_stmxcsr(0); ret 0`, pop rax 脱落) → #417 で override',
    '4159e0': 'InitializeArray: 型 kind バイトの load 脱落 → default 分岐 Error(2) → #417 で override',
    '416db0': 'CopyArray: 同上 (+ kind 12 の間接 call 脱落) → #417 で override',
    '417b70': 'DynArraySetLength: 1 段 deref 脱落 → #414 で override 済',
    '409410': 'GetMem (417b70 波及) → #414 で解消',
    '411d20': 'raise (例外送出)。呼出元 814d30 の IR 定数 `inttoptr i64 <10進 VA>` が LVA 未変換 (§3)',
    '409470': 'ReallocMem (#414 で deref 脱落を確認済・転記は unit 884 でハングし revert)。unit 189 は未解消',
    '410630': 'GetCurrentThreadId と [obj+8] の不一致 → Error(0x19)。unit 492 (ad5700 → 466a40 → 466af0 → 410a50)。原因未特定',
}
SKIP = {'412770', '4128b0__lifted', '4128b0', '412a40', '412a60', '4096b0', '4096d0', '409730'}
def caller(frames):
    for f in (nm(x) for x in frames):
        if f not in SKIP: return f
    return '?'
for p in argv[1:]:
    per = json.load(open(p)); c = collections.defaultdict(list)
    for r in per:
        if r['kind'] == 'halt0': c[caller(r['frames'])].append(r['unit'])
    print('==', p, 'halt0 =', sum(len(v) for v in c.values()))
    for k, v in sorted(c.items(), key=lambda x: -len(x[1])):
        print('%3d  %-8s %s | units %s' % (len(v), k, CLS.get(k, '未分類'), v))
