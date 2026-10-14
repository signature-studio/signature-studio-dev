// 表の引数個数 (sig.params) を FLEngine の書式 (kwsig の required/max) へ正規化した関数 (PY-102 / #2927) について、
// C provider の個数検査 (fl_dispatch.c の argc < nmin || argc > np → code 5) が PE と同じ個数を通すことを確かめる。
//   node tests/sig_arity_probe.mjs     (前提: provider/build.sh 済み)
// 対象は sig.arity_from === "kwsig" の関数のうち C に実装があるもの (未実装は code 2 が先に返り、個数検査に届かない)。
// 各関数について: (1) max 個の呼出しは code 5 にならず、mock と結果が一致する (2) max+1 個・required-1 個は wasm で code 5。
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const table = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_table.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

// 型ごとの代表値 (C 側 type_ok は bool/int/str の tag を検査する。型不明は any 扱い)
const sample = (t) => (t === "bool" ? false : t === "str" ? "x" : 0);

const targets = [];
for (const [m, fs_] of Object.entries(table.modules)) {
  for (const [n, e] of Object.entries(fs_)) {
    if (e.sig?.arity_from === "kwsig") targets.push({ name: `${m}.${n}`, params: e.sig.params, req: e.kwsig.required, max: e.kwsig.max });
  }
}

const probe = (eng, name, args) => {
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : v };
  } catch (e) {
    return { code: e.flCode ?? null, unimpl: /not implemented/.test(e.message) };
  }
};

const implemented = [];
const unimpl = [];
const fails = [];
for (const t of targets) {
  const okArgs = t.params.map((p) => sample(p.type));
  const first = probe(wasm, t.name, okArgs);
  if (first.unimpl) { unimpl.push(t.name); continue; }
  implemented.push(t.name);
  if (first.code === 5) fails.push({ name: t.name, why: `max=${t.max} 個が拒否された`, wasm: first });
  // mock は個数を検査しない (既知) ため、max 個の呼出しで結果を比べる
  const mo = probe(mock, t.name, okArgs);
  if (JSON.stringify(mo) !== JSON.stringify(first)) fails.push({ name: t.name, why: "mock と wasm の結果が違う", mock: mo, wasm: first });
  const over = probe(wasm, t.name, [...okArgs, 0]);
  if (over.code !== 5) fails.push({ name: t.name, why: `max+1 個が拒否されない`, wasm: over });
  if (t.req > 0) {
    const under = probe(wasm, t.name, okArgs.slice(0, t.req - 1));
    if (under.code !== 5) fails.push({ name: t.name, why: `required-1 個が拒否されない`, wasm: under });
  }
}

assert.equal(targets.length, 24, "kwsig と表の個数を正規化した関数の数 (analysis/flapi_table.py pe_arity)");
assert.deepEqual(fails, [], `個数検査の違反 ${fails.length} 件`);
console.log(JSON.stringify({ kwsig_targets: targets.length, implemented, unimplemented: unimpl.length, fails: 0, PASS: true }));
