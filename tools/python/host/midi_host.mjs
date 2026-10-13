// MIDI scripting ホスト (PY-6 #76): device script (.py) ローダ・27 callback 配送・Web MIDI 入力 → fl_rt の結線。
//   const host = new MidiScriptHost(py)                       // py = FlPython (host/flpython.mjs)
//   await host.loadDeviceScript({ name, source, port })       // device_*.py (利用者の FL から実行時供給。非同梱)
//   await host.init()                                         // 全 script に OnInit → OnInitAll
//   await host.midiIn(new Uint8Array([0xb0, 7, 100]), { port: 0 })   // 受信 MIDI: OnMidiIn → OnMidiMsg → 型別 (handled で停止)
//   await host.callback("OnRefresh", 1)                       // 非 MIDI callback (host/lifecycle/midi_out)
//   const detach = host.attachWebMidi(await navigator.requestMIDIAccess({ sysex: true }))
// 配送の実体は src/fl_rt.py (Python 側)。ここは直列化 (MIDI は到着順に 1 本ずつ) とバイト列の解釈だけ。
// Python は UI/MIDI 側の Worker で動き audio スレッドには入らない (BRIDGE.md §4)。

/** Web MIDI の生バイト列 → fl_rt が受ける fields。sysex (0xF0 始まり) は status=0xF0 + sysex 全体。 */
export function parseMidiBytes(bytes) {
  const b = Array.from(bytes);
  if (b.length === 0 || b[0] < 0x80) throw new Error(`invalid MIDI message: [${b.join(",")}]`);
  if (b[0] === 0xf0) return { status: 0xf0, data1: 0, data2: 0, sysex: b };
  return { status: b[0], data1: b[1] ?? 0, data2: b[2] ?? 0 };
}

export class MidiScriptHost {
  #q = Promise.resolve();
  // onDelivery(result, fields): midiIn ごとの配送結果 (Web MIDI 経由は戻り値を受ける呼出し元がいないため、観測用)
  constructor(py, { onDelivery } = {}) {
    this.py = py;
    this.onDelivery = onDelivery;
    this.stats = { midiIn: 0, callbacks: 0, errors: 0 };
  }
  // 1 本ずつ直列化 (前の呼出しが失敗しても次は走る)
  #enq(fn) {
    const r = this.#q.then(fn);
    this.#q = r.catch(() => {});
    return r;
  }
  async #rt(fn, args) {
    const r = await this.py.call(`fl_rt:${fn}`, args);
    if (r.err !== undefined) throw new Error(`${fn}: ${r.err}${r.tb ? "\n" + r.tb : ""}`);
    return JSON.parse(r.ok);
  }
  #count(res) {
    for (const x of res.results ?? []) this.stats.errors += x.errors.length;
    return res;
  }

  callbackTable() { return this.#enq(() => this.#rt("callback_table", {})); }
  loadDeviceScript({ name, source, port = null }) {
    return this.#enq(() => this.#rt("load_device_script", { name, source, port }));
  }
  unloadDeviceScript(name) { return this.#enq(() => this.#rt("unload_device_script", { name })); }
  listDeviceScripts() { return this.#enq(() => this.#rt("list_device_scripts", {})); }
  /** 全 script に OnInit、続けて OnInitAll (OnInitAll の意味は名前からの推定) */
  init(script) {
    return this.#enq(async () => {
      const r = await this.#rt("init_scripts", { script: script ?? null });
      r.forEach((x) => this.#count(x));
      return r;
    });
  }
  deinit(script) { return this.callback("OnDeInit", [], script); }
  /** 非 MIDI callback。args は CALLBACKS の個数と一致が必須 (不一致は reject)。OnMidiOutMsg は args=[fields]。 */
  callback(cb, args = [], script) {
    const a = Array.isArray(args) ? args : [args];
    return this.#enq(async () => {
      this.stats.callbacks++;
      return this.#count(await this.#rt("dispatch_callback", { cb, args_json: JSON.stringify(a), script: script ?? null }));
    });
  }
  /** 受信 MIDI 1 件。port が一致する (または port 無指定の) device script だけに配送する。 */
  midiIn(bytes, { port = 0, timestamp = 0 } = {}) {
    let fields;
    try { fields = { ...parseMidiBytes(bytes), port, timestamp }; } catch (e) { return Promise.reject(e); }
    return this.#enq(async () => {
      this.stats.midiIn++;
      const res = this.#count(await this.#rt("dispatch_script_midi", { fields_json: JSON.stringify(fields) }));
      this.onDelivery?.(res, fields);
      return res;
    });
  }

  /**
   * Web MIDI の全入力 (接続後に増えるものも) を midiIn に結線する。port は portMap[input.id|name] があればそれ、無ければ接続順の連番。
   * 戻り値の detach() で全リスナーを外す。onError(e) は配送失敗の通知 (握り潰さない)。
   */
  attachWebMidi(access, { portMap = {}, onError = (e) => console.error("[midi]", e) } = {}) {
    const bound = new Map();
    let next = 0;
    const bind = (input) => {
      if (input.type !== "input" || bound.has(input.id)) return;
      const port = portMap[input.id] ?? portMap[input.name] ?? next++;
      bound.set(input.id, { input, port });
      input.onmidimessage = (ev) => {
        this.midiIn(ev.data, { port, timestamp: ev.timeStamp }).catch(onError);
      };
    };
    for (const input of access.inputs.values()) bind(input);
    access.onstatechange = (ev) => { if (ev.port?.state === "connected") bind(ev.port); };
    return () => {
      for (const { input } of bound.values()) input.onmidimessage = null;
      bound.clear();
      access.onstatechange = null;
    };
  }
}
