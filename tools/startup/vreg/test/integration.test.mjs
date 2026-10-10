// vreg 結合テスト: 実 wasm (shimx 正本 reg.c) × JS アダプタ × store。受入: Shared\Paths / MachineGuid / CurrentVersion、
// REGISTRY.csv 全キーの往復 (set→export→import→get)、リロードで HKCU 永続。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { boot, seed, keysJson, ROOT, GEN, PATHS, CV } from './helpers.mjs';
import { MemoryStore, FileStore } from '../js/store.mjs';
import * as R from '../js/regfile.mjs';

const ENGINE = 'C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll';

test('起動経路の Reg 読出し: Shared\\Paths / MachineGuid / CurrentVersion が期待値', async () => {
  const v = await boot();
  for (const hive of ['HKCU', 'HKLM']) {
    assert.equal(v.readStr(hive, PATHS, 'FL Studio engine').value, ENGINE);
    assert.equal(v.readStr(hive, PATHS, 'Shared DLLs').value, 'C:\\Program Files\\Image-Line\\FL Studio 2026\\Shared\\');
  }
  assert.equal(v.readStr('HKCU', PATHS, 'Shared data').value, 'C:\\Users\\webstudio\\Documents\\Image-Line\\');
  assert.match(v.readStr('HKLM', 'SOFTWARE\\Microsoft\\Cryptography', 'MachineGuid').value, /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  const cv = (n) => v.readStr('HKLM', CV, n);
  assert.equal(cv('CurrentVersion').value, '6.3');
  assert.equal(cv('CurrentBuild').value, '19045');
  assert.equal(cv('ProductName').value, 'Windows 10 Pro');
  // OS の CurrentMajor/MinorVersionNumber だけ DWORD (他は REG_SZ)
  assert.deepEqual([cv('CurrentMajorVersionNumber').type, cv('CurrentMajorVersionNumber').value], [4, '10']);
  assert.equal(cv('CurrentMinorVersionNumber').type, 4);
  assert.equal(cv('ReleaseId').type, 1);
  // 大小無視 (engine は 'software\microsoft\Windows NT\CurrentVersion' も開く)
  assert.equal(v.readStr('HKLM', 'software\\microsoft\\Windows NT\\CurrentVersion', 'ProductName').value, 'Windows 10 Pro');
  // 起動ゲート G08 の値
  assert.equal(v.readBool('HKCU', GEN, 'CrashLoadingStartupProject', 1), false);
  assert.equal(v.readBool('HKCU', GEN, 'Disable FL CLOUD search', 0), true);
});

test('ReadInt は REG_SZ 文字列→数値変換 (FL は Int/Bool も文字列で保存)', async () => {
  const v = await boot();
  assert.equal(v.readStr('HKCU', GEN, 'AlwaysAskProjectFolder').type, 1);        // seed は REG_SZ
  assert.equal(v.readInt('HKCU', GEN, 'AlwaysAskProjectFolder', -1), 4);
  assert.equal(v.readInt('HKCU', GEN, 'BackColor', -1), 7103582);
  v.writeInt('HKCU', GEN, 'Run counter', 41);
  assert.equal(v.readStr('HKCU', GEN, 'Run counter').value, '41');
  assert.equal(v.readInt('HKCU', GEN, 'Run counter', 0), 41);
  assert.equal(v.readInt('HKCU', GEN, 'No such value', 44100), 44100);
  v.writeStr('HKCU', GEN, 'Junk', 'abc');
  assert.equal(v.readInt('HKCU', GEN, 'Junk', 9), 9);
});

test('FUN_008e6150 相当の登録検査: registered=true / Token は seed しない', async () => {
  const v = await boot();
  assert.deepEqual(v.observeRegistration(), { registered: true, hive: 'HKCU', subkey: 'FL Studio 26.1' });
  assert.equal(v.keyExists('HKCU', 'Software\\Image-Line\\Registrations\\Token'), false);
  assert.deepEqual(v.enumNames('HKCU', 'Software\\Image-Line\\Registrations'), ['FL Data', 'FL Studio 26.1']);
  assert.equal(v.readStr('HKCU', 'Software\\Image-Line\\Registrations', 'FL Studio user name').value, 'WebStudio User');
});

test('REGISTRY.csv の全キー (具象化 %d 本) が set→export(UTF-16LE .reg)→import→get で往復一致'.replace('%d', keysJson.keys.length), async () => {
  const v = await boot();
  const val = (k) => `rt:${k.hive}:${k.key.toLowerCase()}`;      // キーは大小無視で同一 (別名キーは同じ値)
  for (const k of keysJson.keys) assert.equal(v.writeStr(k.hive, k.key, 'vreg_roundtrip', val(k)), 0, k.key);
  const before = v.snapshot(['HKCU', 'HKLM']);
  const bytes = v.exportReg({ hives: ['HKCU', 'HKLM'], utf16le: true });
  assert.deepEqual([bytes[0], bytes[1]], [0xff, 0xfe]);
  // 各キーを丸ごと削除して消えたことを確認
  for (const k of keysJson.keys) v.importReg(`[-${R.ROOT_NAME[k.hive]}\\${k.key}]\n`);
  for (const k of keysJson.keys) assert.equal(v.keyExists(k.hive, k.key), false, 'deleted: ' + k.key);
  assert.ok(v.importReg(bytes) > 0);
  for (const k of keysJson.keys) assert.equal(v.readStr(k.hive, k.key, 'vreg_roundtrip').value, val(k), k.key);
  assert.deepEqual(v.snapshot(['HKCU', 'HKLM']), before);        // レジストリ全体が完全一致
  const lit = keysJson.keys.filter((k) => k.class === 'literal');
  assert.ok(lit.length >= 31, 'literal キー数 ' + lit.length);
});

test('全型 (REG_SZ/DWORD/QWORD/BINARY/MULTI_SZ/EXPAND_SZ/日本語) が C 側を経由して往復', async () => {
  const v = await boot();
  const src = [
    'Windows Registry Editor Version 5.00', '', '[HKEY_CURRENT_USER\\Software\\Types]', '@="d"', '"s"="a\\\\b\\"c"', '"日本語"="値あ😀"',
    '"dw"=dword:deadbeef', '"qw"=hex(b):01,02,03,04,05,06,07,08', '"bin"=hex:00,ff,10', '"ms"=hex(7):61,00,00,00,62,00,00,00,00,00',
    '"ex"=hex(2):25,00,41,00,25,00,00,00', '',
  ].join('\n');
  v.importReg(src);
  const got = v.snapshot(['HKCU']).HKCU['Software\\Types'];
  const want = R.parseToModel(src).HKCU['Software\\Types'];
  assert.deepEqual(got, want);
});

test('リロードで HKCU 値が永続 / 削除も永続 / HKLM はセッション内のみ', async () => {
  const store = new MemoryStore();
  const a = await boot({ store });
  a.writeInt('HKCU', GEN, 'Run counter', 7);
  a.writeStr('HKCU', 'Software\\Image-Line\\FL Studio 26\\MRU', 'Recent 0', 'C:\\x.flp');
  a.writeStr('HKLM', 'Software\\Image-Line\\Shared\\General', 'SessionOnly', '1');
  a.importReg(`[HKEY_CURRENT_USER\\${GEN}]\n"AUSlide"=-\n`);              // seed 値の削除
  await a.flush();
  const b = await boot({ store });                                          // 新 wasm instance = リロード
  assert.equal(b.bootInfo.restored, true);
  assert.equal(b.readInt('HKCU', GEN, 'Run counter', 0), 7);
  assert.equal(b.readStr('HKCU', 'Software\\Image-Line\\FL Studio 26\\MRU', 'Recent 0').value, 'C:\\x.flp');
  assert.equal(b.valueExists('HKCU', GEN, 'AUSlide'), false);               // 削除が seed で復活しない
  assert.equal(b.valueExists('HKLM', 'Software\\Image-Line\\Shared\\General', 'SessionOnly'), false);
  assert.equal(b.readStr('HKLM', PATHS, 'FL Studio engine').value, ENGINE); // HKLM は毎回 seed から
  assert.equal(b.readStr('HKCU', PATHS, 'FL Studio engine').value, ENGINE);
});

test('自動 flush: 変更通知 → 遅延 flush で store に保存 (明示 flush なし)', async () => {
  const store = new MemoryStore();
  const a = await boot({ store, flushDelayMs: 20 });
  const n0 = a.flushes;
  a.writeInt('HKCU', GEN, 'Run counter', 99);
  for (let i = 0; i < 100 && a.flushes === n0; i++) await new Promise((r) => setTimeout(r, 10));
  assert.ok(a.flushes > n0);
  assert.equal((await store.load('default')).hkcu[GEN]['Run counter'].v, '99');
  const g = a.generation(); a.readInt('HKCU', GEN, 'Run counter', 0); assert.equal(a.generation(), g);   // 読出しは世代不変
});

test('MachineGuid: プロファイル毎に生成 / 同一プロファイルでは安定 / 明示指定可', async () => {
  const store = new MemoryStore();
  const g = async (opts) => (await boot({ store, ...opts })).readStr('HKLM', 'SOFTWARE\\Microsoft\\Cryptography', 'MachineGuid').value;
  const a1 = await g({ profile: 'A' }), a2 = await g({ profile: 'A' }), b1 = await g({ profile: 'B' });
  assert.equal(a1, a2); assert.notEqual(a1, b1);
  assert.equal(await g({ profile: 'C', machineGuid: '11111111-2222-4333-8444-555555555555' }), '11111111-2222-4333-8444-555555555555');
});

test('ライセンス: flag_bit0 を seed/オプションで切替 (0=登録済み値あり / 1=Trial: 値なし)。同一プロファイルで往復', async () => {
  const store = new MemoryStore();
  const reg = await boot({ store });
  assert.equal(reg.licenseMode, 'registered'); assert.equal(reg.expectedLicense().expectedBit0, 0);
  assert.equal(reg.observeRegistration().registered, true);
  await reg.flush(true);
  const trial = await boot({ store, licenseFlagBit0: 1 });
  assert.equal(trial.licenseMode, 'trial'); assert.equal(trial.expectedLicense().expectedBit0, 1);
  assert.equal(trial.observeRegistration().registered, false);
  assert.equal(trial.keyExists('HKCU', 'Software\\Image-Line\\Registrations\\FL Studio 26.1'), false);
  assert.equal(trial.keyExists('HKLM', 'Software\\Image-Line\\Registrations\\FL Studio 26.1'), false);
  await trial.flush(true);
  const again = await boot({ store, licenseFlagBit0: 0 });                  // 永続済み Trial 状態から登録済みへ戻る (pinned)
  assert.equal(again.observeRegistration().registered, true);
  // seed 自体の既定を変えた場合
  const trialSeed = { ...seed, license: { ...seed.license, flag_bit0: 1 } };
  const t2 = await boot({ seed: trialSeed, profile: 'T' });
  assert.equal(t2.licenseMode, 'trial'); assert.equal(t2.observeRegistration().registered, false);
});

test('ライセンス external: ユーザ提供 .reg (cracked 資源) を最優先で適用。seed の placeholder は書かない', async () => {
  const ext = '\uFEFFWindows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\Image-Line\\Registrations\\FL Studio 26.1]\r\n"ILRegKey"="EXTERNAL-KEY"\r\n';
  const bytes = R.encodeUtf16le(ext.replace(/^\uFEFF/, ''), true);
  const v = await boot({ externalReg: bytes });
  assert.equal(v.licenseMode, 'external'); assert.equal(v.expectedLicense().expectedBit0, null);
  assert.equal(v.readStr('HKCU', 'Software\\Image-Line\\Registrations\\FL Studio 26.1', 'ILRegKey').value, 'EXTERNAL-KEY');
  assert.equal(v.valueExists('HKCU', 'Software\\Image-Line\\Registrations\\FL Data', 'ILRegKey'), false);
  assert.equal(v.observeRegistration().registered, true);
});

test('seed 更新: 既存プロファイルには不足分だけ補う (ユーザ変更値は保持)', async () => {
  const store = new MemoryStore();
  const a = await boot({ store });
  a.writeInt('HKCU', GEN, 'AlwaysAskProjectFolder', 2);
  await a.flush(true);
  const seed2 = structuredClone(seed); seed2.version = 99;
  seed2.entries.push({ hive: 'HKCU', key: GEN, name: 'NewInV99', type: 'REG_SZ', value: 'x', apply: true, group: 'settings', confidence: '推定', key_conf: '推定', value_conf: '推定', basis: 't', pinned: false });
  const b = await boot({ store, seed: seed2 });
  assert.equal(b.readStr('HKCU', GEN, 'NewInV99').value, 'x');
  assert.equal(b.readInt('HKCU', GEN, 'AlwaysAskProjectFolder', 0), 2);
});

test('skipGroups: コード既定値 (settings/shared) を書かず「値なし」を保てる。paths/os/license は影響なし', async () => {
  const v = await boot({ skipGroups: ['settings', 'shared'] });
  assert.equal(v.valueExists('HKCU', GEN, 'Run counter'), false);
  assert.equal(v.readInt('HKCU', GEN, 'Run counter', 77), 77);
  assert.equal(v.readStr('HKCU', PATHS, 'FL Studio engine').value, ENGINE);
  assert.equal(v.observeRegistration().registered, true);
});

test('FileStore: 別 wasm instance 間で JSON ファイルとして永続', async () => {
  const dir = path.join(ROOT, 'work', 'filestore-' + process.pid);
  const s = new FileStore(dir);
  const a = await boot({ store: s }); a.writeInt('HKCU', GEN, 'Run counter', 5); await a.flush();
  const b = await boot({ store: new FileStore(dir) });
  assert.equal(b.readInt('HKCU', GEN, 'Run counter', 0), 5);
  await s.delete('default'); assert.equal(await s.load('default'), undefined);
});

test('coverage: 全値名に初期値 / apply 値は Reg API で読める / キーの具象化 (data/coverage.json を更新)', async () => {
  const v = await boot();
  const lc = (s) => s.toLowerCase();
  const names = new Set(seed.entries.map((e) => lc(e.name)));
  const csv = parseCsv(readFileSync(path.join(ROOT, '../REGISTRY.csv'), 'utf8')).filter((r) => ['both', 'win'].includes(r.platform));
  const isName = (n) => n && !(n.startsWith('(') || n.startsWith('#') || n.includes('/') || n.includes(';'));
  const csvNames = new Set(csv.map((r) => r.value).filter(isName).map(lc));
  const missing = [...csvNames].filter((n) => !names.has(n));
  assert.deepEqual(missing, [], 'seed に無い値名');
  let readable = 0, applyN = 0, keyless = 0;
  for (const e of seed.entries) {
    if (!e.key) { keyless++; continue; }
    const got = v.readStr(e.hive, e.key, e.name);
    if (e.apply && !(e.group === 'license' && v.licenseMode !== 'registered')) {
      applyN++;
      assert.equal(got.status, 0, `${e.hive}\\${e.key}\\${e.name}`);
      const want = e.value === '${MACHINE_GUID}' ? v.machineGuid : String(e.value);
      assert.equal(got.value, want, e.name);
      readable++;
    } else assert.notEqual(got.status, 0, 'catalog 値は書かれない: ' + e.name);
  }
  assert.equal(readable, applyN);
  const conf = { 確定: 0, 推定: 0 }; for (const e of seed.entries) conf[e.confidence]++;
  const groups = {}; for (const e of seed.entries) groups[e.group] = (groups[e.group] || 0) + 1;
  const keyCls = {};
  for (const k of keysJson.keys) { const c = (keyCls[k.class] ||= { concrete: 0, seeded_exists_after_boot: 0 }); c.concrete++; if (v.keyExists(k.hive, k.key)) c.seeded_exists_after_boot++; }
  const cov = {
    seed_entries: seed.entries.length, distinct_value_names_ci: names.size, csv_distinct_value_names_ci: csvNames.size,
    csv_names_missing_in_seed: missing.length, applied_to_registry: applyN, catalog_only: seed.entries.length - applyN,
    catalog_only_key_unknown: keyless, readable_via_reg_api: readable, confidence: conf, groups, csv_keys: new Set(keysJson.keys.map((k) => k.hive + '|' + k.csv_key)).size,
    concrete_keys: keysJson.keys.length, key_classes: keyCls, boot: v.bootInfo, stats_after_boot: v.stats(),
  };
  writeFileSync(path.join(ROOT, 'data/coverage.json'), JSON.stringify(cov, null, 1) + '\n');
  assert.equal(cov.csv_names_missing_in_seed, 0);
});

function parseCsv(t) {
  const rows = []; let row = [], f = '', q = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (q) { if (c === '"') { if (t[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true; else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n') { row.push(f); rows.push(row); row = []; f = ''; } else if (c !== '\r') f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  const h = rows.shift();
  return rows.filter((r) => r.length >= h.length - 1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ''])));
}
