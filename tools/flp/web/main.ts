// Browser harness: parseFlp -> writeFlp / dumpText / summarize on files given via <input type=file> or drag&drop.
// Results are exposed as window.__flp for tools/e2e (suite/flp.mjs). No network access, no bundled FL data.
import { parseFlp, writeFlp } from '../src/flp.ts';
import { dumpText } from '../src/format.ts';
import { summarize } from '../src/summary.ts';

export interface FileResult {
  name: string;
  size: number;
  inSha: string;
  outSha?: string;
  roundtrip?: boolean;
  events?: number;
  format?: number;
  ppq?: number;
  version?: string;
  tempo?: number;
  channels?: number;
  patterns?: number;
  notes?: number;
  warnings?: number;
  dumpLen?: number;
  dumpSha?: string;
  ms?: number;
  error?: string;
}

interface FlpState {
  source: 'input' | 'drop' | null;
  expected: number;
  results: FileResult[];
  done: boolean;
}

declare global {
  interface Window {
    __flp: FlpState;
  }
}

const sabotage = new URLSearchParams(location.search).has('sabotage');
const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const state: FlpState = { source: null, expected: 0, results: [], done: true };
window.__flp = state;

async function sha256(b: Uint8Array): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', b as Uint8Array<ArrayBuffer>));
  return Array.from(d, (x) => x.toString(16).padStart(2, '0')).join('');
}

async function processFile(file: File): Promise<FileResult & { dump?: string }> {
  const t0 = performance.now();
  const buf = new Uint8Array(await file.arrayBuffer());
  const r: FileResult & { dump?: string } = { name: file.name, size: buf.length, inSha: await sha256(buf) };
  try {
    const f = parseFlp(buf);
    const out = writeFlp(f).slice();
    // ?sabotage: deliberately corrupt the written bytes so the e2e detector can be shown to fail (negative control)
    if (sabotage && out.length > 20) out[out.length - 1] ^= 0xff;
    r.outSha = await sha256(out);
    r.roundtrip = r.outSha === r.inSha;
    const s = summarize(f);
    const dump = dumpText(f);
    r.events = f.events.length;
    r.format = f.header.format;
    r.ppq = f.header.ppq;
    r.version = s.version;
    r.tempo = s.tempo;
    r.channels = s.channels;
    r.patterns = s.patterns;
    r.notes = s.notes;
    r.warnings = f.warnings.length;
    r.dumpLen = dump.length;
    r.dumpSha = await sha256(new TextEncoder().encode(dump));
    r.dump = dump;
  } catch (e) {
    r.error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
  }
  r.ms = Math.round(performance.now() - t0);
  return r;
}

function render(): void {
  const rows = state.results
    .map((r) =>
      r.error
        ? `<tr><td>${esc(r.name)}</td><td colspan="6" class="err">${esc(r.error)}</td></tr>`
        : `<tr><td>${esc(r.name)}</td><td>${r.size}</td><td>${r.events}</td><td>${r.version}</td><td>${r.tempo ?? ''}</td><td>${r.channels}</td><td>${r.roundtrip ? 'byte-exact' : 'MISMATCH'}</td></tr>`,
    )
    .join('');
  $('summary').innerHTML = `<tr><th>file</th><th>bytes</th><th>events</th><th>FL</th><th>tempo</th><th>channels</th><th>roundtrip</th></tr>${rows}`;
}

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]!);
}

async function handle(files: File[], source: 'input' | 'drop'): Promise<void> {
  state.source = source;
  state.expected = files.length;
  state.results = [];
  state.done = false;
  $('status').textContent = `処理中 (0/${files.length})`;
  let firstDump = '';
  for (const file of files) {
    const { dump, ...r } = await processFile(file);
    if (!firstDump && dump) firstDump = dump;
    state.results.push(r);
    $('status').textContent = `処理中 (${state.results.length}/${files.length})`;
  }
  $('dump').textContent = firstDump.split('\n').slice(0, 200).join('\n');
  render();
  const ng = state.results.filter((r) => r.error || r.roundtrip === false).length;
  $('status').textContent = `完了 ${files.length} 件 / 異常 ${ng} 件 (${source})`;
  state.done = true;
}

$<HTMLInputElement>('flp-file').addEventListener('change', (ev) => {
  const input = ev.target as HTMLInputElement;
  void handle(Array.from(input.files ?? []), 'input');
});

const drop = $('drop');
drop.addEventListener('dragover', (ev) => {
  ev.preventDefault();
  drop.classList.add('over');
});
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (ev) => {
  ev.preventDefault();
  drop.classList.remove('over');
  void handle(Array.from(ev.dataTransfer?.files ?? []), 'drop');
});
