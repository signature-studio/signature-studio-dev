#!/usr/bin/env python3
"""chain_chunk_check.py [WORK_DIR] — closure 関数の pdata 終端に chained 断片 (UNW_FLAG_CHAININFO) が続くものを列挙する (#2708 / ICALL-83)。
入力: WORK_DIR (既定 work/rt_freshair-core) の rw.dll (.pdata を持つ PE)・map.json (func_map)。出力: JSON (stdout)。
判定: 関数 S の pdata 終端 E に pdata 項目があり、それが chained (親関数の断片) なら候補。
chain_end は E から連続する chained 断片を連結した終端。icall_rewrite の再配置範囲は pdata の [S, E) だけなので、
E 以降の断片は RetDec の入力に入らず data 区分になる (RetDec は選択範囲の外へ fall-through を辿らない)。"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import audit_icall as A


def chain_end(img, e):
    while e in img.pdata and e in img.pdata_chained:
        e = img.pdata[e]
    return e


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'rt_freshair-core')
    img = A.Image(os.path.join(d, 'rw.dll'))
    fm = json.load(open(os.path.join(d, 'map.json')))['func_map']
    out = []
    for k in fm:
        s = int(k, 16)
        e = img.pdata.get(s)
        if e is None or e not in img.pdata or e not in img.pdata_chained:
            continue
        out.append({'va': hex(s), 'E': hex(e), 'chunk_end': hex(img.pdata[e]), 'chain_end': hex(chain_end(img, e))})
    print(json.dumps({'closure': len(fm), 'chained_at_E': len(out), 'funcs': out}, indent=1))


if __name__ == '__main__':
    main()
