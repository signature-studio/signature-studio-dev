#!/usr/bin/env python3
"""probe_942_obj.py: unit 53・87・138 の trap 上流 (IR 8cbb00 → 418210 → C 418190) で、dest の旧値の由来を記録する IR 変種を作る (#942 受入 1・2, 診断用)。
 使い方: python3 probe_942_obj.py <base.ll> <out.ll>
 記録先は線形メモリ固定番地 PROBE2_BASE + k*SLOT2 (k = SITES の番号): +0 hit 回数, +8/+16/+24/+32 = arg1..arg4 (entry 時点; ptr は ptrtoint, i32 は sext),
 +48 = 記録点の値 (PROBE_LOAD で指定した箇所で読んだ 64bit)。記録は unit 内で各記録点の最後の hit (後の呼出しで上書きされる)。読み方は trap_obj_942.mjs。"""
import re, sys

PROBE2_BASE = 0x11FFE000
SLOT2 = 128
# (関数名, 記録の挿入位置の正規表現 (None なら entry 直後), 読む値の IR 変数名 (None なら読まない))
SITES = [
    ('function_8cbb00', None, None),                                            # entry 引数・[arg1+8]
    ('function_8cbb00', r'call i64 @function_418210\(i64 %__m11c_3060', '%__m11c_3060'),  # 418210 呼出し直前の stack_var (dest)
    ('function_418210', r'call i64 @function_418190\(i64 %arg1, i64 %arg3, i64 %arg3\)', '%arg1'),  # 418190 呼出し直前の *arg1
    ('function_8cbcb0', None, None),
]


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    for k, (name, pat, var) in enumerate(SITES):
        i = next(j for j, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(name), l))
        m = re.match(r'^define .*@%s\((.*)\) ' % re.escape(name), lines[i])
        types = [a.strip().split()[0] for a in m.group(1).split(',') if a.strip()]
        j = next(j for j in range(i + 1, len(lines)) if re.match(r'^[A-Za-z0-9_.$-]+:', lines[j]))
        e = next(e for e in range(j, len(lines)) if lines[e] == '}')
        base = PROBE2_BASE + k * SLOT2
        hdr = [
            '  %%dbg%d_b = inttoptr i64 %d to ptr' % (k, base),
            '  %%dbg%d_h = load i64, ptr %%dbg%d_b, align 8' % (k, k),
            '  %%dbg%d_h1 = add i64 %%dbg%d_h, 1' % (k, k),
            '  store i64 %%dbg%d_h1, ptr %%dbg%d_b, align 8' % (k, k),
        ]
        if pat is None:
            ins = list(hdr)
            for a, t in enumerate(types, 1):
                v = '%%arg%d' % a
                if t == 'ptr':
                    ins.append('  %%dbg%d_v%d = ptrtoint ptr %s to i64' % (k, a, v))
                    v = '%%dbg%d_v%d' % (k, a)
                elif t == 'i32':
                    ins.append('  %%dbg%d_v%d = sext i32 %s to i64' % (k, a, v))
                    v = '%%dbg%d_v%d' % (k, a)
                ins.append('  %%dbg%d_p%d = getelementptr i8, ptr %%dbg%d_b, i64 %d' % (k, a, k, 8 * a))
                ins.append('  store i64 %s, ptr %%dbg%d_p%d, align 8' % (v, k, a))
            if var is None and name == 'function_8cbb00':
                ins += [
                    '  %%dbg%d_fa = add i64 %%arg1, 8' % k,
                    '  %%dbg%d_fp = inttoptr i64 %%dbg%d_fa to ptr' % (k, k),
                    '  %%dbg%d_fv = load i64, ptr %%dbg%d_fp, align 8' % (k, k),
                    '  %%dbg%d_fb = getelementptr i8, ptr %%dbg%d_b, i64 48' % (k, k),
                    '  store i64 %%dbg%d_fv, ptr %%dbg%d_fb, align 8' % (k, k),
                ]
            lines[j + 1:j + 1] = ins
        else:
            c = next(c for c in range(j, e) if re.search(pat, lines[c]))
            ins = list(hdr) + [
                '  %%dbg%d_pa = inttoptr i64 %s to ptr' % (k, var),
                '  %%dbg%d_pv = load i64, ptr %%dbg%d_pa, align 8' % (k, k),
                '  %%dbg%d_pb = getelementptr i8, ptr %%dbg%d_b, i64 48' % (k, k),
                '  store i64 %%dbg%d_pv, ptr %%dbg%d_pb, align 8' % (k, k),
            ]
            lines[c:c] = ins
        print('[probe_942_obj] site %d %s at %s slot=0x%x' % (k, name, pat or 'entry', base))
    open(dst, 'w').write('\n'.join(lines))
    print('[probe_942_obj] %d sites -> %s' % (len(SITES), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
