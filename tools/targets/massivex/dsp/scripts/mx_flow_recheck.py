#!/usr/bin/env python3
"""MX-13 round 推移の独立検算 (規則 37 / §5) と MX-29 の入口判定の検算。

mx_closure.py の round ループ (入口を増やしながら callees を計算する反復) とは別の
アルゴリズムで、同じ出力 (<prefix>_sets.pkl) から閉包を再計算する:
  1. 閉包 = seeds から callees 辺を辿る BFS (到達可能な入口の集合)。
  2. BFS 深さ = 「何 hop 目で初めて入るか」。hop ごとの件数を round 推移の別表示とする。
  3. round ループの最終 entries と一致するか、round ごとの added 合計が
     閉包サイズ - seeds 数 と一致するかを確認する。
PE を渡したとき (MX-29): 閉包の code が直接 call する .text 内・thunk 外の番地 (.pdata begin を除く、
入口 (non-pdata) も含む) を次に分類する。
  (i) 文字列窓 (印字可能 ASCII 8 字以上 + NUL / UTF-16LE 8 字以上 + U+0000、.pdata と重ならないもの)
  (ii) 先頭ブロック (入口から最初の ret / jmp まで・最大 32 命令) が不正命令
  (iii) 先頭ブロックが正常 (leaf 候補)
先頭ブロックのデコード可否は capstone と objdump (別の逆アセンブラ) の 2 通りで判定し、食い違い (mismatch) を数える。
  ENTRY=pdata_call: (iii) が入口に全て入ること (取りこぼし 0) と、入口が (iii) 以外を含まないこと (過剰 0)。
  ENTRY=pdata:      (iii) のうち入口に入らなかった件数 = pdata 案で落ちる code の候補。

usage: mx_flow_recheck.py <sets.pkl> <rounds.json> [<PE>]
"""
import sys, os, re, json, pickle, collections, bisect, threading, tempfile, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor
import capstone, pefile

THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
PRN = rb'\t\r\n\x20-\x7e'
OBJ_LINE = re.compile(r'^\s*[0-9a-f]+:\t[0-9a-f ]+\t(.*)$')
tl = threading.local()


def bfs_check(s, rounds_json):
    callees, seeds, entries = s['callees'], set(s['seeds']), set(s['entries'])
    depth = {x: 0 for x in seeds}
    q = collections.deque(seeds)
    while q:
        f = q.popleft()
        for g in callees.get(f, ()):
            if g not in depth:
                depth[g] = depth[f] + 1
                q.append(g)
    reach = set(depth)
    hop = collections.Counter(depth.values())
    rl = json.load(open(rounds_json))['rounds_log']
    added_sum = sum(r['added'] for r in rl)
    print('seeds=%d bfs_closure=%d loop_entries=%d' % (len(seeds), len(reach), len(entries)))
    print('bfs == loop: %s' % (reach == entries))
    print('loop added 合計=%d, closure-seeds=%d, 一致=%s' % (added_sum, len(reach) - len(seeds),
                                                      added_sum == len(reach) - len(seeds)))
    print('hop 別 (初到達の深さ): ' + ' '.join('%d:%d' % (k, hop[k]) for k in sorted(hop)))
    print('最終 round entries == %d, rounds=%d' % (rl[-1]['entries'], len(rl)))
    return reach == entries and added_sum == len(reach) - len(seeds) and rl[-1]['entries'] == len(entries)


def cap_first_ok(md, chunk, va):
    n = 0
    try:
        for ea, iz, mn, ops in md.disasm_lite(chunk, va):
            n += 1
            if 'ret' in mn.split() or 'jmp' in mn.split() or n >= 32:
                return True
    except capstone.CsError:
        return False
    return False


def obj_first_ok(chunk, va, tmpdir):
    # 戻り値: (判定, 先頭ブロックの命令の文字列列)。判定の理由別集計に使う。
    if not hasattr(tl, 'path'):
        tl.path = os.path.join(tmpdir, 'w%d.bin' % threading.get_ident())
    with open(tl.path, 'wb') as f:
        f.write(chunk)
    out = subprocess.run(
        ['objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64', '--adjust-vma=0x%x' % va, tl.path],
        capture_output=True, text=True).stdout
    n, seen = 0, []
    for line in out.splitlines():
        m = OBJ_LINE.match(line)
        if not m:
            continue
        tok = m.group(1).split()
        seen.append(m.group(1).strip())
        if not tok or '(bad)' in tok:
            return False, seen
        n += 1
        if 'ret' in tok or 'jmp' in tok or n >= 32:
            return True, seen
    return False, seen


def why(lines):
    # objdump だけが受理した先頭ブロックの理由 (SDM の制約。capstone は不正として止まる)
    if any(x.startswith('lock ') for x in lines):
        return 'lock'
    if any(x.startswith('rex') for x in lines):
        return 'rex'
    return 'other'


def windows_of(pe_path, fsz):
    data = open(pe_path, 'rb').read()
    pe = pefile.PE(pe_path, fast_load=True)
    t = [x for x in pe.sections if x.Characteristics & 0x20000000][0]
    t_lo, t_raw = t.VirtualAddress, t.PointerToRawData
    tx = data[t_raw: t_raw + t.Misc_VirtualSize]
    spans = sorted(m.span() for pat in (rb'[%s]{8,}\x00' % PRN, rb'(?:[%s]\x00){8,}\x00\x00' % PRN)
                   for m in re.finditer(pat, tx))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    begins = sorted(fsz)
    wins = []
    for a, b in merged:
        va_a, va_b = t_lo + a, t_lo + b
        if not any(x < va_b and x + fsz[x] > va_a for x in begins):
            wins.append((va_a, va_b))
    return data, t_lo, t_raw, wins, len(merged)


def classify(pe_path, s, entries, fsz, seeds):
    data, t_lo, t_raw, wins, n_merged = windows_of(pe_path, fsz)
    ws = [w[0] for w in wins]

    def inwin(t):
        i = bisect.bisect_right(ws, t) - 1
        return i >= 0 and t < wins[i][1]

    C = set()
    for e in entries:
        C.update(s['callall'].get(e, ()))
    K = {t for t in C if t not in fsz and not (THUNK_LO <= t < THUNK_HI)}
    K |= {t for t in entries if t not in fsz and t not in seeds}
    print('windows: merged=%d kept(not pdata-overlap)=%d' % (n_merged, len(wins)))
    print('call targets (non-pdata, .text, non-thunk)=%d; K (+admitted non-pdata non-seed)=%d' % (len(C - set(fsz)), len(K)))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    todo = sorted(t for t in K if not inwin(t))
    chunk = {t: data[t_raw + t - t_lo: t_raw + t - t_lo + 480] for t in todo}
    cap = {t: cap_first_ok(md, chunk[t], t) for t in todo}
    tmpdir = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(sets_pkl_path)))
    try:
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
            res = dict(zip(todo, ex.map(lambda t: obj_first_ok(chunk[t], t, tmpdir), todo)))
        obj = {t: res[t][0] for t in todo}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    cnt = collections.Counter()
    mism = []
    for t in sorted(K):
        if inwin(t):
            cls = 'i_win'
        else:
            cls = 'iii_leaf' if obj[t] else 'ii_bad'
            if cap[t] != obj[t]:
                mism.append((t, cap[t], obj[t]))
                cnt['mismatch_%s_%s' % ('obj_only' if obj[t] else 'cap_only', why(res[t][1]) if obj[t] else 'bad')] += 1
        cnt[cls] += 1
        if cls == 'iii_leaf' and t not in entries:
            cnt['iii_not_in_entries'] += 1
        if cls != 'iii_leaf' and t in entries:
            cnt['entry_not_iii'] += 1
    cnt['mismatch'] = len(mism)
    return cnt, mism


def main(sets_pkl, rounds_json, pe_path=None):
    global sets_pkl_path
    sets_pkl_path = sets_pkl
    s = pickle.load(open(sets_pkl, 'rb'))
    entries, seeds, fsz = set(s['entries']), set(s['seeds']), s['fsz']
    entry = json.load(open(rounds_json)).get('entry', 'any')
    print('ENTRY=%s' % entry)
    ok = bfs_check(s, rounds_json)
    if pe_path:
        cnt, mism = classify(pe_path, s, entries, fsz, seeds)
        print('(i) 文字列窓=%d  (ii) 先頭ブロック不正=%d  (iii) 先頭ブロック正常 (leaf 候補)=%d'
              % (cnt['i_win'], cnt['ii_bad'], cnt['iii_leaf']))
        print('(iii) のうち入口に入らなかった件数 (取りこぼし)=%d' % cnt['iii_not_in_entries'])
        print('入口のうち (iii) でない件数 (過剰)=%d' % cnt['entry_not_iii'])
        print('capstone と objdump の先頭ブロック判定の不一致 (mismatch)=%d' % cnt['mismatch'])
        for k in sorted(k for k in cnt if k.startswith('mismatch_')):
            print('   %s=%d' % (k, cnt[k]))
        for t, c, o in mism[:5]:
            print('   mismatch 0x%x capstone=%s objdump=%s' % (t, c, o))
        ok = ok and cnt['mismatch'] == 0
        if entry == 'pdata_call':
            ok = ok and cnt['iii_not_in_entries'] == 0 and cnt['entry_not_iii'] == 0
    print('RESULT=%s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
