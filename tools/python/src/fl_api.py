"""fl_api — FL 組込 API モジュール (channels/mixer/transport/... ) を wasm Python 内に生成する。

データ駆動: flapi_table.json (FLEngine rodata 抽出 + 公開 stubs の署名) から、
  各関数 = `_flhost.call(fn_id, args)` を呼ぶ薄いラッパ。fn_id は table の列挙順 (flapi_ids.json と同一)。
実装本体 (FLEngine 側) は JS ホストが fn_id → 実関数に対応付ける。Python 側に FL ロジックは無い。
"""
import ast
import json
import sys
import types

import _flhost

# FL API の例外コード (FLEngine rodata の文言: "Invalid value / Unspecified error / Operation unsafe at current time /
# Range error / Index out of range / Wrong number of function parameters or wrong parameter type / ...")
_ERR = {1: ValueError, 2: RuntimeError, 3: RuntimeError, 4: IndexError, 5: TypeError, 6: RuntimeError,
        7: RuntimeError, 8: RuntimeError}

IDS = []


def _stub_defaults(params):
    # stubs の既定値は単純リテラル (True/False/0/-1/None) だけ採用する。`midi.PIM_None` 等の記号は数値が
    # 静的に分からないので既定値不明 (省略時は C 側に任せ、後続を指定する呼出しは TypeError)。
    out = {}
    for p in params or []:
        if p["default"] is None or p["name"] in out:
            continue
        try:
            out[p["name"]] = ast.literal_eval(p["default"])
        except (ValueError, SyntaxError):
            pass
    return out


def _make(mod, name, fid, sig, kwsig=None):
    params = sig["params"] if sig else None
    names = [p["name"] for p in params] if params else None
    defaults = _stub_defaults(params)
    # kwsig = FLEngine バイナリ由来 (PyArg_ParseTupleAndKeywords の書式 + kwlist)。kwlist があれば stubs 名より優先。
    # kwlist 無し (flags=1/4) は stubs 署名のまま (flags=1 の channelCount を MCPTools が globalCount= で呼ぶため、
    # kwargs 拒否にはしない。実 FL の挙動は未確認)。
    required = None
    kwnames = names
    if kwsig:
        if kwsig.get("kwlist") is not None:
            names = list(kwsig["kwlist"])
            # 既定値は stubs の同名引数のものだけ引き継ぐ。名前だけ違う同位置の引数 (mode→useDb 等) の既定値は
            # 別の引数の値なので入れない (PY-15 #653: 誤束縛 0 の条件)。
            defaults = {n: defaults[n] for n in names if n in defaults}
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
                out.append(defaults[n])
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
