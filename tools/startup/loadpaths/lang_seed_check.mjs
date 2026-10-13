// lang_seed_check.mjs — 非 en 言語 seed の seed 層の確認 (#590)。wasm / FL 素材は不要。
//   usage: node lang_seed_check.mjs [lang=ja]
//   [A] 現行 seed.json: Program language は catalog のみ (apply:false) → 仮想レジストリに値が出ない (= エンジン既定 en)
//   [B] 同 entry を apply:true・value=<lang> にした派生 seed (メモリ上のみ。seed.json は書き換えない) → 値が <lang> で出る
//   [C] ネガコン: 派生 seed の言語 entry を元に戻す / 別 group を skip する → 値が出ない
//   これは「seed が値を載せる」層の確認であり、エンジンがその値で .moe を読むこと (#590 受入条件 1) の確認ではない。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveSeed } from '../vreg/js/seed.mjs';
import { getValue } from '../vreg/js/regfile.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const lang = process.argv[2] ?? 'ja';
const base = JSON.parse(readFileSync(path.join(HERE, '../vreg/data/seed.json'), 'utf8'));
const KEY = 'Software\\Image-Line\\Shared\\Language';
const NAME = 'Program language';
const isLang = (e) => e.hive === 'HKCU' && e.key === KEY && e.name === NAME;
const read = (seed) => getValue(resolveSeed(seed, { machineGuid: 'x' }).model, 'HKCU', KEY, NAME);

const fails = [];
const expect = (cond, msg) => { if (!cond) fails.push(msg); console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${msg}`); };

const n = base.entries.filter(isLang).length;
expect(n === 1, `seed.json に Program language の entry が 1 件 (実際 ${n})`);

const derive = (apply, value) => ({ ...base, entries: base.entries.map((e) => (isLang(e) ? { ...e, apply, value } : e)) });

expect(read(base) === undefined, '[A] 現行 seed: Program language は仮想レジストリに出ない (エンジン既定 en)');
const v = read(derive(true, lang));
expect(v?.v === lang && v?.t === 'REG_SZ', `[B] 派生 seed (apply:true, value=${lang}): REG_SZ "${lang}" が出る (実際 ${JSON.stringify(v)})`);
expect(read(derive(false, lang)) === undefined, '[C1] ネガコン: apply:false に戻すと出ない (= 言語 seed を外すと en 既定に戻る)');
expect(read(derive(true, '')).v === '', '[C2] ネガコン: value が空だと空文字 (0x9deaa0 が OS 言語決定に回る値であり、ja ではない)');
const skipped = resolveSeed(derive(true, lang), { machineGuid: 'x', skipGroups: [base.entries.find(isLang).group] });
expect(getValue(skipped.model, 'HKCU', KEY, NAME) === undefined, '[C3] ネガコン: 当該 group を skip すると出ない');

if (fails.length) { console.error(`lang_seed_check FAIL ${fails.length} 件`); process.exit(1); }
console.log('lang_seed_check PASS');
