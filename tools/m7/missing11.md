# tools/m7/missing11.md — undefined symbol 57 種のうち runtime 到達 missing 11 の分類表

- 作成: 2026-10-10 (M7 準備 subagent)。HEAD=188479b 時点、M6b 検収値 (wasm-ld undefined
  symbol 57 種 = 整数 33 種 + Win/CRT API 24 種 / `__asm_*` 0 種) を前提にする。
- 一次資料: `tools/m6/work/m6_stubs.c` (fail-fast stub 定義一覧),
  `tools/m6/work/full_t1.drc.dsm` (対象関数の機械語実体),
  `tools/m6/work/ott_lift.ll` (closure lift IR の declare signature / 呼出 site),
  `node trap_test.mjs` の実測 FAIL 一覧 (missing 11 = "*missing function*" abort 11 件
  + broken-lift OOB 2 件を除く)。
- 目的: **FLEEngine 部分 wasm 起動 (M7/M8 本スコープ) に向けて、closure 外依存
  (CRT/Win API) の shim 不足面を事前計画する文書** (主実装はしない)。

## 実測 (trap_test で missing fail-fast に到達する 11)

| # | 関数 (期待 signature: closure IR declare) | 実態 (dsm 解読) | (b) 到達経路 (closure 内 caller → 起動経路推定) | (c) 対応方針 |
|---|---|---|---|---|
| 1 | `function_1801bfab4` `(i64)` | thunk: `lea edx,[2]; r8=0; jmp 1801bf938` (UCRT app-policy 系: GetModuleHandleW + PE header パースで managed app 判定) | caller `function_1801be5a8` / `function_1801cc3fc` (CRT 初期化/lock 面の遠巻き) — t1 の ctor/process 経路では到達せず probe 直呼の み | 新 shim 不要 (Win API GetModuleHandleW 依存は深い)。DSP 数値経路外 → fail-fast 維持 or 参照値 0 返し stub 評価 (m6_rt.c 追補) |
| 2 | `function_1801c0ac8` `(i64, ptr, i64)` | **純計算 leaf**: u16 比較 wmemcmp/wcsncmp 相当 (n まで word 每, ret = 差) | caller `function_1801c38c8` (= broken-lift OOB family, M6 REPORT §7-6 同型) — probe で到達 | **hand C stub で足りる** (m6_rt.c 追補; 純計算なの で bit-exact 検証可能。ただし caller 側 broken-lift 対策待ち) |
| 3 | `function_1801c1438` `(i64, i64)` | thunk: `r8d=0x20; lea rdx=const 文字列; jmp 1801c12f4` (UCRT `_invalid_parameter` 報告系) | caller `function_1801a9be0` (数学関数の domain 報告区段; memfix で sqrt 報告 call は削除済のため DSP 経路不到達) | **no-op stub (OK 化)** — M6 実績の RaiseException no-op (m6_stubs.c) と同型 |
| 4 | `function_1801c17e0` `(i64)` | **純計算 leaf**: `rcx |= 0x0008_0000_0000_0000` (double の quiet/NAN bit 付与) → ret xmm0 | caller `function_1801a9a6c` (sqrt 報告; memfix 削除済, t1 不到達) | **hand C stub (OK 化)** — 8B leaf。m6_full_extract.py の full-lift 抽出フローも同様に適用可能 |
| 5 | `function_1801c17fc` `(i64, i32)` | **純計算 leaf**: `ecx |= 0x400000` (f32 quiet bit22 付与) → ret xmm0 | callers `function_1801a9b38` (sqrtf 報告, memfix 済) / `function_1801c1934` | **hand C stub (OK 化)** — 同上 |
| 6 | `function_1801c24d0` `(ptr, i64, i64)` | thunk: `xor r9d; jmp 1801c2350` (大 body: onexit/atexit lock 管理) | caller `function_1801c91cc` (= broken-lift OOB probe の 1) | **既存の方針で足りる**: caller 自体 broken-lift (§7-6)。本体は lock 管理 — 1801be668 hand stub (CRT lock no-op) と同型の m6_rt.c 追補で回収可 |
| 7 | `function_1801c33e0` `()` | **純計算 leaf**: heap 状態 (global+1 比較) 判定 ret | caller `function_1801acbf0` | **hand C stub (OK 化)** — 値 1/0 固定の no-op |
| 8 | `function_1801c6744` `(i64, i32, i64, i64)` | CP 範囲 filter → `jmp qword […]</MultiByteToWideChar>` (Win API import 直 thunk) | caller `function_1801c65b4` (locale / wide 変換 path; 字列処理系, DSP 経路外) | **新 shim 必要 (Win API 面)** — M4 shim に file に相当面なし。 no-op (0) 返しで OK 意味運用; 実値が要る場面 (FLEEngine の .flp 読込) で M4 外挿の変換層 (JS 側 UTF-16) を接続 |
| 9 | `function_1801c67a0` `(i64)` | **純**: `lock inc` 連鎖 (module record refcount addref + 文字列 tag 比較) | callers `function_1801c1ea0` / `function_1801c6b44` (OK 系 probe 同族: module ref 管理) | **hand C stub (OK 化)** — wsmem 上での inc はそのまま写像可 / no-op (lock のみ) でも可 |
| 10 | `function_1801c6a04` `(i64, i64, i64)` | **純**: `lock xadd dword ptr [rcx+0x15c]` (refcount dec) | caller `function_1801c6a2c` (OK 実測の refcount 管理区段 — probe では本関数が fail-fast 側) | **hand C stub (OK 化)** — 引数原点の lock 演算のみ |
| 11 | `function_1801c721c` `(i64, ptr)` | CRT lock (`function_1801be668` hand-stub 同族) + console/locale 状態 release | caller `function_1801c7334` | **hand C stub (OK 化)** — be668/be6bc hand stub (m6_rt.c 既存) 同型の lock no-op |

補足 (preload 側の未到達面): probe で **FAIL しないが未 export の残 5 種**
(`function_1801c144c / 1801cb82c / 1801cba40 / 1801cbb28 / 1801ce3f0`) は
`m6_stubs.c` 上に fail-fast stub 定義済みだが export 未付与 (trap_test は skip 計上)。
DSP 経路外と同様に扱い、M8 で export 面確認が要る。

## FLEEngine 部分 wasm 起動への示唆 (M7/M8 事前計画)

1. **missing 11 は すべて DSP 数値経路外** (CRT lock / UCRT app-policy / locale・
   wide 変換 / refcount 管理)。OTT closure の起動経路 (ctor → setParameter →
   resume → processReplacing) では 1 個も runtime 到達しない (trap_test の probe
   直呼のみ到達) — t1 run-complete の構造的根拠。
2. FLEEngine (Delphi) では **Delphi RTL 初期化 (System.pas 連鎖) が ucrt 初期化
   面に乗る**ため、上記 lock/app-policy/refcount 群は起動直後に到達し得る:
   - CRT lock 群 (1/6/11 + be668/be6bc) = **m6_rt.c hand stub 規模**で回収可
     (M6 実績の lock no-op パターン踏襲)。
   - UCRT app-policy (`function_1801bfab4`) = GetModuleHandleW + PE パース依存
     — wasm 単体では義理 shim 不可、**参照値 0 返し stub** (managed app 判定
     false 相当) を使うのが現実解。
   - wide 変換 (8) は M4 file API 外挿で変換層を JS 側に置く後追い (本数値経路
     では不要)。
3. 純計算 leaf (2/4/5/7/9/10) は **bit-exact 検証可能な hand C stub** 化が可能で、
   m6_rt.c への追補と ir7_argpass (tools/m7/) と同様の「dsm 実体↔C 署名一致」
   検収フローがそのまま使える。
4. 対応に要る新規実装量の推定: hand C stub 7 種 (#2/4/5/7/9/10/11 — うち純計算 leaf
   4 種 #2/4/5/7 は bit-exact 検証可能) + no-op (raise 同型) 1 種 (#3) +
   Win API thunk no-op 2 種 (#1/8) = 新規 10 種 + 既存方針 1 種 (#6, caller
   broken-lift OOB 待ち) = 全 11 種 — M6b の stub 規模 (~60 stub) からは小,
   M8 の bit-exact 評価前に 1 作業単位として処理可 (buyer stub for OK 運用)。
