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
  objdump 2.42 は LOCK の非ロック命令・REX2 (d5)・不正オペランド (字句 (bad) / %?) を受理するため、objdump の出力は
  SDM の規則で後処理してから判定する (obj_insn / first_op_byte)。capstone 側は未後処理 (残件は REPORT_MX25 §5.5)。
  ENTRY=pdata_call: (iii) が入口に全て入ること (取りこぼし 0) と、入口が (iii) 以外を含まないこと (過剰 0)。
  ENTRY=pdata:      (iii) のうち入口に入らなかった件数 = pdata 案で落ちる code の候補。

usage: mx_flow_recheck.py <sets.pkl> <rounds.json> [<PE>]
"""
import sys, os, re, json, pickle, collections, bisect, threading, tempfile, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor
import capstone, pefile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mx_closure import insn_sdm_ok  # closure と同じ LOCK/REX 規則 (capstone 側の判定に使う)

THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
UNDOC = {'fstpnce'}  # D9 D8+i (FSTP1、未文書化の別名)。SDM の命令表に無く、objdump も不正とする
PRN = rb'\t\r\n\x20-\x7e'
OBJ_LINE = re.compile(r'^\s*[0-9a-f]+:\t([0-9a-f ]+)\t(.*)$')
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
    # capstone 側の判定。closure (mx_closure.block_ok) と同じ SDM の LOCK/REX 規則 (insn_sdm_ok) を通す。
    # REX2 (d5) は APX 接頭辞で x64 基準では不正 (capstone 5.0.7 は APX として復号するため除外する)。
    n = 0
    try:
        for ea, iz, mn, ops in md.disasm_lite(chunk, va):
            if mn in UNDOC or first_op_byte(chunk[ea - va:ea - va + iz].hex(' ')) == 'd5':
                return False
            if not insn_sdm_ok(chunk[ea - va:ea - va + iz], mn, ops):
                return False
            n += 1
            if 'ret' in mn.split() or 'jmp' in mn.split() or n >= 32:
                return True
    except capstone.CsError:
        return False
    return False


OBJ_PREFIX = {'lock', 'rep', 'repz', 'repnz', 'data16', 'addr32', 'cs', 'ds', 'es', 'ss', 'fs', 'gs',
              'notrack', 'bnd', 'xacquire', 'xrelease'}
LOCKABLE = {'adc', 'add', 'and', 'btc', 'btr', 'bts', 'cmpxchg', 'cmpxchg8b', 'cmpxchg16b', 'dec', 'inc',
            'neg', 'not', 'or', 'sbb', 'sub', 'xadd', 'xchg', 'xor'}
LEGACY_PREFIX = {'66', '67', 'f0', 'f2', 'f3', '2e', '36', '3e', '26', '64', '65'}
TERM = {'ret', 'retw', 'retq', 'jmp', 'jmpw', 'jmpq'}


def first_op_byte(bytes_col):
    # 先頭の接頭辞 (レガシー) を除いた最初のバイト。d5 は REX2 (APX 接頭辞。x64 基準では不正)。
    for b in bytes_col.split():
        if b not in LEGACY_PREFIX:
            return b
    return ''


def last_operand(ops):
    # AT&T の最後のオペランド (宛先)。括弧の中のカンマは区切りにしない。
    depth, start = 0, 0
    for i, ch in enumerate(ops):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            start = i + 1
    return ops[start:]


def obj_insn(raw):
    # objdump 1 行の SDM 規則による判定 (binutils 2.42 は下の不正を受理するため、後段で落とす)。
    #   (bad) / 不正セグメントレジスタ %? / REX2 (APX。x64 基準では不正) / REX の直後の VEX /
    #   LOCK 接頭辞で非ロック命令 or メモリ宛先でない形。戻り値: None (不正) か (命令名, 最後のオペランド, 理由)。
    if '(bad)' in raw or '%?' in raw or '{rex2' in raw:
        return None, '(bad)/%?/rex2'
    tok = raw.split()
    pre = set()
    while tok and (tok[0] in OBJ_PREFIX or tok[0].startswith('rex')):
        pre.add('rex' if tok[0].startswith('rex') else tok[0])
        tok.pop(0)
    if not tok:
        return ('', '', 'prefix'), 'prefix'
    mn = tok[0]
    last = last_operand(''.join(tok[1:]))
    if 'rex' in pre and mn.startswith('v') and mn not in ('verr', 'verw'):
        return None, 'rex+vex'
    if 'lock' in pre:
        base = mn if mn in LOCKABLE else mn[:-1]
        if base not in LOCKABLE or '(' not in last:
            return None, 'lock'
    return (mn, last, ''), ''


def obj_first_ok(chunk, va, tmpdir):
    # 戻り値: (判定, 不正の理由, 不正と判定した行)。理由は最初に不正と判定した行の規則名 (正常なら '')。
    if not hasattr(tl, 'path'):
        tl.path = os.path.join(tmpdir, 'w%d.bin' % threading.get_ident())
    with open(tl.path, 'wb') as f:
        f.write(chunk)
    out = subprocess.run(
        ['objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64', '--adjust-vma=0x%x' % va, tl.path],
        capture_output=True, text=True).stdout
    n = 0
    for line in out.splitlines():
        m = OBJ_LINE.match(line)
        if not m:
            continue
        if first_op_byte(m.group(1)) == 'd5':
            return False, 'rex2', m.group(2)
        ins, why_bad = obj_insn(m.group(2))
        if ins is None:
            return False, why_bad, m.group(2)
        if not ins[0]:
            continue
        n += 1
        if ins[0] in TERM or n >= 32:
            return True, '', ''
    return False, 'no-ret', ''


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
                mism.append((t, cap[t], obj[t], res[t][1], res[t][2], chunk[t][:12].hex(' ')))
                if obj[t]:
                    cnt['mismatch_cap_bad_obj_ok'] += 1
                else:
                    cnt['mismatch_cap_ok_obj_bad_%s' % res[t][1]] += 1
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
        for t, c, o, r, txt, hx in mism[:5]:
            print('   mismatch 0x%x capstone=%s objdump=%s (%s %r)' % (t, c, o, r, txt))
        with open(os.path.splitext(rounds_json)[0] + '_mismatch.tsv', 'w') as f:
            f.write('va\tcapstone\tobjdump\treason\tobjdump_line\tbytes\n')
            for t, c, o, r, txt, hx in mism:
                f.write('0x%x\t%s\t%s\t%s\t%s\t%s\n' % (t, c, o, r, txt, hx))
        ok = ok and cnt['mismatch'] == 0
        if entry == 'pdata_call':
            ok = ok and cnt['iii_not_in_entries'] == 0 and cnt['entry_not_iii'] == 0
    print('RESULT=%s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
