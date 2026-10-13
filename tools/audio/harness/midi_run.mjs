// MIDI shim e2e ランナー (AU-3 #188)。使い方: node harness/midi_run.mjs [--out results/midi_results.json]
//  1. 本番シナリオ: flmidi_test.wasm の checks[] が全て ok であること (1 件でも false なら exit 1)
//  2. ネガティブコントロール: 入力を壊して (500 番を欠落 / SysEx を 1 ビット反転) 該当 check が FAIL することを確認 (FAIL しなければ「検出能力なし」で exit 1)
//  3. Worker 内 Web MIDI の実測 (記録のみ。判定は「Worker 内で API が露出し/拒否されたか」を記録するだけで合否には使わない)
import { withChrome } from "./chrome.mjs";
import path from "node:path"; import fs from "node:fs"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const outFile = args.includes("--out") ? args[args.indexOf("--out") + 1] : path.join(here, "../results/midi_results.json");
const root = path.join(here, "../build/web");
const out = { date: new Date().toISOString(), chrome: "headless google-chrome 154", runs: [] };
let failed = 0;
const EXPECT_CHECKS = 54;   // 実装済み check 数 (増減したら更新。数が合わなければ FAIL = 空振り防止)

async function runOne(name, q, judge) {
  const t0 = Date.now();
  let r, err = null;
  await withChrome({ root, page: "index_midi.html" + (q ? "?" + q : ""), log: () => {} }, async (cdp) => { try { r = await cdp.eval("window.__done"); } catch (e) { err = String(e); } });
  const ms = Date.now() - t0;
  let ok = false, msg = err ?? "";
  if (r) { try { [ok, msg] = judge(r); } catch (e) { msg = "judge 例外: " + e.message; } }
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name.padEnd(34)} ${msg} (${ms} ms)`);
  out.runs.push({ name, query: q, ok, msg, ms, result: r ?? null, error: err });
  return r;
}

const bad = (r) => (r.checks ?? []).filter((c) => !c.ok);
await runOne("midi_all", "", (r) => {
  if (r.aborted) return [false, "abort: " + r.what];
  const b = bad(r), js = r.js ?? {};
  const jsOk = js.synShortOk === true && js.synSysex?.length === 2 && js.synSysex.every((x) => x.ok) && js.synSysex[0].len === 3000 && js.synSysex[1].len === 40000 && js.outSent?.drum === 0 && js.handlerAfterClose === true && js.noHandlerEmits === 3;
  const n = r.checks.length;
  return [b.length === 0 && n === EXPECT_CHECKS && jsOk, `checks ${n - b.length}/${n} (want ${EXPECT_CHECKS}) ${b.map((c) => c.name + ":" + c.detail).join(" | ")} js: synShortOk=${js.synShortOk} sysexOut=${JSON.stringify(js.synSysex?.map((x) => [x.len, x.ok]))} drumSent=${js.outSent?.drum} handlerDetachedAfterClose=${js.handlerAfterClose}`];
});
const rall = out.runs[0].result;
if (rall?.checks) console.log("  checks: " + rall.checks.map((c) => `${c.ok ? "+" : "-"}${c.name}`).join(" "));
// ネガティブコントロール: 壊した入力で、対応する check が FAIL し、かつ無関係な check は PASS のまま (巻き込み FAIL でなく狙い撃ちで検出)
await runOne("negctl_drop_one_short_msg", "corrupt=drop500", (r) => { const b = bad(r).map((c) => c.name); return [!r.aborted && b.includes("short_seq_ok") && b.length <= 3, `FAIL した check = ${JSON.stringify(b)} (short_seq_ok を含み、巻き込み FAIL が 3 件以内なら検出成功)`]; });
await runOne("negctl_flip_sysex_bit", "corrupt=sysexflip", (r) => { const b = bad(r).map((c) => c.name); return [!r.aborted && b.includes("sysex_content") && b.length <= 3, `FAIL した check = ${JSON.stringify(b)} (sysex_content を含み、巻き込み FAIL が 3 件以内なら検出成功)`]; });

// Worker 内 Web MIDI 実測
{
  let r, err = null; const t0 = Date.now();
  await withChrome({ root, page: "index_midiprobe.html", log: () => {} }, async (cdp) => { try { r = await cdp.eval("window.__done"); } catch (e) { err = String(e); } });
  const ok = !!r && !err && r.worker && !r.worker.error;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"} worker_webmidi_probe              ${err ?? JSON.stringify(r)} (${Date.now() - t0} ms)`);
  out.runs.push({ name: "worker_webmidi_probe", ok, result: r ?? null, error: err });
}
fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
console.log(`\n${out.runs.length - failed}/${out.runs.length} PASS -> ${outFile}`);
process.exit(failed ? 1 : 0);
