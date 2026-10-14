#!/usr/bin/env python3
"""A7 (uselistorder 除去) の回帰テスト (#1664): directive の有無が正規化後の bytes に残らないこと。

RetDec は use-list の並びが既定と違う関数にだけ `\\n; uselistorder directives\\n  uselistorder ...` を出し,
その有無は実行ごとに変わる。A7 が先頭の空行を残すと, 同一入力でも lift.ll の空行数が実行ごとにずれる。
使い方: python3 tools/m11/test_a7_uselistorder.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..")

BODY = "define i64 @function_1(i64 %arg1) local_unnamed_addr {\n  %1 = add i64 %arg1, 1\n  ret i64 %1\n"
WITH_DIRECTIVE = BODY + "\n; uselistorder directives\n  uselistorder i64 %arg1, { 1, 0 }\n  uselistorder label %2, { 1, 0 }\n}\n"
WITHOUT_DIRECTIVE = BODY + "}\n"
MODULE_LEVEL = "\n; uselistorder directives\n  uselistorder ptr @g, { 1, 0 }\n"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check(label, normalize):
    a = normalize(WITH_DIRECTIVE + "\n" + WITH_DIRECTIVE.replace("@function_1", "@function_2"))
    b = normalize(WITHOUT_DIRECTIVE + "\n" + WITHOUT_DIRECTIVE.replace("@function_1", "@function_2"))
    mixed = normalize(WITH_DIRECTIVE + "\n" + WITHOUT_DIRECTIVE.replace("@function_1", "@function_2"))
    mixed_ref = normalize(WITHOUT_DIRECTIVE + "\n" + WITHOUT_DIRECTIVE.replace("@function_1", "@function_2"))
    assert a == b, f"{label}: directive 有り/無しで出力が違う\n{a!r}\n{b!r}"
    assert mixed == mixed_ref, f"{label}: 片方だけ directive 有りでも出力が一致しない"
    tail = normalize(WITHOUT_DIRECTIVE + MODULE_LEVEL)
    assert tail == normalize(WITHOUT_DIRECTIVE), f"{label}: module 末尾の directive が空行を残す"
    assert "uselistorder" not in a
    print(f"[test_a7_uselistorder] {label}: PASS")


def main():
    m5 = load(os.path.join(TOOLS, "m5", "ir5_patch.py"), "ir5_patch_m5")
    check("m5/ir5_patch.py", m5.normalize)
    sys.path.insert(0, os.path.join(TOOLS, "liftlib"))
    from liftlib.passes import base
    check("liftlib/passes/base.py", base.normalize)


if __name__ == "__main__":
    main()
