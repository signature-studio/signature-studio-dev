#!/usr/bin/env python3
"""compare_dumps.py ORIG.bin LB.bin ORIG.json LB.json — 再配置前 / 再配置後 (OTT module 0 の 500blk×128f 出力 f32 bit) の比較と メモリ表を出力. exit 0 = 差分セルが全て junk-tiny 領域 (|v|<1e-30) 以内."""
import sys, struct, json
ld = lambda p: struct.unpack('<%dI' % (len(open(p, 'rb').read()) // 4), open(p, 'rb').read())
f = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
o, l = ld(sys.argv[1]), ld(sys.argv[2]); jo, jl = json.load(open(sys.argv[3])), json.load(open(sys.argv[4]))
d = [i for i in range(len(o)) if o[i] != l[i]]
mx = max([max(abs(f(o[i])), abs(f(l[i]))) for i in d] or [0])
big = max(abs(f(x)) for x in o if x == x)
print('RetDec chain 自然経路 (obj+0x248=1, 500blk×128f×2ch = %d cell): 再配置前 vs lowbase 差分 %d cell (差分セルの |v|max=%.3g; 全体 |v|max=%.3g = junk 含む)' % (len(o), len(d), mx, big))
mo, ml = jo['mem'], jl['mem']
print('メモリ (OTT×%d): linear memory 1 module %.0f MiB → %.0f MiB, 合計 %.0f → %.0f MiB (+Balance %.0f MiB); VmData(commit) %.0f → %.0f MB (Δ %.0f → %.0f MB); RSS %.0f → %.0f MB' % (
    jo['nmod'], mo['ott_linear_bytes_each'] / 1048576, ml['ott_linear_bytes_each'] / 1048576, mo['ott_linear_bytes_sum'] / 1048576, ml['ott_linear_bytes_sum'] / 1048576, ml['bal_linear_bytes'] / 1048576,
    mo['after_ott']['vmdata'], ml['after_ott']['vmdata'], mo['after_ott']['vmdata'] - mo['base']['vmdata'], ml['after_ott']['vmdata'] - ml['base']['vmdata'], mo['after_run']['rss'], ml['after_run']['rss']))
print('sha256 一致 (module 間, lowbase): %s / 再配置前との一致: %s' % (len(set(jl['ott_sha256'])) == 1, jo['ott_sha256_full'] == jl['ott_sha256_full']))
sys.exit(0 if mx < 1e-30 else 1)
