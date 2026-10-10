// reader.mjs — FLEngine 0x10c7cd0 (登録パーサ) の判定を reader 側で再現する模擬検証器。
//
// 出典: tools/startup/vreg/ilreg/FORMAT.md (アドレス証拠付き)。
// 実装方針: 「確定」(逆アセンブルでピン留めされた制御フロー) をそのまま移植する。
// 「未確定」(実データでの最終確認が必要な点) はオプションとログで明示。
//
// 対応エンジン: FLEngine_x64.dll 26.1.7 (win64, ImageBase 0x400000)
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
export const CONSTANTS = JSON.parse(
  readFileSync(join(HERE, '..', 'data', 'constants.json'), 'utf8'));

// ------------------------------------------------------------------
// 1. マシン識別文字列 (FORMAT.md §3)
//    SHA-256( lowByte(AppData path) ++ lowByte(ComputerName) ++ lowByte(MachineGuid) )
//    → 64 文字の大文字 hex を 8 文字ずつ '-' で区切り、末尾にチェックサム 2 文字 (小文字 hex)。
// ------------------------------------------------------------------

// エンジンは UTF-16 コードユニット毎にハッシュへ「下位バイト」を積む
// (0x10c7cd0 内 +0x70 AppendChar / SHA-256 ブロック充填が *(byte*)dst = char)。
export function machineBytes({ appData, computerName, machineGuid }) {
  const parts = [appData, computerName, machineGuid];
  const out = [];
  for (const s of parts) {
    for (const ch of String(s ?? '')) {
      const u = ch.codePointAt(0) > 0xffff ? 0xfffd : ch.codePointAt(0);
      out.push(u & 0xff);
    }
  }
  return Buffer.from(out);
}

// チェックサム: 区切り済み 71 文字に対し acc = (acc + c*2 - 3) & 0xff
// (0x10c93bf-0x10c93d0: mov al,2 / imul cl / add cl,al / sub cl,3 / mov [rbp+0x72b],cl)
export function checksumByte(dashed) {
  let acc = 0;
  for (const c of dashed) acc = (acc + c.codePointAt(0) * 2 - 3) & 0xff;
  return acc;
}

export function machineString(ids) {
  const digest = createHash('sha256').update(machineBytes(ids)).digest(); // 32B
  const hex = digest.toString('hex').toUpperCase();                       // 64
  const dashed = hex.match(/.{8}/g).join('-');                            // 71
  const ck = checksumByte(dashed);
  return `${dashed}-${ck.toString(16).padStart(2, '0')}`;                 // 73
}

// ------------------------------------------------------------------
// 2. ILRegKey 値のエンベロープ (FORMAT.md §4)
//    FUN_008cfd20 (box) → FUN_008e7080 (cache) → FUN_008d0580:
//    各 wchar を 16 進ニブルとみなして pack ('0'-'9' → -0x30, 以外 → -0x37)、
//    2 文字で 1 バイト (奇数長は最終ニブルが捨てられる)。
//    → VM (FUN_008d0380 / プログラム 0x14111e0, 0x2af byte) で復号 → 平文。
//    VM は本チケットでは実装しない (次段)。ここでは pack 結果までを返す。
// ------------------------------------------------------------------

export function envelopeHexPack(s) {
  const chars = [...String(s ?? '')];
  const n = Math.floor(chars.length / 2);
  const out = Buffer.alloc(n);
  let w = 0;
  for (let i = 0; i < chars.length; i++) {
    const c = chars[i].codePointAt(0);
    let v = (c >= 0x30 && c <= 0x39) ? c - 0x30 : c - 0x37;   // 0x8d0580 内分岐
    v &= 0xff;
    if ((i & 1) === 0) out[w] = (v << 4) & 0xff;
    else { out[w] |= v; w++; }
  }
  return { bytes: out, charCount: chars.length, odd: (chars.length % 2) === 1 };
}

// ------------------------------------------------------------------
// 3. 平文の構造解析 (FORMAT.md §5)
//    FUN_008e6770: 最初の ':' で head / 残りを ':' で F0, date8(F1), rest に分割。
// ------------------------------------------------------------------

export function idxOf(s, sub) {           // Delphi Pos 互換 (1-based, 見つからない=0)
  return String(s).indexOf(sub) + 1;
}
export function substr1(s, from, count) { // Delphi Copy(s, from, count) 互換
  s = String(s);
  if (from < 1 || from > s.length) return '';
  return s.slice(from - 1, from - 1 + Math.max(0, count));
}

export function splitFirstGroup(plain) {
  // FUN_008e6770 (0x8e6770) の SplitBy(':','|') 相当
  plain = String(plain ?? '');
  const p1 = idxOf(plain, ':');
  const p2 = idxOf(plain, '|');
  let head, tail;
  if (p1 === 0 || (p2 !== 0 && p2 < p1)) {
    head = plain; tail = '';
  } else {
    head = plain.slice(0, p1 - 1);        // Copy(plain, 1, p1-1)
    tail = plain.slice(p1);               // Copy(plain, p1+1, MAX) — ':' 消費
  }
  const fields = [];
  let cur = tail;
  for (;;) {
    const a = idxOf(cur, ':');
    const b = idxOf(cur, '|');
    if (a === 0 || (b !== 0 && b < a)) { if (cur.length) fields.push(cur); break; }
    fields.push(cur.slice(0, a - 1));
    cur = cur.slice(a);
  }
  const F0 = fields[0] ?? '';
  const F1 = fields[1] ?? '';
  const rest = fields.slice(2).join(':');
  return { head, F0, F1, rest };
}

// FUN_008e6660: 8 文字 (YYYYMMDD) → Delphi TDate (double, 1899-12-30=0)。8 文字以外/不正は 0。
export function dateFrom8(s8) {
  if (typeof s8 !== 'string' || s8.length !== 8) return 0;
  const y = Number(s8.slice(0, 4));
  const m = Number(s8.slice(4, 6));
  const d = Number(s8.slice(6, 8));
  // FUN_00442770 (0x442770): y∈1..9999, m∈1..12, d∈1..daysInMonth(y,m)
  if (!Number.isInteger(y) || y < 1 || y > 9999) return 0;
  if (!Number.isInteger(m) || m < 1 || m > 12) return 0;
  if (!Number.isInteger(d) || d < 1) return 0;
  const dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let dm = dim[m - 1];
  if (m === 2 && ((y % 4 === 0 && y % 100 !== 0) || y % 400 === 0)) dm = 29;
  if (d > dm) return 0;
  return Date.UTC(y, m - 1, d) / 86400000 + 25569;
}

export function todayStr(d = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

// ------------------------------------------------------------------
// 4. 判定 (FORMAT.md §6) — 0x10c7cd0 の制御フローを再現
// ------------------------------------------------------------------

// 重複検出フラグ (0x15e1b10): 0x10ca4e4-0x10ca52f の走査 (検索語の前缀 3 文字は推定実装)。
export function dupFlagOf(rest) {
  for (const k of [31035, 31020, 31010]) {
    if (idxOf(rest, '|' + String(k)) > 0) return true;
  }
  return false;
}

// "|<key>:<date8>:" レコードから date8 を取り出す (0x10cb741-0x10cb945)
function extractRecordDate(rest, key) {
  const pos = idxOf(rest, '|' + key);
  if (pos === 0) return null;
  let sub = String(rest).slice(pos);          // '|' の直後から (= "key:date8:...")
  const c1 = idxOf(sub, ':');
  if (c1 === 0) return { date8: null };
  const inner = sub.slice(c1);                // ':' を消費 → "date8:..."
  const c2 = idxOf(inner, ':');
  if (c2 === 0) return { date8: null };
  return { date8: inner.slice(0, c2 - 1) };
}

function tierGrade(rest, key, today) {
  const rec = extractRecordDate(rest, key);
  if (!rec) return { grade: 0, reason: `record |${key} なし → grade 0 (0x10cb79b)` };
  if (rec.date8 == null) return { grade: 0, reason: `record |${key} あり・日付フィールドなし` };
  const dv = dateFrom8(rec.date8);
  // days = dv - today (FUN_0040c750 = Trunc)。FUN_010c7850 の min/max は平文日付が
  // 期限として直接使われるケース (Fire モード) を除き、ここでは単純差分。
  const days = (dv > 0) ? Math.trunc(dv - today) : 0;
  let grade = 2;                                          // 0x10cb96a
  if (days !== 0 && days <= 0) grade = 1;                 // 0x10cb971-0x10cb98a
  const reason = (dv === 0) ? '日付8文字不正(=0) → grade 2 (quirk)'
    : (grade === 2 ? 'record あり・期限内 → grade 2' : 'record あり・期限切れ → grade 1');
  return { grade, reason, date8: rec.date8, days };
}

/**
 * judge() — 0x10c7cd0 の判定を再現する。
 * @param {object} p
 *   plain        復号済み ILRegKey 平文 (VM 復号は次段。undefined/空 は「デコード結果空」扱い)
 *   machineStr   machineString() の結果
 *   today        エンジンの「今日」(TDate double)。未指定ならシステム日付
 *   dupFlag      重複検出フラグ (未指定なら rest から推定)
 *   strictHead   true (既定): head 空 (':' 始まり) のみ grade 判定へ進む (0x10cae5c 実装)
 */
export function judge({ plain, machineStr, today, dupFlag, strictHead = true }) {
  today = today ?? dateFrom8(todayStr());
  const flag = { value: 0 }; // byte[0x14f84a8] (0x10c877c で 0 に初期化)
  const out = {
    flagByte: flag, gradeChar: 0x40, daysRemaining: 0x7fffffff,
    buttonId: 3, button: 'Update registration', registeredDisplay: false,
    perTier: [], notes: [],
  };
  const has = typeof plain === 'string' && plain.length > 0;
  const sg = has ? splitFirstGroup(plain) : { head: '', F0: '', F1: '', rest: '' };
  const dup = dupFlag ?? dupFlagOf(sg.rest);

  const tiers = CONSTANTS.feature_table.tiers;   // A/B/C (0x15b7f00)
  for (let i = 0; i < tiers.length; i++) {
    const tier = tiers[i];
    const t = { tier: tier.grade_char, key: tier.first, second: tier.second, grade: 0, reason: '' };
    let grade = 0;
    do { // 制御フローを直列に書くための疑似ブロック (grade 0 は break で抜ける)
      if (!has) { t.reason = 'decoded-empty'; break; }
      // marker (0x10cad1c-0x10cae5c): head 空のみ先へ。head 非空でも charsum 比較に
      // 進むが FUN_008e5e90(head,[],0) が常に -1 のため比較は到達不能 (死蔵コード)。
      const marker = (sg.head.length === 0);
      if (!marker && strictHead) { t.reason = 'head 非空 → marker=0 → grade 0 (0x10cae5c)'; break; }
      if (!marker) out.notes.push(`tier ${tier.grade_char}: strictHead=false で head 非空のまま継続`);
      // マシン突合 (0x10cb6b8-0x10cb728)
      let ch;
      if (sg.rest.length === 0) ch = 'c';
      else if (idxOf(sg.rest, '|id:' + machineStr) !== 0) ch = 'L';
      else if (dup) ch = 'L';
      else ch = '+';
      t.machineChar = ch;
      if (ch !== 'L') { t.reason = `machineChar=${ch} → grade 0 (0x10cb728)`; break; }
      // 機能日付レコード (0x10cb741-0x10cb98a)
      const r = tierGrade(sg.rest, tier.first, today);
      grade = r.grade; t.reason = r.reason; t.date8 = r.date8;
    } while (false);
    t.grade = grade;
    out.perTier.push(t);
    // 第一次ティアの反映 (0x10cbb00-0x10cbb28)
    if (grade === 2) {
      out.gradeChar = 0x41 + i;
      flag.value &= 0xfd;
      flag.value &= 0xfb;
    }
    // 第二次ティア (0x10cbb28-0x10cd105): first の grade != 2 のときのみ評価
    if (grade !== 2 && tier.second !== 0x7fffffff) {
      const r2 = has ? tierGrade(sg.rest, tier.second, today) : { grade: 0 };
      t.secondGrade = r2.grade;
      if (r2.grade === 2) { flag.value |= 2; out.gradeChar = 0x41 + i; }
      if (r2.grade === 1 || r2.grade === 2) flag.value |= 4;   // mask 6 (0x10d0be0)
    }
  }

  // 残日数 (FUN_010c7850 → 0x15e14a8): 入力に Fire モード日付がない場合は
  // local_40 == 0 → 0x7fffffff (無期限)。grade 0x3f 降格条件 (days<=7 && days<=0) 不成立。
  out.daysRemaining = 0x7fffffff;

  // bit0 (0x10cf4e6): Pos("Please remember to register", ログ文字列) > 0 で |1。
  // ログ文字列は関数内で常に空 (0x10c8192 初期化後の書込なし。読出は 0x10cf4d0 のみ)
  // → このビルドでは bit0 が立つ経路は静的に存在しない。
  out.bit0WriterReachable = false;

  // ボタン/表示 (0x10cf531-0x10cf58f)
  if (out.gradeChar < 0x41) {
    out.buttonId = 3; out.button = 'Update registration';
  } else if (out.gradeChar < 0x44) {
    out.buttonId = 1; out.button = 'Upgrade registration';
  } else {
    out.buttonId = 2; out.button = 'Registration details';
  }
  out.registeredDisplay = out.gradeChar > 0x40; // FUN_010c7530: 0x40 < grade で表示
  return out;
}
