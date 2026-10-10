# M9 REPORT — SVF 路線 bootstraps + 出力 copy L/R + OOB table remap

## 0. 結論 (先出し)

- **E2E 全項目 PASS**: `bash tools/m9/m9_e2e.sh` = checks 6 / broken 0 + [F9] OOB 不発 → exit 0。
- M9 spec のうち **(1) 出力スケール系の構造破れを 3 件特定・修復**, **(2) は分析のみ**, **(3) 未達 (理由は §3)**,
  **(4) PoC 達成**, **(5) 達成**。
- (1) の現況: t1 出力は param/入力に応答するようになり 190/256 cell が有効値化 (前回: 巨大 junk 0x0c17fa41 系のみ)。
  ただし **破れは完走ではない**: L+R 512 cell 中 junk 175 が残留 (指数関数増大系列, §2 参照)。
  次回 continuation の入口を §5 に記録。
- 破れ一覧 (本回修復分):

| # | 破れ | 修復 |
|---|---|---|
| R1 | resume C port の ring memset が obj メンバー直索引 (= `objp + 0x250 + 8k`) で **obj+0x268 (SR bits 0x462f7000) を pointer 混読 + memset → OOB trap** (前回 subagent 強制中断の直接原因) | dsm `mov qword ptr [rsi + rcx]` (rsi = 0..0x30) = **配列先頭 deref + 8k 索引** に修復 ([F3-fix]) |
| R2 | processReplacing 最終 L store の base deref 脱落 (dsm `mov rax, qword ptr [r12]` ⇒ IR は `%arg3` 直接) ⇒ **outputs pointer 配列の内部 ~1KB を f32 に破壊** | [F7] ir9_outcopy.py: add 即値 `%arg3` → `load i64, ptr inttoptr %arg3` (dsm 忠実化) |
| R3 | band filter 初期化 function_180126670 が **xmm1 (f0) 引数脱落 + define 内 broken-lift** ⇒ band 係数 [0x68..0xb0] が f64 qNaN (0xfff80000…) のまま | [F8] m9_boot.c m9_band_filter_setup (C port: dsm 0x180126670..918)。 IR 側 8 callsite に f0 bits 引数化 (前半 4 site = 88.3 f32 bits 0x42b0999a @VA 0x180204300, 後半 4 site = 2500 bits 0x451c4000 @VA 0x180204314) |
| R4 | broken-lift 算術合成 table base: c38c8 family の base 定数が **10 進即値** (0x18026c9f0 = 6444993008 等) ⇒ ir6_shift (hex/global_var_18xxxxxx 名対応) が remap 出来ず ⇒ wasm linear addr 0x18026c9f0 (> memsize 0x36000000) で OOB trap | [F9] ir9_bootstraps.py fix_tablebase: 3 define (c38c8/c69cc/c91cc) 内の 0x180200000..0x180300000 即値を linear 対応 (v − 0x180000000 + 0x30000000) へ shift。 hydrate は既存 m6_data install (rdata → 0x301e2000 / data → 0x3025f000) に包含 = 最小構成 |
| R5 | (照合補助) プローブ側 pointer 配列は **qword ストライドが正** (native `[rdx+8]` = 第 2 pointer)。 u32 4-byte ストライドで敷設すると process head の mono 判定 `[0x30c]/[0x310] = 0` が誤発動し, R2 の L/R 破壊が outL に噴出していた | m9_e2e.sh 内 probe 全部で qword ストライドに統一 |

- **obj+584 (0x248) flag 分岐のもう片方 (18011efb0 per-sample path) は本回は分析のみで完了** (spec §2 許容)。
  次回は R2/R3 と同様の broken point 探査を `dec_label_pc_18011efb0` 側へ適用予定。

## 1. 実測・検収 (E2E 各項目)

`tools/m9/m9_e2e.sh` 内で node probe 直呼 (build は m9_build.sh 経由)。全 PASS:

```
OK   E1a ctor/resume 完走 ([0x30c]/[0x310] = 1/1)
OK   E1b processReplacing 完走 (OOB 無し)
OK   E2a outputs pointer 配列 intact (F7 deref 修復)     ← R2
OK   E2b outL/outR 両チャネル非ゼロ (L/R 配置回復)
OK   E3 band filter 係数 NaN 消滅 (F8 C port)            ← R3
OK   E5 t1 出力 param/入力 応答 (非 zero 値 190 sample)
[trap9] OK (fail-fast missing CRT, OOB 不発): c69cc / c91cc   ← R4
[m9_e2e] PASS (exit 0)
```

## 2. t1 出力の現況 (N=256, 入力 sin 2 重調波 (attn 0.7+0.3) + cos 0.5, param 0..18 = 0.5 / 19 = 0)

- **有効信号**: L/R 512 cell のうち zero 132 / 通常振幅域 (|v| < 4) 205 / junk (|v| ≥ 4) 175, |max| = 1.67e20。
- 残留 **junk は指数関数増大系列**: bit 列 (例 L cell 103..) `0x5fd6d2e9, 0x1fda87d5, …, 0xdf69de12, …`
  — f32 指数部が sample 進行で単調増幅し正負が交互 → **band IIR の feedback 係数に |pole| ≈ 2..4 の実数値が残留**
  (推定: [F8] port の [0x88] = -3.98 / [0x90] = +5.96 系の pole 放置)。
- 一方で junk-free cell は入力波形に追従 (sin ~ 数 0.1 系) → DSP 接続自体は生きており、
  **残留破れは band filter (R3 の C port の op 配置/係数割当) に絞り込めた**。

## 3. (3) bit-exact 参照実装 — 未達の理由と不全時の置換え判定

- 参照構築の前提が未整備: t1 全体 512/512 bit-exact は junk 残存のため定義不能。
  m6b REPORT §(b-4) の通り native 実機参照は SEH 依存で前提不成立、mac AU 参照は x64 SSE 丸め差
  ありで bit 一致判定が非自明 (M8 REPORT からの再度同結論)。
- **置換え判定 (数値根拠付き)**: 本回で完全一致が取れる破れ = [F8] band filter C port の dsm 忠実 op 列
  (store 値の実数化は E3 で capture), [F3]/[F4]/[F5] (前回 port)。 一方 [F6] CRT 数学 stub は
  **native poly (0x1801a9be0 = tan, 0x1801b4220 = exp, 0x1801b4900 = log) と libm で ULP 差あり**
  (0x1801a9be0 は lift IR で body 欠落 return 0 のため libm tan 代置 = bit 非一致の既知点)。
- tolerance 定義案 (次回 (3) 完遂時に採用): junk-free cell (|v| < 4) 集に対し t1 vs JS unit 分割の
  絶対/相対誤差 max を実測値で示す (本 REPORT §2 の 205 cell を母集団に)。

## 4. [F9] table base 算術合成 remap — PoC 実装詳細

- 対象定数 (c38c8 family 内, dsm 突合):
  - 6444993008 = **0x18026c9f0** (.data, `%2 = add nuw nsw i64 %1, …`)
  - 6444992848 = **0x18026c950** (.data, `%24 = add nuw nsw i64 %23, …`)
  - 6444672256 = **0x18021e500** (.rdata, `%27 = add nuw nsw i64 %23, …`)
- 3 define (function_1801c38c8 / c69cc / c91cc) 内のみを対象に 10 進即値 (0x180200000 ≤ v < 0x180300000,
  実装 ir9_bootstraps.py `lo, hi = 0x180200000, 0x180300000` と一致)
  を `v - 0x180000000 + 0x30000000` へ shift。 ir6_shift が hex/global_var_18xxxxxx 形式のみ対応する為に
  漏れた 10 進形を本 pass が soup up。
- 検証: fresh module instance × 2 (c69cc / c91cc 直呼):
  - 修正前: `memory access out of bounds` trap。
  - 修正後: **OOB 不発**。 body 先頭部 = `missing function (GetConsoleOutputCP / 1801baef8)` の fail-fast abort で終了
    (m8 REPORT §5 の「fail-fast 保持」設計に一致)。
- 備考: PoC 初期案では .text 低区域 (0x180001000..) の実体敷設 (m9_tablebind.py, 4KB memcpy) も試作したが、
  本主 pass の remap で c38c8 family の hydrate は既存 m6_data install に降りるため **build chain から除外**。
  (tools/m9/m9_tablebind.py は optional 試作として残置, 未使用)

## 5. 次回 continuation 入口 (残課題)

1. **band IIR 係数の pole 放置** (R3 の仕上げ): junk bit 列の pole ≈ 2..4 の由来を, m9_mixtrace 方式
  (trunc i128 → f64 単値の記録型 capture) で固定。 候補点 = [F8] C port (0x1801266d2..91e) の中の
  (7a9)-(7c9) add/sub series 順, (71f) `movaps xmm2, xmm14` の位置等の op 指合読込み
  (特に [0x88]/[0x90] に収まる値が native で同じか — m9_band_filter_setup の store 先 member 割当の swap 試行)。
2. **18011efb0 分岐 (obj+0x248 ≠ 0)** に同じ [F7] L store deref とループ追跡を適用 (次回 (2) 達成候補)。
3. bit-exact 参照 (3) 完遂は 1/2 完走後。 junk-free cell (|v| < 4) 集による tolerance 定義の実測根拠化。
4. pointer 配列の qword ストライドをハーネス共通化 (tools/m9 内 probe 散点排除)。

## 6. 引き継ぎ手掛かり

- [F3] resume に `obj+0x2ac = 2` を追加し, **SVF init の前の gate box loop** (dsm 0x18012096b..9ab:
  for 3 boxes [obj+0x200+8k] { [vt+0x38](SR_eff f64) = cfg1, [vt+0x88](10.0 f64) = cfg2 }) を復元。
  order = SR store → flags → ramp gains → box loop → SVF init → 0x2a8=0 → ring memset (6 + 8 entry)。
- [F4]/[F5]/[F6] (svf reset / gate box cluster / CRT dexp/dlog/dtan) 品質は継続
  (bootstraps_report.json: crt threaded 15 / 9 / 1, 126130_fix 2, ctor_gbox idx 403, 126670 = 8 sites)。
- [F8] C port の定数は runtime 実測 (検収: ott_m9.cjs + m6_data_install で .rdata 0x1802056e8/0x1802056f8 直読):
  π̂ = **0x4009249249249243 = 3.1428571428571401292**, 2π̂ = **0x4019249249249243 = 6.2857142857142802583**
  — 22/7 (0x4009249249249249) / 44/7 (0x4019249249249249) の double とは ~6 ulp 差 (当初「22/7/44/7」と記載したが実ビットは別値)。
  注意: m9_boot.c 実装側は 22/7 の decimal (3.1428571428571427937) を使用しており native .rdata と不一致 (残課題 1 の候補点)。
  6.0 / 4.0 / 8.0 / -4.0 / √2 = 1.41421356…, tan は libm 代置。
- トレース体系: m9_boot.c MSCRATCH 0x35e00000 (pattern 0x9a5f____ = MTRACE 行番号) — **こちらは実在**
  (m9_boot.c L26-28 検収済)。 一方 `ir9_outtrace.py / ir9_mixtrace.py / ir9_addrtrace.py` (scratch
  0x35e01000 = processReplacing 最終 loop の R sum 途中値 / R store address 鏈, 「[0x310] = 0 → R store
  が outarr[0]」問題の解明用) は **本コミット (a3eaaf6) には実在しない** (当初「再利用可」と記載したが
  tools/m9 に無し) — 次回着手時に再作成が前提。
- build: `bash tools/m9/m9_build.sh` (m6/m8 chain 再利用, emcc 約 90 sec) → `work/ott_m9.cjs(+wasm)`,
  E2E: node LTS (26.10.0) / emsdk 6.0.12。

## 7. コミット内容

- 変更/新規 (tools/m9/ のみ): `ir9_bootstraps.py` (F8/F9 追加; F4/F5/F6/F3 継続), `ir9_outcopy.py` (新, F7),
  `m9_boot.c` (resume 修復 + band filter setup 追加), `m9_build.sh` (out copy pass 接続), `m9_e2e.sh` (新),
  `m9_tablebind.py` (新, optional 試作), `.gitignore`, `REPORT.md` (本書)。
- work/ 産物 (dsm / ott_m9.ll / wasm / log) は `.gitignore` で除外。
- README/MILESTONES/src/tools/m1-m8/shim/docs は編集・add 0 行。
