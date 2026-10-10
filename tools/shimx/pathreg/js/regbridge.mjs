// regbridge.mjs — shimx reg.c (Reg* API) と vreg 永続化 (IndexedDB store) をつなぐブリッジ (CAB-168)。
//
//   wasm (shimx Reg* + pathreg) ⇄ 本モジュール ⇄ store {load,save,delete} (vreg js/store.mjs 互換)
//     store は MemoryStore / FileStore / IdbStore (DB "webstudio-vreg" / store "profiles" / key=profile) をそのまま使える。
//
// 2 つのリンク構成を自動判別する (pathreg.h「ホストブリッジ (JS) フック契約」参照):
//   - vreg reg.c 結線 (推奨; _vreg_export_root 等が有る): 通知フック (vreg_set_notify) で dirty 化 → 遅延 flush。
//     restore は vreg_clear_root(HKCU) 後に model を import (削除も model 演算で確実)。
//   - shimx reg.c のまま (代替; 通知口なし): flush 点で C hash (pathreg_reg_hash) を比較して差分時のみ保存。
//     restore は「内蔵既定の HKCU にあって永続 model に無い値/キー」を Reg* で差分削除 (_applyHkcuDeletions)。
//
// flush 契約 (vreg REPORT §8-1 準拠): 変更 → 遅延 flush (既定 200ms) に加え、メッセージポンプの yield 点で
// onYield() / pagehide・visibilitychange で onPageHide() を明示的に呼ぶこと (Atomics.wait 中は JS タイマが
// 走らないため setTimeout だけに頼らない)。
//
// 永続レコードは vreg Vreg.flush() と同一形 (相互運用可):
//   { schema:1, seedVersion, machineGuid, savedAt, hkcu: { "<key>": { "<name>": { t, v } } } }   (HKCU のみ永続)
import {
  ROOTS, ROOT_NAME, parseToModel, serializeReg, emptyModel, setValue, deleteValue, deleteKey, fillMissing,
  parseReg, applyOps, countModel, valueText, regBytes,
} from '../../../startup/vreg/js/regfile.mjs';
import { resolveSeed } from '../../../startup/vreg/js/seed.mjs';

const ROOT_IDX = { HKCR: 0, HKCU: 1, HKLM: 2, HKU: 3, HKCC: 4 };
const PERSISTED = 'HKCU';
const ROOT_HANDLE = { HKCR: 0x80000000, HKCU: 0x80000001, HKLM: 0x80000002, HKU: 0x80000003, HKCC: 0x80000005 };

function newGuid() {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  const b = new Uint8Array(16); (c?.getRandomValues ? c.getRandomValues(b) : b.forEach((_, i) => (b[i] = (Math.random() * 256) | 0)));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export class RegBridge {
  /**
   * @param {object} o
   * @param {object} o.mod                       pathreg 入り wasm モジュール (build.sh module-a / module-b)。
   *                                             必要エクスポートは include/pathreg.h 参照。
   * @param {{load,save,delete}} o.store         vreg store.mjs 互換 (IdbStore 推奨)
   * @param {object} o.seed                      vreg data/seed.json
   * @param {string} [o.profile='default']
   * @param {string} [o.machineGuid]             無ければ生成して永続
   * @param {0|1} [o.licenseFlagBit0]            seed license.flag_bit0 の上書き (0=registered / 1=trial)
   * @param {'registered'|'trial'|'external'} [o.licenseMode]
   * @param {string|Uint8Array} [o.externalReg]  追加 .reg (最優先・毎回適用)
   * @param {string[]} [o.skipGroups]            書かない seed group
   * @param {boolean} [o.applyCatalog=false]
   * @param {number} [o.flushDelayMs=200]        変更通知からの遅延 flush (0=無効)
   * @param {boolean} [o.installMapper=true]     pathreg_install() (shimx_set_path_mapper へ登録) を行うか
   */
  static async create(o) {
    const b = new RegBridge(o);
    await b._boot();
    return b;
  }

  constructor(o) {
    this.o = o;
    this.mod = o.mod;
    this.store = o.store;
    this.seed = o.seed;
    this.profile = o.profile ?? 'default';
    this.flushDelayMs = o.flushDelayMs ?? 200;
    this.dirty = false;
    this.timer = null;
    this.chain = Promise.resolve();
    this.flushes = 0;
    this.bootInfo = {};
    this.lastPersisted = null;       // { gen } (vreg 結線時) / { hash } (shimx reg.c のまま)
    this.notifyFp = null;
  }

  // ------------------------- 能力判定 / wasm ヘルパ -------------------------
  get hasVreg() { return typeof this.mod._vreg_export_root === 'function'; }

  _cstr(s, fn) {
    const m = this.mod, n = m.lengthBytesUTF8(s) + 1, p = m._malloc(n);
    try { m.stringToUTF8(s, p, n); return fn(p); } finally { m._free(p); }
  }
  _importText(text) { return this._cstr(text, (p) => this.mod._shimx_reg_import_text(p)); }
  _exportText() {   // 全ハイブの .reg テキスト (vreg 未結線構成用 / hash 用)
    const p = this.mod._shimx_reg_export_text();
    try { return this.mod.UTF8ToString(p); } finally { this.mod._free(p); }
  }
  _exportHiveText(hive) {   // 1 ハイブ分 (vreg 結線時は C 直、それ以外は全体から抽出)
    if (this.hasVreg) {
      const p = this.mod._vreg_export_root(ROOT_IDX[hive]);
      try { return this.mod.UTF8ToString(p); } finally { this.mod._free(p); }
    }
    const m = emptyModel();
    m[hive] = parseToModel(this._exportText())[hive];
    return serializeReg(m, { hives: [hive] });
  }
  _wp(s) {  // UTF-16LE 文字列を wasm へ (Reg* W 版呼出用)。戻り: ptr (caller が _free)
    const m = this.mod, p = m._malloc((s.length + 1) * 2);
    m.stringToUTF16(s, p, (s.length + 1) * 2);
    return p;
  }

  // ------------------------- ブート -------------------------
  async _boot() {
    const o = this.o, mod = this.mod;
    mod._shimx_init();
    if (o.installMapper !== false && typeof mod._pathreg_install === 'function') mod._pathreg_install();

    const rec = await this.store.load(this.profile);
    const guid = o.machineGuid ?? rec?.machineGuid ?? newGuid();
    this.machineGuid = guid;
    const ext = o.externalReg !== undefined ? parseReg(o.externalReg) : null;
    const explicit = o.licenseMode ?? (o.licenseFlagBit0 !== undefined ? (o.licenseFlagBit0 ? 'trial' : 'registered') : undefined);
    const mode = explicit ?? (ext ? 'external' : (this.seed.license?.flag_bit0 ? 'trial' : 'registered'));
    const r = resolveSeed(this.seed, { licenseMode: mode, machineGuid: guid, applyCatalog: o.applyCatalog, skipGroups: o.skipGroups });
    this.licenseMode = mode;

    // live model = seed (復元時は HKCU を永続値で置換。seed 版更新時は不足分のみ補完)
    const restored = !!rec;
    let hkcu;
    if (rec) {
      hkcu = structuredClone(rec.hkcu ?? {});
      if (rec.seedVersion !== this.seed.version) fillMissing(hkcu, r.model[PERSISTED]);
    } else hkcu = structuredClone(r.model[PERSISTED] ?? {});
    const live = emptyModel();
    for (const h of ROOTS) live[h] = h === PERSISTED ? hkcu : structuredClone(r.model[h] ?? {});
    // pinned (license / MachineGuid) は永続値より優先
    for (const p of r.pinned) setValue(live, p.hive, p.key, p.name, p.t, p.v);
    if (mode !== 'registered') for (const n of r.licenseNames) {
      if (!n.key) continue;
      deleteValue(live, n.hive, n.key, n.name);
    }
    if (mode !== 'registered') for (const hv of ['HKCU', 'HKLM']) for (const k of ['Software\\Image-Line\\Registrations\\FL Studio 26.1', 'Software\\Image-Line\\Registrations\\FL Data']) {
      const vals = (live[hv] || {})[k]; if (vals && !Object.keys(vals).length) deleteKey(live, hv, k);
    }
    if (ext) applyOps(live, ext);

    // C 側へ投入。C インスタンスは毎回新規 (= shimx 内蔵既定のみの状態) なので reset は不要。
    //   vreg 結線: 復元時は HKCU を clear してから live を import (削除も含め HKCU は永続値が正)。
    //   shimx reg.c のまま: import 後、「内蔵既定の HKCU にあって live に無い値/キー」を差分削除
    //   (shimx の import は削除構文を解釈しないため。HKLM 等は vreg と同じくセッション内のみ)。
    let baseHkcu = null;
    if (this.hasVreg) {
      if (restored) this.mod._vreg_clear_root(ROOT_IDX[PERSISTED]);
    } else if (restored) {
      baseHkcu = parseToModel(this._exportText())[PERSISTED];   // import 前の内蔵既定 HKCU
    }
    const text = serializeReg(live, { hives: ROOTS }) + '\n';
    const imported = this._importText(text);
    if (baseHkcu) this._applyHkcuDeletions(live[PERSISTED], baseHkcu);

    // 変更検出の基準 + 通知フック
    this._markSavedBase();
    if (this.hasVreg && typeof mod.addFunction === 'function' && typeof mod._vreg_set_notify === 'function') {
      this.notifyFp = mod.addFunction(() => this._onChange(), 'vi');
      mod._vreg_set_notify(this.notifyFp);
    }
    this.bootInfo = { restored, imported, applied: r.applied, catalogSkipped: r.catalogSkipped, pinned: r.pinned.length, external: ext ? ext.length : 0, mode, link: this.hasVreg ? 'vreg' : 'shimx' };
    if (!restored) await this.flush(true);   // 新規プロファイル: MachineGuid 等を直ちに永続
  }

  /** 復元時 (shimx reg.c 構成) の HKCU 差分削除: 内蔵既定 (base) にあって永続 model (want) に無い
   *  値/キーを Reg* で削除する。vreg 結線時は clear_root + import で同等になるため不要。
   *  ※ HKCU のみ (HKLM 等は vreg と同じく「セッション内のみ」)。深い順で削除 (RegDeleteKeyW は葉のみ) */
  _applyHkcuDeletions(want, base) {
    const mod = this.mod;
    const openKey = (key) => {
      const hp = this._wp(key);
      const out = mod._malloc(4);
      let h = 0;
      try {
        if (mod._RegOpenKeyExW(ROOT_HANDLE.HKCU, hp, 0, 0xf003f /*KEY_ALL_ACCESS*/, out) === 0) h = mod.HEAPU32[out >> 2];
      } finally { mod._free(hp); mod._free(out); }
      return h;
    };
    // 値の差分削除
    for (const key of Object.keys(base)) {
      const w = want[key];
      const names = Object.keys(base[key]);
      const gone = w ? names.filter((n) => !Object.hasOwn(w, n)) : names;
      if (!gone.length) continue;
      const h = openKey(key);
      if (!h) continue;
      try { for (const n of gone) { const np = this._wp(n); try { mod._RegDeleteValueW(h, np); } finally { mod._free(np); } } }
      finally { mod._RegCloseKey(h); }
    }
    // キーの差分削除 (深い順)
    const delKeys = Object.keys(base).filter((key) => !want[key]);
    delKeys.sort((a, b) => b.split('\\').length - a.split('\\').length);
    for (const key of delKeys) {
      const hp = this._wp(key);
      try { mod._RegDeleteKeyW(ROOT_HANDLE.HKCU, hp); } finally { mod._free(hp); }
    }
  }

  // ------------------------- 永続化 -------------------------
  _onChange() {
    this.dirty = true;
    const d = this.flushDelayMs;
    if (d > 0 && !this.timer && typeof setTimeout === 'function') {
      this.timer = setTimeout(() => { this.timer = null; this.flush().catch((e) => console.error('[pathreg] flush failed', e)); }, d);
      this.timer.unref?.();
    }
  }

  _markSavedBase() {
    if (this.hasVreg) this.lastPersisted = { gen: this.mod._vreg_generation() };
    else {
      const h = this.mod._malloc(8);
      try { this.mod._pathreg_reg_hash(h); this.lastPersisted = { hash: `${this.mod.HEAPU32[h >> 2]}:${this.mod.HEAPU32[(h + 4) >> 2]}` }; }
      finally { this.mod._free(h); }
    }
  }
  _hasChanges() {
    if (!this.lastPersisted) return true;
    if (this.hasVreg) return this.mod._vreg_generation() !== this.lastPersisted.gen;
    const h = this.mod._malloc(8);
    try {
      this.mod._pathreg_reg_hash(h);
      return `${this.mod.HEAPU32[h >> 2]}:${this.mod.HEAPU32[(h + 4) >> 2]}` !== this.lastPersisted.hash;
    } finally { this.mod._free(h); }
  }

  /** HKCU を store に保存 (vreg 互換レコード)。無変更なら no-op (force で強制)。戻り: 保存したか */
  flush(force = false) {
    const run = async () => {
      if (!force && !this._hasChanges()) return false;
      const hkcu = parseToModel(this._exportHiveText(PERSISTED))[PERSISTED];
      await this.store.save(this.profile, { schema: 1, seedVersion: this.seed.version, machineGuid: this.machineGuid, savedAt: Date.now(), hkcu });
      this._markSavedBase();
      this.dirty = false;
      this.flushes++;
      return true;
    };
    return (this.chain = this.chain.then(run, run));
  }

  /** メッセージポンプの yield 点 (ポンプ 1 周ごと等)。遅延 flush を待たずに畳む */
  onYield() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (this.dirty) return this.flush();
    return this.chain;
  }

  /** pagehide / visibilitychange(vhidden) 発火口。同期を返せないため fire-and-forget + 戻りは Promise */
  onPageHide() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    this.dirty = true;                    // 強制ではないが pagehide は最終保存機会
    return this.flush();
  }

  async close() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    await this.flush();
    if (this.notifyFp !== null) { this.mod._vreg_set_notify(0); this.mod.removeFunction(this.notifyFp); this.notifyFp = null; }
  }
  async resetProfile() { await this.store.delete(this.profile); }

  // ------------------------- 検証用 API (FL と同じ呼出パターン / C へ書き込み) -------------------------
  writeStr(hive, key, name, val) {   // shimx_reg_set_sz 経由 (vreg reg.c でも同名)
    const path = `${ROOT_NAME[hive]}${key ? '\\' + key : ''}`;
    return this._cstr(path, (a) => this._cstr(name, (b) => this._cstr(val, (c) => this.mod._shimx_reg_set_sz(a, b, c))));
  }
  writeInt(hive, key, name, v) {
    const path = `${ROOT_NAME[hive]}${key ? '\\' + key : ''}`;
    return this._cstr(path, (a) => this._cstr(name, (b) => this.mod._shimx_reg_set_dword(a, b, v >>> 0)));
  }
  /** 値削除 (RegOpenKeyExW + RegDeleteValueW)。vreg 結線時は通知 → dirty、shimx reg.c のままでは
   *  flush 点の hash 差分で検出される。戻り 0=削除 / -1=失敗 */
  deleteValue(hive, key, name) {
    const mod = this.mod;
    const hp = this._wp(key), np = this._wp(name), out = mod._malloc(4);
    try {
      if (mod._RegOpenKeyExW(ROOT_HANDLE[hive], hp, 0, 0xf003f /*KEY_ALL_ACCESS*/, out) !== 0) return -1;
      const h = mod.HEAPU32[out >> 2];
      const r = mod._RegDeleteValueW(h, np);
      mod._RegCloseKey(h);
      return r === 0 ? 0 : -1;
    } finally { mod._free(hp); mod._free(np); mod._free(out); }
  }
  /** キー削除 (葉のみ。RegDeleteKeyW はルート + サブキーパスを辿る) */
  deleteKey(hive, key) {
    const mod = this.mod;
    const hp = this._wp(key);
    try { return mod._RegDeleteKeyW(ROOT_HANDLE[hive], hp) === 0 ? 0 : -1; } finally { mod._free(hp); }
  }
  /** 数値読み (FL の TRegistry.ReadInteger 相当: REG_DWORD は数値、REG_SZ は 10 進文字列を解釈) */
  readInt(hive, key, name, def = 0) {
    const v = this.readStr(hive, key, name);
    if (typeof v === 'number') return v;
    if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
    return def;
  }
  /** .reg 取り込み。戻り = 適用数 */
  importReg(input) { return this._importText(opsToText(parseReg(input))); }
  exportReg({ hives = ['HKCU', 'HKLM'], utf16le = true } = {}) {
    const m = emptyModel();
    for (const h of hives) m[h] = parseToModel(this._exportHiveText(h))[h];
    return utf16le ? regBytes(m, { hives }) : serializeReg(m, { hives });
  }
  snapshot(hives = ROOTS) {
    const m = emptyModel();
    for (const h of hives) m[h] = parseToModel(this._exportHiveText(h))[h];
    return m;
  }
  readModel(hive = PERSISTED) { return parseToModel(this._exportHiveText(hive))[hive]; }
  /** サブキー名一覧 (vreg probe enum kind=0 相当) */
  subKeys(hive, key = '') {
    const m = this.readModel(hive);
    const pref = key ? key.toLowerCase() + '\\' : '';
    const set = new Set();
    for (const k of Object.keys(m)) {
      const low = k.toLowerCase();
      if (pref && !low.startsWith(pref)) continue;
      const rest = k.slice(pref.length);
      if (rest) set.add(rest.split('\\')[0]);
    }
    return [...set];
  }
  readStr(hive, key, name) { return this.readModel(hive)?.[key]?.[name]?.v; }
  valueExists(hive, key, name) { return this.readModel(hive)?.[key]?.[name] !== undefined; }
  keyExists(hive, key) { return this.readModel(hive)?.[key] !== undefined; }
  enumNames(hive, key) { return this.subKeys(hive, key); }
  stats() { const a = this.mod._malloc(8); this.mod._shimx_reg_stats(a, a + 4); const r = { keys: this.mod.HEAPU32[a >> 2], values: this.mod.HEAPU32[(a + 4) >> 2] }; this.mod._free(a); return r; }
  counts() { return countModel(this.snapshot()); }

  /** FL の登録状態検査 (engine FUN_008e6150 と同じ判定。vreg Vreg.observeRegistration と同一) */
  observeRegistration() {
    for (const hive of ['HKCU', 'HKLM']) {
      const names = this.subKeys(hive, 'Software\\Image-Line\\Registrations');
      for (const n of names.filter((x) => x.startsWith('FL Studio '))) {
        const v = this.readStr(hive, `Software\\Image-Line\\Registrations\\${n}`, 'ILRegKey');
        if (v) return { registered: true, hive, subkey: n };
      }
    }
    return { registered: false };
  }
}

// .reg ops → shimx_reg_import_text へ渡せるテキスト (削除操作も保持。vreg.mjs opsToText と同一規則)
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
