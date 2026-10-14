// license_import.mjs — ユーザ自身が書き出した .reg を vreg に取り込む入口 (DOM 非依存のロジック部)。
//   取り込む .reg は生成・改変せず、受け取ったバイト列をそのまま store の別キー (`<profile>#user-reg`) に保存する。
//   以後の boot では externalReg として最後に適用する (seed の license 値より優先 = external モード)。
//   取込と MachineGuid 変更は「保存 → 仮想レジストリを開き直す」で行う。取込直後と再読込後の状態を一致させるため。
import { Vreg } from './vreg.mjs';
import { parseReg, decodeRegBytes } from './regfile.mjs';

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HEADER = 'Windows Registry Editor Version 5.00';
const userKey = (profile) => `${profile}#user-reg`;

/** .reg として受理できるかを検査する。失敗は throw (状態は変えない)。 */
export function checkUserReg(bytes) {
  const text = decodeRegBytes(bytes);
  if (text.split(/\r?\n/, 1)[0].trim() !== HEADER) throw new Error(`.reg ではありません (1 行目が "${HEADER}" ではありません)`);
  const values = parseReg(text).filter((o) => o.op === 'set').length;
  if (values === 0) throw new Error('.reg に値がありません');
  return { values };
}

export class LicenseImport {
  /**
   * @param {object} o
   * @param {() => Promise<object>} o.createModule  vreg wasm の factory (build/vreg_wasm.mjs)
   * @param {{load,save,delete}} o.store            永続化 (IdbStore 等)
   * @param {object} o.seed                         data/seed.json
   * @param {string} [o.profile='default']
   */
  static async open(o) {
    const s = new LicenseImport(o);
    await s._serial(() => s._reopen());
    return s;
  }

  constructor(o) {
    this.o = o; this.profile = o.profile ?? 'default'; this.vreg = null; this.userReg = null; this.machineGuid = undefined;
    this.chain = Promise.resolve();
  }

  _serial(fn) { return (this.chain = this.chain.then(fn, fn)); }

  async _reopen() {
    this.userReg = (await this.o.store.load(userKey(this.profile))) ?? null;
    if (this.vreg) await this.vreg.close();
    this.vreg = await Vreg.create({
      createModule: this.o.createModule, store: this.o.store, seed: this.o.seed, profile: this.profile,
      externalReg: this.userReg ? this.userReg.bytes : undefined,
      machineGuid: this.machineGuid,
    });
    await this.vreg.flush(true);   // boot で決めた MachineGuid・取込状態を記録へ (vreg は新規プロファイル以外で保存しない)
  }

  /** ユーザの .reg (バイト列) を取り込む。不正なら throw し、保存済みの取込みは変えない。 */
  importUserReg(bytes, name = '') {
    return this._serial(async () => {
      const info = checkUserReg(bytes);
      await this.o.store.save(userKey(this.profile), { schema: 1, name, savedAt: Date.now(), bytes: new Uint8Array(bytes) });
      await this._reopen();
      return info;
    });
  }

  /** MachineGuid をユーザ指定にする (8-4-4-4-12 の 16 進)。以後の boot でも保存値が使われる。 */
  setMachineGuid(guid) {
    if (!GUID_RE.test(guid)) throw new Error('MachineGuid は xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx 形式で指定してください');
    return this._serial(async () => {
      this.machineGuid = guid.toLowerCase();
      await this._reopen();
    });
  }

  status() {
    const v = this.vreg;
    const reg = v.observeRegistration();
    return {
      restored: v.bootInfo.restored,
      licenseMode: v.licenseMode,
      registered: reg.registered,
      userReg: this.userReg ? { name: this.userReg.name, savedAt: this.userReg.savedAt } : null,
      machineGuid: v.machineGuid,
    };
  }
}
