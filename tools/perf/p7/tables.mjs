// results/p7.jsonl → results/TABLES.md (自動生成)。  node tools/perf/p7/tables.mjs > tools/perf/p7/results/TABLES.md
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const rows = fs.readFileSync(path.join(HERE, 'results/p7.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
const f = (x, d = 1) => (typeof x === 'number' && Number.isFinite(x) ? x.toFixed(d) : '-');
const med = (xs) => { const s = xs.filter((x) => typeof x === 'number').sort((a, b) => a - b); return s.length ? s[s.length >> 1] : NaN; };
const out = [];
out.push('自動生成: node tools/perf/p7/tables.mjs > tools/perf/p7/results/TABLES.md (入力 results/p7.jsonl)', '');
out.push('## 環境', '', '| cfg | version | CPU | nproc | loadavg(開始時) | wall s | crossOriginIsolated | SIMD |', '|---|---|---|--:|--:|--:|---|---|');
for (const r of rows) out.push(`| ${r.cfg} | ${r.version} | ${r.cpu} | ${r.nproc} | ${f(r.loadavg, 2)} | ${f(r.wallMs / 1000)} | ${r.env?.crossOriginIsolated} | ${r.env?.simd} |`);
out.push('', '## Worker compile / 初回呼出 / 定常 (各サイズ 3 反復の中央値; 反復ごとに別 salt)', '', '| cfg | size | bytes | compile ms | instantiate ms | 初回 ws_process ms | 定常 µs/128f (区間平均 p50) | 区間平均 max µs |', '|---|---|--:|--:|--:|--:|--:|--:|');
for (const r of rows) for (const c of ['small', 'mid', 'large']) {
  const w = [0, 1, 2].map((i) => r[`worker_${c}_${i}`]).filter(Boolean);
  out.push(`| ${r.cfg} | ${c} | ${w[0]?.bytes ?? '-'} | ${f(med(w.map((x) => x.compileMs)))} | ${f(med(w.map((x) => x.instantiateMs)), 2)} | ${f(med(w.map((x) => x.firstCallMs)), 2)} | ${f(med(w.map((x) => x.steadyUsPerBlockP50)), 2)} | ${f(med(w.map((x) => x.steadyUsPerBlockMax)), 1)} |`);
}
out.push('', '## メインスレッド compile / 同期 compile 上限', '', '| cfg | size | bytes | compileStreaming ms | compile(bytes) ms | 同期 new Module (main) |', '|---|---|--:|--:|--:|---|');
for (const r of rows) for (const c of ['mid', 'large']) { const m = r[`main_${c}`]; if (m) out.push(`| ${r.cfg} | ${c} | ${m.bytes ?? '-'} | ${f(m.streamMs)} | ${f(m.compileBytesMs)} | ${m.syncMainOk === undefined ? '-' : m.syncMainOk ? 'OK ' + f(m.syncMainMs) + ' ms' : 'NG ' + (m.syncMainErr || '')} |`); }
out.push('', '## 上限', '', '| cfg | 関数 1,000,000 | 関数 1,000,001 | Memory 256p(16MiB)×≤400 | Memory 12288p(768MiB)×≤400 | module 1GiB | module 1GiB+1 |', '|---|---|---|---|---|---|---|');
const lim = (x) => (!x ? '-' : x.error ? 'ERR ' + x.error.slice(0, 60) : x.ok === true ? `OK ${f(x.compileMs ?? x.ms)} ms` : x.ok === false ? 'NG ' + x.err.slice(0, 90) : `${x.allocated} 本${x.hitCap ? ' (CAP 到達)' : ' で失敗'}`);
for (const r of rows) out.push(`| ${r.cfg} | ${lim(r.limit_funcs_1000000)} | ${lim(r.limit_funcs_1000001)} | ${lim(r.limit_memories_256)} | ${lim(r.limit_memories_12288)} | ${lim(r.limit_bytes_0)} | ${lim(r.limit_bytes_1)} |`);
out.push('', '## Module の structuredClone / IndexedDB', '', '| cfg | structuredClone(Module) | IndexedDB put(Module) |', '|---|---|---|');
for (const r of rows) out.push(`| ${r.cfg} | ${r.module_transfer?.structuredClone} | ${r.module_transfer?.idb}${r.module_transfer?.idbErr ? ' (' + r.module_transfer.idbErr + ')' : ''} |`);
out.push('', '## 同一 URL (immutable) 再ロードの compileStreaming ms と code cache ディレクトリ', '', '| cfg | round0 | round1 | round2 | 終了後 `Code Cache/wasm` or cache2 |', '|---|--:|--:|--:|---|');
for (const r of rows) out.push(`| ${r.cfg} | ${[0, 1, 2].map((i) => f(r[`cache_round${i}`]?.compileStreamingMs)).join(' | ')} | ${(r.cacheFinal || []).slice(0, 6).join('; ') || '(空)'}${(r.cacheFinal || []).length > 6 ? ' …' : ''} |`);
out.push('', '## AudioWorklet (実 AudioContext 48 kHz, 約 2 s 駆動)', '', '| cfg | 状態 | baseLatency ms | process() 回数 / 期待 | wall ms | 最大呼出間隔 ms | >10ms 間隔数 | >20ms 間隔数 | worklet 内 compile ms | Module 直 postMessage 例外 |', '|---|---|--:|--:|--:|--:|--:|--:|--:|---|');
for (const r of rows) { const w = r.worklet || {}; const x = w.result || {}; out.push(`| ${r.cfg} | ctx ${w.stateAfterResume ?? '-'} | ${f((w.baseLatency ?? NaN) * 1000, 2)} | ${x.calls ?? '-'} / ${x.expectedCalls ?? '-'} | ${x.wallMs ?? '-'} | ${x.maxGapMs ?? '-'} | ${x.gapsOver10ms ?? '-'} | ${x.gapsOver20ms ?? '-'} | ${w.loaded?.compileMs ?? '-'} | ${w.moduleDirectPostThrew} |`); }
console.log(out.join('\n'));
