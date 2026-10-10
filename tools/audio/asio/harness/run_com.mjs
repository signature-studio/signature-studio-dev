// CAB-97 シナリオランナー: 1 つの headless Chrome で COM 経由の全シナリオを実行し判定する。
// 使い方: node harness/run_com.mjs [--quick] [--only name,name] [--out work/results_com.json]
// chrome 駆動は既存 tools/audio/harness/chrome.mjs を流用 (読取専用の参照利用)。
import { withChrome } from "../../harness/chrome.mjs";
import path from "node:path"; import fs from "node:fs"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const quick = args.includes("--quick");
const only = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
const outFile = args.includes("--out") ? args[args.indexOf("--out") + 1] : path.join(here, "../work/results_com.json");
const secs = (n) => (quick ? Math.min(n, 3) : n);

// COM 面の共通期待 (CAB-97 実測値との一致)
const comOk = (r) => {
  const c = r.com ?? {};
  const wantSel = JSON.stringify([[1, 2], [2, 0], [1, 7], [7, 0]]);   // ドライバ→ホスト問合せ (flasio_create_buffers ハンドシェイク)
  const gotSel = JSON.stringify(c.sellog ?? []);
  const probs = [];
  if (c.hr_register !== 0) probs.push(`hr_register=${c.hr_register}`);
  if (c.hr_enum !== 0) probs.push(`hr_enum=${c.hr_enum}`);
  if (c.enum_n !== 1) probs.push(`enum_n=${c.enum_n}`);
  if (c.hr_cocreate !== 0) probs.push(`hr_cocreate=${c.hr_cocreate}`);
  if (c.driver !== "FL Studio ASIO") probs.push(`driver=${c.driver}`);
  if (c.refs_last !== 0) probs.push(`refs_last=${c.refs_last}`);
  if (c.alive !== 0) probs.push(`alive=${c.alive}`);
  if (gotSel !== wantSel) probs.push(`sellog=${gotSel}`);
  if (c.msglog_n !== 4) probs.push(`msglog_n=${c.msglog_n}`);
  if (c.dialogs !== 0) probs.push(`dialogs=${c.dialogs}`);
  if (c.cmd17 !== 0) probs.push(`cmd17=${c.cmd17}`);
  if (c.output_ready !== -1000) probs.push(`output_ready=${c.output_ready}`);
  return [probs.length === 0, probs.length ? "COM: " + probs.join(", ") : `COM 取得→Release 一気通貫 (QI ${c.qi_ok} 回, sellog ${gotSel})`];
};
const underrunFree = (r) => [r.stats.underruns === 0 && r.stats.silence_frames === 0, `underruns=${r.stats.underruns} silence=${r.stats.silence_frames}`];
const reportedOk = (r) => {
  const rep = r.reported ?? {};
  const probs = [];
  if (rep.nin !== 2 || rep.nout !== 2) probs.push(`ch=${rep.nin}/${rep.nout}`);
  if (rep.min !== 0x100 || rep.max !== 0x1000 || rep.gran !== 0) probs.push(`buf=${rep.min}/${rep.max}/${rep.gran}`);
  if (rep.pref_created !== r.buf) probs.push(`pref_created=${rep.pref_created}`);
  if (rep.ch_type !== 0x13) probs.push(`type=${rep.ch_type}`);
  if (rep.lat_out <= 0) probs.push(`lat_out=${rep.lat_out}`);
  return [probs.length === 0, probs.length ? "報告値: " + probs.join(", ") : `getChannels 2/2, getBufferSize 0x100/0x1000/gran0, type 0x13, lat_out=${rep.lat_out}f`];
};

const scenarios = [
  { name: "com_ramp_b256_d2", q: `mode=ramp&buf=256&secs=${secs(5)}`,
    expect: (r) => { const [a1, m1] = comOk(r); const [a2, m2] = underrunFree(r); const [a3, m3] = reportedOk(r);
      const ramp = r.verify?.ramp;
      const a4 = ramp && ramp.mismatches === 0 && ramp.frames_checked > 0;
      return [a1 && a2 && a3 && a4, [m1, m2, m3, `ramp ${ramp ? `${ramp.mismatches}/${ramp.frames_checked}` : "n/a"} (bufferSwitchTimeInfo ${r.timeinfo?.calls} calls bad=${r.timeinfo?.bad})`].join("; ")]; } },
  { name: "com_ramp_b1024_d2", q: `mode=ramp&buf=1024&secs=${secs(5)}`,
    expect: (r) => { const [a1, m1] = comOk(r); const [a2, m2] = underrunFree(r); const ramp = r.verify?.ramp;
      return [a1 && a2 && ramp && ramp.mismatches === 0, [m1, m2, `ramp ${ramp ? `${ramp.mismatches}/${ramp.frames_checked}` : "n/a"}`].join("; ")]; } },
  { name: "com_sine_b256_d2", q: `mode=sine&buf=256&secs=${secs(5)}`,
    expect: (r) => { const [a1, m1] = comOk(r); const [a2, m2] = underrunFree(r); const s = r.verify?.sine;
      const a3 = s && s.max_abs_err < 1e-5 && s.zero_runs_ge16 === 0;
      return [a1 && a2 && a3, [m1, m2, `sine maxErr=${s ? s.max_abs_err.toExponential(2) : "n/a"} rms=${s ? s.rms?.toFixed(4) : "-"}`].join("; ")]; } },
];

const sel = scenarios.filter((s) => !only || only.includes(s.name));
const results = [];
let failed = 0;
await withChrome({ root: path.join(here, "../work/web"), page: "index_com.html?" + sel[0].q, log: () => {} }, async (cdp) => {
  let first = true;
  for (const sc of sel) {
    if (!first) await cdp.navigate("index_com.html?" + sc.q);
    first = false;
    let r, err = null;
    try { r = await cdp.eval("window.__done"); } catch (e) { err = String(e); }
    let ok = false, msg = err ?? "";
    if (r) {
      try { [ok, msg] = sc.expect(r); }
      catch (e) { ok = false; msg = r.aborted ? `想定外の abort: ${r.stderr?.find((l) => l.includes("FAIL-FAST")) ?? r.what}` : `expect 例外: ${e.message}`; }
    }
    if (!ok) failed++;
    results.push({ name: sc.name, query: sc.q, ok, msg, result: r ?? null, error: err });
    const st = r?.stats ?? {};
    console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(18)} ${msg}` +
      (r && !r.aborted ? `\n       cb=${st.cb_count} cb_max=${st.cb_max_us}us burst=${st.burst_obs} T=${st.T} (${st.T ? (st.T * 1000 / r.sr).toFixed(1) : "-"}ms) ` +
        `ti_cb=${st.timeinfo_cb} lat(in/out)=${r.reported?.lat_in}/${r.reported?.lat_out} QI=${r.com?.qi_ok} alive=${r.com?.alive}` : ""));
  }
});
fs.mkdirSync(path.dirname(outFile), { recursive: true });
for (const x of results) x.ran_at = new Date().toISOString();
fs.writeFileSync(outFile, JSON.stringify({ date: new Date().toISOString(), quick, chrome: "headless google-chrome", results }, null, 1));
console.log(`\n${results.length - failed}/${results.length} PASS -> ${outFile}`);
process.exit(failed ? 1 : 0);
