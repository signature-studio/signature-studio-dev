// vreg.mjs — 仮想レジストリ アダプタ (JS 側)。
//   C 側 (vreg/src/reg.c = shimx reg.c 派生) が Reg* API 本体。ここは seed 投入・永続化 (store)・.reg 入出力・ライセンス状態の切替を担当。
//   hostbridge 規約に合わせ: ESM (.mjs) / 外部依存なし / wasm モジュールは factory (createModule) を注入 / 永続化は注入式 store。
import { ROOTS, ROOT_NAME, parseToModel, parseReg, applyOps, serializeReg, regBytes, emptyModel, setValue, deleteKey, deleteValue,
  getValue, fillMissing, countModel, decodeRegBytes, valueText } from './regfile.mjs';
import { resolveSeed, expectedLicenseFlag } from './seed.mjs';

const ROOT_IDX = { HKCR: 0, HKCU: 1, HKLM: 2, HKU: 3, HKCC: 4 };
const PERSISTED = 'HKCU';     // 永続化するハイブ。HKLM 等はセッション内のみ

function newGuid() {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  const b = new Uint8Array(16); (c?.getRandomValues ? c.getRandomValues(b) : b.forEach((_, i) => (b[i] = (Math.random() * 256) | 0)));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export class Vreg {
  /**
   * @param {object} o
   * @param {() => Promise<object>} o.createModule  build.sh module の出力 (createVregModule)。
   * @param {{load,save,delete}} o.store            MemoryStore / FileStore / IdbStore
   * @param {object} o.seed                         data/seed.json の内容
   * @param {string} [o.profile='default']
   * @param {0|1} [o.licenseFlagBit0]               seed の license.flag_bit0 を上書き (0=登録済み値を書く / 1=Trial: 書かない)
   * @param {'registered'|'trial'|'external'} [o.licenseMode]
   * @param {string|Uint8Array} [o.externalReg]     ユーザ提供の .reg (cracked 資源等)。最優先で適用・毎回再適用 (pinned)
   * @param {string} [o.machineGuid]                指定が無ければプロファイル毎に 1 回生成して永続
   * @param {boolean} [o.applyCatalog=false]        catalog 値 (apply=false, key 既知) も書く
   * @param {string[]} [o.skipGroups]               書かない seed group (例 ['settings','shared'] = エンジン既定値を書かず「値なし」を保つ)
   * @param {number} [o.flushDelayMs=200]           変更通知からの遅延 flush (0 で無効)
   */
  static async create(o) {
    const v = new Vreg(o);
    await v._boot();
    return v;
  }

  constructor(o) {
    this.o = o; this.profile = o.profile ?? 'default'; this.store = o.store; this.seed = o.seed;
    this.dirty = false; this.timer = null; this.chain = Promise.resolve(); this.flushes = 0; this.bootInfo = {};
  }

  // ------------------------- wasm ヘルパ -------------------------
  _cstr(s, fn) {
    const m = this.mod, n = m.lengthBytesUTF8(s) + 1, p = m._malloc(n);
    try { m.stringToUTF8(s, p, n); return fn(p); } finally { m._free(p); }
  }
  _importText(text) { return this._cstr(text, (p) => this.mod._shimx_reg_import_text(p)); }
  _exportRoot(hive) {
    const p = this.mod._vreg_export_root(ROOT_IDX[hive]);
    try { return this.mod.UTF8ToString(p); } finally { this.mod._free(p); }
  }

  async _boot() {
    const o = this.o;
    this.mod = await o.createModule();
    this.mod._shimx_init();
    const rec = await this.store.load(this.profile);
    const guid = o.machineGuid ?? rec?.machineGuid ?? newGuid();
    this.machineGuid = guid;
    const ext = o.externalReg !== undefined ? parseReg(o.externalReg) : null;
    const explicit = o.licenseMode ?? (o.licenseFlagBit0 !== undefined ? (o.licenseFlagBit0 ? 'trial' : 'registered') : undefined);
    const mode = explicit ?? (ext ? 'external' : (this.seed.license?.flag_bit0 ? 'trial' : 'registered'));
    const r = resolveSeed(this.seed, { licenseMode: mode, machineGuid: guid, applyCatalog: o.applyCatalog, skipGroups: o.skipGroups });
    this.licenseMode = mode; this.licenseFlagBit0 = r.flagBit0;
    // 1) seed を内蔵既定の上に重ねる (HKLM 等)
    const seedModel = r.model;
    const restored = !!rec;
    let hkcu;
    if (rec) {
      hkcu = structuredClone(rec.hkcu ?? {});
      if (rec.seedVersion !== this.seed.version) fillMissing(hkcu, seedModel[PERSISTED]);   // seed 更新: 不足分だけ補う
    } else hkcu = seedModel[PERSISTED];
    const live = emptyModel();
    for (const h of ROOTS) live[h] = h === PERSISTED ? hkcu : seedModel[h] ?? {};
    // 2) pinned / license 状態を永続値より優先して反映
    for (const p of r.pinned) setValue(live, p.hive, p.key, p.name, p.t, p.v);
    if (mode !== 'registered') for (const n of r.licenseNames) {
      if (!n.key) continue;
      deleteValue(live, n.hive, n.key, n.name);
    }
    if (mode !== 'registered') for (const hv of ['HKCU', 'HKLM']) for (const k of ['Software\\Image-Line\\Registrations\\FL Studio 26.1', 'Software\\Image-Line\\Registrations\\FL Data']) {
      const vals = (live[hv] || {})[k]; if (vals && !Object.keys(vals).length) deleteKey(live, hv, k);
    }
    // 3) external .reg (cracked 資源等) を最後に適用
    if (ext) applyOps(live, ext);
    // 4) C 側へ投入: 復元時は HKCU を入れ替え、新規は seed を内蔵既定へ重ねる
    if (restored) this.mod._vreg_clear_root(ROOT_IDX[PERSISTED]);
    const text = serializeReg(live, { hives: ROOTS }) + '\n';
    const n = this._importText(text);
    this.bootInfo = { restored, imported: n, applied: r.applied, catalogSkipped: r.catalogSkipped, pinned: r.pinned.length, external: ext ? ext.length : 0, mode };
    // 5) 通知フック (以降の変更で dirty → flush)。新規プロファイルは直ちに保存 (MachineGuid の永続)
    this._fp = this.mod.addFunction(() => this._onChange(), 'vi');
    this.mod._vreg_set_notify(this._fp);
    if (!restored) await this.flush(true);
  }

  _onChange() {
    this.dirty = true;
    const d = this.o.flushDelayMs ?? 200;
    if (d > 0 && !this.timer && typeof setTimeout === 'function') {
      this.timer = setTimeout(() => { this.timer = null; this.flush().catch((e) => console.error('[vreg] flush failed', e)); }, d);
      this.timer.unref?.();
    }
  }

  // ------------------------- 永続化 -------------------------
  /** HKCU を store に保存。変更が無ければ no-op (force で強制)。flush 中の呼出は直列化される */
  flush(force = false) {
    const run = async () => {
      if (!this.dirty && !force) return false;
      this.dirty = false;
      const hkcu = parseToModel(this._exportRoot(PERSISTED))[PERSISTED];
      await this.store.save(this.profile, { schema: 1, seedVersion: this.seed.version, machineGuid: this.machineGuid, savedAt: Date.now(), hkcu });
      this.flushes++;
      return true;
    };
    return (this.chain = this.chain.then(run, run));
  }
  async close() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    await this.flush();
    this.mod._vreg_set_notify(0); this.mod.removeFunction(this._fp);
  }
  async resetProfile() { await this.store.delete(this.profile); }

  // ------------------------- .reg 入出力 -------------------------
  /** .reg (UTF-16LE BOM / UTF-8 / 文字列) を取り込む。戻り値 = 適用した値/削除の数 */
  importReg(input) { return this._importText(opsToText(parseReg(input))); }
  /** 現在の仮想レジストリを .reg に。utf16le=true で regedit 互換 (BOM + CRLF) の Uint8Array、false で文字列 */
  exportReg({ hives = ['HKCU', 'HKLM'], utf16le = true } = {}) {
    const m = emptyModel();
    for (const h of hives) m[h] = parseToModel(this._exportRoot(h))[h];
    return utf16le ? regBytes(m, { hives }) : serializeReg(m, { hives });
  }
  snapshot(hives = ROOTS) {
    const m = emptyModel(); for (const h of hives) m[h] = parseToModel(this._exportRoot(h))[h]; return m;
  }

  // ------------------------- 検証用 (FL と同じ呼出パターン) -------------------------
  probe(fn, ...args) { return this.mod[`_vreg_probe_${fn}`](...args); }
  readStr(hive, key, name) {
    const m = this.mod, cap = 8192, out = m._malloc(cap), ty = m._malloc(4);
    try {
      const st = this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => m._vreg_probe_read_str(a, b, c, out, cap, ty))));
      return st === 0 ? { status: 0, value: m.UTF8ToString(out), type: m.HEAPU32[ty >> 2] } : { status: st };
    } finally { m._free(out); m._free(ty); }
  }
  readInt(hive, key, name, def = 0) { return this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => this.mod._vreg_probe_read_int(a, b, c, def)))); }
  readBool(hive, key, name, def = 0) { return !!this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => this.mod._vreg_probe_read_bool(a, b, c, def ? 1 : 0)))); }
  writeStr(hive, key, name, val) { return this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => this._cstr(val, (d) => this.mod._vreg_probe_write_str(a, b, c, d))))); }
  writeInt(hive, key, name, v) { return this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => this.mod._vreg_probe_write_int(a, b, c, v)))); }
  keyExists(hive, key) { return !!this._cstr(hive, (a) => this._cstr(key, (b) => this.mod._vreg_probe_key_exists(a, b))); }
  valueExists(hive, key, name) { return !!this._cstr(hive, (a) => this._cstr(key, (b) => this._cstr(name, (c) => this.mod._vreg_probe_value_exists(a, b, c)))); }
  enumNames(hive, key, kind = 0) {
    const m = this.mod, cap = 65536, out = m._malloc(cap);
    try {
      const st = this._cstr(hive, (a) => this._cstr(key, (b) => m._vreg_probe_enum(a, b, kind, out, cap)));
      return st === 0 ? m.UTF8ToString(out).split('\n').filter(Boolean) : null;
    } finally { m._free(out); }
  }
  deleteKey(hive, key) { return this._cstr(hive, (a) => this._cstr(key, (b) => this.mod._vreg_probe_delete_key(a, b))); }

  /**
   * FL の登録状態検査 (engine FUN_008e6150 と同じ判定): HKCU (無ければ HKLM) の Registrations 配下で
   * 名前が "FL Studio " で始まるサブキーのうち、ILRegKey が非空のものが 1 つでもあれば true。
   * ※ これは存在検査のみ。0x10c7cd0 の本検証 (byte[0x14f84a8]) の結果ではない。
   */
  observeRegistration() {
    for (const hive of ['HKCU', 'HKLM']) {
      const names = this.enumNames(hive, 'Software\\Image-Line\\Registrations') ?? [];
      for (const n of names.filter((x) => x.startsWith('FL Studio '))) {
        const r = this.readStr(hive, `Software\\Image-Line\\Registrations\\${n}`, 'ILRegKey');
        if (r.status === 0 && r.value !== '') return { registered: true, hive, subkey: n };
      }
    }
    return { registered: false };
  }
  expectedLicense() { return expectedLicenseFlag(this.seed, this.licenseMode); }
  stats() { const a = this.mod._malloc(8); this.mod._shimx_reg_stats(a, a + 4); const r = { keys: this.mod.HEAPU32[a >> 2], values: this.mod.HEAPU32[(a + 4) >> 2] }; this.mod._free(a); return r; }
  generation() { return this.mod._vreg_generation(); }
}

// .reg の ops を C 側 import (shimx_reg_import_text) に渡せるテキストへ再構成する (削除操作も保持)
function opsToText(ops) {
  const out = ['Windows Registry Editor Version 5.00', ''];
  let cur = null;
  for (const o of ops) {
    const path = `${ROOT_NAME[o.hive]}${o.key ? '\\' + o.key : ''}`;
    if (o.op === 'delkey') { out.push(`[-${path}]`, ''); cur = null; continue; }
    if (cur !== path) { out.push('', `[${path}]`); cur = path; }
    if (o.op === 'set') out.push(valueText(o.name, o));
    else if (o.op === 'delvalue') out.push(`${o.name === '' ? '@' : '"' + o.name.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"'}=-`);
  }
  return out.join('\n') + '\n';
}
export { decodeRegBytes, getValue, countModel };
