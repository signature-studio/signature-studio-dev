"""fl_api — FL 組込 API モジュール (channels/mixer/transport/... ) を wasm Python 内に生成する。

データ駆動: flapi_table.json (FLEngine rodata 抽出 + 公開 stubs の署名) から、
  各関数 = `_flhost.call(fn_id, args)` を呼ぶ薄いラッパ。fn_id は table の列挙順 (flapi_ids.json と同一)。
実装本体 (FLEngine 側) は JS ホストが fn_id → 実関数に対応付ける。Python 側に FL ロジックは無い。
"""
import json
import sys
import types

import _flhost

# FL API の例外コード (FLEngine rodata の文言: "Invalid value / Unspecified error / Operation unsafe at current time /
# Range error / Index out of range / Wrong number of function parameters or wrong parameter type / ...")
_ERR = {1: ValueError, 2: RuntimeError, 3: RuntimeError, 4: IndexError, 5: TypeError, 6: RuntimeError,
        7: RuntimeError, 8: RuntimeError}

IDS = []


def _make(mod, name, fid, sig):
    params = sig["params"] if sig else None
    names = [p["name"] for p in params] if params else None
    defaults = {p["name"]: p["default"] for p in params if p["default"] is not None} if params else {}

    def bind(args, kw):
        if not kw:
            return args
        if names is None:
            raise TypeError(f"{mod}.{name}() takes no keyword arguments (signature unknown)")
        out = list(args)
        for n in names[len(args):]:
            if n in kw:
                out.append(kw.pop(n))
            elif n in defaults:
                out.append(eval(defaults[n], {}))  # stubs 由来の単純リテラル (True/False/0/-1/None)
            else:
                raise TypeError(f"{mod}.{name}() missing argument '{n}'")
        if kw:
            raise TypeError(f"{mod}.{name}() unexpected keyword arguments {sorted(kw)}")
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
            setattr(m, name, _make(mod, name, fid, funcs[name].get("sig")))
            n += 1
        sys.modules[mod] = m
    return n
