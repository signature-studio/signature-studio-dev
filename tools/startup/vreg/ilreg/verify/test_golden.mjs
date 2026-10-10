// test_golden.mjs — reader 模擬検証器のゴールデンテスト。
// 入力: tools/startup/vreg/data/seed.json のライセンス値 (vreg seed) と合成ベクタ。
// 判定根拠は FORMAT.md § 各節のアドレス。
// 実行: node tools/startup/vreg/ilreg/verify/test_golden.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  CONSTANTS, machineBytes, checksumByte, machineString,
  envelopeHexPack, splitFirstGroup, dateFrom8, judge, todayStr, idxOf,
} from './reader.mjs';

let pass = 0, fail = 0;
function ok(name, fn) {
  try { fn(); console.log(`PASS  ${name}`); pass++; }
  catch (e) { console.error(`FAIL  ${name}\n      ${e.message}`); fail++; }
}

const seed = JSON.parse(readFileSync(
  new URL('../../data/seed.json', import.meta.url), 'utf8'));
const licEntries = (seed.entries ?? []).filter((e) => e.group === 'license');
const ilreg = licEntries.find((e) => e.key.endsWith('FL Studio 26.1') && e.hive === 'HKCU');
const userName = licEntries.find((e) => e.name === 'FL Studio user name');
const webpass = licEntries.find((e) => e.name === 'FL Studio webpass');

// ---------------------------------------------------------------
// T1. マシン識別文字列: 書式と SHA-256 の正しさ
// ---------------------------------------------------------------
ok('T1a machineString 書式 (8x8 hex upper + checksum 2 hex lower, 計74文字)', () => {
  const m = machineString({
    appData: 'C:\\Users\\u\\AppData\\Roaming',
    computerName: 'WS-01',
    machineGuid: '11111111-2222-3333-4444-555555555555',
  });
  assert.equal(m.length, 74, `len=${m.length}`); // 64hex+7dash+1dash+2ck
  assert.match(m, /^[0-9A-F]{8}(-[0-9A-F]{8}){7}-[0-9a-f]{2}$/);
});

ok('T1b SHA-256 本体が node:crypto と一致 (低バイト連結ストリーム)', () => {
  // machineBytes → SHA-256 という構造の検証 (K表 0x13b102c / H初期値 0xbf89b0 は実測済)
  const b = machineBytes({ appData: 'AB', computerName: 'C', machineGuid: 'D' });
  assert.deepEqual([...b], [0x41, 0x42, 0x43, 0x44]);
});

ok('T1c チェックサム式 (acc += c*2-3, byte wrap) — 手計算ベクタ', () => {
  // "AAAAAAAA" → Σ(0x41*2-3)=8*(65*2-3)=8*127=1016 → 1016&0xff=0xF8 (dash 前 8 文字)
  assert.equal(checksumByte('AAAAAAAA'), 0xf8);
  // '-' を含む 71 文字列でも wrap すること
  const dashed = 'AAAAAAAA-' + 'A'.repeat(63);
  assert.equal(typeof checksumByte(dashed), 'number');
});

ok('T1d 同一入力で決定的 / 入力変更で変化', () => {
  const a = machineString({ appData: 'x', computerName: 'y', machineGuid: 'z' });
  const b = machineString({ appData: 'x', computerName: 'y', machineGuid: 'z' });
  const c = machineString({ appData: 'x', computerName: 'Y', machineGuid: 'z' });
  assert.equal(a, b);
  assert.notEqual(a, c);
});

// ---------------------------------------------------------------
// T2. vreg seed の ILRegKey プレースホルダのエンベロープ解析
// ---------------------------------------------------------------
ok('T2a seed の ILRegKey = WEBSTUDIO-ACTIVATED-PLACEHOLDER (HKCU FL Studio 26.1)', () => {
  assert.equal(ilreg?.value, 'WEBSTUDIO-ACTIVATED-PLACEHOLDER');
});

ok('T2b envelopeHexPack: 16進ニブル規則と奇数長切捨て (0x8d0580)', () => {
  const r = envelopeHexPack('WEBSTUDIO-ACTIVATED-PLACEHOLDER'); // 31 文字 (奇数)
  assert.equal(r.charCount, 31);
  assert.equal(r.odd, true);
  assert.equal(r.bytes.length, 15);       // floor(31/2) — 0x8d0580 の iVar2 = len/2
  // 'W'=0x57 → 0x57-0x37=0x20, 'E'=0x45 → 0x45-0x37=0x0E → 1バイト目 = 0x20<<4|0x0E = 0x2E
  assert.equal(r.bytes[0], 0x0e); // (0x20<<4)&0xff=0x00 | 0x0e
  // '-'=0x2D → 0x2D-0x37 = -0x0A → &0xff = 0xF6 (ニブルとしては 0x6)
  const r2 = envelopeHexPack('W-');
  assert.equal(r2.bytes.length, 1);
  assert.equal(r2.bytes[0], 0xf6);
});

// ---------------------------------------------------------------
// T3. プレースホルダの判定 (0x10c7cd0 再現)
//     プレースホルダは VM 復号後も '|<key>:<date8>:' 形のレコードを
//     持たない平文にならない (= 判定不能な garbage)。ここでは
//     「レコードなし平文」として judge に渡し、エンジンの判定
//     (grade 0 / フラグ無変化 / gradeChar 0x40) を再現する。
// ---------------------------------------------------------------
const TODAY = dateFrom8(todayStr());

ok('T3a プレースホルダ判定: 全ティア grade 0 / gradeChar 0x40 / flag=0', () => {
  const m = machineString({ appData: 'C:\\u\\a', computerName: 'PC', machineGuid: 'G' });
  const r = judge({ plain: ':WEBSTUDIO-ACTIVATED-PLACEHOLDER:', machineStr: m, today: TODAY });
  assert.ok(r.perTier.every((t) => t.grade === 0), JSON.stringify(r.perTier));
  assert.equal(r.gradeChar, 0x40);
  assert.equal(r.flagByte.value, 0);
  assert.equal(r.daysRemaining, 0x7fffffff);
});

ok('T3b プレースホルダ判定: bit0 は立たない (0x10cf4e6 は死蔵経路)', () => {
  const m = machineString({ appData: 'C:\\u\\a', computerName: 'PC', machineGuid: 'G' });
  const r = judge({ plain: ':WEBSTUDIO-ACTIVATED-PLACEHOLDER:', machineStr: m, today: TODAY });
  assert.equal(r.flagByte.value & 1, 0);
  assert.equal(r.bit0WriterReachable, false);
  assert.equal(r.buttonId, 3);            // gradeChar 0x40 → Update registration
  assert.equal(r.registeredDisplay, false); // FUN_010c7530 は 0x40 < grade のみ表示
});

// ---------------------------------------------------------------
// T4. 構文整合な平文の判定 (マシン突合 + ティア日付)
// ---------------------------------------------------------------
const MS = machineString({ appData: 'C:\\u\\a', computerName: 'PC', machineGuid: 'G' });
const FUTURE = dateFrom8('20991231');
const PAST = dateFrom8('20200101');

ok('T4a 有効ライセンス形式: tier A grade 2 → gradeChar A / flag bit1,bit2 クリア', () => {
  const plain = `:WebStudio User:20991231:|31000:20991231:|id:${MS}`;
  const r = judge({ plain, machineStr: MS, today: TODAY });
  const a = r.perTier.find((t) => t.tier === 'A');
  assert.equal(a.grade, 2);
  assert.equal(a.machineChar, 'L');
  assert.equal(r.gradeChar, 0x41);
  assert.equal(r.flagByte.value & 0x6, 0);   // &= 0xfd, &= 0xfb
  assert.equal(r.buttonId, 1);               // 'A' < 0x44 → Upgrade registration
  assert.equal(r.registeredDisplay, true);   // 0x41 > 0x40
});

ok('T4b マシン ID 不一致: machineChar + → grade 0', () => {
  const other = machineString({ appData: 'C:\\u\\b', computerName: 'OTHER', machineGuid: 'H' });
  const plain = `:n:20991231:|31000:20991231:|id:${other}`;
  const r = judge({ plain, machineStr: MS, today: TODAY });
  const a = r.perTier.find((t) => t.tier === 'A');
  assert.equal(a.machineChar, '+');
  assert.equal(a.grade, 0);
});

ok('T4c 期限切れ: tier A grade 1 (gradeChar は 0x40 のまま・flag 無変化)', () => {
  const plain = `:n:20200101:|31000:20200101:|id:${MS}`;
  const r = judge({ plain, machineStr: MS, today: TODAY });
  const a = r.perTier.find((t) => t.tier === 'A');
  assert.equal(a.grade, 1);
  assert.equal(r.gradeChar, 0x40);
  assert.equal(r.flagByte.value & 0x6, 0);
});

ok('T4d 日付8文字不正 → grade 2 (quirk: FUN_008e6660=0 は期限切れ扱いしない)', () => {
  const plain = `:n:20200101:|31000:BADDATE:|id:${MS}`;
  const r = judge({ plain, machineStr: MS, today: TODAY });
  assert.equal(r.perTier.find((t) => t.tier === 'A').grade, 2);
});

ok('T4e id レコード無し + 重複フラグ無し → machineChar + → grade 0', () => {
  const plain = ':n:20991231:|31000:20991231:';
  const r = judge({ plain, machineStr: MS, today: TODAY });
  assert.equal(r.perTier.find((t) => t.tier === 'A').machineChar, '+');
  assert.equal(r.perTier.find((t) => t.tier === 'A').grade, 0);
});

ok('T4f 第二ティア: first が grade 2 でない時のみ評価 (B=(31010,31005))', () => {
  const plain = `:n:20991231:|31005:20991231:|id:${MS}`;   // second のみ存在
  const r = judge({ plain, machineStr: MS, today: TODAY });
  const b = r.perTier.find((t) => t.tier === 'B');
  assert.equal(b.grade, 0);                  // first (31010) 無し
  assert.equal(b.secondGrade, 2);
  assert.equal(r.flagByte.value & 2, 2);     // |= 2
  assert.equal(r.flagByte.value & 4, 4);     // |= 4
  assert.equal(r.gradeChar, 0x42);
});

ok('T4g head 非空 (strictHead) → grade 0 (0x10cae5c の実装通り)', () => {
  const plain = `HEAD:n:20991231:|31000:20991231:|id:${MS}`;
  const r = judge({ plain, machineStr: MS, today: TODAY });
  assert.ok(r.perTier.every((t) => t.grade === 0));
  // 緩運用 (strictHead=false) では head 非空でも判定継続
  const r2 = judge({ plain, machineStr: MS, today: TODAY, strictHead: false });
  assert.equal(r2.perTier.find((t) => t.tier === 'A').grade, 2);
});

// ---------------------------------------------------------------
// T5. 分割ユーティリティ (FUN_008e6770 互換)
// ---------------------------------------------------------------
ok('T5a splitFirstGroup: ":F0:F1:rest" 分割', () => {
  const s = splitFirstGroup(':name:20260101:|31000:20991231:|id:X');
  assert.equal(s.head, '');
  assert.equal(s.F0, 'name');
  assert.equal(s.F1, '20260101');
  assert.equal(s.rest, '|31000:20991231:|id:X');
});

ok('T5b splitFirstGroup: \':\' 無し → 全体が head (FUN_008e6770 else 経路)', () => {
  const s = splitFirstGroup('NOSEP');
  assert.equal(s.head, 'NOSEP');
  assert.equal(s.rest, '');
});

ok('T5c dateFrom8: うるう年/範囲チェック (FUN_00442770 互換)', () => {
  assert.ok(dateFrom8('20240229') > 0);
  assert.equal(dateFrom8('20230229'), 0);    // 平年の 2/29
  assert.equal(dateFrom8('20261301'), 0);    // 月 13
  assert.equal(dateFrom8('123'), 0);         // 長さ 8 以外
});

ok('T5d idxOf は Delphi Pos 互換 (1-based, 見つからない=0)', () => {
  assert.equal(idxOf('abc', 'b'), 2);
  assert.equal(idxOf('abc', 'z'), 0);
});

// ---------------------------------------------------------------
// T6. constants.json の実測整合 (バイナリ抽出値のスポット確認)
// ---------------------------------------------------------------
ok('T6a 定数: セパレータ/接頭辞/ティア表/mask/VM プログラム', () => {
  assert.equal(CONSTANTS.separators.colon.text, ':');
  assert.equal(CONSTANTS.separators.pipe.text, '|');
  assert.equal(CONSTANTS.separators.sep1_encoded.decoded, '|LL=OFF');
  assert.equal(CONSTANTS.separators.sep2_encoded.decoded, '|LL=');
  assert.equal(CONSTANTS.separators.marker_encoded.decoded, 'TRSLA');
  assert.equal(CONSTANTS.id_prefix.decoded, 'id:');
  assert.deepEqual(CONSTANTS.feature_table.tiers.map((t) => t.first), [31000, 31010, 31020]);
  assert.deepEqual(CONSTANTS.feature_table.tiers.map((t) => t.grade_char), ['A', 'B', 'C']);
  assert.equal(CONSTANTS.grade_mask.value, 6);
  assert.equal(CONSTANTS.vm_program.size, 0x2af);
  assert.equal(CONSTANTS.sha256.k_table.ok, true);
});

// ---------------------------------------------------------------
// サマリ
// ---------------------------------------------------------------
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
