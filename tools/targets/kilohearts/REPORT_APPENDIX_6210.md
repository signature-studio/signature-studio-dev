# REPORT 付録 (#6210 / KH-184): FUN_180fc6870 の宣言を float 1 引数にする census

親: #6160 (分割元 #6160 の停止報告)・本件は受入 2 (census の件数・既存規則への波及・gain/haas/gate の `.o` 不変)。
受入 1 (全経路の入力読み替え) は前 run の停止報告 (#6210 コメント) で確認済み。本付録は受入 2 の実測。

## 1. 規則 (`patches.py` の `ABI['delay']`・commit `d931ff801`)

- 測定 commit: `d931ff801` (コードを変えた最後の commit)。
- 変更: `FUN_180fc6870` の宣言 `ulonglong FUN_180fc6870(undefined8 ×4)` → `ulonglong FUN_180fc6870(float fParam)`、本体の `fVar3 = in_ZMM0._0_4_;` → `fVar3 = fParam;`。件数は各 1 件を assert。
- 根拠 (機械語 `0x180fc6870`〜`0x180fc6d6f`): 入力は xmm0 の下位 4 バイトだけ。入口で `movd edx,xmm0` (通常経路) と `vmovd eax,xmm0` (AVX 経路 `180fc6b50`) の 2 箇所で読む。rcx・rdx・r8・r9・r11 は入口で読まず、書いてから使う。
- 本体の `param_1`〜`param_4` は従来どおり未定義のまま残す。142 行目 (`FUN_180fdc320(param_1, ...)`) だけが `param_1` を読むが、これは既存の未定義値 (前 run で確認済み。本規則では変えない)。
- `FUN_180fc6d70` (別 callee) は変えていない。

## 2. census (`gtype_census.sh`・既定 FX = `bitcast,intload,stackpair,assoc,concat,gtype`)

| 測定 | delay emcc error 行 | 引数数不一致 | 型不一致 (演算・代入・ポインタ) | lane (V128・undefined1[N]) |
|---|---:|---:|---:|---:|
| 基点 `origin/main` `6e8a31479` | 290 | 57 | 67 | 166 |
| HEAD `d931ff801` (本 PR) | 273 | 41 | 67 | 165 |

- 差分: 引数数不一致 57 → 41 (-16)。基点の `FUN_180fc6870 ... expected 4, have 1` 16 件 (`auVar50._N_4_` を引数に渡す呼出し) が消えた。
- 基点と HEAD の emcc ログ差分 (エラー本文ごとの件数): `expected 4, have 1` (`FUN_180fc6870` の 1 引数呼出し) 16 件が消えた。`undefined1[64]` の member 参照 (`in_ZMM0._0_4_` の読みの除去) が 106 → 105。`expected 4, have 0` は 2 → 1 件だが、これは 935 行 (`FUN_180fc6870`) のメッセージが `single argument 'fParam' was not specified` に変わった分。基点 5111 行 (HEAD では 5115 行) の呼出しは `FUN_180fe3310()` (`expected 4` は別 callee の宣言) で、本規則とは無関係に残る。他の行は完全一致。`FUN_180fc6d70` の行は基点と HEAD で同一 (16 件のまま・未変更)。
- 0 引数呼出し `delay.c:935` `fVar23 = (float)FUN_180fc6870();` は残る (エラー本文は `single argument 'fParam' was not specified` に変わった)。呼出元 934 行は `FUN_1802ed7f0` 内で xmm7 を `mulss` (定数 `0x181563038`) した値を xmm0 に入れて呼ぶ。C の上で xmm0 の源をどう表すかは未確定 (issue #6210 の残件)。
- 本規則で件数が増えた行は無い (emcc error 行は 290 → 273 で単調減少)。

## 3. 既存規則への波及 (3594・3653・FUN_180fc6d70)

- 3594・3653 (`f2u(fVar3)` の指数マスク判定): 左辺 `fVar3` の型・名前は変わらない。`fVar3 = fParam` の float → 既存の `f2u(fVar3)` が従来どおり効く。規則 `3595`・`3653` の呼出し規則 (`FUN_180fdc6ec(f2u(fVar3))`) は件数 1 のまま通る (ABI 規則の assert が通過)。
- `FUN_180fc6d70` (3785・3909): 別 callee。本規則では変わらない。宣言・本体とも不変。

## 4. gain / haas / gate の `.o` 不変

- 基点 `origin/main` の `ghidra_route` (`git archive` 展開) で作った `.o` と、HEAD の `.o` を `cmp` (`gtype_census.sh <work> <base ghidra_route>` の第 2 引数):
  - gain: 1435 B・旧規則と一致
  - haas: 3217 B・旧規則と一致
  - gate: 3756 B・旧規則と一致
- 注: `FUN_180fc6870` は Gain / Haas / Gate の生成 C に現れない (`cmp` 0 差分はそのことと整合)。

## 5. 実行条件・所要 (実測)

- 素材: `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`)。`toolchain-emsdk` (emcc 6.0.12)。Ghidra 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。JDK 21 (temurin-21)。素材・ツールは repo 外 (`$RUNNER_TEMP/kh`)。
- 展開の注意: `toolchain-emsdk` は `emsdk/emsdk/` 配下に展開される。`emsdk_env.sh` は emcc を PATH に載せないため、`PATH=<emsdk>/upstream/emscripten:<emsdk>/upstream/bin:$PATH EMSDK=<emsdk>` で通す (REPORT_APPENDIX_4671 と同じ)。
- 所要 (HEAD `d931ff801`・`gtype_census.sh` + 基点 `.o` の比較): real 43.9 s (load 1.08 → 1.15、測定開始・終了時)。
- 基点 (`6e8a314`) の census 所要: real 44.3 s。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 934 行 (`FUN_1802ed7f0` 内 `fVar23 = (float)FUN_180fc6870();`・0 引数) の xmm0 源 (xmm7 の mulss 式) を C でどう表すか | 引数数不一致の残り 1 件 | #6210 の残件 (本 issue) |
| `FUN_180fc6870` の 1 引数呼出し 16 件 (`auVar50._N_4_` の lane) を、機械語で xmm0 の源と一致させたか | 本規則の呼出し側は字句上の一致のみ。lane の対応は未確認 (emcc は通すが数値は未検証) | #6160 [KH-181] (親 #5440) |
| 引数数不一致の残り 41 件 (`FUN_180fc6d70` 16 ほか) | Delay の emcc 不通過 | #5440 [KH-163] / #3847 [KH-73] (既存) |
