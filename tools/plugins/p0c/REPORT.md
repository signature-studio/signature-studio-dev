# tools/plugins/p0c REPORT — kernel 表妥当性検証 + f80 assessment (CAB-196)

> **正本**: `tools/plugins/p0c/REPORT.md` (§1〜§7)。§8 以降は付録 `REPORT_APPENDIX_A.md`〜`REPORT_APPENDIX_F.md` に
> **無変更で分割移動** (#378, `docs/DOC_MAP.md` §1 の 250 行上限)。付録索引は本ファイル末尾。

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
bash tools/plugins/p0c/p0c_e2e.sh      # 初回実測 355 秒 (work/ 無し・HEAD 1d63f01f・#893)。work/ 付きは短縮
```

### 6.1 CI 準備後の実測 (#893)
- agent-setup が `$HOME/.local/agent-py` の venv に `pefile` `capstone` `numpy` を入れ、PATH 先頭に置く。runner の `pip install` は不要。
- HEAD `1d63f01f`・`work/` を削除したクリーン状態で `p0c_e2e.sh`: **rc=0 / 355 秒 / `== e2e OK ==`**。`[2]` は kernel_matrix 走査を実行 (skip なし)。
[1] kernel_table.py (表復元) → [3] verify_table.py (130 DLL×80 kernel 再検証) → [5] f80_assess.py (分類) → [6] f80_micro (実測)。コミット対象は p0c 直下の script 3 本 + e2e + REPORT (work/ は gitignore)。

## 7. ユーザ依頼事項 / 次タスク提案
- **用語定義の確認**: 指示の「helper 9件・distinct 6名・Harmless i256 trap 6箇所」に一致する測定量が残骸に無い (§2.6 の対応候補を提示)。出所 (前回 run の進捗メモ等) を頂けると REPORT を追記できる。
- 次タスク案 (CAB-196 ticket 本体の続き): (1) f80→f64 lowering pass の実装 (§3.4 の 4 点, i64 保持含む) + ARG pass (xmm3/stack, ir7/ir8 系) 再適用; (2) 55/80 f80 無し kernel から差分試験 (native_ref 汎用化 — kernel_args_raw.json の interface 抽出済み); (3) capstone disp_size quirk の共有 fix を inventory 正規化系へ反映。

## 8〜16. 付録索引 (#378 で REPORT.md から無変更で分割移動)

節番号・見出し・測定値は移動前と同一。節間の相互参照 (例: §11.3) は下表で該当付録を引く。

| 節 | 内容 | 付録 |
|---|---|---|
| §8 | P0c-2 (CAB-241): f80→f64 lowering pass の実装と検証 | `REPORT_APPENDIX_A.md` |
| §9 | P0c-3 (CAB-251): RetDec x87 スタック模型修復 pass | `REPORT_APPENDIX_A.md` |
| §10 | P0c-4 (CAB-196 継続): ext-emulation mode のバグ修正と 2 kernel bit-exact 化 | `REPORT_APPENDIX_B.md` |
| §11 | P0c-4 (CAB-253): ARG pass の ABI 推定強化 | `REPORT_APPENDIX_C.md` |
| §12 | P0c-5 (#269): 0x5dfdb0 / 0x5de710 の残差はハーネス/e2e 側の欠陥 | `REPORT_APPENDIX_D.md` |
| §13 | P0c-7 (#310): 0x5df610 / 0x5e0d80 bit-exact | `REPORT_APPENDIX_D.md` |
| §14 | P0c-6 (#277): native crash 7 / abi-mismatch 7 kernel の原因 | `REPORT_APPENDIX_E.md` |
| §15 | 環境パス置換 (#346) | `REPORT_APPENDIX_E.md` |
| §15.4 | #360: 追加素材での full e2e before/after (main で #378 後に追記) | `REPORT_APPENDIX_E.md` |
| §15.6 | #346 受入 2: 現 HEAD (4b3616e5) での置換前後 e2e 一致 | `REPORT_APPENDIX_F.md` |
| §16 | P0c-8 (#311): ext IR の wasm32 検証 + framework 統合 | `REPORT_APPENDIX_F.md` |
| §18 | #197: 80 kernel の最終センサス (測定 HEAD `6444b186`・非 ext 鎖 67 測定 / buf_diff=0 は 49) | `REPORT_APPENDIX_H.md` |
| §19 | #2182: 18 kernel の buf_diff 0 化 (修復と検証) | `REPORT_APPENDIX_H.md` |
| §20 | #197: 未測定 13 kernel と Group B 12 kernel の分類 | `REPORT_APPENDIX_H.md` |
| §21 | #3439: 0x5e12b0 の ucomiss 被演算子・flags を接続し census に入れる (測定 commit `14731ce2c`・戻り値 2001/2001) | `REPORT_APPENDIX_I.md` |
| §22 | #3513: 戻り値の機械語 slot (`ret_slot`) を分類し、xmm0 の kernel を戻り値試験 [5b] の gate に入れる (測定 commit `9c38a83e4`・xmm0 1 件・負論対照 2 本 FAIL) | `REPORT_APPENDIX_I.md` |
| §23 | #3280: 0x5dffc0 の 10000 case 残差 (x87 fsincos の 66-bit π 縮約) の解消 (測定 commit `9e49eb950`・buf_diff 3 → 0) | `REPORT_APPENDIX_J.md` |
| §24 | #3281: GLOBAL_INITS を PE の .data から読む pass に置換 (測定 commit `74ae2bbf2`) | `REPORT_APPENDIX_K.md` |
| §25 | #3951: 0x5e1280 の buf_diff=3996 の原因は k80_diff の 64bit xmm 引数の渡し方 (driver)。修復 `73409179c` で buf_diff=0 (2000/10000) | `REPORT_APPENDIX_L.md` |
| §26 | #5832 (E7): x86_fp80 ↔ i80 bitcast の展開。bit 一致 (`f80b_rt/run.sh`)・subnormal carry の修正・19165 の測定 | `REPORT_APPENDIX_M.md` |
| §27 | #3281 残件 B: 0x5e12c0 の ucomisd flags を `k80_ucomi_br.py` で jbe に接続し、手書き本体を外す (本 PR で BODIES 14→13。main の #6046 と合わせた現 head は 8 本・測定 commit `4541f8de3`) | `REPORT_APPENDIX_N.md` |
| §28 | #6046: 手書き本体 14 → 9 (x87 の 5 本を既存 x87fix の対象に入れ置換。測定 commit `ecadfb82d`・負論対照 5 本 FAIL → 0) | `REPORT_APPENDIX_O.md` |

## 26. #5832 (E7): x86_fp80 ↔ i80 bitcast の展開

- **結論**: `bitcast x86_fp80 ↔ i80` を整数のビット演算へ展開する (`expand_f80_bitcasts`)。 bit 一致・subnormal の修正・19165 の測定は `REPORT_APPENDIX_M.md` §1〜§3。 19165 は E7 が消え、次の類型 (`fp_extend` の libcall) で止まる (受入 1 未達)。
- 詳細・測定値・未解決: `REPORT_APPENDIX_M.md`。

## 17. #1366 (CI-26): lift 段の alloca 並び正規化と before/after 一致

- **方式**: `lift_ranges.sh` に opt-in 段 (`PLUG_CANON_ALLOCA=1`) を追加し、`ir5_patch` (A7 で uselistorder 除去済み) の後に `liftlib.passes.base.canon_alloca_order` を掛ける。正本は liftlib 側 (`passes/canon_alloca.py` は import のラッパ)。既定 0 のため他の lift は不変。p0c_e2e.sh の k80 lift だけ有効化。理由: 比較時だけ正規化すると `k80.lift.ll` 自体が揺れたまま残るため、lift 段で固定した。
- **測定 commit**: `d5959204`。
- **素材**: `fl-win64` (`[WIN64]` の `extracted/block18983_PE.bin`)、`toolchain-retdec` (`[RETDEC]`, RetDec v5.0)。`toolchain-emsdk` (`[EMSDK]`, clang-24)。
- **llvm-as**: `toolchain-emsdk` に `llvm-as` が無いため、システムの LLVM 18 の `llvm-as` を PATH に追加して `p0c2_e2e.sh` step [4] を通した (スクリプトは無変更)。

### 受入条件の結果

| 条件 | 結果 |
|---|---|
| 1. lift 段で canon_alloca 相当の正規化 | 達成 (上記 opt-in 段) |
| 2. 同一入力 2 回で `lift.ll` / `final.ll` の sha256 一致 | 達成。`lift.ll` `628fa71e...` 両 run 一致、`final.ll` `5a5aee3c...` 両 run 一致 |
| 2'. `drc.ll` (RetDec 生出力) の sha256 一致 | **決定により対象外 (CI-28 #1560)**。raw は実行ごとに揺れるため、比較は正規化後 (run_base + canon) の base で行う方針 (liftlib `REPORT_APPENDIX_1560.md`)。k80 で base 4/4 一致を再確認 |
| 3. 置換前後の p0c2 出力一致 (lift の取り直しなし) | 達成。canon 無し lift (`d38a7c66...`) と canon 有り lift (`628fa71e...`) を同一 p0c2 に通し、`p0c2_sweep.csv` が `cmp` 一致 |

### 実測 (HEAD `d5959204`・素の work/ から再生成)

| e2e | rc | 所要 | load (前→後) |
|---|---|---|---|
| `p0c_e2e.sh` (lift 込み・k80 80 kernel) | 0 | 514 s | 0.70 → 7.86 |
| `p0c2_e2e.sh` | 0 | 50 s | 7.86 → 3.98 |

k80 lift 単体の測定commit時点の旧所要時間は**記録しない**。測定時に RetDec を再実行したか `PLUG_REUSE_DRC=1` で再開したかの記録が無く、条件不明の数値は判定に使えないため。`b38ff403` 以降の所要時間は下記の 3 run を記録する。
- **再測定 (PM run と reviewer の実測・測定 commit 以降の差分分)**: 条件は `PLUG_CANON_ALLOCA=1` のみ。`PLUG_NO_STATIC_DETECT`・`PLUG_I32PTR_FUNCS`・`PLUG_REUSE_DRC` は未設定 (RetDec を実行)。素材は `fl-win64` と `toolchain-retdec` を展開して使用。入力は `kernel_table.json` から生成した k80 ranges (80 kernel。`tools/plugins/lift/kernel_ranges_balance.txt` と一致)。一時ディレクトリで実行。
  - 「所要」の定義: `lift_ranges.sh` 1 回の実行の lift 全体 wall (RetDec 段を含む)。「最終 `cleanup`」は `k80.retdec.log` 最後の phase の時間で、RetDec 段の内訳の 1 つ。
  - 測定 run は 3 回 (rc は記録のある run すべて 0):
    - PM run (HEAD `b38ff403`): 所要 2 s (秒精度)・最終 `cleanup` 1.76 s・`k80.drc.ll` = `b760d51a…`
    - reviewer 1 回目 (HEAD `b38ff403`): 所要は記録なし (旧記載の「4 s」は条件・定義が確認できないため採用しない)・`k80.drc.ll` = `aa52403e…`
    - reviewer 2 回目 (HEAD `1ad307fd`): 所要 4.4 s・最終 `cleanup` 2.93 s・`k80.drc.ll` = `097478ab…`
    - 所要の min–max: 2 s〜4.4 s (記録のある 2 run)
  - `k80.lift.ll` sha256 = `628fa71edeca59318c75e48287cc09e108b09894240b12b34393d64b80ac3b6f` (**一致**。PM run と reviewer 2 回目の 2 run で確認。全長)
  - `k80.final.ll` sha256 = `5a5aee3c…` (一致。先頭 8 桁のみ確認。全長は review 本文に無い)
  - `k80.drc.ll` sha256 は実行ごとに揺れる (受入 2' 未達の根拠。#1560 に紐づけ): `b760d51a…` (PM run) / `aa52403e…` (reviewer 1 回目) / `097478ab…` (reviewer 2 回目)。単独の値は参考にしない。
  - 注: 本 run (fix モード) では再測定していない (PM 指示)。上記は PM run と reviewer の実測の転記。
- 再測定不可 (履歴。HEAD `9d943df3` 時点の記録): 修正時点の runner には `toolchain-retdec` ([RETDEC]) が `$ARTIFACTS_DIR` に無く、`k80.drc.ll` と k80 の `work/` も無いため、k80 lift を再実行できなかった。この欠落は PM 判断事項。
- 再試行 (fix モード, HEAD `9d943df3`): `$ARTIFACTS_DIR` は `fl-win64` のみ。`[RETDEC]` の実体が無いため RetDec 段を実行できず、k80 lift を再実行していない (rc・所要・load・sha256 は未取得)。`oc_artifacts: fl-win64 toolchain-retdec` を PR 本文に追記した。この時点の再測定は未実施 (後続の HEAD `b38ff403` 再測定で実施済み。上記「再測定」行)。
- 一致判定 (受入条件 2・3) は lift の sha256 と `p0c2_sweep.csv` の `cmp` で行い、所要時間には依存しない。

### 検証の注記
- 置換前後の lift 比較は同じ `block18983_PE.bin` / 同じ 80 ranges。`before` は `PLUG_CANON_ALLOCA` 未設定、`after` は設定。p0c2 の before/after は `work/k80.lift.ll` を差し替えて各 1 回ずつ実行 (50 s / 51 s)。
- `argfix.ll` (中間 IR) のテキストは alloca 番号が変わるため before/after で byte 差が出る。最終判定の `p0c2_sweep.csv` は一致。

### 差分 (測定 commit 以降のコード差分)
測定 commit = `d5959204`。p0c 配下のコード差分は 0 (`git diff d5959204 HEAD -- tools/plugins/p0c` は `REPORT.md` の 32 行追加のみ)。

ただし k80 lift が実行する `tools/plugins/lift/lift_ranges.sh` は main 取り込み (`243f75d9`) で変わっている (`git diff d5959204 HEAD -- tools/plugins/lift/lift_ranges.sh`):
- `PLUG_NO_STATIC_DETECT` (RetDec に `--disable-static-code-detection`) を追加。展開は `${PLUG_NO_STATIC_DETECT:+...}` で、未設定時は空になる。
- `PLUG_I32PTR_FUNCS` の有無で `fix_i32_ptr_arg.py` を通す `i3.ll` 段を追加。未設定時は `cp` で従来どおり。

既定 (両変数未設定) の経路は、bash で展開を確認し引数・出力とも変わらないと判断した。`p0c_e2e.sh` は両変数を設定しない。`lift_ranges.sh` は `bash -n` を通る。

これは「差分 0」ではない。`WORKFLOW.md` §6 に従い、差分分 (k80 lift が通る `lift_ranges.sh`) を HEAD `b38ff403` で再測定した (上記「再測定」行。reviewer の実測。`k80.lift.ll` sha256 一致)。§17 の lift 514 s / p0c2 50 s は `d5959204` 時点の値。p0c2 は `k80.lift.ll` の sha256 一致により同一入力とみなし、再実行していない。

- **PM 判断 (#1366 コメント)**: 「既定経路の等価性での受入」(§6 例外 (b)) は**採用しない**。再測定で `k80.lift.ll` の一致を確認したため、例外は不要。受入 2' の未達 (生の `k80.drc.ll`) は #1560 [CI-28] に分割し、本 PR は `Refs #1366` の部分達成とする。
- 現 head は `b38ff403` 以降、REPORT.md (本節の記述) のみの差分。コード差分は無い。
