# tools/plugins/p0c REPORT — kernel 表妥当性検証 + f80 assessment (CAB-196)

> 正本: `tools/plugins/p0c/REPORT.md`。
> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

作成: 2026-10-10 / HEAD = 1c4b7c7 時点 / 担当 dir: tools/plugins/p0c のみ

## 0. 結論 (先出し)

1. **kernel 表は妥当**。`inventory/kernel_table.py` の復元値 (init 0x5e19f0, **45 変数 / 80 実装 / 10,886 B**, 35 変数は 2 実装選択・10 変数は 1 実装, x87 機械語 28/80) を全 Delphi DLL で再検証した結果、**130/130 DLL で 80/80 kernel が正規化ハッシュ一致** (`p0c/verify_table.py`)。kernel_matrix.py が報告していた「DLL 毎に 1 件 hash mismatch (79/80)」は **capstone 5.0.7 の disp_size 誤報告による測定 artifact** で、実差異は 0 (§2.3)。
2. **soft-float80 は不要**。f80→f64 lowering の bit 差分を実測した結果 (§3): f32 入出力系 **21/28 kernel は実測 0 差分** (2M case, 構造的にも exact: f32×f32 の正確積は 48 bit ≤ f64 の 53 bit)。f64 出力系は **±1 destination-ulp が 0.018%** (2,000,000 中 357) — これを許容条件として明記すれば足りる。i64 経由の 2 kernel (0x5e0330 / 0x5de3e0) だけは f64 経由だと **64% 不一致** → lowering pass を **i64 保持** (fild→i64, fistp(RC=nearest) は i64 恒等) にすれば bit-exact。超越関数 kernel (0x5dfae0, f2xm1/fscale) は f32 出力で実測 0/200,000。
3. **前回中断 run (insufficient_credits) の残骸は品質が十分なため引継ぎ採用** (§1)。kernel 実装の wasm 化 lift は本チケットの指示 (「表と判定まで」) により未実施。lift 産物 (work/k80.*, work/kall.*) は検証入力としてのみ使用。
4. 指示にあった「helper 9件・distinct 6名・Harmless i256 trap 6箇所」は残骸からは一意に同定できず (§2.6)。実測値と定義を REPORT に記録したので、指示側での定義確認を依頼する。

## 1. 残骸精査と引継ぎ判断

| ファイル (tools/plugins/p0c/) | 内容 | 判定 |
|---|---|---|
| kernel_matrix.py (20 KB) | 141 plugin × kernel 表の一致検証 + 呼出 site 引数抽出 (12 job 並列) | **採用** (動作確認済) |
| work/kernel_matrix.json ほか | 181 block 走査結果 (delphi 判定/init 探索/hash 一致/呼出 site) | **採用** (本検証の入力) |
| work/k80.* / kall.* (lift 一式, 52 MB, gitignore) | 80 kernel (+136 ranges) の RetDec lift → pass 鎖 → final.ll | 検証入力として採用。wasm 化は scope 外 |
| work/emcc_base.log (20 error) | f80 の wasm バックエンド失敗の再現 (ticket 記載「再現済み」の実体) | **採用** (記録) |
| lift_kall.log / work/lift_k80.log | lift 実行ログ (pass 鎖 / helper 計数) | 採用 (計数の一次資料) |
| REPORT.md | 無し | 本報告が初回 |

ワークツリー汚染は無し (p0c 追加のみ。`git status` の他 dir 変更は並行 agent のもの)。

## 2. kernel 表の妥当性検証 (実測)

### 2.1 復元 (決定的・再現済み)
`inventory/kernel_table.py` 再実行 → `{'init': '0x5e19f0', 'init_size': 1669, 'assignments': 80, 'variables': 45, 'implementations': 80, 'bytes': 10886, 'impl_per_var': {2: 35, 1: 10}, 'kernels_with_x87_asm': 28}` — ticket 記載の 45/80/10,886B と完全一致。lift 経緯 ranges (`lift/kernel_ranges_balance.txt`) も再生成で同一 (e2e が git diff で確認)。

### 2.2 全 DLL 伝播
181 block 走査 (kernel_matrix.py) の結果: Delphi (FP_DelphiPlug) 133 DLL 中 **130 で init 関数 (Balance 0x5e19f0 と正規化ハッシュ一致) を発見**、全て **nvars=45 / nimpls=80**。init 未発見は 3 DLL = Dashboard (21206) / Fruity Envelope Controller (23648) / Wave Traveller (24315) — batch_plan 記載の「別構成 3 本」と一致。plugin 単位では 141 本中 Delphi 132 種、init 確認 126 種 (Patcher / Fruity Wrapper は 2 DLL 構成)。

### 2.3 capstone quirk の特定と 80/80 再検証
- 症状: 129/130 DLL が「79/80 一致 + 1 mismatch」。mismatch VA は各 DLL の 0x5e03f0 対応物。
- 原因: `norm_hash` が capstone の `disp_size` を信用して disp32 をゼロ化するが、**capstone 5.0.7 は 66-prefix SSE の RIP 相対 (movupd/addpd 等) で disp_size=2 を誤報告**する (実測: `movupd xmm7,[rip+disp32]` → disp_size=2, 実エンコーディングは 4B)。よって movupd の disp32 が正規化されず、DLL 間の VA 差がハッシュ差に化ける。
- 検証: `verify_table.py` は「RIP 相対の disp32 は命令末尾 (imm 直前) 4B」というエンコーディング事実から位置を決める修正版正規化で全実装 VA を再ハッシュ → **130/130 DLL で 80/80 一致** (`work/table_verify.json`)。
- 0x5e03f0 の per-DLL variant は機械語が同一 (差分は rip disp32 のみ) で、参照先定数も同一 (f64 **0.5** = 0x3FE0000000000000, Balance 0x6FFFB0 と 18914 0x6ECDD0 の先頭 8B が一致 — 検収で再確認)。

### 2.4 表の構造 (実測)
- **80 実装 → 73 distinct** (正規化ハッシュ; 7 件 + 2 件の完全重複 group)。全 DLL の kernel_va_map が `{x:2, y:7}` の dup を示すのはこの重複に起因する (測定 artifact ではなく実データの重複)。
- 呼出 site (plugin 固有部の Eff_Render 候補から静的走査): 総数 **3,763 site / 130 DLL** (DLL 当たり 22〜62)。使用 kernel **45 実装 / 38 distinct-group、不使用 35 実装** (0x5e03f0 は使用される → 旧集計の「不使用」も正規化漏れだった)。
- 呼出 interface (work/kernel_args_raw.json): 80 kernel の引数設定源 (gpr/xmm/stack) を抽出済み。float 引数 (xmm2/xmm3) を持つのは 9 kernel、stack 引数 9 kernel — **ARG pass (ticket 項目 3) が必要な面**。

### 2.5 IR 側の f80 実態
- `work/k80.lift.ll` (80 kernel の RetDec lift): **26 関数に x86_fp80**。うち 25 は機械語 x87 28 本と重複、残り 1 (0x5e1870) は機械語が SSE のみ (cvtss2sd 等を RetDec が x87 レジスタで模型化した artifact)。
- 機械語 x87 28 本のうち IR で f80 が消えた 3 本 (0x5df210 / 0x5df240 / 0x5e0330) は RetDec が既に他形式へ落としている。
- ticket 記載「25/80 の IR に x86_fp80」は k80 lift の計数としては 26 (内訳上 25+1) — 微差は 0x5e1870 の数え方による。

### 2.6 「helper 9件・distinct 6名・Harmless i256 trap 6箇所」の対応候補 (実測)
| 実測量 | 値 |
|---|---|
| SIMD helper (`__asm_*`, k80 lift / m11_simd2) | declares 48 / 実装 48 / 未実装 0 / **i256 trap 0** |
| 同 (kall lift = 136 ranges に init/mix/peak 等含む) | declares 65 / 実装 61 / 未実装 0 / **i256 trap 4 種** (vmovups, vmovups__2, vmovaps, vmovntps) |
| f80 kernel のみが使う helper | 4 種 (`__asm_fnclex`, `__asm_movd`, `__asm_movq`, `__asm_ucomiss__15`) |
| f80 kernel 20 種が使う helper 総数 / 非f80 kernel 43 種 | 20 / 43 |
| machine level の kernel 外 helper 呼出 target | 7 種 (0x408810, 0x409d00, 0x409df0, 0x40d840, 0x43c5e0, 0x5d10b0, 0x5de330=kernel 内部) |
| distinct kernel group | 73 (80 実装中) |
| i256 呼出 site (kall.final.ll) | function_4076b0 (framework 関数) 32 line / **function_5e1870 (kernel) 4 line** |
| Harmless 根拠 | 0x5e1870 の実機械語は SSE のみ (AVX 命令無し) → IR の i256 経路は実在しない = trap しても到達しない **無害** |

9/6/6 にそのまま一致する測定量は見付からなかった (f80 kernel の xmm 引数 9 件・stack 引数 9 件という数字は存在する)。**定義の確認を依頼** (§7)。

## 3. f80 assessment — soft-float80 要否判定 (実測)

### 3.1 方法
`p0c/f80_micro.c`: 同一演算列を (A) `long double` = x87 80bit (Linux x86-64 gcc は x87 命令を生成, PC=64bit) と (B) `double` = f80→f64 lowering 後の形 (`-ffp-contract=off`) で実行し bit 比較。**先に実機械語 kernel 4 本 (0x5df210 / 0x5e0330 / 0x5de820 / 0x5de390) を PE を VA 0x400000 に MAP_FIXED 敷設して直接実行し、(A) が bit-exact (全差分 0) であることを検証** → ハーネスの妥当性を確定してから (B) 差分を測定。入力は全ビットランダム f32/f64 + 指数集中 + 日常値 + NaN。

### 3.2 実測 (N=2,000,000, `p0c_e2e.sh` で再現)
| pattern | ncases | bit-diff | diff% | max ulp(出力精度) |
|---|---:|---:|---:|---:|
| P1 f32 mul → f32 | 2,000,000 | **0** | 0 | 0 |
| P2 f32 add → f32 | 2,000,000 | **0** | 0 | 0 |
| P3 f32 mul+add → f32 (0x5de820 形, stereo) | 2,000,000 | **1** | 0.0001 | 1 |
| P4 f64 mul → f64 (f64 全エントロピー) | 2,000,000 | **357** | 0.0179 | 1 |
| P5 i64 → f80/f64 → i64 (2^53 超混在) | 4,000,000 | 2,408,182 | 60.2 | 1 |
| P6 f32→i32 fistp RC=chop vs trunc cast | 1,000,000 | **0** | 0 | 0 |
| P7 pow 列 f2xm1/fscale (T∈[-20,20]) → f32 | 200,000 | **0** | 0 | 0 |
| P8 f64 ノイズゲート (unordered 含む) → f64 | 100,000 | **0** | 0 | 0 |
| K0x5df210 実機械語 vs A(long double) | 300,000 | **0** | 0 | — |
| K0x5df210 実機械語 vs B(f64) | 300,000 | **0** | 0 | — |
| K0x5e0330 実機械語 vs A / vs B | 600,000 | 0 / **385,088** | 0 / 64.2 | — / 1 |
| K0x5de820 実機械語 vs A / vs B | 600,000 | **0 / 0** | 0 | — |
| K0x5de390 実機械語 vs A / vs B | 300,000 | **0 / 0** | 0 | — |

NaN は別計数 (x87 real-indefinite と C の NaN 伝播でビットパターンが違うだけ; 全 case の約 0.4%)。

### 3.3 kernel 分類 (f80_assess.py, 機械語 28 本, 複数ラベル)
f32chain **21** / cmpsel 14 / int32x87 8 / f64mem 6 / int64x87 **2** (0x5de3e0, 0x5e0330) / rc_chop 3 (0x5dfbe0, 0x5dfc90, 0x5dfdb0 — fldcw 0x0F3F=RC:chop → 0x033F=RC:nearest 復帰) / transc **1** (0x5dfae0)。

### 3.4 判定
| class | kernel 数 | f64 lowering の結果 | soft-float80 |
|---|---:|---|---|
| f32chain (+cmpsel) | 21 | **bit-exact** (実測 0; 構造的根拠: 24+24=48bit の正確積/和が f64 53bit に収まる。f64 経由の 2 段丸めが f32 格納で顕在化しない) | **不要** |
| f64mem (f64 出力) | 4 (0x5de390/410/4b0/540) | ±1 destination-ulp が 0.018% (P4)。80→64bit 仮数丸めの 2 段丸め差分 | **不要** (許容条件: ±1 ulp, 実測率 0.018%) |
| int32x87 | 8 | **bit-exact** (i32 は f64 に正確; fistp RC=nearest は恒等, RC=chop は trunc cast と一致 = P6 実測 0) | **不要** |
| int64x87 | 2 | f64 経由は **64% 不一致** (|v|>2^53 で f64 丸めが発生) | **不要 — ただし lowering pass を i64 保持に**: fild qword→i64 sext (正確), fistp(RC=nearest)←i64 は恒等。f80 を介さない | 
| transc (0x5dfae0) | 1 | f32 出力で実測 0/200k (T∈[-20,20])。f64 段差は 2^-53 級で f32 格納 (2^-24 粒度) に吸収 | **不要** (bit-exact 100% を厳守する場合のみ Intel x87 アルゴリズム再実装 = 将来オプション) |
| rc_chop | 3 | bit-exact (P6) | **不要** |

**結論: soft-float80 (80bit ソフトエミュ) は全 kernel で不要。** 必要な lowering pass 設計は (1) x86_fp80→f64 型置換 (fpext/fptrunc は実質 no-op 化)、(2) fild/fistp qword は i64 保持 (f80 を経由させない)、(3) fldcw 区間の fist/fistp は trunc 系 cast へ、(4) NaN は real-indefinite (0xFFC00000 系) に正規化 (bit 一致率を上げる化粧; 音響的影響なし)。

## 4. ticket 出口条件との対応
- ticket「80 kernel 全て native 機械語と bit-exact (不可能な kernel は許容条件を記録)」: 本委任は「表と判定まで」のため lift+差分試験は未実施。**判定結果に基づく許容条件案**: f64 出力系 4 kernel は ±1 destination-ulp かつ実測率 0.018% 以下、i64 系 2 kernel は i64 保持 lowering で bit-exact、他 74 kernel は bit-exact 見込み (実測 0)。差分試験 (ARG pass 適用後) は ticket の次工程。
- emcc f80 失敗の再現 log (work/emcc_base.log, 20 error: fp_extend / fp_round / fadd/fsub/fmul / setult) — lowering pass 適用対象の op 種は **6 種**に集約される。

## 5. 未解決・リスク
- **RetDec 非決定性**: 同一関数 (0x5e1870) が k80 lift と kall lift で異なる IR (i256 有無, fp80 配置) を生成。kernel lift を本格化する際は lift 実績との差分 fixup (tools/m7/m6_e2e.sh の教訓) が必要。
- capstone disp_size quirk は本検証以外 (fw_overlap.py, family_table.py 等の正規化ハッシュ系) にも潜在し得る — 66-prefix RIP 相対を使う関数の cross-DLL 照合で同種の偽 mismatch が起こる。
- 別構成 3 DLL (Dashboard / Envelope Controller / Wave Traveller) は今回対象外 (init 関数自体が非一致)。

## 6. 再現手順
```sh
bash tools/plugins/p0c/p0c_e2e.sh      # 約 2 分 (work/ 付き初回は kernel_matrix 走査 + RetDec lift で +10〜20 分)
```
[1] kernel_table.py (表復元) → [3] verify_table.py (130 DLL×80 kernel 再検証) → [5] f80_assess.py (分類) → [6] f80_micro (実測)。コミット対象は p0c 直下の script 3 本 + e2e + REPORT (work/ は gitignore)。

## 7. ユーザ依頼事項 / 次タスク提案
- **用語定義の確認**: 指示の「helper 9件・distinct 6名・Harmless i256 trap 6箇所」に一致する測定量が残骸に無い (§2.6 の対応候補を提示)。出所 (前回 run の進捗メモ等) を頂けると REPORT を追記できる。
- 次タスク案 (CAB-196 ticket 本体の続き): (1) f80→f64 lowering pass の実装 (§3.4 の 4 点, i64 保持含む) + ARG pass (xmm3/stack, ir7/ir8 系) 再適用; (2) 55/80 f80 無し kernel から差分試験 (native_ref 汎用化 — kernel_args_raw.json の interface 抽出済み); (3) capstone disp_size quirk の共有 fix を inventory 正規化系へ反映。

## 8. P0c-2 追記 (CAB-241): f80→f64 lowering pass の実装と検証

作成: 2026-10-10 / 担当 dir: tools/plugins/p0c のみ (新規 5 ファイル、既存記述は本節のみ追記)

### 8.0 結論 (先出し)

1. **f80→f64 lowering pass を実装** (`f80_lower.py`): k80.lift.ll の x86_fp80 968 token → **0**、
   **llvm-as 通過・冪等 (2 回適用 byte 一致)・wasm32 バックエンド通過** (101,150 B; emcc_base.log の 20 error 全解消)。
2. **ARG pass 再適用** (`k80_argfix.py`): RetDec が落とす xmm 引数 46 site と spill 初期化落ち 27 件を
   機械語 ABI 走査 (`k80abi.py`) と突合して再接続。冪等。引数は**末尾追記** (m7 ir7 同規約)。
3. **差分試験ハーネス** (`k80_diff.py`, fork 隔離): 実機械語 vs lowering+ARG 適用 IR を同一入力で突合。
   **f32 mul 系 0x5df210/0x5df240 は出力バッファ bit-exact**、0x5e0760/0x5e0bb0/0x5e0b70/0x5e1590/
   0x5e1780 も bit-exact。i64 系: 0x5e0330 は IR が i64 完結で構造的 bit-exact、0x5de3e0 は
   `llvm.rint.f64` 挿入で RC=nearest を再現 (実機 native==rint **100%** / trunc 74.1% を実測。検収再現: rint 100% (0/200k)、trunc 一致率は入力分布依存 — 音響 k/1000 50.4% / f64 全エントロピー 98.7%)。
4. **既存 lift IR の x87 スタック模型欠陥を検出** (RetDec 起源・本 pass と独立): fld→演算→fstp 型
   (0x5de820/0x5dedf0/0x5dfb60/0x5dfd30 + rc_chop 3 本) で fstp 読出が st(1) になり (0x5de820 の出力が
   定数 c2 に化ける)、loop 末尾 TOP も +2 ずれる。§3 f80_micro (C model) では bit-exact だった面。
5. 既存 e2e は両方完走 (`p0c_e2e.sh` exit=0 / `p0c2_e2e.sh` exit=0)。

### 8.1 pass 仕様 (f80_lower.py — §3.4 の 4 点の実装)

| # | 変換 | k80 実測 |
|---|---|---|
| 1 | `x86_fp80`→`double` 型置換 (define/declare/alloca/load/store/算術/fcmp/select/call/frontend_reg 署名) — **f80 spill slot 排除はこの帰結** (alloca 3 件 16B→8B) | 968→0 |
| 2 | f80 定数 `0xK`→f64 bits (Fraction で正確な最近接丸め; bare 位置は `0xH` のみ) | 14 |
| 3 | `@llvm.*.f80`→`.f64` + 重複 declare 除去 | 13 |
| 4 | same-type 化した `fpext/fptrunc double→double` を RAUW 消去 (連鎖収束; f64→f80→f64 往復は -0.0/NaN 含め恒等) | 24 |
| 5 | `i3`→`i32` (wasm legalization; add の wrap は &7 で整合) | 813 |
| 6 | chop 区間外の `fptosi double→iN` に `llvm.rint.f64` 挿入 (`--chop-funcs` で rc_chop 3 本は trunc 保持)。冪等性は「%v が既に rint 結果なら挿入しない」 | 4 |
| 7 | `sitofp i64→double` 直後 `fptosi double→i64` (中間 def 無し) を恒等畳み込み = **i64 保持**。k80 は RetDec 既 i64 化のため適用例 0 (framework 向け) | 0 |

### 8.2 ARG pass 再適用 (k80_argfix.py)

A: movd-from-zero — `%Z = xor i128 0,0` が `__asm_movX*(i128 %Z)` 専用のとき機械語 xmm slot を
`i64 %in.xmmN.bits` 引数で追加し `zext(trunc)` に置換 (46 site / 26 kernel)。B1: orphan spill —
load のみの alloca に引数+entry store (1)。B2: reg2mem 初期化落ち — `%rcx.0.reg2mem` 等に
slot 名から引数追加 (26)。abi json は `k80abi.py` (read-before-write + copy 逆向き伝播)。

### 8.3 検証結果

**(a) pass 品質**: llvm-as OK / 冪等 OK (両 pass) / wasm32 compile OK。k80.final.ll・kall.final.ll
にも同一変換計数で適用可能。

**(b) 差分試験 (2000 case/kernel)**: bit-exact 7 (§8.0-3)。RetDec x87 模型欠陥による不一致 7
(§8.0-4)。SSE 系の差分は pass 非干渉 (f80 無し kernel は変換 0) で lift 品質由来。crash 4
(ABI 推定の harness 限界, fork 隔離)。Group B 12 kernel (Delphi RTL / x87 helper 外部呼出) は
数値差分対象外 — framework 統合時に翻訳単位ごと。

**(c) model level 回帰**: f80_micro を N=2,000,000 で再実行し §3.2 と同値 (P1/P2=0, P3=1/2M,
P4=±1ulp 0.018%, K5e0330 native vs LD=0) — lowering 設計前提は不変。

### 8.4 CAB-194 (framework lift) への統合手順

1. `fw_f80.py` を `f80_lower.py` に置換 (`--chop-funcs` に rc_chop 分類)。fadd 0.0 近似 (73 site) は
   RAUW 消去に、0xK 定数は正確な最近接丸めに改善。
2. 引数末尾追記: `%in.xmmN.bits` (i64) / `%in.xmmN` (float/double) を呼出側 (dispatch/ir8) で末尾追加。
   site 計数は `k80_argfix.py --report` を流用。ABI json は `k80abi.py` を PE 毎に実行。
3. wasm 化は triple/datalayout を wasm32 に置換してから emcc (p0c2_e2e.sh [5])。
4. x87 模型欠陥 (§8.0-4) は framework 側にも同型発生が見込まれる — liftdiff (CAB-121) への分類追加を推奨。

### 8.5 限界

- fstp dword の chop 区間内 f32 丸めは nearest のまま (tie ~2^-25/case、実測未観測)。
- fistp overflow→indefinite / NaN→real-indefinite 正規化 (§3.4 (4)) 未実装 — 極端値域で
  native=indefinite vs IR=0 の差分 (rc_chop 系で観測)。
- RetDec x87 スタック模型欠陥 (fstp off-by-one / TOP 破綻) は本 pass scope 外 — 7 kernel 不一致の原因。
- 差分試験の入力は音響レベル (f32 指数 2^-17..2^7)。ABI 推定はヒューリスティック (crash 4 kernel は fork 隔離)。

### 8.6 再現手順 / 次タスク提案

再現: `bash tools/plugins/p0c/p0c2_e2e.sh 2000` (約 3 分) / 既存 e2e 回帰: `p0c_e2e.sh`。

次タスク (下流チケット案):

1. **[P0c-3] RetDec x87 スタック模型修復 pass** — fstp off-by-one / TOP 更新の機械的修復
   (transform C)。0x5de820 系 7 kernel の bit-exact 化見込み (欠陥様式と実機正解は確定済み)。
2. **[P0c-4] ARG pass の ABI 推定強化** — mid-function push のある rsp 相対 frame と
   movd site↔xmm slot の機械語主導対話で crash 4 kernel を救済。
3. CAB-194 framework への f80_lower 適用 (§8.4) + frontend_reg C 実装の共有化。
4. liftdiff (CAB-121) への「x87 fstp off-by-one」欠陥分類追加。

## 9. P0c-3 追記 (CAB-251): RetDec x87 スタック模型修復 pass

作成: 2026-10-10 / 担当 dir: tools/plugins/p0c のみ / 新規: x87fix.py, p0c3_e2e.sh

### 9.0 結論 (先出し)

1. **x87 スタック模型修復 pass を実装** (`x87fix.py`): RetDec が生成する fpr[] 配列 +
   fpu_stat_TOP 変数模型の欠陥 (fstp 読出 off-by-one / fld 書込先ずれ / 演算 operand 絶対
   slot ずれ / loop 末尾 TOP 更新過大 / fisub 零化 / fxch 対象ずれ / 初期 TOP store 欠落) を
   IR のみから機械検出し、真の TOP シミュレーションで全 fpr アクセスの絶対 slot を再導出して
   書替える。**0x5de820 / 0x5dedf0 / 0x5dfb60 の 3 kernel が k80_diff.py で bit-exact** (buf_diff=0)。
2. **0x5dfbe0 / 0x5dfc90 / 0x5dfdb0 / 0x5dfd30 の構造も修復** (fist overflow→0x80000000 化、
   fstp f32 の chop 丸め、frac/index の構造) し、残差を桁で圧縮 (下表)。残差の原因は
   **x87 64-bit mantissa (ext) と double 53-bit の演算精度差** であり論理欠陥ではない (§9.4)。
3. **k80_diff.py の driver bug を修復**: ir 引数式が mslot index (4..7) を value slot として
   使い stack 引数が未初期化 vI[4..7] を渡していた (正は sidx 8..11)。これにより 0x5dfb60 の
   差分が消えた (P0c-2 の §8.0-4 での「b60 不一致」の実体はこの harness bug だった)。
4. p0c_e2e.sh / p0c2_e2e.sh exit 0 (回帰なし)、x87fix 冪等 (2 回適用 byte 一致)、
   llvm-as + wasm32 通過。`bash tools/plugins/p0c/p0c3_e2e.sh` で 1 コマンド再現。

### 9.1 x87 模型と欠陥の機構

RetDec 模型: `st(i) = fpr[(TOP+i)&7]`、fld=`store.fpr(TOP-1)`+`TOP:=TOP-1`、fstp/fist=`load.fpr(TOP)`(+pop)、entry TOP=0。
欠陥: 翻訳中の内部 TOP 追跡が loop 内で破綻し (D1) fstp 読出 st(1) 化、(D2) 第2 fld 書込先 +1、
(D3) 演算 operand 絶対 slot ずれ、(D4) loop 末尾 TOP 更新 +1/+2、(D5) fist 直後 fisub が
`fsub %X,%X`(=0)、(D6) fxch 対象ずれ、(D7) 初期 TOP store 欠落。0x5de820 では fstp が定数 c2 を読む。

### 9.2 修復規則 (x87fix.py — 機械検出+機械的書替え)

| # | 規則 | 欠陥 | 実装 |
|---|---|---|---|
| R1 | emission パターン (push/dup/binop dest-st0,st1+pop/memarith/fstp_mem/fist/fstpst0/fxch/fisub) を復元し真 TOP で全 index を `add i32 <block先頭TOP>, <真slot-先頭TOP>` 正準形へ再導出 | D1/D2/D3 | process_function |
| R2 | fpu_stat_TOP store を真 delta へ (平衡 loop = 0) | D4 | simulate |
| R3 | fisub 零化: `fsub %X,%X` → `fsub %X, sitofp(fptosi(%X))` (fpr/devirtualized 両方) | D5 | composite / fix_fsub_zero_global |
| R4 | 初期 TOP store 補完 | D7 | process_function |
| R5 | fst/fist/fstp st(0) の pop 有無は 2^k 組合せを試し back-edge TOP 平衡が一意な組合せのみ採用 (非平衡/複数解はスキップ) | D1 | simulate |
| R6 | chop 区間の fstp f32 store を RC=toward-zero 化 (nearest が真値を跨いだら nextafterf で 1 つ戻す。符号ゲート付) | fstp chop RC | fix_chop_f32 |
| R10 | fist/fistp overflow → 0x80000000: fptosi 入力を \|v\|≥2^31 で -2^31 へ clamp (poison 解消) | fist overflow | fix_fist_overflow |

パターン外は関数単位で未変更スキップ (安全側)。適用スコープは `--funcs` (+`--chop-f32-fns`)。

### 9.3 検証結果 (k80_diff.py, 2000 case/kernel, fork 隔離)

| kernel | 修復前 buf_diff | 修復後 | 判定 |
|---|---:|---:|---|
| 0x5de820 | 5,136,704 | **0** | bit-exact |
| 0x5dedf0 | 2,571,305 | **0** | bit-exact |
| 0x5dfb60 | 758,431 (harness bug) | **0** | bit-exact |
| 0x5dfbe0 | 790,341 | 288,922 | 構造修復 / 残差 §9.4 |
| 0x5dfc90 | 757,178 | 52,323 | 構造修復 / 残差 §9.4 |
| 0x5dfd30 | 2,552,059 (ret 1518) | 38,099 (ret 59) | 構造修復 / 残差 §9.4 |
| 0x5dfdb0 | 2,454,776 (ret 1712) | 841,305 (ret 79) | 構造修復 / 残差 §9.4 |

回帰: 既修復 0x5df210/0x5df240/0x5e0760/0x5e0b70/0x5e0bb0/0x5e1590/0x5e1780 (+0x5e0330/0x5de3e0)
すべて buf_diff=0 維持。f80_lower/argfix 冪等性・llvm-as・wasm32 (101,539 B) 通過。

### 9.4 残限界 (ext 精度 — 据置と [P0c-4] 引継)

修復後も be0/c90/d30/db0 に ±1-8 f32 ulp が残る (cell 比率 14%/2.5%/1.9%/41%)。
原因は論理ではなく **x87 64-bit mantissa (ext) と double 53-bit の演算精度差**:
(1) frac = p - trunc(p) の精度が \|p\| の整数部ビット数分圧縮される (p~1e9 で frac 粒度
1.2e-7、ext では 7.5e-12)。(2) interp/積鎖の各段の丸めが 53-bit。(3) harness の入力分布が
f6/f7 最大 2^116 級の極端スケールを含み、frac の微小差が f32 下位 bit に増幅する。
対処には x87 ext 演算の double-double/64-bit-grid エミュレーション (fma 鎖で各段の丸め剰余を
伝搬) が必要 — 試作 (fma 補正) は compiled-IR の FMA 収縮と干渉し悪化したため未採用。
f32 音響出力への影響は ±1ulp 時点で実質無視できるが、bit-exact 完走には上流の
f80_lower に ext-emulation mode を追加するのが正しい設計位置。

### 9.5 [P0c-4] への引き継ぎ

1. **ARG pass ABI 推定強化** (本チケット繰越): mid-function push のある rsp 相対 frame、
   movd site↔xmm slot 対話、crash 4 kernel (0x5de710/0x5df610/0x5e05b0/0x5e0d80, sig11) 救済。
2. **x87 ext-precision emulation** (§9.4): f80_lower の mode 追加 (frac/interp 鎖の
   double-double 化)。bit-exact 完走の前提。
3. liftdiff (CAB-121) への分類追加候補: 「x87 fstp/fld index ドリフト」「fisub 零化」
   「fpu_stat_TOP loop 更新過大」「fptosi poison (fist overflow)」。
4. harness 注意: k80_diff.py の stack 引数 value-slot 対応修正済み (§9.0-3) —
   P0c-2 時点の sweep 数値とは driver 分だけ非互換 (改善)。

## 10. P0c-4 追記 (CAB-196 継続): ext-emulation mode のバグ修正と 2 kernel bit-exact 化

作成: 2026-10-11 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD (WIP 評価前): `016f91c`
検証手順: `docs/WORKFLOW.md` §6 (旧 `preflight RULES_SHA` 証跡は廃止・`docs/DECISIONS.md` D6)

### 10.0 結論 (先出し)

1. **前回 WIP の `f80_lower.py --ext` に実アルゴリズム bug を 3 件発見・修正**
   (`drop_lines` が store 行を飲み込む / `startswith` のインデント見落とし /
   RE_EXT_RINT と RE_EXT_FPTOSI の二重出力)。修正後、**0x5dfbe0 と 0x5dfc90 の
   2 kernel が buf_diff=0 (bit-exact) を達成** (§10.2)。P0c-3 時点で未達だった
   4 kernel のうち 2 本。
2. **残り 2 kernel (0x5dfd30 / 0x5dfdb0) は x87fix 後ベースラインに戻らず未達**
   (§10.2)。**真因は dd (double-double) 演算系列そのもの**であり、fpr2 slot 運搬では
   ないことを負論対照で実証した (§10.3・10.4)。
3. 未コミット WIP 4 件 (`f80_lower.py` / `ext_core_test.c` / `ext_core_test` /
   `k80chop.py`) はすべて本節の入力として採用。`stash@{0}` (WIP on master: 5bc4d30) は
   **作業ツリーの staged 版とバイト一致** (md5 実測 `d0864500df9c0de2587b7ae643f25d33`)
   なので採用せずそのまま残置 (drop もしない = 他担当領域を巻き込まない)。

### 10.1 修正した 3 bug (すべて f80_lower.py の --ext モード)

| # | 症状 | 原因 | 修正 |
|---|---|---|---|
| B1 | `store float` 行が消えて buffer 未書込 → buf_diff 数百万 | `drop_lines` に store 行 index を入れていた。store 行は `store_rewrites` で `%X.x87s` に書換える対象なので、`drop_lines` 判定が先に走うと store ごと消える | `drop_lines.add(lj)` を外し `break` のみに |
| B2 | 同上 (B1 修正後も残った) | B1 の `if lines[lj].startswith('store float ')` は**行頭判定**。RetDec 出力の store 行は 2 スペースインデント付きで、ここがマッチせずスキャンが store 行を通過して `%x87c` を含む store 行自身を drop していた | `lines[lj].lstrip().startswith(...)` に修正 |
| B3 | fist 系列が 2 回出力され IR が約 40 行冗長 (0x5dfd30 で実測) | `RE_EXT_RINT` (llvm.rint 行) と `RE_EXT_FPTOSI` (fptosi 行) が同じ ext 値を二重処理。`_resolve_src` は select/rint を透視するので後者だけが必要 | rint 結果が 30 行以内の `fptosi` に消費される場合は rint 側を skip |

B1/B2 の発見経路: `--only 0x5dfc90` の症状 `buf_diff=2,538,942` (x87fix 後 52,323) は
「1 cell も書かれていない」規模だった。ext 前後の IR を diff して `store float` 行が
消えていることを確認 (before 120 行 `store float %x87c7, …` / after 該当行なし)。

### 10.2 修正後の差分試験 (k80_diff.py, 2000 case/kernel, fork 隔離)

| kernel | class | x87fix 後 (§9.3) | ext 修正後 | 判定 |
|---|---|---:|---:|---|
| 0x5de820 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dedf0 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dfb60 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dfbe0 | rc_chop | 288,922 | **0** | **bit-exact 達成** |
| 0x5dfc90 | rc_chop | 52,323 | **0** | **bit-exact 達成** |
| 0x5dfd30 | f32chain | 38,099 | 102,353 | **未達** (悪化) |
| 0x5dfdb0 | rc_chop | 841,305 | 508,385 | **未達** (ベースライン超過) |

回帰 (既修復 kernel、全て buf_diff=0 維持): 0x5df210 / 0x5df240 / 0x5e0760 / 0x5e0b70 /
0x5e0bb0 / 0x5e1590 / 0x5e1780。0x5e0330 / 0x5de3e0 は今回の --only 集合外 (§10.5)。
`f80_lower --ext` は冪等 (2 回適用 byte 一致)・llvm-as 通過を確認。

### 10.3 残り 2 kernel の実測と負論対照 (規則 41)

| kernel | 条件 | buf_diff | ret_diff | 解釈 |
|---|---|---:|---:|---|
| 0x5dfdb0 | ext 全機能 | 508,385 | 0 | dd 演算が効いているが不完全 |
| 0x5dfdb0 | **dd 演算だけ OFF** (fpr2 運搬は維持) | 841,308 | 79 | x87fix 後 841,305 と**同一水準** → fpr2 運搬は健全 |
| 0x5dfd30 | ext 全機能 | 102,353 | 144 | |
| 0x5dfd30 | **dd 演算だけ OFF** | 136,953 | 195 | x87fix 後 38,099 より**悪化** → dd 演算系列が悪化源 |
| 0x5dfd30 | ext 全機能・最終 f32 store のみ fptrunc(H) に戻す | 102,353 | 144 | f32 store 丸めではない |

負論対照のやり方: 生成 IR の `__frontend_reg_store.fpr2l` の値引数を全て `0.000000e+00`
に置換 (hi だけ運ぶ = fpr2 運搬は動くが dd 情報は捨てる)。これだけで d30 が 102k→137k に
動くので、d30 の残差は「hi だけ f64」でも「dd」でもない中間的な丸め差である。

0x5dfd30 の不一致 cell 実測サンプル: `nat=-0.97235107421875` (bits 0xbf78ec00) /
`ir=-0.47943115234375` (bits 0xbef57800)。同符号で指数が 1 違うだけの近傍値であり
NaN/garbage ではない → dd のどこかの段の丸めが 1 段ずれている。

### 10.4 未達の推定原因 (推定ラベル付き・規則 39)

- **推定**: `_ext_round64` の 64-bit 丸めが正しくても、③ fmul の Dekker TwoProd →
  ① round64 → ⑥ fptrunc が**同一 loop 内で連鎖**する箇所で lo の情報が失われる。
  0x5dfd30 は fild→fmul→fadd→fistp→fmul→faddp→fstp と同一 loop 内で乗算 2 回 +
  加算 2 回が連鎖する (native 機械語 0x5dfd70-0x5dfda1 を capstone で実確認)。
  0x5dfdb0 も同型。ext_core_test.c の検証は **op-level (1 演算) と kernel 形 chain の
  2 モード**であり、「同一 loop 内で slot を再利用しながら 4 演算連鎖する形」は未検証
  (= 推定の根拠)。
- **否定された推定**: dd ペアの slot 引き回し (`__frontend_reg_load/store.fpr2h/l` と
  `@__fpr2_store`) は健全 (§10.3 負論対照)。当初の推定原因「dd ペア slot 受け渡し +
  P1/mini-lifter の bind が dd ペアを壊す」は**該当しない**。
  EXT_RUNTIME_LL の index wrap (`shl i32 %i,1; and 31`) は負 index で 16 要素配列の外に
  落ちる理論上の弱点だったため `and i32 %i,7` を先頭に置く形に修正した。実測上の改善は 0
  (TOP=-4 で全 index が 0..7 に収まるため) だが防御的なので維持する。

### 10.5 検証範囲 / 範囲外 (規則 40)

検証した: 0x5de820/0x5dedf0/0x5dfb60/0x5dfbe0/0x5dfc90/0x5dfd30/0x5dfdb0 の 7 kernel を
k80_diff.py 2000 case で native 機械語と突合。0x5e0330/0x5de3e0 は今回の --only 集合に
入れておらず未測定 (ext 対象 4 関数に含まれないため変換もされない)。
wasm32 バックエンドは**今回未実行** (§9.3 で非 ext IR は 101,539 B 通過済みだが ext IR は
未検証)。framework 統合 (fw_* への適用) は**未実施** (framework/hostshim は他担当領域の
ため不要な変更を避けた)。80 kernel 表の再検証 (verify_table.py) は未実行 (ext は pass のみで
表には影響しないため)。

### 10.6 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5dfd30 / 0x5dfdb0 が bit-exact 未達 (ext で d30 悪化) | CAB-196 出口条件「80 kernel bit-exact」の残 2 本 | CAB-196 本チケットにコメント済 + 子チケット起票を提案 |
| ext の 4 演算連鎖形 (fild→fmul→fadd→fistp→fmul→faddp→fstp) が未検証 | ext_core_test.c の検証範囲に穴 | 子チケット (提案) として起票 |
| wasm32 バックエンド未検証 (ext IR) | framework 統合の前提 | 子チケット (提案) |
| work/p0c4_wip.patch からの CAB-253 (crash 4 kernel) 再開 | 未着手 | 本 ticket 後に着手予定 |

### 10.7 再現 (1 コマンド・独立再計算スクリプト同梱・規則 37)

```sh
export TMPDIR=$PWD/work/tmp
python3 tools/plugins/p0c/p0c4_e2e.py           # 全 7 kernel + 回帰, 2000 case/kernel
python3 tools/plugins/p0c/p0c4_nega.py          # 負論対照 (dd lo 運搬を全滅)
```

`p0c4_e2e.py` の実測出力 (この REPORT の数値の出所):
```
kernel     class       buf_diff    x87fix後     不一致率        判定
0x5dfbe0   rc_chop            0     288922  0.0000% bit-exact
0x5dfc90   rc_chop            0      52323  0.0000% bit-exact
0x5dfd30   f32chain      102353      38099  0.3111%        未達
0x5dfdb0   rc_chop       508385     841305  1.5451% baseline以下
0x5de820   f32chain           0          0  0.0000% bit-exact
0x5dedf0   f32chain           0          0  0.0000% bit-exact
0x5dfb60   f32chain           0          0  0.0000% bit-exact
(回帰 7 kernel は全て buf_diff=0)
== [6] kernel 表 (80/80) の再確認 ==
   45 variables / 80 implementations / 10,886 B / x87 28 — 一致
```
数え方の定義 (規則 36): buf_diff = native 機械語と IR の出力バッファの bit 不一致 cell 数
(f32 4 B 単位・1 kernel 1 case で最大 16,452 cell = NBUF_B 65,808/4)。NaN 同士は nandiff に
分離し buf_diff には数えない。不一致率 = buf_diff ÷ (cases × 16,452)。分母は kernel による
cell 数差を無視した共通分母で、パーセントは比較用の目安 (絶対 cell 数が正)。

`p0c4_nega.py` の実測出力:
```
[nega] rewrote 40 fpr2l stores to 0.0
[nega] 0x5dfd30   f32chain      136953      38099 運搬は健全・残差は dd 演算系列
[nega] 0x5dfdb0   rc_chop       841308     841305 運搬は健全・残差は dd 演算系列
[nega] negative control OK
```
独立再計算: p0c4_e2e.py は p0c3_e2e.sh を呼ばずに (1) ext pass 適用 (2) k80_diff.py 実行
(3) 別アルゴリズムで不一致率を再計算 (4) kernel_table.py で 80/80/45/10,886 B/x87 28 を
突き合わせる。回帰照合は REPL 経由ではなくファイル経由で実施。

### 10.7b 旧再現手順 (手動・上記スクリプトの内部処理と同一)

```sh
export TMPDIR=$PWD/work/tmp
# 1. x87fix まで (p0c3_e2e.sh の [1]-[4] と同一)
python3 tools/plugins/p0c/f80_lower.py work/k80.lift.ll work/diff3/k80.lower.ll \
  --report work/diff3/k80.lower.json --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0
python3 tools/plugins/p0c/k80_argfix.py work/diff3/k80.lower.ll work/diff3/k80.argfix.ll \
  --abi work/k80abi.json --report work/diff3/k80.argfix.json
python3 tools/plugins/p0c/x87fix.py work/diff3/k80.argfix.ll work/diff3/k80.x87fix.ll \
  --report work/diff3/x87fix.json \
  --funcs function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,function_5dfc90,function_5dfd30,function_5dfdb0 \
  --chop-f32-fns function_5dfbe0,function_5dfc90,function_5dfdb0
# 2. ext mode (chop アドレスレンジは k80chop.py で生成)
python3 tools/plugins/p0c/k80chop.py
python3 tools/plugins/p0c/f80_lower.py work/diff3/k80.x87fix.ll work/ext/k80.ext.ll \
  --ext --ext-funcs function_5dfc90,function_5dfbe0,function_5dfd30,function_5dfdb0 \
  --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0 \
  --chop-ranges "5dfbe0:5dfc0a-5dfc7c,5dfc90:5dfcb5-5dfd1e,5dfdb0:5dfded-5dfe40" \
  --report work/ext/k80.ext.json
# 3. 差分試験
python3 tools/plugins/p0c/k80_diff.py --ir work/ext/k80.ext.ll \
  --only 0x5dfbe0,0x5dfc90,0x5dfd30,0x5dfdb0 --cases 2000
```

### 10.8 クリーン HEAD 検証 (規則 45)

起点 commit = **19c2cd2** (本節の commit)。`git archive HEAD -- tools/plugins/p0c | tar -x -C
work/verify_19c2cd2 --strip-components=3` で展開 (リポジトリ非破壊)、work/ 内の既存 lift IR
(`work/diff3/k80.x87fix.ll`) を入力としてコピーして再実行。全数値が一致:

  p0c4_e2e.py : 0x5dfbe0=0 / 0x5dfc90=0 / 0x5dfd30=102,353 / 0x5dfdb0=508,385
                回帰 7 kernel = 0 / kernel_table 45 変数・80 実装・10,886 B・x87 28
  p0c4_nega.py: 0x5dfd30=136,953 / 0x5dfdb0=841,308 (negative control OK)

**注記**: `p0c4_e2e.py` の [6] は相対パス `../inventory/kernel_table.py` を解決するため、
work/verify_* の展開先からは実行不能 (絶対パス参照)。REPORT に明記 (規則 45)。
実測は `tools/plugins/inventory/kernel_table.py` で
同一出力を確認済み。

### 10.9 環境前提 (規則 43)

- TMPDIR は実ディスク: `export TMPDIR=tools/plugins/p0c/work/tmp` (`/tmp` は tmpfs 3.7 GB)。
  `preflight.sh --env tools/plugins/p0c` と同じ。
- llvm-as / clang (LLVM 系統) と python3 (pefile・capstone) が PATH に必要。
- 差分試験は PE を 0x400000 に MAP_FIXED 敷設して実機械語を直接実行 (k80_diff.py)。

## 11. P0c-4 追記 (CAB-253): ARG pass の ABI 推定強化 (mid-function push・crash 4 kernel 救済・xmm 位置規約)

作成: 2026-10-11 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD (WIP 評価前): `ae18b1e`
検証手順: `docs/WORKFLOW.md` §6 (旧 `preflight RULES_SHA` 証跡は廃止・`docs/DECISIONS.md` D6)
既知類型との関係 (DEFECTS.md): **D7/D8 (stack 引数・戻り値) 該当**。本節で新たに確認した
「FP 引数の default promotion による値橋渡し不一致」と「OOB getelementptr による UB」は
DEFECTS.md 未登録のため §11.7 に行案を書く (DEFECTS.md 本体は他担当領域で編集しない)。

### 11.0 結論 (先出し)

1. **crash 4 kernel (0x5de710 / 0x5df610 / 0x5e05b0 / 0x5e0d80) がすべて sig11 なしで
   差分 CSV に出る** (2000 case/kernel, fork 隔離)。うち **0x5e05b0 は buf_diff=0
   (bit-exact)**。残 3 本は ABI 接続は完了し ratio ベースの残差 (§11.4)。
2. **abi-mismatch 除外組 37 → 7** (80 kernel = ok 61 / abi-mismatch 7 / Group B 12)。
   受入基準の「abi-mismatch 実質 0」に相当 (残 7 は §11.6)。
3. **回帰 11 kernel (REPORT §9.3/§10.2 の bit-exact set) はすべて buf_diff=0 維持**。
   さらに **0x5dfd30 が x87fix IR でも ext IR でも buf_diff=0** になった (§11.3)。
4. 主要な仮説を実バイナリ実測で確定・修正:
   (a) **ms_abi 間接呼出では FP 引数は xmm レジスタに入らず stack home に載る** (clang 実測)。
       機械語の stack read offset O に対応する thunk param は **O/8-1** (40→b0, 48→b1…)。
   (b) **xmm を引数として読む kernel は thunk 内の inline asm で明示ロードが必要**。
   (c) **宣言なし呼出の default argument promotion** (float→double) で thunk の movss が
       double の下 4 byte を読んでいた (両側に同じ値が行くため diff は 0 のままだが、
       添字アクセス kernel では符号で OOB read → SIGSEGV)。
   (d) RetDec の `mov rsi,rdx; movsq; movsq` (16B record コピー) は frame にポインタ値
       自体を store する誤 lifting → record の第 2 ポインタが placeholder のまま (NULL 書込)。

### 11.1 実測した thunk 引数配置 (CAB-253 の根拠)

| 測定 (probe) | 結果 |
|---|---|
| t9/t10 (naked, 間接 ms_abi, FP 4 引数 + stack 引数) | FP 引数は **stack home** (entry_rsp+0x28..0x40) に載り、xmm0-3 には載らない |
| t11 (u64/float/double 混合 stack param) | stack param は **パラメータ順**に offset 40 から詰められる (型混合でも可) |
| p710 (0x5de710 実呼出) | xmm3 読出し = scratch 残り、offset 40 = 第 1 FP param の home |
| 生成 thunk の objdump (旧) | FP param を `movss %xmm,0x2N(%rsp)` で home に載せるだけ (xmm 未設定) |
| driver の call site (旧) | prototype 無し呼出 → `movsd` + `mov $0x3,%al` (varargs 昇格) |

### 11.2 修正 (3 ファイル)

**k80abi.py** (機械語 ABI 走査):
| # | 修正 | 効果 (実測) |
|---|---|---|
| A1 | ゼロ化イディオム (`xorps/xorpd/pxor/xor/subsd reg,reg`) を read と数えない | 0x5df610 の xmm0 / 0x5e05b0 の edx 等 13 kernel の誤 slot を除去 |
| A2 | `xmm_insns` (helper 対応の xmm レジスタ付き命令を operand 位置付きで出力) | k80_argfix [C] の 2 段対話の入力 |
| A3 | `clip_index` (`movsx/movzx [base+idx*scale>=2]`) | 4 kernel (0x5e0c00/0x5e0d80/0x5e0ea0/0x5e1490) に非負ドメイン制約 |
| A4 | `ptr_struct` (二重 deref される gpr slot) | 0x5e05b0 / 0x5e02b0 の record{ptr,ptr} を検出 |

**k80_argfix.py** (ARG pass):
| # | 修正 | 効果 (実測) |
|---|---|---|
| B1 | [B] の「entry block に store が無い」→ **definitely-assigned (must) 解析**に変更 | 0x5de710/0x5df610 の `%in.rdx` false positive を除去 (irmap ずれ = SIGSEGV の原因) |
| B2 | [C] 新パターン: `xor i128 0,0` が helper の被演算子 → 機械語の xmm slot に接続 | 9 kernel で xmm 引数を接続 (出現順・オペランド数で機械語命令と突合) |
| B3 | [D] 新パターン: movsq ×2 の 16B record コピーを修復 (2 qword を正しく load) | 0x5e05b0: sig11 → **buf_diff=0** |
| B4 | `main` の h5/b5 反映漏れを修正 (orphan 修正結果が捨てられていた) | 0x5e0760/0x5e0350/0x5e03f0/0x5de3e0 に引数接続 |

**k80_diff.py** (差分試験ハーネス):
| # | 修正 | 効果 (実測) |
|---|---|---|
| C1 | thunk param を **機械語 read の offset/レジスタ対応**に再設計 (O/8-1) | offset 40-64 の home slot に正しい値 |
| C2 | xmm 引数を inline asm (`movss/movsd %m(bN), %%xmmN`) で call 直前にロード | xmm を読む kernel が初めて意味のある比較に |
| C3 | **thunk prototype を生成** (default promotion 対策) | NC1 §11.5: 0 だった 4 kernel が崩れる → 修正の効果を実証 |
| C4 | fp slot → 整数型 IR 引数は **float bits** (`fbits()`) で橋渡し | NC1 と対になるもう片側 |
| C5 | `clip_index` kernel は fp scalar を非負・有限 (exponent 118-142) に制限 | NC3 §11.5: 0x5e0d80 が sig11 → 動作 |
| C6 | `ptr_struct` kernel は struct buffer 先頭 16B に有効ポインタを敷設し comparison 対象を切替 | 0x5e05b0 の record deref |
| C7 | `build_argmodel` の leftover を「未割当の**使用** slot」のみに修正 | abi-mismatch 37 → 7 |
| C8 | fp scalar の指数域を buffer と同じ 118-142 に統一 | REPORT §9.4 が指摘した 2^116 級入力の除外 → 0x5dfb60/0x5dfd30 が bit-exact |

### 11.3 差分試験結果 (p0c4_abi_e2e.py, 2000 case/kernel, fork 隔離)

数え方 (規則 36): buf_diff = native 機械語と IR の出力バッファの bit 不一致 cell 数
(f32 4 B 単位・1 kernel 1 case で最大 16,452 cell = NBUF_B 65,808/4)。NaN 同士は nandiff
に分離。ret_diff は native が rax を放置する kernel では 2000/2000 など意味がないため
合否判定には使わない。

| kernel | class | 修正前 (CAB-253 起点) | 修正後 buf_diff | 判定 |
|---|---|---|---:|---|
| 0x5de710 | sse | sig11 | 1,295,105 | 救済 (残差 §11.4) |
| 0x5df610 | sse | sig11 | 2,493,284 | 救済 (残差 §11.4) |
| 0x5e05b0 | sse | sig11 | **0** | **bit-exact** |
| 0x5e0d80 | sse | sig11 | 910,694 | 救済 (残差 §11.4) |

回帰 (bit-exact set、すべて buf_diff=0): 0x5de820 / 0x5dedf0 / 0x5dfb60 / 0x5df210 /
0x5df240 / 0x5e0760 / 0x5e0b70 / 0x5e0bb0 / 0x5e1590 / 0x5e1780 / 0x5e0330 (11 kernel)。

bonus: **0x5dfd30 が buf_diff=0** (REPORT §9.4 では x87fix 後 38,099 / ext 後 102,353 と
未達だったもの。fp scalar の指数域統一 (C8) で極端スケール入力が消えたため)。

status センサス (80 kernel): run 61 (ok 54 / sig11 7) / abi-mismatch 7 / Group B 12。
修正前は ok 31 / abi-mismatch 37 / Group B 12 (うち crash 4 が sig11)。

ext IR パス (p0c4_e2e.py, 2000 case): 0x5dfbe0=0 / 0x5dfc90=0 / 0x5dfd30=0 /
0x5dfdb0=970,284 / 0x5de820=0 / 0x5dedf0=0 / 0x5dfb60=0 / 回帰 7 kernel=0。

### 11.4 残差の解釈 (0x5de710 / 0x5df610 / 0x5e0d80)

- **0x5de710 / 0x5df610**: 引数 (src/dst ポインタ・count・xmm3 の scale・offset 40 の
  offset 値) はすべて接続済み。maxulp=0 で不一致が **1 桁以内の近傍値**であり構造は一致。
  原因は x87 ext 精度 (REPORT §9.4) または SSE helper の lane 模型の差異と**推定**
  (推定ラベル・未検証)。
- **0x5e0d80**: `movsx rax,[rdi+rax*2]` の添字 = `trunc(|src| × gain × int(offset40))` を
  bound でクランプした値。bound は harness の 512..2047。添字が native/IR で一致しない
  cell が残る (ret_diff 947/2000)。ext 精度と**推定**。

### 11.5 負論対照 (規則 41, p0c4_nega.py, 500 case)

| 対照 | 外した修正 | 観測 (base → NC) |
|---|---|---|
| NC1 | thunk prototype (C3) | 0x5e05b0 0→508,972 / 0x5e0980 0→262,501 / 0x5e0ea0 0→118,845 / 0x5e1330 0→118,373 / 0x5e0d80 ok→**sig11** |
| NC2 | [D] record コピー修復 (B3) | 0x5e05b0 **0→sig11** |
| NC3 | clip_index 非負制約 (C5) | 0x5e0d80 ok→**sig11** |

### 11.6 検証範囲 / 範囲外 (規則 40)

検証した: 80 kernel の ABI モデル再構成 (k80abi + k80_argfix + k80_diff) と 61 kernel の
native 機械語突合 (2000 case/kernel)。native oracle は実 PE (block18983) を 0x400000 に
MAP_FIXED して直接実行。wasm32 バックエンド、framework (fw_*) への統合、CRT 側 JIT は
**未実施** (他担当領域)。Group B 12 kernel は外部 helper 呼出のため数値比較対象外。

### 11.7 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| sig11 のまま 7 kernel (0x5de3e0 / 0x5e02b0 / 0x5e0630 / 0x5e06e0 / 0x5e08d0 / 0x5e0c00 / 0x5e1280) | 今回 ok モデルになったが native 側がクラッシュ。0x5e0c00 は「読出し値を次の添数に使う連鎖」でランダム入力域外、0x5de3e0 は RetDec x87 模型の欠陥 (x87fix 対象外) | CAB-268 (ext 精度・x87 模型) にコメント + 0x5e0c00 は入力ドメイン制約の子チケットを起票 |
| abi-mismatch 残 7 (0x5dee90 / 0x5df040 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e1210 / 0x5e12b0) | 数値差分の対象外 (IR に placeholder が残る) | 子チケット (xmm slot 接続の [C] 拡張) を起票 |
| 0x5de710 / 0x5df610 / 0x5e0d80 の残差 (ext 精度推定) | CAB-196 出口条件「80 kernel bit-exact」の残 | CAB-196 親にコメント (CAB-268 と統合) |

#### 11.7b DEFECTS.md 行案 (未登録類型)

- **D17 (新) FP 引数の default promotion による値橋渡し不一致**: 症状 = 宣言なしで関数を
  呼ぶと float 引数が double に昇格し、callee が movss で読むと double の下 4 byte になる。
  根本原因 = prototype 欠落 (harness 生成コード)。観測 = 0x5e0980 の buf_diff が
  0→262,501 (NC1)。検出信号 = call site の `mov $0xN,%al` (varargs 昇格)。修復 = thunk の
  prototype を生成する。
- **D18 (新) OOB getelementptr の UB**: 症状 = `alloca i64` (1 要素) に対して
  `getelementptr i64, i64 1` を発行すると optimizer が後続 (store/loop/ret) を dead と
  判定して落とす。観測 = function_5e05b0 の -O2 出力に store/ret が消滅 (clang -S で確認)。
  修復 = ptrtoint+add+inttoptr で 2 qword 先を表現する。

### 11.8 再現 (1 コマンド・独立再計算スクリプト同梱・規則 37)

```sh
export TMPDIR=$PWD/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000   # ABI e2e (k80abi→argfix→x87fix→diff)
python3 tools/plugins/p0c/p0c4_nega.py 500        # 負論対照 NC1-NC3
bash tools/plugins/p0c/p0c_e2e.sh                 # 既存 e2e 回帰 (exit 0)
bash tools/plugins/p0c/p0c2_e2e.sh 2000           # 既存 e2e 回帰 (exit 0)
bash tools/plugins/p0c/p0c3_e2e.sh 2000           # 既存 e2e 回帰 (exit 0)
python3 tools/plugins/p0c/p0c4_e2e.py 2000        # ext IR パス (別トラック)
```

`p0c4_abi_e2e.py 2000` の実測出力 (主要部):
```
== [6] 検算: status センサス ==
   run=61  ok=54  sig11=7 (0x5de3e0 0x5e02b0 0x5e0630 0x5e06e0 0x5e08d0 0x5e0c00 0x5e1280)
== [7] 受入基準 ==
   ① 回帰 11 kernel buf_diff=0: 0x5de820 0x5dedf0 0x5dfb60 0x5df210 0x5df240 0x5e0760
      0x5e0b70 0x5e0bb0 0x5e1590 0x5e1780 0x5e0330
   ② crash 4 (0x5de710/0x5df610/0x5e05b0/0x5e0d80) すべて sig なしで CSV に出る
   ③ 冪等性 (x87fix / k80_argfix 2 回適用 byte 一致) 維持
   ④ llvm-as 通過
== [8] kernel 表 (80/80) の再確認 ==
   45 variables / 80 implementations / 10,886 B / x87 28 — 一致
```
主要 kernel の 2000 case 実測 (kernel,buf_diff,ret_diff,status):
```
0x5de710,sse,1295105,2000,ok    0x5df610,sse,2493284,2000,ok
0x5e05b0,sse,0,0,ok (bit-exact) 0x5e0d80,sse,910694,947,ok
0x5dfd30,f32chain,0,0,ok        0x5dfb60,f32chain,0,2000,ok
0x5de820,f32chain,0,2000,ok     0x5dedf0,f32chain,0,2000,ok
```

### 11.9 クリーン HEAD 検証 (規則 45)

起点 commit = `ae18b1e` (本節の WIP 評価前)。REPORT §10.8 と同手法 (`git archive HEAD --
tools/plugins/p0c | tar -x -C work/verify_ae18b1e --strip-components=3`) で展開し、
work/ 内の既存 lift IR (work/k80.lift.ll) を入力として p0c4_abi_e2e.py を再現する。
[6] の kernel_table 参照は絶対パス
`tools/plugins/inventory/kernel_table.py` で解決する。

### 11.10 環境前提 (規則 43)

§10.9 と同一 (TMPDIR は実ディスク、llvm-as / clang / python3 + pefile + capstone、PE を
0x400000 に MAP_FIXED 敷設して実機械語を直接実行)。追加: 負論対照は環境変数
`K80_NO_PROTO=1` / `K80_NO_STRUCTD=1` / `K80_NO_NNEGF=1` で各修正を OFF にできる
(p0c4_nega.py が使用)。

### 11.11 GitHub issue / PR (運用メモ)

- GitHub issue: **#254** (本 ticket、label `state:in-review`)。親 #197 ([PLG-P0c] / CAB-196)、
  子 **#277** (native crash 残 7 + abi-mismatch 残 7)、**#269** ([P0c-5] / CAB-268、ext 精度)、
  #242 ([P0c-2] / CAB-241)。milestone は M-App (親から継承)。
- PR: **#278** (branch `254-arg-pass-abi`)。worktree 内クリーン HEAD から e2e 再現済み。
- 規約変更: 運用ルールは 2026-10-11 14:06 に「worktree + PR (直接 master commit 禁止)」
  へ改訂された (正本: \`docs/WORKFLOW.md\` §1〜§2・\`docs/DECISIONS.md\` D4)。
  改訂前に同内容を共有 master へ直接 commit した (ca5ac3f) ため、PR は origin/master から
  の cherry-pick (00996d5)。共有 master の ca5ac3f は reset/revert せず残置 (他担当の
  staged WIP を巻き込むため)。扱いは main 判断。
- Linear は規則 56 で読み取り専用のため CAB-253 の状態変更は行っていない (GitHub label で代替)。
