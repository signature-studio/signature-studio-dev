#!/usr/bin/env python3
"""m11_cond.py: IR 生成条件 (ldfix / qstore の適用有無・PE・IR 指紋) を work/ir_conditions.json に記録する (#680).
使い方:
  python3 m11_cond.py --reset K=V ...      ファイルを作り直して K=V を書く (m11_gen_ir2.sh 冒頭)
  python3 m11_cond.py K=V ...              既存ファイルに K=V を上書き (m11_gen_ir2.sh / m11_build.sh)
  python3 m11_cond.py --get K              K の値を印字 (無ければ空行)
  python3 m11_cond.py --bind [FILE]        FILE (既定 work/boot_final.ll) の sha256 を ir_sha256 に記録.
                                           IR を書き換える正規の pass (gen_ir2 / qstore / alloca) の直後だけ呼ぶ
  python3 m11_cond.py --check [FILE]       FILE の sha256 が ir_sha256 と一致すれば 0、不一致・未記録なら 1
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, 'work', 'ir_conditions.json')
DEFAULT_IR = os.path.join(HERE, 'work', 'boot_final.ll')


def load():
    if not os.path.exists(P):
        return {}
    with open(P) as f:
        return json.load(f)


def save(d):
    os.makedirs(os.path.dirname(P), exist_ok=True)
    with open(P, 'w') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write('\n')


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


args = sys.argv[1:]
if args[:1] == ['--get']:
    if len(args) != 2:
        sys.exit('usage: m11_cond.py --get K')
    print(load().get(args[1], ''))
    sys.exit(0)
if args[:1] == ['--bind']:
    d = load()
    d['ir_sha256'] = sha256(args[1] if len(args) > 1 else DEFAULT_IR)
    save(d)
    sys.exit(0)
if args[:1] == ['--check']:
    p = args[1] if len(args) > 1 else DEFAULT_IR
    rec = load().get('ir_sha256', '')
    ok = bool(rec) and os.path.exists(p) and sha256(p) == rec
    if not ok:
        print('m11_cond: %s は ir_conditions.json の指紋と一致しない (未記録を含む)' % p, file=sys.stderr)
    sys.exit(0 if ok else 1)
d = {} if args[:1] == ['--reset'] else load()
for a in args[1:] if args[:1] == ['--reset'] else args:
    k, _, v = a.partition('=')
    d[k] = v
save(d)
