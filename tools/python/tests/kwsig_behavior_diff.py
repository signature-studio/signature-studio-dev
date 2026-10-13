#!/usr/bin/env python3
"""kwsig_bind_check.py --dump の 2 出力 (旧 / 新) を同じケース単位で比べ、挙動変更を分類する。PY-15 #653。
  python3 tests/kwsig_bind_check.py --src <旧 src> --dump old.jsonl
  python3 tests/kwsig_bind_check.py --dump new.jsonl
  python3 tests/kwsig_behavior_diff.py old.jsonl new.jsonl
分類 (旧 = 8d883c3 の main の fl_api.py、新 = 本 PR):
  拒否       旧: 値を返す → 新: TypeError       (旧で通っていた呼出しが新で拒否される。利用者影響)
  値変更     旧: 値を返す → 新: 値を返すが違う  (同じ呼出しで別の値が入る)
  受理       旧: TypeError → 新: 値を返す
  NameError  旧: eval の NameError (midi.* 既定値) → 新: TypeError または値 (main 既存の欠陥の解消)
  同一       旧と新で同じ結果
"""
import collections
import json
import sys


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


old, new = load(sys.argv[1]), load(sys.argv[2])
assert len(old) == len(new), (len(old), len(new))
cnt = collections.Counter()
groups = collections.defaultdict(list)
for a, b in zip(old, new):
    assert a[:4] == b[:4], (a[:4], b[:4])
    ka, kb = a[4], b[4]
    if ka == kb == "tuple" and a[5] == b[5]:
        cls = "同一"
    elif ka == "tuple" and kb == "TypeError":
        cls = "拒否"
    elif ka == kb == "tuple":
        cls = "値変更"
    elif ka == "TypeError" and kb == "tuple":
        cls = "受理"
    elif ka.startswith("ERR:NameError"):
        cls = "NameError"
    elif ka == kb:
        cls = "同一"
    else:
        cls = f"その他 {ka}->{kb}"
    cnt[cls] += 1
    if cls in ("拒否", "値変更", "受理"):
        groups[cls].append(f"{a[0]}.{a[1]} pos={a[2]} kw={a[3]}: old={a[5] if ka == 'tuple' else ka} new={b[5] if kb == 'tuple' else kb}")
print(f"cases {len(old)}")
for k, v in cnt.most_common():
    print(f"  {k}: {v}")
for cls in ("拒否", "値変更", "受理"):
    print(f"[{cls}] {len(groups[cls])} 件")
    for line in groups[cls]:
        print("  " + line)
