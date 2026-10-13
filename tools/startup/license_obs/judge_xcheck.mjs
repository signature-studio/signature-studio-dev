// results/cases.json の各ケース (実機械語の unicorn 実行) を、ilreg の reader.mjs judge() (FORMAT.md を移植した別実装) に通して突合する。
// 入力: cases.json の machine (AppData/ComputerName/MachineGuid) と、実機械語が復号した結果 head (0x10cad6e 時点; ':' が無ければ復号結果全体)。
// 出力 (stdout): JSON {case, emu:{gradeChar,flag,button}, judge:{gradeChar,flag,button}, match}[]。不一致があれば exit 1。
// --neg: ネガティブコントロール。B1 の機械語観測値 (gradeChar 0x40) に対し、judge() に正規書式の合成平文 (`:F0:20991231:` + `|id:<機械文字列>` + `|31000:20991231:`) を与えると
//        gradeChar が 0x41 になり突合が **不一致になる** ことを確認する (突合が常に match を返す形骸でないことの証明)。不一致を検出したら exit 0。
// 実行: node tools/startup/license_obs/judge_xcheck.mjs [--neg]   (verify.py が呼ぶ)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { judge, machineString } from '../vreg/ilreg/verify/reader.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(HERE, 'results', 'cases.json'), 'utf8'));
const hex2 = (n) => n.toString(16).padStart(2, '0');
const NEG = process.argv.includes('--neg');
const out = [];
for (const c of cases) {
  // 比較対象: ILRegKey の有無/内容だけが違い、機械語の改変 (N*/NB*) を含まない入力。cl=1 (Fire check) と units 無しは別経路なので除外
  if (!/^(A1|A3|A4|D2|B1|B3|D1|D3)\b/.test(c.case) || c.status !== 'ok') continue;
  const m = c.machine;
  const ms = machineString({ appData: m.appData, computerName: m.computerName, machineGuid: m.machineGuid });
  // 復号結果 head を UTF-16LE → 文字列 (非文字列バイトでも 1 コードユニット = 1 文字として扱う)
  let plain;
  if (c.head_utf16_hex) {
    const b = Buffer.from(c.head_utf16_hex, 'hex');
    plain = '';
    for (let i = 0; i + 1 < b.length; i += 2) plain += String.fromCharCode(b.readUInt16LE(i));
  }
  if (NEG) {
    if (!c.case.startsWith('B1')) continue;
    plain = `:F0:20991231:|id:${ms}|31000:20991231:`;
  }
  const j = judge({ plain, machineStr: ms });
  const emu = { gradeChar: c.gradeChar_hex, flag: c.flag_hex };
  const jd = { gradeChar: hex2(j.gradeChar), flag: hex2(j.flagByte.value) };
  // ボタン ID: 実機械語で ILRegKey 非空のとき 0x10cf531- が実行される (A 群・空 D2 は別経路で 0 のまま) ため、非空のみ比較
  const nonempty = c.head_utf16_hex !== null && c.head_utf16_hex !== undefined && c.head_utf16_hex.length > 0;
  if (nonempty) { emu.button = c.button_id; jd.button = j.buttonId; }
  out.push({ case: c.case.split(' ')[0], emu, judge: jd, match: JSON.stringify(emu) === JSON.stringify(jd) });
}
console.log(JSON.stringify(out));
if (NEG) process.exit(out.length === 1 && !out[0].match && out[0].judge.gradeChar === '41' ? 0 : 1);
process.exit(out.length > 0 && out.every((o) => o.match) ? 0 : 1);
