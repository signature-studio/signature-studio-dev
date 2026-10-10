// wasm CPython 単体スモーク (worker/RPC 無し): print(1+1), 標準ライブラリ主要部, _flhost 往復
import createFlPython from "../dist/flpy.js";

const out = [];
const M = await createFlPython({
  locateFile: (p) => new URL("../dist/" + p, import.meta.url).pathname,
  print: (t) => out.push(t),
  printErr: (t) => out.push("ERR " + t),
  flHostCall: (fn, args) => (fn === 0 ? { echo: args, f: 1.5 } : null),
});
const rc = M.ccall("flpy_init", "number", ["string"], [""]);
if (rc !== 0) throw new Error("init failed: " + M.UTF8ToString(M._flpy_last_error()));
const run = (code) => {
  const r = M.ccall("flpy_run", "number", ["string", "string"], [code, "<smoke>"]);
  if (r !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error()));
};
run(`
import sys, struct, json, math, array, binascii, zlib, hashlib, datetime, re, random, decimal, collections, itertools, functools, inspect, ast, dis, typing
print(1 + 1)
print(sys.version.split()[0], sys.platform, sys.byteorder)
print(struct.pack('<If', 7, 1.5).hex(), struct.unpack('>H', b'\\x01\\x02'))
print(json.dumps({'a': [1, 2.5, None]}), round(math.sqrt(2), 6), zlib.crc32(b'abc'))
print(hashlib.sha256(b'x').hexdigest()[:16], datetime.date(2026, 10, 10).isoformat())
print(re.sub(r'(\\d+)', r'<\\1>', 'a12b345'), decimal.Decimal('1.1') + decimal.Decimal('2.2'))
print(sorted(collections.Counter('mississippi').items()), list(itertools.islice(itertools.count(5), 3)))
def f(x: int) -> int: return x * 2
print(inspect.signature(f), f(21))
# FL 同梱スクリプト群 (pyscript/pyc 65 本) が実際に import する stdlib 22 モジュールが全て解決できること
import importlib
mods = "__future__ abc ast collections copy enum functools inspect itertools json math operator os pathlib random re sys time traceback types typing zlib".split()
bad = []
for m in mods:
    try: importlib.import_module(m)
    except Exception as e: bad.append((m, repr(e)))
print("stdlib used by FL scripts:", len(mods), "missing:", bad)
def rec(n): return rec(n - 1) if n else 0
print("recursion 900 ok:", rec(900) == 0)
import _flhost
print(_flhost.call(0, (1, 2.5, 'あ', None, True, b'xy')))
`);
console.log(out.join("\n"));
