// PY-280 (#3978) 競合実測用: 関数を 1 つ実装する疑似ブランチの編集を作る (worktree 上で実行)。
//   node tests/provider_expect_sim.mjs <worktree の tools/python> new <tag> <fn> <0|1>
//     provider_expect/<tag>.json を 1 つ足し、provider/fl_engine.c と host/fl_mock.mjs に実装行を足す (0: screen 側, 1: channels 側)
//   node tests/provider_expect_sim.mjs <worktree の tools/python> old <tag> <fn> 0
//     旧方式の再現 (provider_check.mjs 本体に const・OR 連鎖・手書き件数 assert を足す)。基点は旧方式の provider_check.mjs (origin/main の手書き件数版)。
//     件数は正規表現で拾い、基点の値に +1 / -1 する (値は基点ごとに違うため固定しない)
//   競合の判定: git merge-tree --write-tree --name-only <A> <B>  (REPORT_PY280.md §5)
import fs from "node:fs";
const [dir, mode, tag, fn, anchor] = process.argv.slice(2);
const mod = fn.split(".")[0], name = fn.split(".")[1];
const rd = (p) => fs.readFileSync(`${dir}/${p}`, "utf8");
const wr = (p, s) => fs.writeFileSync(`${dir}/${p}`, s);
const insertAfter = (lines, pred, add) => { const k = lines.findIndex(pred); if (k < 0) throw new Error("anchor missing"); lines.splice(k + 1, 0, add); };
const insertBefore = (lines, pred, add) => { const k = lines.findIndex(pred); if (k < 0) throw new Error("anchor missing"); lines.splice(k, 0, add); };
if (mode === "new") {
  fs.mkdirSync(`${dir}/tests/provider_expect`, { recursive: true });
  wr(`tests/provider_expect/${tag}.json`, `{\n  "tag": "${tag}",\n  "refs": [],\n  "note": "sim",\n  "functions": ["${fn}"]\n}\n`);
  const c = rd("provider/fl_engine.c").split("\n");
  const cAnchor = ["FL_H(screen, isBlanked)", "FL_H(channels, getStepParam)"][+anchor];
  insertAfter(c, (l) => l.includes(cAnchor), `FL_H(${mod}, ${name}) { NARGS(0, 0); return fl_ret_b(c, 0); }`);
  wr("provider/fl_engine.c", c.join("\n"));
  const m = rd("host/fl_mock.mjs").split("\n");
  const mAnchor = ["    \"screen.isBlanked\": ", "    \"channels.getStepParam\": "][+anchor];
  insertBefore(m, (l) => l.startsWith(mAnchor), `    "${fn}": (...a) => { arity(a, 0, 0); return 0; },`);
  wr("host/fl_mock.mjs", m.join("\n"));
} else {
  const p = rd("tests/provider_check.mjs").split("\n");
  insertBefore(p, (l) => l.startsWith("let impl = 0, unimpl = 0;"), `const ${tag} = new Set(["${fn}"]);`);
  const s0 = p.join("\n");
  const s = s0
    .replace(/\|\| (\w+)\.has\(id\)\) assert\.ok/, (_, v) => `|| ${v}.has(id) || ${tag}.has(id)) assert.ok`)
    .replace(/assert\.equal\(impl, (\d+)\); assert\.equal\(unimpl, (\d+)\);/, (_, a, b) => `assert.equal(impl, ${+a + 1}); assert.equal(unimpl, ${+b - 1});`);
  if (s === s0) throw new Error("old: anchor missing");
  wr("tests/provider_check.mjs", s);
}
console.log(`sim ${mode} ${tag} ${fn} ok`);
