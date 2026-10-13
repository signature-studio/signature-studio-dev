#!/usr/bin/env python3
"""evidence_check.py — evidence/*.c (Ghidra decompile) の文面から REPORT の主張を検査する (h10_check.py の PE 解析とは別経路).

usage: evidence_check.py <evidence_dir> [--break <key>]   (key: d4use | callers | ext)
"""
import re, sys
from pathlib import Path

ev = Path(sys.argv[1])
brk = sys.argv[sys.argv.index('--break') + 1] if '--break' in sys.argv else None
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        fails += 1


load = (ev / 'fw_state_load.c').read_text()
resolve = (ev / 'fw_resolve.c').read_text()
callers = (ev / 'fw_ctor_callers.txt').read_text()

# record 57 の実体 local_d4: 宣言 + 既定値 1 + 読込 (record 0x39) + 使用 1 箇所 (param_1+0x8a0 へ格納) の計 4 出現のみ
n = len(re.findall(r'\blocal_d4\b', load))
if brk == 'd4use':
    n += 1
check('record 57 (local_d4): 出現は 4 件 (宣言 / 既定値 1 / record 0x39 読込 / +0x8a0 へ格納) のみ', n == 4, f'occurrences={n}')
check('record 57: 既定値 local_d4 = 1', re.search(r'local_d4 = 1;', load) is not None)
m = re.search(r'if \(bVar16\) \{\s*\n\s*bVar3 = bVar3 \| 0x80;\s*\n\s*\*\(int \*\)\(param_1 \+ 0x89c\) = local_91;\s*\n\s*\*\(undefined4 \*\)\(param_1 \+ 0x8a0\) = local_d4;', load)
check('record 57 / 51 の格納 (+0x8a0 / +0x89c) は bitness 不一致 (bVar16) 分岐の中だけ', m is not None)
m = re.search(r'bVar16 = false;\s*\n\s*if \(\(local_74 & 0x100000\) == 0x100000\) \{\s*\n\s*bVar16 = \(\(local_74 & 0x400\) == 0x400\) !=\s*\n\s*\(\*\(char \*\)\(\*\(longlong \*\)\(param_1 \+ 0x5064\) \+ 0x2d\) == \'\\x03\'\);', load)
check('bVar16 = (flags&0x100000) && ((flags&0x400) != host64) — record 2 の bitness 判定', m is not None)
check('record 2 flags 0x400000 → 個別 option bit を適用しない (lVar7+0x18 = bVar16 / if (!bVar16) …)',
      re.search(r'bVar16 = \(local_74 & 0x400000\) == 0x400000;\s*\n\s*lVar7 = \*\(longlong \*\)\(param_1 \+ 0x874\);\s*\n\s*\*\(bool \*\)\(lVar7 \+ 0x18\) = bVar16;\s*\n\s*if \(!bVar16\) \{', load) is not None)
check('version 検査: local_24 < 0xd かつ != -1 のとき処理、>= 0xd は error 5', re.search(r'if \(local_24 < 0xd\) \{\s*\n\s*if \(local_24 != -1\)', load) is not None
      and re.search(r'FUN_007924d0\(uVar2,5,0,0\)', load) is not None)
check('version 5 以上は FUN_00875af0 (record loop)、4 以下は FUN_00875800 (legacy)', re.search(r'if \(local_24 < 5\) \{\s*\n\s*local_25 = FUN_00875800.*\n\s*\}\s*\n\s*else \{\s*\n\s*local_25 = FUN_00875af0', load) is not None)
check('reader が false を返すと raw stream を +0xf6c に保持 (state を失わない)', re.search(r"if \(local_25 == '\\0'\) \{", load) is not None and '*(undefined8 *)(param_1 + 0xf6c) = uVar2;' in load)

# host への問い合わせ書式 (msg 7)
for tok in ('|class=%d', '|name=%s', '|vstid=%d', '|guid=%s', '|id=%s'):
    check(f'host query 書式に {tok}', tok in resolve)
exts = {'.vst3': 'L".vst3"', '.component': 'L".component"', '.clap': 'L".clap"', '.dll': 'L".dll"'}
for e, tok in exts.items():
    check(f'拡張子付与に {e}', (tok if brk != 'ext' else 'XXX') in resolve)
check('host へ送る message id = 7 (FL host 問い合わせ)', len(re.findall(r',7,', resolve)) >= 3 or len(re.findall(r'\),7,', resolve)) >= 1)

# ctor 呼出元
direct = [l for l in callers.split('=== refsto 87c980')[0].splitlines() if 'UNCONDITIONAL_CALL' in l]
if brk == 'callers':
    direct.append('  from 00000000 in ? UNCONDITIONAL_CALL')
check('TVSTPlugin ctor (fw:0x7a9db0) の直接 call は 1 件 (fw:0x87c9ad)、他は .pdata の DATA 参照のみ', len(direct) == 1 and '0087c9ad' in direct[0], direct[0].strip() if direct else '')

print(f'\nSUMMARY evidence checks fails={fails} break={brk}')
sys.exit((0 if fails > 0 else 1) if brk else (1 if fails else 0))
