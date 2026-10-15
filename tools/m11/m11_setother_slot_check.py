#!/usr/bin/env python3
"""set_other スタック slot 未決の再集計と C 規則の IR 突合 (#3933 / M11-N202 / 親 #3906).

入力: m11_setother_slot_class.py の出力 mem_class_rows.json と、呼出し元 IR (boot_final.ll).
出力: 3 値 (実値化 / 復元不能 / 未決) の件数と未分類、および C 規則の突合 (引数単位・名前単位) を stdout に出す。
IR は変更しない。

使い方: python3 m11_setother_slot_check.py mem_class_rows.json --ir boot_final.ll
"""
import argparse, collections, json, re

HEAD = re.compile(r'^define\b.*?@(function_[0-9a-fA-F]+)\(')


def bodies_of(ir_path):
    body, cur = {}, None
    for ln in open(ir_path):
        ln = ln.rstrip('\n')
        if ln.startswith('define'):
            m = HEAD.match(ln)
            cur = m.group(1) if m else None
            if cur:
                body[cur] = []
        elif ln.startswith('}'):
            cur = None
        elif cur:
            body[cur].append(ln)
    return body


def name_re(name):
    return re.compile(r'(?<![\w.])' + re.escape(name) + r'(?![\w.])')


def three_value(row):
    if row['class'] in ('実値化', '未決'):
        return row['class']
    return '未分類'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rows')
    ap.add_argument('--ir', required=True)
    a = ap.parse_args()

    rows = json.load(open(a.rows))
    body = bodies_of(a.ir)

    cnt3 = collections.Counter(three_value(r) for r in rows)
    print('[slot-check] 対象 %d 件' % len(rows))
    for k in ('実値化', '復元不能', '未決', '未分類'):
        print('  %-8s %d' % (k, cnt3[k]))
    print('[slot-check] 未決の理由別')
    for (why), v in sorted(collections.Counter(r['reason'] for r in rows if three_value(r) == '未決').items()):
        print('  %-22s %d' % (why, v))

    # C 規則の突合: lea_alloca (実値化 25) の呼出し元 IR で、対応する call の引数に alloca 名が現れるか。
    lea = [r for r in rows if r['reason'] == 'lea_alloca']
    arg_stat = collections.Counter()
    name_stat = collections.Counter()
    seen = set()
    for r in lea:
        name = r['value'][1:]  # %stack_var_X
        calls = [ln for ln in body.get(r['caller'], []) if ('@' + r['callee'] + '(') in ln]
        with_args = [ln for ln in calls if not re.search('@' + re.escape(r['callee']) + r'\(\)', ln)]
        if not calls:
            arg_stat['no_call_in_caller'] += 1
        elif not with_args:
            arg_stat['only_argless_call'] += 1
        else:
            arg_stat['arg_match' if any(name_re(name).search(ln) for ln in with_args) else 'arg_mismatch'] += 1
        key = (r['caller'], name)
        if key in seen:
            continue
        seen.add(key)
        refs = [ln for ln in body.get(r['caller'], [])
                if name_re(name).search(ln) and not re.match(r'\s*%' + re.escape(name) + r'(\.\S*)? = alloca', ln)]
        name_stat['ref_elsewhere' if refs else 'alloca_only'] += 1
    print('[slot-check] C 突合 (lea_alloca %d 件の引数単位)' % len(lea))
    for k, v in sorted(arg_stat.items()):
        print('  %-20s %d' % (k, v))
    print('[slot-check] C 突合 (一意な (呼出し元, alloca) %d 件の名前単位)' % len(seen))
    for k, v in sorted(name_stat.items()):
        print('  %-20s %d' % (k, v))


if __name__ == '__main__':
    main()
