#!/usr/bin/env python3
"""rep_watch_3972.py (#3972): rep 系 helper (`__asm_rep_movsq_memcpy`・`__asm_rep_movsb_memcpy`・`__asm_rep_stosq_memset`) の
呼出し直前に m11_rep_in(dst, bytes, site) を入れる。store 命令の計装 (watch_store_682.py) と copy (`409c80`) の計装に映らない書込みを
記録するため。C 側 (watch_copy_3972.c) が [WA, WA+32) との重なりを判定し、重なるときだけ `[rp]` 行を出す。
  usage: rep_watch_3972.py <in.ll> <out.ll> <sites.txt>
  sites.txt: `site<TAB>関数名<TAB>IR 行` (site は `[rp] site=K` の K)。入口の計装は call の追加のみ (IR の値・分岐は不変)。"""
import re, sys

src, dst, sites_path = sys.argv[1], sys.argv[2], sys.argv[3]
CALL = re.compile(r'^(\s*)call void @__asm_rep_(movsq_memcpy|movsb_memcpy|stosq_memset)\((ptr (?:nonnull )?(?:inttoptr \(i64 \d+ to ptr\)|%[\w.$-]+|null)), (.*?), (i64 [^,()]+)\)\s*$')
DEF = re.compile(r'^define [^@]*@([\w.$-]+)\(')
out, sites, k = [], [], 0
with open(src, errors='replace') as f:
    lines = f.readlines()
fn = '?'
for idx, line in enumerate(lines):
    m = DEF.match(line)
    if m:
        fn = m.group(1)
    c = CALL.match(line)
    if c:
        ind, kind, a1, _a2, cnt = c.group(1), c.group(2), c.group(3), c.group(4), c.group(5)
        k += 1
        dst_val = re.sub(r'^ptr (nonnull )?', 'ptr ', a1)
        cval = cnt[len('i64 '):]
        mult = 8 if kind.startswith(('movsq', 'stosq')) else 1
        out.append(f'{ind}%m11rp{k}.a = ptrtoint {dst_val} to i64\n')
        out.append(f'{ind}%m11rp{k}.b = mul i64 {cval}, {mult}\n')
        out.append(f'{ind}call void @m11_rep_in(i64 %m11rp{k}.a, i64 %m11rp{k}.b, i64 {k})\n')
        sites.append(f'{k}\t{fn}\t{idx + 1}\t{kind}')
    out.append(line)
if out and not out[-1].endswith('\n'):
    out[-1] += '\n'
out.append('declare void @m11_rep_in(i64, i64, i64)\n')
with open(dst, 'w') as f:
    f.writelines(out)
with open(sites_path, 'w') as f:
    f.write('\n'.join(sites) + '\n')
print(f'[rep_watch_3972] rep helper call hooks: {k}')
if k == 0:
    sys.exit(1)
