"""fl_api — FL 組込 API モジュール (channels/mixer/transport/... ) を wasm Python 内に生成する。

データ駆動: flapi_table.json (FLEngine rodata 抽出 + 公開 stubs の署名) から、
  各関数 = `_flhost.call(fn_id, args)` を呼ぶ薄いラッパ。fn_id は table の列挙順 (flapi_ids.json と同一)。
実装本体 (FLEngine 側) は JS ホストが fn_id → 実関数に対応付ける。Python 側に FL ロジックは無い。
"""
import ast
import importlib
import json
import operator
import sys
import types

import _flhost

# FL API の例外コード (FLEngine rodata の文言: "Invalid value / Unspecified error / Operation unsafe at current time /
# Range error / Index out of range / Wrong number of function parameters or wrong parameter type / ...")
_ERR = {1: ValueError, 2: RuntimeError, 3: RuntimeError, 4: IndexError, 5: TypeError, 6: RuntimeError,
        7: RuntimeError, 8: RuntimeError}

# stubs 既定値の許可表。midi.* の値は利用者の midi モジュールから実行時に取る (値を repo に複製しない)。
_DEFAULT_NAMES = frozenset({"midi.PIM_None", "midi.GT_All", "midi.LB_Status_Default", "midi.EKRes", "midi.MaxInt",
                            "midi.ST_Int", "midi.PME_System", "midi.REC_None", "midi.GC_BackgroundColor",
                            "midi.FPN_Param"})
_DEFAULT_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_DEFAULT_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _default_value(expr):
    # literal_eval は 1 / 24 (BinOp) を扱えないため、四則演算だけ operator で計算する
    def ev(n):
        if isinstance(n, ast.Constant) and (n.value is None or isinstance(n.value, (bool, int, float))):
            return n.value
        if isinstance(n, ast.UnaryOp) and type(n.op) in _DEFAULT_UNARY:
            return _DEFAULT_UNARY[type(n.op)](ev(n.operand))
        if isinstance(n, ast.BinOp) and type(n.op) in _DEFAULT_BINARY:
            return _DEFAULT_BINARY[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            if f"{n.value.id}.{n.attr}" in _DEFAULT_NAMES:
                return getattr(importlib.import_module(n.value.id), n.attr)
        raise ValueError(f"unsupported stub default: {expr!r}")
    return ev(ast.parse(expr, mode="eval").body)

IDS = []


def _make(mod, name, fid, sig, kwsig=None):
    params = sig["params"] if sig else None
    names = [p["name"] for p in params] if params else None
    defaults = {p["name"]: p["default"] for p in params if p["default"] is not None} if params else {}
    # kwsig = FLEngine バイナリ由来 (PyArg_ParseTupleAndKeywords の書式 + kwlist)。kwlist があれば stubs 名より優先。
    # kwlist 無し (flags=1/4) は stubs 署名のまま (flags=1 の channelCount を MCPTools が globalCount= で呼ぶため、
    # kwargs 拒否にはしない。実 FL の挙動は未確認)。
    required = None
    kwnames = names
    if kwsig:
        if kwsig.get("kwlist") is not None:
            names = list(kwsig["kwlist"])
            sn = [p["name"] for p in params] if params else []
            # stubs の既定値の引き継ぎ: 同名ならその引数の値、改名 (同位置で名前だけ違う) なら同位置の値。
            # stubs 側の名前が kwlist の別位置に現れる (位置がずれた) 場合は別の引数の値なので引き継がない。
            defaults = {}
            for i, n in enumerate(names):
                if n in sn:
                    d = params[sn.index(n)]["default"]
                elif i < len(sn) and sn[i] not in names:
                    d = params[i]["default"]
                else:
                    d = None
                if d is not None:
                    defaults[n] = d
            # kwlist 内の重複名 (バイナリ由来。arrangement.selectionSet の 2 つ目) は、最初の出現だけを kw で束縛し、
            # 2 つ目以降は位置専用として扱う (実 CPython は重複の 2 つ目を kw で束縛する場合があるが、誤記を kw で踏まない側に倒す)。
            kwnames = [n if n not in names[:i] else None for i, n in enumerate(names)]
        required = kwsig.get("required")

    def bind(args, kw):
        if not kw:
            return args
        if names is None:
            raise TypeError(f"{mod}.{name}() takes no keyword arguments (signature unknown)")
        free = {n for i, n in enumerate(kwnames) if i >= len(args) and n is not None}
        extra = sorted(k for k in kw if k not in free)
        if extra:
            raise TypeError(f"{mod}.{name}() unexpected keyword arguments {extra}")
        out = list(args)
        gap = None  # 省略された任意引数 (既定値が C 側にあり不明) の位置
        for i, n in enumerate(names[len(args):], start=len(args)):
            if kwnames[i] is not None and n in kw:
                if gap is not None:
                    raise TypeError(f"{mod}.{name}() cannot skip optional argument '{names[gap]}' (default unknown)")
                out.append(kw.pop(n))
            elif gap is not None:
                continue  # gap 以降の未指定引数は省略 (既定値を足すと位置がずれる)
            elif n in defaults:
                out.append(_default_value(defaults[n]))  # stubs 由来の既定値 (許可した式だけ)
            elif required is not None and i >= required:
                gap = i if gap is None else gap
            else:
                raise TypeError(f"{mod}.{name}() missing argument '{n}'")
        return tuple(out)

    def f(*args, **kw):
        a = bind(args, kw)
        try:
            return _flhost.call(fid, a)
        except _flhost.HostError as e:
            code, msg = e.args if len(e.args) == 2 else (0, str(e))
            raise _ERR.get(code, RuntimeError)(msg) from None

    f.__name__ = name
    f.__qualname__ = f"{mod}.{name}"
    f.__module__ = mod
    return f


def install(table_path="/fl/Lib/flapi_table.json"):
    t = json.load(open(table_path))
    n = 0
    for mod, funcs in t["modules"].items():
        m = types.ModuleType(mod)
        for name in funcs:
            fid = len(IDS)
            IDS.append(f"{mod}.{name}")
            setattr(m, name, _make(mod, name, fid, funcs[name].get("sig"), funcs[name].get("kwsig")))
            n += 1
        sys.modules[mod] = m
    return n
