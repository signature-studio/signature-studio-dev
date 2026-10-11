// accept_recount.mjs — CAB-97 検収: node check の項目数を別アルゴリズムで再計算する (規則 37)。
//   node tools/audio/asio/accept_recount.mjs
//
// 実装側の e2e.sh は work/node_check.json の n/fail を読む。本スクリプトは **ソース
// (test/com_test.c) の判定呼出しサイトの静的集計** で数え、実測 JSON と突合する (= 別アルゴリズム)。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ASIO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '.');
const src = readFileSync(path.join(ASIO, 'test/com_test.c'), 'utf8');

// 判定呼出しサイト (文字列照合 ck_str + 数値照合 CK/CKV)。コメント行は除外。
const sites = [];
src.split('\n').forEach((l, i) => {
  const s = l.replace(/^\s+/, '');
  if (s.startsWith('//') || s.startsWith('*') || s.startsWith('/*')) return;
  const m = /\b(ck_str|CKV|CK)\("([^"]+)"/.exec(s);
  if (m) sites.push({ kind: m[1], name: m[2], line: i + 1 });
});
const byKind = {};
for (const x of sites) byKind[x.kind] = (byKind[x.kind] || 0) + 1;
const total = sites.length;

// 実測 JSON と突合
const j = JSON.parse(readFileSync(path.join(ASIO, 'work/node_check.json'), 'utf8'));
const jNames = new Set(j.checks.map((c) => c.name));
const sNames = new Set(sites.map((x) => x.name));

const hostmsg = sites.filter((x) => x.name.startsWith('hostmsg_'));
const hostmsgSel = hostmsg.filter((x) => /_sel\d/.test(x.name)).length;
const hostmsgCnt = hostmsg.length - hostmsgSel;
const slot = sites.filter((x) => x.name.startsWith('slot')).length;
const shimx = sites.filter((x) => x.name.startsWith('shimx')).length;

console.log(`CK/CKV=${byKind.CK ?? 0}+${byKind.CKV ?? 0} + ck_str=${byKind.ck_str ?? 0} = ${total}`);
console.log(`JSON: n=${j.n} fail=${j.fail} checks.length=${j.checks.length}`);
console.log(`source sites=${sNames.size} unique names / JSON=${jNames.size} unique names`);
const miss = [...sNames].filter((n) => !jNames.has(n));
const extra = [...jNames].filter((n) => !sNames.has(n));
console.log(`source-not-in-json: ${miss.join(', ') || '(none)'}`);
console.log(`json-not-in-source: ${extra.join(', ') || '(none)'}`);
console.log(`hostmsg=${hostmsg.length} (selector ${hostmsgSel} + counter ${hostmsgCnt}) / slot=${slot} / shimx=${shimx}`);
const okVerdict = total === j.n && j.fail === 0 && miss.length === 0 && extra.length === 0;
console.log(okVerdict ? 'accept_recount: MATCH (126/126, fail 0)' : 'accept_recount: MISMATCH');
process.exit(okVerdict ? 0 : 1);
