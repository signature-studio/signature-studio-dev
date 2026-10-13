#!/usr/bin/env python3
"""RetDec が PE の export 名で命名した define を `function_<VA>` に改名する (#707)。

  export_rename.py <final.ll> <PE> <ranges> [--report JSON]

RetDec は export 表に載る関数を export 名 (例: `@CreatePlugInstance`) で出力し、`function_<VA>` で出さない。
関数本体は欠けていないので、改名だけを行う。 改名の対象は、export の VA (ImageBase + RVA) が ranges に含まれ、
かつ final.ll に `define @<export 名>(` がある組だけ。 参照 `@<export 名>` も同じ名前に書き換える。
改名先の `function_<VA>` が既に出力中にある場合は衝突として異常終了する (黙って上書きしない)。
監査 (indirect_defs.py) の定義は変えない。 改名を外すと監査が FAIL する (unr_nega.sh NC7)。
"""
import argparse, json, re, sys
import pefile

ap = argparse.ArgumentParser()
ap.add_argument('ll')
ap.add_argument('pe')
ap.add_argument('ranges')
ap.add_argument('--report', default='')
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
base = pe.OPTIONAL_HEADER.ImageBase
want = {int(r.split('-')[0], 16) for r in open(a.ranges).read().strip().split(',') if r}
exp = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
symbols = exp.symbols if exp is not None else []

text = open(a.ll).read()
out, log = text, {}
for e in symbols:
    if not e.name:
        continue
    name = e.name.decode('ascii', 'replace')
    va = base + e.address
    if va not in want:
        continue
    if not re.search(r'^define [^\n]*@%s\(' % re.escape(name), out, re.M):
        continue
    new = 'function_%x' % va
    if re.search(r'@%s\b' % new, out):
        sys.exit('[export_rename] 改名先 @%s が既に存在する (衝突)' % new)
    out, n = re.subn(r'@%s\b' % re.escape(name), '@' + new, out)
    log[name] = {'va': hex(va), 'new': new, 'refs_renamed': n}

open(a.ll, 'w').write(out)
if a.report:
    json.dump(log, open(a.report, 'w'), indent=1)
print('[export_rename] renamed %d: %s' % (len(log), ', '.join('%s->%s' % (k, v['new']) for k, v in log.items()) or '-'))
