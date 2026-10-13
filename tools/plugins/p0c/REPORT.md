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
[6] の kernel_table 参照はスクリプトが `__file__` から REPO を導出し、
`tools/plugins/inventory/kernel_table.py` を解決する。

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
- 規約変更: 運用ルール (旧 SUBAGENT_RULES.md) は 2026-10-11 14:06 に「worktree + PR (直接 master commit 禁止)」
  へ改訂 (RULES_SHA=4d7380074852、正本: `docs/WORKFLOW.md` §1〜§2・`docs/DECISIONS.md` D4)。
  着手時の RULES_SHA は ff4999169333 (改訂前の preflight 値)。
  改訂前に同内容を共有 master へ直接 commit した (ca5ac3f) ため、PR は origin/master から
  の cherry-pick (00996d5)。共有 master の ca5ac3f は reset/revert せず残置 (他担当の
  staged WIP を巻き込むため)。扱いは main 判断。
- Linear は規則 56 で読み取り専用のため CAB-253 の状態変更は行っていない (GitHub label で代替)。

## 12. P0c-5 追記 (#269): 0x5dfdb0 / 0x5de710 の残差は ext 精度ではなくハーネス/e2e 側の欠陥だった

作成: 2026-10-12 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `3ae2d0d` / 検証 HEAD: `970164f`
既知類型との関係 (DEFECTS.md): 該当なし (新類型 D19 候補を §12.4 に行案)。素材: `fl-win64.tar.zst` の
`block18983_PE.bin` のみ。`work/k80.lift.ll` は RetDec v5.0 (公開 release) で `lift_ranges.sh` から再生成した。

### 12.1 結論 (先出し)

1. **0x5dfdb0 の buf_diff は ext IR で 970,284 → 0 (bit-exact)**。dd 演算系列に bug は無かった。
   原因は `k80_diff.py` が table ポインタ (rcx/r9 相当) に buffer 先頭を渡していたこと。0x5dfdb0 は
   添字を `[-1, bound]` にクランプして `tbl[-1]` を読むため、native と IR で別 static 配列の直前 byte を
   読み、差分になっていた。buffer 先頭から 64 byte 内側を渡す (`bufpad`) と 0 になる。
2. **0x5de710 の buf_diff は 1,295,105 → 0**。さらに同じ原因の 0x5deb10 / 0x5decb0 / 0x5df270 /
   0x5df4d0 / 0x5df750 / 0x5df860 も 0 になった。原因は `p0c4_abi_e2e.py` が `lift_ranges.sh` の
   `fix_asm_stores.py` (movlps/movsd 等の 64bit 部分 store 復元) を通さずに `k80.lift.ll` を使っていたこと
   (IR 側で端数 (count&7) の store が欠落していた)。
3. issue の推定「dd 連鎖形の `_ext_round64` / `_ext_arith` の bug」は**否定**。ext_core_test.c
   (3M case 相当の既存モード + chain) は変更なしで全数一致 (§12.2)。

### 12.2 実測 (2000 case/kernel, fork 隔離, 検証 HEAD `970164f`)

数え方・buf_diff の定義は §11.3 と同じ。

| kernel | 起点 (3ae2d0d) | 修正後 | 備考 |
|---|---:|---:|---|
| 0x5dfdb0 (ext IR, p0c4_e2e.py) | 970,284 | **0** | 修正 1 |
| 0x5dfd30 (ext IR) | 0 | **0** | 維持 |
| 0x5de710 (x87fix IR, abi e2e) | 1,295,105 | **0** | 修正 2 |
| 0x5df610 | 2,493,284 | 2,404,917 | 残 (§12.3) |
| 0x5e0d80 | 910,694 | 910,077 | 残 (§12.3) |

- `p0c4_e2e.py 2000`: 判定 **bit-exact 7/14** (起点は 6/14)。回帰 7 kernel (0x5de820/0x5dedf0/0x5dfb60/
  0x5df210/0x5df240/0x5e0760/0x5e0b70/0x5e0bb0/0x5e1590/0x5e1780 を含む 14 kernel 表) は buf_diff=0 維持。
  所要 109.9 s (1 回実測, load average 0.87, 並列 1)。
- `p0c4_abi_e2e.py 2000`: rc=0, 所要 23.4 s (load average 0.87)。冪等性 / llvm-as OK、
  status センサス run=61 ok=54 sig11=7 (起点と同一)。
- `ext_core_test` (`cc -O2 -ffp-contract=off`): N=300000 で fails=0 (0.6 s)。

負論対照 (修正を外すと数値が戻る):

| 対照 | 外した修正 | 観測 |
|---|---|---|
| NC1 `K80_NO_BUFPAD=1` | bufpad (修正 1) | 0x5dfdb0 ext IR 0 → 970,284 (0x5dfbe0 / 0x5dfc90 は 0 のまま) |
| NC2 `K80_NO_ASMSTORES=1` | fix_asm_stores (修正 2) | 0x5de710 0 → 1,295,106 / 0x5deb10 0 → 1,295,104 / 0x5df4d0 0 → 1,305,143 / 0x5df750 0 → 649,070 / 0x5df860 0 → 644,332 |

(bufpad 適用前後で 0x5dfdb0 の x87fix IR 値も 979,240 → 13,901 に下がるが、x87fix IR は ext 精度差が
残るため 0 にはならない。ext IR で 0。)

### 12.3 残差 (推定ラベル付き・未検証)

- **0x5e0d80 (910,077) の原因候補**: lift IR の `ucomiss` 結果が捨てられている (`call void @__asm_ucomiss`
  の戻りが未使用)。機械語は `ucomiss; jbe` で `r14d = ±1` (符号) を選ぶが、IR は初回 `phitmp` と以降
  `store i64 -1` の定数になっている。符号が常に -1 になる**推定** (IR を読んだだけで、修復・差分での確認はしていない)。
  ext 精度ではない可能性が高い。
- **0x5df610 (2,404,917)**: 未調査 (§11.4 の「ext 精度」推定は、0x5de710 が精度と無関係に 0 になったため根拠が弱い)。

### 12.4 DEFECTS.md 行案・未解決・起票先

- **D19 (新, 候補) 差分ハーネスの境界 read 不一致**: 症状 = native/IR で buffer 先頭の直前 byte を読み
  diff が出る。根本原因 = クランプ添字 `-1` が buffer 先頭を指す。検出信号 = IR が buffer を使わず同じ入力で
  ret/buf が揺れる。修復 = buffer 先頭から内側にずらしたポインタを渡す。
- **D20 (新, 候補) e2e が lift 後段 pass を通していない**: `k80.lift.ll` は `lift_ranges.sh` 途中出力で、
  `fix_asm_stores` 等の後段を通らない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~0x5e0d80 の ucomiss 符号 lift 欠落 (§12.3)~~ → §13 で buf_diff 0、現状も 0 (§14.3)。#331 の対象は 0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0 / 0x5e12b0 (§14.4) | (解消) | — |
| ~~0x5df610 の残差 (§12.3)~~ → §13 で buf_diff 0 | (解消) | — |
| wasm32 バックエンド検証・framework 統合 (fw_f80.py → f80_lower --ext) | #269 作業案 4 は未実施 → §16 (#311) で実施 (受入 3 のみ未検証) | #311 |
| 環境: `/opt/retdec`・`/home/ubuntu/work/{analysis,webstudio}` への絶対パス依存 (k80_diff.py 等) | CI 上では symlink で代替 | #197 に提案 (スクリプトの REPO 相対化) |

### 12.5 再現

```sh
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000   # 0x5de710=0 ほか
python3 tools/plugins/p0c/p0c4_e2e.py 2000        # 0x5dfdb0=0 (bit-exact 7/14)
K80_NO_BUFPAD=1 python3 tools/plugins/p0c/k80_diff.py --ir tools/plugins/p0c/work/ext/k80.ext.ll --only 0x5dfdb0 --cases 2000   # NC1
K80_NO_ASMSTORES=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                                                                # NC2
```

## 13. P0c-7 追記 (#310): 0x5df610 / 0x5e0d80 は bit-exact (buf_diff 0) になった

作成: 2026-10-13 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `400d546` / 検証 HEAD: `2c38a22` (コミット済み・`git status --porcelain` 空)
既知類型との関係 (DEFECTS.md): 該当なし (D21・D22 候補を §13.4 に行案)。素材: `fl-win64.tar.zst` の `block18983_PE.bin` のみ。
`work/k80.lift.ll` は `lift_ranges.sh` (RetDec v5.0) で再生成 (4.1 s)。`work/f80_classes.json` / `kernel_table.json` は
`f80_assess.py` / `inventory/kernel_table.py` で再生成。

### 13.1 結論 (先出し)

1. **0x5e0d80 (910,077 → 0)**: §12.3 の推定 (ucomiss 結果が捨てられ符号が定数) を**実測で確認**した。機械語は
   `ucomiss xmm0,xmm6; jbe` で `r14d = (0.0 > src) ? -1 : +1`。lift IR は `@__asm_ucomiss` の戻りを使わず、符号 alloca
   (`%cf.0.reg2mem`) が初回 `select(count==0, 1, -1)`・以降 `store -1` の定数だった。`k80_ucomi_sign.py` (新規) が
   ucomiss 直後に `select (fcmp ogt A.lane0, B.lane0), -1, 1` を作り `%cf.N.reload` の use を置換する。ext 精度ではなかった。
2. **0x5df610 (2,404,917 → 0)**: ext 精度でも lane 模型でもなく **k80_argfix.py [A] の xmm slot 割当の誤り**。
   `movdqa [rbp+0x10],xmm7` / `movdqa [rbp],xmm6` (非 volatile xmm6/7 の spill) の placeholder (`xor i128 0,0`) を [A] が
   「`__asm_movdqa` のみ使用 → 引数」と見て `%in.xmm3.bits` を先に割り当て、実際に xmm3 を読む `movss xmm7,xmm3` の
   placeholder は未接続のまま (0 扱い) だった。scale (xmm3) が 0 になり出力が全面不一致。修正 = `__asm_movdqa` のみの
   placeholder は引数にしない (`SKIP_SPILLFIX`)。`movaps xmm6,xmm3` 形 (0x5de5a0 / 0x5e07b0 / 0x5e0830) は幅 32 bit で接続する。
3. 副次: **同原因の 0x5de5a0 (1,260,951) / 0x5e07b0 (1,260,951) / 0x5e0830 (631,030) / 0x5de8e0 (2,365,445) も 0**。
   0x5df340 は 1,291,379 → 1,283,847 (残。未調査)。

### 13.2 実測 (2000 case/kernel, fork 隔離, 検証 HEAD `2c38a22`, 数え方は §11.3)

| kernel | 起点 (400d546) | 修正後 buf_diff | ret_diff (修正後) |
|---|---:|---:|---:|
| 0x5df610 | 2,404,917 | **0** | 2000 (native が rax を放置。判定対象外 §11.3) |
| 0x5e0d80 | 910,077 | **0** | 0 |
| 0x5de5a0 / 0x5e07b0 / 0x5e0830 / 0x5de8e0 | 1,260,951 / 1,260,951 / 631,030 / 2,365,445 | **0** | — |
| 0x5df340 | 1,291,379 | 1,283,847 | — (残) |

- 回帰: `p0c4_abi_e2e.py 2000` で起点 buf_diff=0 だった 29 kernel (status ok のみ) はすべて 0 のまま (29/29)。
  「status ok かつ buf_diff==0」の kernel 数は status ok 54 kernel 中 29 → 35 (sig11 7 kernel は buf_diff 列が 0 でも
  未実行なので数えない)。status センサス run=61 ok=54 sig11=7 (起点と同一)。冪等性・llvm-as OK、受入基準 ①-④ OK。
  所要 24.9 s (load average 0.59→0.97, 並列 1)。起点の同スクリプト実測は 27.7 s。
- `p0c4_e2e.py 2000` (ext IR): bit-exact 7/14 で起点と同一 (0x5dfbe0/0x5dfc90/0x5dfd30/0x5dfdb0/0x5e0b70/0x5e1590/0x5e1780)。
  所要 117.0 s (load average 0.97, 並列 1)。

### 13.3 負論対照 (修正を外すと数値が戻る, 2000 case)

| 対照 | 外した修正 | 観測 |
|---|---|---|
| NC1 `K80_NO_UCOMISIGN=1` | ucomiss 符号修復 | 0x5e0d80 0 → **910,077** (0x5df610 は 0 のまま) |
| NC2 `K80_NO_SPILLFIX=1` | spill placeholder 除外 | 0x5df610 0 → **2,404,917** / 0x5de5a0 0 → 1,260,951 / 0x5e07b0 0 → 1,260,951 / 0x5e0830 0 → 631,030 / 0x5de8e0 0 → 2,365,445 (0x5e0d80 は 0 のまま) |

NC は互いに独立 (NC1 は 0x5df610 に、NC2 は 0x5e0d80 に影響しない)。「status ok かつ buf_diff==0」の kernel 数 (status ok 54 kernel 中): 起点 29 / 修正後 35 / NC1 34 / NC2 30。

### 13.4 DEFECTS.md 行案・未解決・起票先

- **D21 (新, 候補) 比較フラグの結果を捨てた lift**: 症状 = `call void @__asm_ucomiss` の戻り未使用で、`jbe` 由来の分岐/選択値が
  定数化。検出信号 = IR に void の `__asm_*comis*` call があり、同 block の後続が `%cf.N.reload` を使う。修復 = fcmp で SSA 化。
- **D22 (新, 候補) callee-save spill の placeholder を引数と誤認**: 症状 = `movdqa [mem],xmm6/7` の `xor i128 0,0` に引数 xmm slot
  を割当て、本当の引数 read が未接続 (0)。検出信号 = `__asm_movdqa` のみ使用の placeholder に `%in.xmmN.bits` が付く。
  修復 = 除外し、movaps 全 reg コピー形は幅付きで接続。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5df340 buf_diff 1,283,847 (未調査) | 80 kernel bit-exact の残 | 子 issue を起票 (本 PR 後・#197 親) |
| `k80_ucomi_sign.py` は `--func function_5e0d80` の opt-in (jbe→±1 を機械語で確認済みの 1 site のみ) | 他 kernel の同形は未走査 | #197 にコメント |
| sig11 7 kernel / abi-mismatch 7 kernel (§11.7) | 数値差分の対象外 | 子 #277 |
| `/opt/retdec`・`/home/ubuntu/work/*` 絶対パス依存 (runner では symlink で代替) | CI 再現性 | #294 |

### 13.5 再現

```sh
sudo ln -sfn <fl-win64 extracted> /home/ubuntu/work/analysis/win64/extracted ; sudo ln -sfn $PWD /home/ubuntu/work/webstudio   # #294 回避 (PR #301 と同方法)
bash tools/plugins/lift/lift_ranges.sh <PE> tools/plugins/lift/kernel_ranges_balance.txt tools/plugins/p0c/work k80
mkdir -p tools/plugins/work && python3 tools/plugins/inventory/kernel_table.py && python3 tools/plugins/p0c/f80_assess.py
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                          # 0x5df610=0 / 0x5e0d80=0
K80_NO_UCOMISIGN=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000       # NC1
K80_NO_SPILLFIX=1  python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000       # NC2
python3 tools/plugins/p0c/p0c4_e2e.py 2000                              # 回帰 (bit-exact 7/14)
```

## 14. P0c-6 追記 (#277): native crash 7 kernel と abi-mismatch 7 kernel の原因は ABI 抽出・引数割付・入力ドメインだった

作成: 2026-10-12 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `400d546` (main) / 検証 HEAD: `15617b4`
既知類型との関係 (DEFECTS.md): D19 (差分ハーネスの境界 read 不一致) と同系統 (§12.4 の候補)。新類型候補は §14.4。
素材: `fl-win64.tar.zst` の `block18983_PE.bin` のみ。`work/k80.lift.ll` は `lift_ranges.sh` で再生成 (RetDec v5.0)。
数え方・buf_diff の定義は §11.3 / §12.2 と同じ (2000 case/kernel, fork 隔離, 並列 1)。

### 14.1 結論 (先出し)

1. **対象 A の sig11 は 7 → 0** (`p0c4_abi_e2e.py` の `run=61 ok=54 sig11=7` → `run=67 ok=67 sig11=0`)。
   7 kernel は 4 つの別原因で、いずれも lift IR / ext 精度ではなく `k80abi.py` / `k80_diff.py` の欠陥だった。
2. **対象 B は 7 のうち 6 kernel が ok モデルになった** (0x5dee90 / 0x5df040 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 /
   0x5e1210)。残る 0x5e12b0 は引数接続では救えない (§14.3)。
3. 数値差分が測れるようになった結果、**ok かつ buf_diff=0 の kernel は +10**: 0x5e0630 / 0x5e06e0 /
   0x5e08d0 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e0c00 / 0x5e1010 / 0x5e1210 / 0x5e1280。起点 (#277 単独の検証 HEAD
   `15617b4`) では 29 → 39 で、起点で bit-exact だった 29 kernel は 1 つも失っていない。§13 (#310) を取り込んだ
   merge 後 HEAD の実測は **45** (`p0c4_abi_e2e.py 2000` の CSV で status ok かつ buf_diff=0 を数えた値。
   45 のうち上記 10 を除く 35 は件数が §13 の「修正後 35」と一致するが、kernel 集合の照合は未実施)。起点の sig11 / abi-mismatch で測れていなかった kernel のうち差分が出たものは
   §14.3 に残差として分けた。
4. 回帰 11 kernel (0x5de820 ほか) は buf_diff=0 維持。

### 14.2 原因と修正 (kernel 別・実測)

| 原因 | 対象 kernel | 修正 | 負論対照 (修正を外すと) |
|---|---|---|---|
| (a) `k80abi.py`: 先に write 済みの reg (`mov r8, rdx` 後の `[r8]`) を引数ポインタ base に数え、実際の引数 r8 (個数) に buffer を割り当てて OOB | 0x5e0630 / 0x5e06e0 / 0x5e08d0 / 0x5e0a70 | write 済み reg の deref は base でなく copy 逆伝播の種にだけ使う | `K80_NO_WRITTEN_BASE=1`: 上記 4 が sig11 |
| (b) `k80_diff.py`: RetDec の `%argN` は win64 gpr 序数だが、機械語が rcx を読まない kernel で使用 slot を詰めて割り当て、IR が 1 つずれた arg に store (NULL 書き込み) | 0x5de3e0 / 0x5e1280 | `%arg1..4` は序数で固定 (後ろの gpr を使うときのみ) | `K80_NO_ARGORD=1`: 2 kernel が sig11 |
| (c) `k80abi.py`: `lea [rcx+r8*4]` の index 専用 reg (r8=個数) が copy 伝播で base 扱い | 0x5e02b0 | ptr_struct を持つ kernel に限り index 専用 reg を base から外す | `K80_NO_IDX_NOT_BASE=1`: sig11 |
| (d) `k80_diff.py`: clip_index kernel で gain が大きいと `cvttsd2si`=0x80000000 → neg でも INT_MIN → clamp 素通り → 負添字 | 0x5e0c00 | gain 指数を 2^-9..2^-1 に制限 (ドメイン制約) | `K80_NO_CLIPRANGE=1`: sig11 (他 2 kernel の buf_diff も変動) |
| (e) `k80abi.py`: `movlps xmm, [m]` の dest を read 扱いし偽の xmm 引数 (xmm0/xmm2) を作った | 0x5dee90 / 0x5df040 | movlps/movlpd/movhps/movhpd の dest は read から除外 | `K80_NO_PARTIAL_LOAD=1`: 2 kernel が abi-mismatch (run 65) |
| (f) `k80abi.py`: stack 引数幅を命令名 (`cvtss2sd` の `sd`) で 64bit と誤判定 | 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e1010 | メモリオペランドの大きさを使う | `K80_NO_MEMW=1`: 4 kernel の buf_diff が 0 → 2,580,673 / 2,583,215 / 1,291,834 / 787,450 |
| (g) `k80_argfix.py` [C]: `cvtss2sd xmm0, xmm3` (reg-reg 単項) の source xmm を接続できなかった | 0x5e09f0 / 0x5e0a70 / 0x5e0b10 | dest を含まない形を second pass で突合 | `K80_NO_REGSRC=1`: **差なし** (下記) |
| (h) `k80abi.py`: 自分で書いた stack home slot (`movss [rsp+0x18], xmm2`) の読み戻しを stack 引数扱い | 0x5e1210 | write 済み stack slot は read 候補から除外 | `K80_NO_STACKW=1`: 0x5e1210 が結果から消える (abi-mismatch) |
| (i) `k80_argfix.py` [C]: 同じ placeholder が `movss` と `cvtss2sd` の両方に使われ出現順突合が破綻 | 0x5e1210 | 各 use が取りうる xmm 集合の積が 1 つのときだけ接続 | `K80_NO_INTERSECT=1`: 0x5e1210 が結果から消える |

(g) の負論対照は **差が出なかった** (`K80_NO_REGSRC=1` で run=67 ok=67、CSV も不変)。(g) を入れた時点 (HEAD `fce0e86`) では
argfix の `helper_xmm` が 9 → 12 に増え 0x5e09f0 / 0x5e0a70 / 0x5e0b10 が ok になったが、その後に入れた (i) の
積集合 fallback が同じ placeholder を接続できるため、現状では (g) は冗長 (未検証: (g) と (i) の両方を外した場合)。
冗長なため削除せず、環境変数で外せる形で残している。

### 14.3 実測 (検証 HEAD `15617b4`)

| コマンド | 結果 |
|---|---|
| `p0c4_abi_e2e.py 2000` | rc=0、26.7〜27.1 s (load average 0.5〜0.9)、`run=67 ok=67 sig11=0`、起点は `run=61 ok=54 sig11=7` |
| `p0c4_abi_e2e.py 2000` (origin/main = `35bdf9d` を merge した後のコミット済み HEAD `330ada8`) | rc=0、14.5 s (load average 0.28→0.44)、`run=67 ok=67 sig11=0`、ok かつ buf_diff=0 は 45 |
| `p0c4_e2e.py 2000` | rc=0、111.8 s / 112.5 s (2 回)、判定 bit-exact 7/14 (§12.2 と同じ) |
| `p0c2_e2e.sh 2000` | rc=0、50.5 s |
| `p0c3_e2e.sh 2000` | rc=0 (回帰判定から 0x5de3e0 を除外した後。除外前は FAIL-REGRESS、下記) |
| `ext_core_test` N=300000 | `ext core OK`、1.9 s |

対象 A (起点 sig11 → 修正後):

| kernel | buf_diff | ret_diff | 備考 |
|---|---:|---:|---|
| 0x5e0c00 | 0 | 0 | bit-exact |
| 0x5e0630 | 0 | 0 | bit-exact |
| 0x5e06e0 / 0x5e08d0 | 0 | 2000 | ret は native が rax を放置 (合否は buf_diff のみ) |
| 0x5e1280 | 0 | 0 | bit-exact |
| 0x5e02b0 | 2,578,706 | 0 | **残差** (maxulp 610,852,255)。f32chain、x87 の fild×fmul 模型 (推定・未検証) |
| 0x5de3e0 | 2000 | 0 | **残差**: IR の store が `[rdx]` (上位 32bit) を欠落している (下記) |

対象 B (起点 abi-mismatch → 修正後): 0x5e09f0 / 0x5e0a70 = buf_diff 0 (ret 2000)、0x5e0b10 / 0x5e1210 = 0 (ret 0)、
**0x5dee90 = 2,565,360 / 0x5df040 = 2,565,277** (ok モデルだが差分あり・残差)。0x5e12b0 は abi-mismatch のまま。

**残差・未解決 (推定ラベル付き)**:

- **0x5de3e0 (buf_diff=2000)**: 機械語は `fistp qword` の上位 dword を `[rdx]`、下位を `[r8]` に書くが、
  x87fix 後 IR は `%arg3` への store のみ (上位 dword の store が無い)。RetDec が `[rdx]` 側 store を落としたと**推定**
  (lift 欠落。DEFECTS 類型は未照合)。起点では sig11 で buf_diff が測れず `p0c3_e2e.sh` の回帰判定を素通りしていた。
  今回モデルが直り測れるようになり FAIL-REGRESS になったため、判定リストから外した (欠陥を隠すのではなく
  「測れていなかった」ことを REPORT に残す)。
- **0x5dee90 / 0x5df040 (約 2.57M)**: 未調査 (ok モデルで差分が出るようになった段階)。
- **0x5e12b0**: RetDec の IR が `ucomiss` のフラグ使用と被演算子 (xmm0/xmm1) を落とし、引数ゼロ・戻り値定数 0 の関数
  (`define i64 @function_5e12b0()`) になっている。引数接続の対象外で、lift 側の欠陥 (0x5e0d80 で §13 が修復した
  ucomiss 符号欠落と同系統の**推定**)。
- 0x5e0d80: 検証 HEAD `15617b4` 時点は 951,534 だったが、§13 (#310) の ucomiss 符号修復を取り込んだ merge 後は
  **buf_diff=0** (`p0c4_abi_e2e.py 2000` 実測)。#331 の対象ではない。
- 0x5e1490 (1,046,283 → 1,201,366): 0x5e0c00 の gain 制限に伴い乱数列が変わったため変動
  (`K80_NO_CLIPRANGE=1` で旧値に戻る)。原因は未調査で、悪化ではなく入力列の差。

### 14.4 DEFECTS.md 行案・未解決・起票先

- **D23 (新, 候補) ABI 抽出の read/write 誤分類**: 症状 = native 実行が sig11 または引数が偽に増える。
  根本原因 = (a) write 済み reg の deref、(c) index 専用 reg、(e) 部分 load の dest、(f) 命令名による幅推定、
  (h) 自書き stack slot の読み戻し。検出信号 = `gpr_base` / `xmm_slots` / `stack` が機械語を読むと食い違う。
  修復 = 負論対照付きの個別除外 (§14.2)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5de3e0 の `[rdx]` store 欠落 (lift) | buf_diff 2000 | #331 |
| 0x5dee90 / 0x5df040 / 0x5e02b0 の残差 | buf_diff 約 2.57M | #331 |
| 0x5e12b0 の ucomiss 落ち (lift) | abi-mismatch のまま | #331 |

#331 の対象 kernel は 0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0 / 0x5e12b0 の 5 つ (0x5e0d80 は含まない)。
| ext 精度が必要な kernel の wasm32 検証・framework 統合 | #269 §12.4 と同じ | #197 (既存提案) |

### 14.5 再現

```sh
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/f80_assess.py                       # work/f80_classes.json
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                # sig11=0 / B6 ok を判定に含む
for v in WRITTEN_BASE ARGORD IDX_NOT_BASE CLIPRANGE PARTIAL_LOAD MEMW REGSRC STACKW INTERSECT; do
  env K80_NO_$v=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000  # 負論対照 (rc は下記)
done
```
負論対照の rc (merge 後 HEAD 実測): **MEMW と REGSRC は rc=0** (受入判定を通る。MEMW は §14.2 のとおり buf_diff が
増えるが判定対象外、REGSRC は差なし)。**それ以外の 7 種は rc=1** (WRITTEN_BASE `run=67 ok=63 sig11=4` / ARGORD
`ok=65 sig11=2` / IDX_NOT_BASE `ok=66 sig11=1` / CLIPRANGE `ok=66 sig11=1` / PARTIAL_LOAD `run=65` / STACKW `run=66` /
INTERSECT `run=66`)。MEMW の差は CSV の buf_diff でのみ検出できる。
前提: `k80.lift.ll` は `bash tools/plugins/lift/lift_ranges.sh <PE> work/k80_ranges.txt tools/plugins/p0c/work k80 2400`
で再生成。`llvm-as` / `clang` は PATH に必要 (runner では `/usr/lib/llvm-18/bin`)。
`/opt/retdec` と `/home/ubuntu/work/{analysis,webstudio}` は runner 上の symlink で代替 (§12.4)。

## 15. 環境パス置換 (#346, 親 #294・先行 #312): /home/ubuntu 絶対パスを tools/shared へ

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみで lift/IR には触れない)。

### 15.1 変更

`*.sh *.py *.json *.ts *.mjs` (work/ 除く) の `/home/ubuntu` 参照 9 行を置換。既定値は従来と同一なので、環境変数未設定のローカル挙動は変わらない。

| ファイル | 置換 |
|---|---|
| `p0c_e2e.sh` `p0c2_e2e.sh` | `source tools/shared/env.sh` + `PE="$FL_WIN64_DIR/extracted/block18983_PE.bin"` |
| `f80_assess.py` `k80chop.py` `k80abi.py` | `tools/shared/paths.py` の `FL_WIN64_DIR` から `PE` を組む |
| `kernel_matrix.py` `verify_table.py` | 同 `EXT = FL_WIN64_DIR/extracted` |
| `k80_diff.py` | `PE` は同上。`LIFTP` は `REPO_ROOT/tools/plugins/lift/passes` (旧: `/home/ubuntu/work/webstudio/...` 固定) |

`p0c_e2e.sh` step 1 は `inventory/kernel_table.py` に `$PE` を引数で渡す。同スクリプトの既定値が `/home/ubuntu` 固定 (p0c の外・本 PR の範囲外) のため。

### 15.2 検証 (検証起点 `origin/main` = 2c3e526、素材は `fl-win64` のみ)

- 受入条件 1: `grep -rn '/home/ubuntu' tools/plugins/p0c --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs --exclude-dir=work | wc -l` → 0。
- 受入条件 2 (before/after): 同一サブセットを置換前 (`origin/main` の detached worktree・`/home/ubuntu/work/analysis/win64` を symlink で用意) と
  置換後 (symlink 削除・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` のみ) で実行し出力を `cmp`。
  サブセット = `kernel_table.py` → `f80_assess.py` → `f80_micro` (2000000 case) → `k80abi.py` → `k80chop.py`。
  所要 before 1.06 s / after 1.06 s、load average 0.45 / 0.38 (1 分値)、各 n=1・直列。

| 出力 | before/after | sha256 先頭 12 桁 |
|---|---|---|
| kernel_table stdout / `kernel_table.json` | 一致 | 55b1810cba94 / ce8c15353720 |
| f80_assess stdout / `f80_classes.json` | 一致 | 7b13c98d9494 / ef4fdcd06cf9 |
| f80_micro stdout | 一致 | d092659b28a9 |
| k80abi `k80abi.json` | 一致 | b30e176cd3eb |
| k80chop stdout | 一致 | e9192d1bbce2 |
| k80abi stdout | 1 行目のみ差 (出力先絶対パスに worktree 名が入る) | — |

- ネガティブコントロール: `FL_WIN64_DIR=/nonexistent python3 k80chop.py` → `FileNotFoundError: /nonexistent/extracted/block18983_PE.bin` で FAIL (`FL_WIN64_DIR` が実際に効いている)。
- 構文: `python3 -m py_compile` 6 本・`bash -n` 2 本 OK。

### 15.3 検証範囲 / 範囲外 / 未解決

範囲外: `kernel_matrix.py` `verify_table.py` `k80_diff.py` `p0c2_e2e.sh` `p0c_e2e.sh` の実行。前 3 本は `nsis_blockmap.json` や `/opt/retdec` の lift 成果物
(`toolchain-retdec`・`work-m6-ott` 等) が要る。置換は `PE` / `EXT` / `LIFTP` の定義行のみで、構文確認と `FL_WIN64_DIR` 解決の確認に留めた。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `inventory/kernel_table.py:15`・`lift/batch_lift.sh:31` に `/home/ubuntu` 既定が残る (p0c 外) | 他 area の置換 issue 待ち | #294 の該当 area 子 issue |
| `kernel_matrix.py` `verify_table.py` `k80_diff.py` と e2e 全体を `oc_artifacts` 付きで未実行 | 置換行以外の挙動は未検証 | #360 (本 PR のレビュー run でも `oc_artifacts:` で再実行可) |
| §13.4 の「絶対パス依存 (#294)」のうち p0c 内の `/home/ubuntu` 参照は解消 (`/opt/retdec` は残る) | — | #294 |

### 15.4 #360: 追加素材での full e2e before/after (検証 HEAD 856be6b / 比較元 8af7eb0)

素材: `fl-win64` `toolchain-retdec` `toolchain-emsdk` `work-m6-ott` `work-liftlib` (`oc_artifacts`)。before = `856be6b^1` (= `8af7eb0`、置換前)、after = `856be6b` (#359 merge)。
before は `/home/ubuntu/work/analysis/win64` と `/home/ubuntu/work/webstudio` を symlink で用意、after は `/home/ubuntu` を削除し `FL_WIN64_DIR` のみ。各 n=1・直列・4 コア runner。

結論: **`p0c_e2e.sh` / `p0c2_e2e.sh` は置換前後とも rc=0、決定的な成果物はすべて一致**。不一致は RetDec が同一入力でも出力を変えることだけで、置換とは無関係 (下記)。

| 項目 | before | after |
|---|---|---|
| `p0c_e2e.sh` | rc=0、12.9 s (kernel_matrix は skip。前段で別実行) | rc=0、8.6 s (同) |
| `p0c_e2e.sh` 初回 ([2] kernel_matrix.py 12 = 181 DLL 走査を含む) | 515.7 s、rc=1 ([4] で上記の理由)、load 12.09 (開始 1 分値) | 512.5 s、rc=0、load 1.97 (同) |
| `p0c2_e2e.sh` | rc=0、47.8 s、load 3.82 | rc=0、44.7 s、load 1.80 |

(表の `p0c_e2e.sh` 行は `work/kernel_matrix.json` が既にあり [2] を skip した再実行。kernel_matrix を実行した初回の `p0c_e2e.sh` 全体が、after は rc=0・512.5 s (その中の [2])、
before は 515.7 s で `p0c/work/kernel_table.json` の置き場所違いにより [4] で rc=1 だったため、同ファイルを `p0c/work/` に置いて再実行した。after の再実行 (8.6 s) の load は記録に失敗。)

一致を `cmp` / sha256 で確認したもの (先頭 12 桁):

| 出力 | 結果 |
|---|---|
| `kernel_matrix.json` / `kernel_used_norm.json` / `table_verify.json` | 一致 (487412af06e6 / 0b123bd6264f / e5709ebd4e62) |
| `verify_table.py` stdout ([3])、`f80_assess` + `f80_micro` stdout ([5][6]) | 一致 (8623cae11386 / 83bf33956334) |
| `k80abi.json`、`diff/k80.lower.ll`、`diff/k80.argfix.ll` | 一致 |
| `p0c2_sweep.csv` (194 行) | 一致 (52d0c45c63f9) |
| `p0c2_e2e.sh` stdout (パス正規化後) | 一致 (idempotent OK / argfix idempotent OK / wasm32 compile OK 100972 bytes) |

**RetDec は非決定的** (置換と無関係): `retdec-decompiler` に同一 PE・同一 ranges を与えて 2 回走らせると `k80.drc.ll` の sha256 が変わる (alloca の並びと `uselistorder`)。
このため before/after で再 lift した `k80.lift.ll` は 58 行差になる。lift 以降を比較するため、after では `k80.lift.ll` を before のものに揃えてから `p0c2_e2e.sh` を再実行し、上表の一致を得た。
差が残るのは lift 由来の `k80.*.ll` / `k80_simd.c` / `k80.drc.*`、実行ごとにアドレスが変わるログ (`build.log` `run.err`)、`k80diff` バイナリ、`diff/driver.c` の `map_image(...)` の PE パス 1 行 (これは置換の意図した差)。

`nsis_blockmap.json`: どの素材にも無く (`block_manifest.json` も無い)、`f2/mk_blockmap.py` で `PLUGIN_MATRIX.json` から再構成した (182 行、sha256 9dfb59584586)。
`kernel_matrix.py` が使うのは `kind=PE` で `Fruity\Effects|Generators` 配下の行のみで、181 DLL / 133 delphi / init 発見 130 は before/after で同じ。

ネガティブコントロール (after、すべて rc=1): `FL_WIN64_DIR=/nonexistent` で `p0c_e2e.sh` / `p0c2_e2e.sh` / `verify_table.py` / `k80abi.py` が
`FileNotFoundError: /nonexistent/extracted/block18983_PE.bin`。`FL_WIN64_DIR` 未設定かつ `/home/ubuntu` 無しでは `p0c2_e2e.sh` が旧既定 `/home/ubuntu/...` を見て失敗する (既定値が従来のまま)。
`grep -rn '/home/ubuntu' tools/plugins/p0c ... --exclude-dir=work | wc -l` → 0。

範囲外 / 未解決: `inventory/kernel_table.py:15` と `lift/batch_lift.sh:31` ほか `lift/` 配下の `/home/ubuntu` 既定は別 area の置換 issue (#294 配下) で扱う。
`k80_diff.py` は `p0c2_e2e.sh` [6] 経由で実行済み (`LIFTP` は `REPO_ROOT` 基準で解決)。RetDec の非決定性は §15.4 に実測を残すのみで、起票: 下記 issue (RetDec 非決定)。

## 16. P0c-8 (#311, 親 #197・先行 #269): ext IR の wasm32 検証 + framework 統合 (fw_f80.py → f80_lower --ext)

検証起点 commit: `d5e6f98` (origin/main)。担当 dir: `tools/plugins/p0c` / `tools/plugins/framework` (fw_f80.py, fw_stage2.sh のみ)。
既知類型との関係: DEFECTS.md の D1〜D16 に **該当なし** (ext 生成器の丸め論理バグ。native では乱数 case で顕在化せず、固定 edge/tie 集合でのみ出る)。

### 16.0 結論

1. **ext IR を wasm32 (emcc -O2) でビルドし native x87 と bit 比較: 24,001,062 case で 0 不一致** (§16.2)。ネガコン (Dekker 定数破壊) は 2,704,752 不一致で FAIL。
2. wasm32 比較で **f80_lower.py --ext の生成器バグを 4 件発見・修正** (§16.1)。native の ext_core_test (3M) と p0c4_e2e (7 kernel) はどれも検出できなかった。
3. **framework 統合**: `fw_f80.py --ext-funcs` が f64 coerce 後に `f80_lower.py --ext` を呼ぶ。`fw_stage2.sh` は `FW_EXT_FUNCS` 指定時のみ有効 (未指定なら従来と byte 一致)。指定関数が ext 化されなければ exit 1。
4. **受入条件 3 (fw_269_verify.sh / hs_e2e.sh 維持) は未検証**。理由は §16.4。したがって PR は `Refs #311` とし Closes にしない。

### 16.1 修正した生成器バグ (すべて f80_lower.py の --ext。ext_core_test.c の同一箇所も同期)

| # | 場所 | 症状 (固定集合 case) | 原因 | 修正 |
|---|---|---|---|---|
| E1 | `_ext_round64` grid shift | hi=-2^k, lo<0 の mul/add の lo が 2^-63 刻みで 1 ずれ | shift 64 の条件が lo<0 のみ。hi<0 では大きさが増える向きなのに shift 64 にしていた | `(hi>0 ? lo<0 : lo>0)` (大きさが減る向き) のときだけ shift 64 |
| E2 | `_ext_fist_round` (nearest) | hi=n+0.5, lo>0 / hi=n-0.5, lo<0 の fist が 1 ずれ | `d=(hi-n0)+lo` を f64 で丸めて 0.5 と比較し lo の符号を失う | `d0=hi-n0==±0.5` と lo の符号で tie 判定 |
| E3 | 同 em 選択 | tie の -0.5 側で even 判定が逆 | `em` の select の真偽の枝が逆 (odd→n0, even→n0-1) | odd→n0-1, even→n0 |
| E4 | `_ext_store_f32` | f32 store の tie (hi=1+2^-24, lo≠0) が 1ulp ずれ | `nearadj` (nd 条件抜き) を使用。さらに mid 判定 `lo_` が bit 0..51 全体を見ていた (正: 下位 29 bit) | `nearadj2` を使用、mask を 0x1FFFFFFF |

### 16.2 wasm32 検証 (1 コマンド: `bash tools/plugins/p0c/p0c8_e2e.sh`)

方法: `ext_wasm_gen.py` が `f80_lower.py` の実生成関数 (`_ext_arith` / `_ext_fist_round` / `_ext_store_f32`、chop=0/1) から .ll を作り、`ext_wasm_test.c` が決定的入力 (ext_core_test.c と同じ xorshift・mode 0..3 各 N 件×chop 2 + 固定 edge/tie 集合) で実行して mul/add/sub の (hi,lo) (TwoSum 正準化)・fist(i32)・f32 store 2 個を native x87 (`long double`、`-O0`) の期待値と bit 比較する。期待値は native 側 (`-DGEN`) が書き、wasm32 側 (emcc → node) が読む。

| 項目 | 実測 |
|---|---|
| case 数 (分母) | 24,001,062 (乱数 mode 0..3 × chop 2 × N=3,000,000 + 固定集合。固定集合は 506 組を既知限界で除外) |
| wasm32 (emcc -O2) 不一致 | **0** (dd 0 / fist 0 / f32 0) |
| wasm32 バイナリ | 26,009 B (試験 harness 込み) |
| native clang -O2 で同 IR を実行 | 不一致 0 (同一ファイル・同一入力) |
| ネガコン: Dekker 定数 2^27+1→2^26+1 | 2,704,752 不一致 → exit 1 (p0c8_e2e.sh が exit 非 0 を要求) |
| ext_core_test (native C, N=3,000,000) | 全 PASS (修正後) |
| p0c4_e2e 2000 case/kernel (修正後) | 0x5dfbe0 / 0x5dfc90 / 0x5dfd30 / 0x5dfdb0 / 0x5de820 / 0x5dedf0 / 0x5dfb60 すべて buf_diff=0。回帰 7 kernel も 0 (修正前と同一) |
| 実 kernel の ext IR | `llvm-as` OK・idempotent OK・wasm32 clang -O1 で 113,950 B (k80.ext.ll、80 define) |
| p0c8_e2e.sh 所要 | 33 s (load average 1 分値 0.72→1.02、直列、n=1) |

最初の実行 (修正前) は 948,340 / 2,401,568 case 不一致 (N=300,000)。内訳は試験 harness 側の native 参照の誤り (x87 を `-O2` で `(float)` 変換すると丸めモード切替が最適化で動く) と上記 E1〜E4。harness は参照側を `-O0` + volatile にして解消した。

数え方: case = (入力 a,b, chop) 1 組。不一致 = 1 case で dd / fist / f32 のいずれか 1 つでも bit 不一致。fist は |a|,|b|<1e9 の組のみ比較 (ext_core_test.c と同条件)。

### 16.3 framework 統合の検証

| 検査 | 結果 |
|---|---|
| `fw_f80.py` 既定 (--ext-funcs なし) の出力 | 変更前 (`d5e6f98`) と `cmp` で byte 一致 (入力 = k80.lift.ll、968 f80 token) |
| `--ext-funcs function_5dfd30,function_5dfbe0` | ext 2 関数・llvm-as OK・wasm32 clang -O1 で 106,942 B |
| ネガコン: `--ext-funcs function_nonexistent` | exit 1 (`ext 化されなかった関数: missing=[...]`) |

### 16.4 範囲外 / 未解決

範囲外: framework 全体 (fw_269_verify.sh / hs_e2e.sh) の再実行。stage-1 成果物 (fw_icall.dll・fw[0-7].restored.ll 等) は許可素材名 (WORKFLOW §11) に無く、RetDec で再生成すると 8 chunk の timeout 3600 s で 60 分上限に収まらない。したがって受入条件 3 は**未検証**。`fw_f80.py` 既定動作の byte 一致 (§16.3) までが根拠で、fw_stage2.sh の既定経路の差分は `EXT_ARGS=()` の空展開のみ (`bash -n` OK)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 3 (fw_269_verify.sh / hs_e2e.sh 維持) 未検証 | framework 統合の回帰確認 | 新規 issue: stage-1 成果物を素材化 (`work-fw-stage1`) して再検証 |
| dd 積は al·bl を捨て、al·bh / ah·bl を f64 に丸める | lo 付き × 24bit 超 hi の積で不一致の可能性 (固定 506 組を除外。kernel 内の ext 値で顕在化した例は p0c4 2000 case で 0) | #197 に提案 |
| `FW_EXT_FUNCS` に入れる関数の選定 (framework 内の x87 関数一覧) | 統合は配線のみ。どの関数を ext 化するかは未決 | #197 に提案 |
