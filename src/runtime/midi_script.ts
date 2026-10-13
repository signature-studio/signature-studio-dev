/**
 * midi_script.ts — MIDI scripting ホスト (tools/python/host/midi_host.mjs) をアプリ内 UI / devtools に公開する (PY-6 #76)。
 *   devtools:  await flMidi.start(); await flMidi.loadDeviceScript("x", src, { port: 0 }); await flMidi.init();
 *              await flMidi.connectWebMidi();  /  await flMidi.midiIn([0xb0, 7, 100])
 *   UI:        /?midi=1 で左下にパネル (device_*.py / midi.py / utils.py を選択 or ドロップ → 起動 → Web MIDI 接続)
 * device script (.py) は利用者の FL インストールから実行時に供給する (リポジトリ・配信物に非同梱)。
 * flapi の提供側は FLEngine 未完成の間 host/fl_mock.mjs (FLEngine 模擬)。Web MIDI → FL エンジン本体への結線は #37 (AU-14) の範囲。
 */

type Json = unknown;
type DeliverResult = { results?: { script: string; called: string[]; errors: { cb: string; err: string }[] }[] };

export type FlMidi = {
  /** wasm Python を起動 (flapi は FLEngine 模擬)。files のキーは FS パスまたはファイル名 (midi.py / utils.py は /fl/Lib/ へ) */
  start(files?: Record<string, Uint8Array>): Promise<{ python: string }>;
  /** device_*.py を読込む。port = この script が受ける MIDI 入力ポート番号 (省略 = 全ポート) */
  loadDeviceScript(name: string, source: string | Uint8Array, opts?: { port?: number | null }): Promise<{ name: string; module: string; callbacks: string[]; meta: Record<string, string> }>;
  /** 全 script に OnInit → OnInitAll */
  init(): Promise<Json>;
  /** 非 MIDI の callback (27 個のうち受信 MIDI 以外)。例: callback("OnRefresh", [4]) */
  callback(cb: string, args?: Json[]): Promise<Json>;
  /** 受信 MIDI 1 件 (生バイト列)。OnMidiIn → OnMidiMsg → 型別 callback */
  midiIn(bytes: ArrayLike<number>, opts?: { port?: number; timestamp?: number }): Promise<DeliverResult>;
  /** navigator.requestMIDIAccess の全入力を結線する */
  connectWebMidi(opts?: { sysex?: boolean; portMap?: Record<string, number>; access?: unknown }): Promise<{ inputs: string[] }>;
  disconnectWebMidi(): void;
  scripts(): Promise<Record<string, { module: string; port: number | null; callbacks: string[] }>>;
  /** Python の stdout / stderr (Script output 相当) */
  readonly output: string[];
  /** 直近 100 件の MIDI 配送結果 (Web MIDI 経由の観測用) */
  readonly deliveries: { fields: Record<string, unknown>; result: DeliverResult }[];
  stop(): Promise<void>;
  readonly started: boolean;
};

declare global {
  interface Window {
    flMidi?: FlMidi;
  }
}

const PY_BASE = "/py";
const LIB_DEST: Record<string, string> = { "midi.py": "/fl/Lib/midi.py", "utils.py": "/fl/Lib/utils.py" };
const dynImport = (url: string): Promise<any> => import(/* @vite-ignore */ url);

export function installFlMidi(): FlMidi {
  if (window.flMidi) return window.flMidi;
  const output: string[] = [];
  const deliveries: FlMidi["deliveries"] = [];
  let py: any = null;
  let host: any = null;
  let detach: (() => void) | null = null;
  let starting: Promise<{ python: string }> | null = null;
  const supplied: Record<string, Uint8Array> = {};

  const need = (): any => {
    if (!host) throw new Error("flMidi.start() が未実行です");
    return host;
  };
  const start: FlMidi["start"] = (files) => {
    if (files) for (const [k, v] of Object.entries(files)) supplied[k.split("/").pop()!] = v;
    if (starting) return starting;
    starting = (async () => {
      if (!crossOriginIsolated) throw new Error("crossOriginIsolated=false: SAB が使えません (COOP/COEP を確認)");
      const origin = location.origin + PY_BASE;
      const [{ FlPython }, { createMockEngine }, { MidiScriptHost }, ids] = await Promise.all([
        dynImport(`${origin}/host/flpython.mjs`),
        dynImport(`${origin}/host/fl_mock.mjs`),
        dynImport(`${origin}/host/midi_host.mjs`),
        fetch(`${origin}/analysis/flapi/flapi_ids.json`).then((r) => {
          if (!r.ok) throw new Error(`flapi_ids.json: HTTP ${r.status}`);
          return r.json();
        }),
      ]);
      const fsFiles: Record<string, Uint8Array> = {};
      for (const [n, dest] of Object.entries(LIB_DEST)) if (supplied[n]) fsFiles[dest] = supplied[n]!;
      py = await FlPython.create({
        flpyUrl: `${origin}/dist/flpy.js`,
        engine: createMockEngine(),
        ids,
        files: fsFiles,
        onStdout: (t: string) => output.push(t),
        onStderr: (t: string) => output.push(`ERR ${t}`),
      });
      await py.run("import fl_rt\nfl_rt.install_flapi()");
      host = new MidiScriptHost(py, {
        onDelivery: (result: DeliverResult, fields: Record<string, unknown>) => {
          deliveries.push({ fields, result });
          if (deliveries.length > 100) deliveries.shift();
        },
      });
      const ver = (await py.call("platform:python_version", []).catch(() => null)) as { ok?: string } | null;
      return { python: ver?.ok ?? "3.12" };
    })();
    starting.catch(() => { starting = null; });
    return starting;
  };

  const api: FlMidi = {
    start,
    async loadDeviceScript(name, source, opts = {}) {
      const text = typeof source === "string" ? source : new TextDecoder().decode(source);
      return need().loadDeviceScript({ name, source: text, port: opts.port ?? null });
    },
    init: () => need().init(),
    callback: (cb, args = []) => need().callback(cb, args),
    midiIn: (bytes, opts) => need().midiIn(Uint8Array.from(Array.from(bytes)), opts),
    async connectWebMidi(opts = {}) {
      const h = need();
      const access = (opts.access ?? (await navigator.requestMIDIAccess({ sysex: opts.sysex ?? false }))) as { inputs: Map<string, { name?: string }> };
      detach?.();
      detach = h.attachWebMidi(access, { portMap: opts.portMap, onError: (e: unknown) => output.push(`ERR midi: ${String(e)}`) });
      return { inputs: Array.from(access.inputs.values()).map((i) => i.name ?? "?") };
    },
    disconnectWebMidi() { detach?.(); detach = null; },
    scripts: () => need().listDeviceScripts(),
    output,
    deliveries,
    async stop() {
      detach?.();
      detach = null;
      if (py) await py.terminate();
      py = host = starting = null;
    },
    get started() { return host !== null; },
  };
  window.flMidi = api;
  return api;
}

export function mountMidiPanel(): void {
  const api = installFlMidi();
  const panel = document.createElement("div");
  panel.id = "midi-panel";
  panel.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:20;width:460px;max-height:70vh;overflow:auto;background:#000c;padding:10px;font:12px/1.4 monospace;color:#cfe;border:1px solid #345";
  panel.innerHTML = `
    <div><b>MIDI scripting</b> (ローカル / flapi は FLEngine 模擬)</div>
    <div style="margin:6px 0">FL の <code>device_*.py</code> (+ 任意で <code>midi.py</code> <code>utils.py</code>) を選択/ドロップ:
      <input id="midi-files" type="file" multiple></div>
    <div>port: <input id="midi-port" type="number" value="0" min="0" style="width:4em"> <button id="midi-start" disabled>起動 + 読込 + OnInit</button>
      <button id="midi-connect" disabled>Web MIDI 接続</button></div>
    <div id="midi-state" style="margin-top:4px">device script 未供給</div>
    <pre id="midi-out" style="margin:6px 0 0;white-space:pre-wrap;max-height:30vh;overflow:auto"></pre>`;
  document.body.appendChild(panel);
  const $ = <T extends HTMLElement>(id: string) => panel.querySelector<T>(`#${id}`)!;
  const state = $("midi-state"), out = $("midi-out");
  const startBtn = $<HTMLButtonElement>("midi-start"), connectBtn = $<HTMLButtonElement>("midi-connect"), portIn = $<HTMLInputElement>("midi-port");
  const devices: Record<string, Uint8Array> = {};
  const libs: Record<string, Uint8Array> = {};
  const showOutput = () => { out.textContent = api.output.slice(-30).join("\n"); };
  const ingest = async (list: FileList | File[]) => {
    for (const f of Array.from(list)) {
      const bytes = new Uint8Array(await f.arrayBuffer());
      if (f.name in LIB_DEST) libs[f.name] = bytes;
      else if (/^device_.*\.py$/.test(f.name)) devices[f.name] = bytes;
    }
    startBtn.disabled = Object.keys(devices).length === 0 || api.started;
    state.textContent = Object.keys(devices).length ? `供給済み: ${Object.keys(devices).join(", ")}` : "device script 未供給";
  };
  $<HTMLInputElement>("midi-files").addEventListener("change", (e) => void ingest((e.target as HTMLInputElement).files ?? []));
  panel.addEventListener("dragover", (e) => e.preventDefault());
  panel.addEventListener("drop", (e) => { e.preventDefault(); void ingest(e.dataTransfer?.files ?? []); });
  startBtn.addEventListener("click", async () => {
    state.textContent = "起動中…";
    try {
      await api.start(libs);
      const port = Number(portIn.value);
      for (const [n, b] of Object.entries(devices)) await api.loadDeviceScript(n.replace(/\.py$/, ""), b, { port });
      await api.init();
      state.textContent = `起動済み: ${Object.keys(await api.scripts()).join(", ")}`;
      connectBtn.disabled = false;
    } catch (e) {
      state.textContent = `失敗: ${String(e)}`;
    }
    startBtn.disabled = api.started;
    showOutput();
  });
  connectBtn.addEventListener("click", async () => {
    try {
      const r = await api.connectWebMidi({ sysex: true });
      state.textContent = `Web MIDI 接続: 入力 ${r.inputs.length} 件 (${r.inputs.join(", ") || "なし"})`;
    } catch (e) {
      state.textContent = `Web MIDI 失敗: ${String(e)}`;
    }
  });
  setInterval(showOutput, 500);
}
