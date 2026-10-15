#!/usr/bin/env python3
"""kh656_closure.py — module F (ブラウザ分類 0x180ef7fc0) の未 lift callee を反復的に lift 対象へ加える閉包展開 (#656).

  python3 scripts/kh656_closure.py [--rounds N]

各ラウンド: (1) lic_build.py --module F を実行 → (2) kh_lower の unlifted callees を取得 →
(3) shims (modules.F.shims) に無く、lift にも excluded_i256 にも無いものを modules.F.lift へ追記。
lic_build が gen_simd.py の失敗 (i256 / ptr を引数・戻り値に持つ __asm_ 宣言) で止まり、その宣言を直接呼ぶ関数があれば、
それを lift から外して modules.F.excluded_i256 へ記録し再試行する (未 lift のままなら fail-fast stub)。
gen_simd 以外の失敗では lic_config を書き換えず終了する (失敗時に lift 集合を空にしない)。
増分が 0 になったら終了。各ラウンドの build 成功後に入口 function_180ef7fc0 の結果 (kh249_check.mjs) を記録する。
書換えは lic_config.json の modules.F ブロックだけ。
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
CFG = os.path.join(LIC, 'lic_config.json')
WORK = os.path.join(LIC, 'work', 'licF')
ROUNDS_JSON = os.path.join(LIC, 'work', 'kh656_rounds.json')


def load_f():
    return json.load(open(CFG, encoding='utf-8'))['modules']['F']


def set_key(key, items):
    s = open(CFG, encoding='utf-8').read()
    i = s.index('"F": {')
    end = s.index('"emcc_opt"', i)
    blk = s[i:end]
    body = '[\n' + ',\n'.join('    "%s"' % v for v in items) + '\n   ]'
    if '"%s": [' % key in blk:
        a = blk.index('"%s": [' % key)
        b = blk.index(']', a) + 1
        blk = blk[:a] + '"%s": %s' % (key, body) + blk[b:]
    else:
        blk = blk.replace('   "raw_va"', '   "%s": %s,\n   "raw_va"' % (key, body), 1)
    open(CFG, 'w', encoding='utf-8').write(s[:i] + blk + s[end:])


def unsupported_defs():
    """gen_simd.py が扱えない __asm_ 宣言 (引数・戻り値に i256 か ptr) を直接呼ぶ関数の番地。
    i256 の語を含む関数を広く拾うと、ymm 状態 (@ymm0 等) の load だけの関数まで外れるため、呼び先の宣言で判定する。"""
    L = open(os.path.join(WORK, 'final.ll')).read().split('\n')
    decl = set()
    for l in L:
        m = re.match(r'^declare (\S+) @(__asm_[\w.]+)\(([^)]*)\)', l)
        if m and re.search(r'\b(i256|ptr)\b', m.group(1) + ' ' + m.group(3)):
            decl.add(m.group(2))
    bad = set()
    cur = None
    for l in L:
        m = re.match(r'^define \S+ @(?:function_|kh_)([0-9a-f]+)\(', l)
        if m:
            cur = m.group(1)
        elif l.startswith('}'):
            cur = None
        elif cur and any('@%s(' % d in l for d in decl):
            bad.add(cur)
    return bad


def run_build():
    r = subprocess.run([sys.executable, os.path.join(LIC, 'lic_build.py'), '--module', 'F'],
                       cwd=LIC, capture_output=True, text=True)
    return r


def entry_check():
    """入口 function_180ef7fc0 の実行結果 (kh249_check.mjs)。受入 2 の判定値: 最初の未 lift callee か trap 文言"""
    try:
        r = subprocess.run(['node', os.path.join(LIC, 'kh249_check.mjs')], cwd=LIC, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {'entry': 'timeout', 'check': None}
    out = r.stdout + r.stderr
    e = re.search(r'entry run -> (.*)', out)
    s = re.search(r'kh249_check ok=\d+ ng=\d+', out)
    return {'entry': e.group(1) if e else None, 'check': s.group(0) if s else None}


def build():
    """戻り値: (stat or None, unlifted list, i256 excluded list)"""
    r = run_build()
    if r.returncode:
        bad = unsupported_defs() & set(load_f()['lift']) if 'gen_simd' in r.stdout + r.stderr else set()
        if not bad:
            print(r.stdout[-1500:], r.stderr[-1500:])
            raise SystemExit('lic_build F failed (gen_simd 未対応の宣言以外の原因。lic_config は書き換えていない)')
        f = load_f()
        set_key('lift', [x for x in f['lift'] if x not in bad])
        set_key('excluded_i256', sorted(set(f.get('excluded_i256', [])) | bad))
        return None, [], sorted(bad)
    st = json.load(open(os.path.join(WORK, 'stat.json'), encoding='utf-8'))
    m = re.search(r"unlifted callees (\[[^\]]*\])", st['passes'])
    unl = json.loads(m.group(1).replace("'", '"')) if m else []
    return st, unl, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=8)
    a = ap.parse_args()
    rounds = []
    closed = False
    for n in range(1, a.rounds + 1):
        f = load_f()
        lift = list(f['lift'])
        shims = set(f.get('shims', {}))
        excl = set(f.get('excluded_i256', []))
        st, unl, dropped = build()
        if st is None:
            rec = {'round': n, 'build': 'failed', 'dropped_i256': dropped}
            rounds.append(rec)
            print(json.dumps(rec, ensure_ascii=False))
            continue
        todo = [x for x in unl if x not in shims and x not in lift and x not in excl]
        rec = {'round': n, 'lift': len(lift), 'unlifted': len(unl), 'shimmed': sorted(x for x in unl if x in shims),
               'excluded_i256': sorted(excl), 'new_lift': todo, 'wasm_bytes': st['wasm_bytes'],
               'wasm_sha256': st['wasm_sha256'], 'undefined_imports': st['undefined_imports'],
               'emcc_peak_rss_mb': st.get('emcc_peak_rss_mb'), **entry_check()}
        rounds.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        if not todo:
            closed = True
            break
        set_key('lift', lift + todo)
    os.makedirs(os.path.dirname(ROUNDS_JSON), exist_ok=True)
    json.dump(rounds, open(ROUNDS_JSON, 'w'), indent=1, ensure_ascii=False)
    # 閉包に到達したとき (todo == []) だけ成功。--rounds を使い切った場合は、追記した lift が未検証のまま残るため非 0
    if not closed:
        print('FAIL: --rounds %d 内に閉包 (todo == []) へ到達せず。最終 lift 集合は未検証' % a.rounds, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
