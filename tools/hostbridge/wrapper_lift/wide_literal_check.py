"""#2071: `retdec_repair.py --wide` が直した `(int16_t *)u"..."` が PE 内の UTF-16LE 文字列と一致するかを判定する。

使い方 (cwd=リポジトリルート):
  python3 tools/hostbridge/wrapper_lift/wide_literal_check.py <before_dir> <after_dir> <block_PE.bin> [--control]
入力: retdec_repair.py の出力 2 つ (同名 .c・同じ行数)。before は直す前、after は直した後。
対象: 行が変わった行の中で、after に増えた `(int16_t *)u"..."` (before 側の同じ行に同じ中身が無いもの)。
  before に `--int-ptr` のみの版を使うと修復で直した全件 (引数・代入・初期化)。
  before に引数のみ直した版 (`--wide` の代入・初期化追加前) を使うと、代入・初期化で直した分だけ。
判定: u"..." の中身を C の escape で復元し、1 文字 2B (UTF-16LE) を並べ、末尾に NUL 2B を付けたバイト列が PE 内にあるか。
--control: 同じ中身を UTF-32LE (wasm32 の wchar_t 4B) + NUL 4B で探す。判定が無差別でないことの対照 (一致は少ないはず)。
出力: JSON 1 行 (対象件数・一致件数・不一致の先頭 20 件・復元不能件数)。不一致・復元不能が 1 件でもあれば終了コード 1。
対象 0 件は判定できないので終了コード 2。
"""
import collections
import json
import os
import re
import sys

LIT_RE = re.compile(r'\(int16_t \*\)u"((?:[^"\\\n]|\\.)*)"')
ESC = {"n": 10, "r": 13, "t": 9, "\\": 92, '"': 34, "'": 39, "0": 0}


def decode(body):
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            if i + 1 >= len(body) or body[i + 1] not in ESC:
                return None
            out.append(ESC[body[i + 1]])
            i += 2
        elif ord(c) >= 0x80 or c < " ":
            return None
        else:
            out.append(ord(c))
            i += 1
    return out


def read_lines(path):
    with open(path, errors="replace") as fh:
        return fh.read().split("\n")


def targets(before_dir, after_dir):
    out = []
    for f in sorted(os.listdir(after_dir)):
        if not f.endswith(".c"):
            continue
        a = read_lines(os.path.join(after_dir, f))
        b = read_lines(os.path.join(before_dir, f))
        if len(a) != len(b):
            sys.exit("line count differs: %s" % f)
        for i, (x, y) in enumerate(zip(b, a), 1):
            if x == y:
                continue
            new = collections.Counter(LIT_RE.findall(y)) - collections.Counter(LIT_RE.findall(x))
            for body, k in new.items():
                out.extend([(f, i, body)] * k)
    return out


def main():
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    before_dir, after_dir, pe_path = [a for a in sys.argv[1:] if not a.startswith("--")]
    with open(pe_path, "rb") as fh:
        pe = fh.read()
    tg = targets(before_dir, after_dir)
    if not tg:
        print(json.dumps({"targets": 0}))
        sys.exit(2)
    matched = 0
    undecodable = 0
    unmatched = []
    for f, ln, body in tg:
        codes = decode(body)
        if codes is None:
            undecodable += 1
            continue
        data = b"".join(c.to_bytes(2, "little") for c in codes) + b"\0\0"
        if data in pe:
            matched += 1
        else:
            unmatched.append({"file": f, "line": ln, "literal": body})
    res = {
        "pe": os.path.basename(pe_path),
        "targets": len(tg),
        "matched_utf16le": matched,
        "unmatched": len(unmatched),
        "undecodable": undecodable,
        "unmatched_head": unmatched[:20],
    }
    if "--control" in flags:
        hit = 0
        for f, ln, body in tg:
            codes = decode(body)
            if codes is None:
                continue
            data = b"".join(c.to_bytes(4, "little") for c in codes) + b"\0" * 4
            hit += data in pe
        res["control_utf32le_matched"] = hit
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if not unmatched and not undecodable else 1)


if __name__ == "__main__":
    main()
