#!/usr/bin/env python3
# P0a: chunk .ll マージ (複数 RetDec lift の統合). tools/m11/m11_merge.py 準拠 + P0a 拡張:
#   - 無名 global (@N) / 無名 metadata (!N) は chunk 固有の番号空間のため, ファイル毎に offset を足して
#     衝突を無くしてからマージする (番号衝突で別 chunk の別データを指す事故の防止; RetDec chunked
#     decode は各 chunk で 0 起番の無名 global/metadata を出す。self-contained は実測で確認済)。
#   - define は名前毎に最長のものを採用, global/declare/type は重複除去で連結。
# 使い方: python3 fw_merge.py work/fwN.restored.ll ... -o work/fw_all.restored.ll
import sys, re


def main():
    infiles, out = [], None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '-o':
            out = sys.argv[i + 1]
            i += 2
        else:
            infiles.append(sys.argv[i])
            i += 1
    defines = {}
    declares = []
    decls_seen = set()
    globals_seen = {}
    types = []
    types_seen = set()
    header = []
    gcounter = 0      # 無名 global の付番
    mcounter = 0      # 無名 metadata の付番
    dpat = re.compile(r'^declare \S+ @')
    gpat = re.compile(r'^@([\w.$-]+) = ')
    tpat = re.compile(r'^%([\w.$-]+) = type ')

    for f in infiles:
        lines = open(f).read().split('\n')
        n = len(lines)
        # この chunk の無名 global / metadata の最大番号 (offset 計算)
        gmax = max([int(m.group(1)) for m in re.finditer(r'(?m)^@(\d+) = ', '\n'.join(lines))] or [0])
        text_all = '\n'.join(lines)
        mmax = max([int(m.group(1)) for m in re.finditer(r'(?m)^!(\d+) = ', text_all)] or [0])
        goff, moff = gcounter, mcounter
        gcounter += gmax + 1
        mcounter += mmax + 1
        if goff or moff:
            # 無名 global 参照 (@<digits>) と metadata (!<digits>) を offset 附番で書換え
            text_all = re.sub(r'@(\d+)\b', lambda m: '@%d' % (int(m.group(1)) + goff), text_all)
            text_all = re.sub(r'!(\d+)\b', lambda m: '!%d' % (int(m.group(1)) + moff), text_all)
        lines = text_all.split('\n')
        i = 0
        while i < n:
            l = lines[i]
            if l.startswith('define ') and '@' in l:
                m = re.match(r'^define (.+?) @([\w.$_-]+)', l)
                if not m:
                    i += 1
                    continue
                nm = m.group(2)
                buf = [l]
                i += 1
                while i < n and not lines[i].startswith('}'):
                    buf.append(lines[i])
                    i += 1
                if i < n:
                    buf.append(lines[i])
                    i += 1
                # 最長 define 採用 (同一名の再定義差分は RetDec 非決定性由来; 大きい方を残す)
                if nm not in defines or len(buf) > len(defines[nm]):
                    defines[nm] = buf
                continue
            m = dpat.match(l)
            if m and l not in decls_seen:
                decls_seen.add(l)
                declares.append(l)
                i += 1
                continue
            m = gpat.match(l)
            if m:
                if m.group(1) not in globals_seen:
                    globals_seen[m.group(1)] = l
                i += 1
                continue
            m = tpat.match(l)
            if m:
                if l not in types_seen:
                    types_seen.add(l)
                    types.append(l)
                i += 1
                continue
            if l.startswith('source_filename') or l.startswith('target ') or l.startswith('; Function') or l.startswith('attributes '):
                if l.startswith('source_filename') or l.startswith('target ') and l not in header:
                    header.append(l)
                i += 1
                continue
            i += 1

    def gkey(nm):
        return int(nm) if nm.isdigit() else -1

    with open(out, 'w') as f:
        f.write('source_filename = "p0a"\n')
        f.write('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"\n')
        for t in types:
            f.write(t + '\n')
        f.write('\n')
        for nm in sorted(globals_seen, key=gkey):
            f.write(globals_seen[nm] + '\n')
        f.write('\n')
        cnt = 0
        for nm in sorted(defines):
            f.write('\n'.join(defines[nm]) + '\n\n')
            cnt += 1
        # 未参照 declare の除去 (chunk 境界で R1 改名が揃わず残る Declare の排他的対処)
        allrefs = '\n'.join('\n'.join(b) for b in defines.values())
        for d in declares:
            m = re.search(r'@[\w.$_-]+', d)
            if m and ('@' + m.group(0)[1:] + '(') in allrefs:
                f.write(d + '\n')
    print('[merge] defines: %d / globals: %d / declares: %d / %s -> %s'
          % (cnt, len(globals_seen), len(declares), ' '.join(infiles), out))


if __name__ == '__main__':
    main()
