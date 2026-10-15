// PY-2 (#82): 48 tool の result を全文 (切り詰めなし) で 3 経路 (mock / SAB+provider / 静的リンク) 比較する。
//   node tests/fulltext_parity.mjs
//   前提: fetch_inputs.sh・build_cpython_wasm.sh・build_flpy.sh・provider/build.sh・build_flpy_static.sh 済み (dist/ と work/ が揃っている)。
//   出力: work/fulltext/{mock,wasm,static}.json と各組の差件数。組の差が 1 件でもあれば exit 1。
//   ネガコン: 先頭 160 字より後ろの 1 字を変えた値を入れ、全文比較が検出し、先頭 160 字のゲートは検出しないことを確認する。
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const J = JSON.stringify;
const root = new URL("../", import.meta.url);
const out = new URL("work/fulltext/", root);
fs.mkdirSync(out, { recursive: true });
let fails = 0;
const fail = (m) => { fails++; console.log("FAIL", m); };

const engines = [
  ["mock", "tests/all_tools.mjs", { FL_ENGINE: "" }],
  ["wasm", "tests/all_tools.mjs", { FL_ENGINE: "wasm" }],
  ["static", "tests/static_check.mjs", { STATIC_WASM: "" }],
];
execFileSync(process.execPath, [fileURLToPath(new URL("tests/all_tools.mjs", root))], {
  cwd: fileURLToPath(root), env: { ...process.env, FL_ENGINE: "wasm" }, stdio: ["ignore", "ignore", "inherit"],
});
console.log("前提: analysis/mcp/tool_coverage.wasm.json を再生成 (gitignore 対象、static_check の SAB 比較元)");
for (const [name, script, env] of engines) {
  execFileSync(process.execPath, [fileURLToPath(new URL(script, root))], {
    cwd: fileURLToPath(root),
    env: { ...process.env, ...env, FULLTEXT_OUT: fileURLToPath(new URL(`${name}.json`, out)) },
    stdio: ["ignore", "ignore", "inherit"],
  });
  console.log(`${name}: 実行 rc=0`);
}
const E = Object.fromEntries(engines.map(([n]) => [n, JSON.parse(fs.readFileSync(new URL(`${n}.json`, out)))]));
for (const [n, e] of Object.entries(E)) if (e.tools.length !== 48) fail(`${n}: tool 数 ${e.tools.length} != 48`);

const diffs = (a, b) => {
  const B = new Map(b.tools.map((t) => [t.name, t.text]));
  return a.tools.filter((t) => B.get(t.name) !== t.text).length;
};
for (const [a, b] of [["mock", "wasm"], ["mock", "static"], ["wasm", "static"]]) {
  const d = diffs(E[a], E[b]);
  fails += d;
  console.log(J({ pair: `${a} vs ${b}`, tools: E[a].tools.length, text_diff: d }));
}

const over = E.static.tools.filter((t) => t.text.length > 160);
console.log(J({ tools_with_result_over_160: over.map((t) => `${t.name}:${t.text.length}`), gate_cut: 160 }));
for (const n of ["get_highlight_names", "get_browser_names"]) {
  const s = E.static.tools.find((t) => t.name === n).text;
  console.log(J({ tool: n, utf16_length: s.length, utf8_bytes: Buffer.byteLength(s, "utf8"), codepoints: [...s].length, ascii_only: /^[\x00-\x7f]*$/.test(s) }));
}

const orig = E.mock.tools.find((t) => t.name === "get_highlight_names").text;
if (orig.length <= 300) fail("ネガコン: get_highlight_names が 300 字以下 (改変位置 300 が無い)");
const at = 300;
const mut = { tools: E.mock.tools.map((t) => (t.name === "get_highlight_names" ? { ...t, text: orig.slice(0, at) + (orig[at] === "x" ? "y" : "x") + orig.slice(at + 1) } : t)) };
const detected = diffs(E.mock, mut);
const gateSees = mut.tools[E.mock.tools.findIndex((t) => t.name === "get_highlight_names")].text.slice(0, 160) !== orig.slice(0, 160);
console.log(J({ negctrl: `get_highlight_names の ${at} 字目 (160 字より後ろ) を 1 字変更`, full_text_detects: detected, prefix160_gate_detects: gateSees }));
if (detected !== 1) fail(`ネガコン: 全文比較が 1 件を検出しない (${detected})`);
if (gateSees) fail("ネガコン: 先頭 160 字のゲートが改変を検出した (前提が違う)");

console.log(fails ? `FULLTEXT PARITY FAIL (${fails})` : "FULLTEXT PARITY OK");
process.exit(fails ? 1 : 0);
