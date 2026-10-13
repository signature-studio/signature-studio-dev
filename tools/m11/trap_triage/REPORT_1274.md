# REPORT_1274 — ClassCreate ON の ok 退行 unit 190 の trap 経路 (#1274, 親 #912)

結論 (部分達成): unit 190 の ON の oob は、**現 main では `function_412e40` ではなく `function_407a50` で起きる**。REPORT_912 §3 の記録 (`412e40`) は、現 main では再現しない。trap の経路 (`6cf480 → 6cf2a0 → 6ced90 → 409410 → 407a50`) は実測できた。原因の特定・既存類型への分類・ON の ok 退行 0 は未達 (下記 §4 の起票先)。

既知類型との関係: 該当なし (未切り分け。原因特定は #1274 次 run で `407a50` の lift 内容を確認して判定)。

## 1. 測定条件

- 測定 commit: `851c342e` (origin/main、`Merge pull request #1466 from signature-studio/1275-m11-n78`)。本 PR は REPORT のみ変更で、`tools/m11` のコードは変えていない。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR` に指定)。`work-m11` を repo ルートに展開。`toolchain-retdec` を `$HOME/retdec`、`toolchain-emsdk` を `$HOME/emsdk` に展開 (`RETDEC_ROOT` / `EMSDK` に指定)。
- IR: `m11_gen_ir2.sh` rc=0 (44.9 s、`ldfix=applied`、F1=902、errors=0)。
- build: `M11_OV_CLASSCREATE=1 m11_build.sh` rc=0 (24.7 s、signature mismatch 0・undefined symbol 0)。OFF (`M11_OV_CLASSCREATE=0`) も rc=0。
- survey: `SV_RAW=1 node survey_units.mjs` (ON 12.2 s、OFF 12.8 s、いずれも load は低い)。

注: 最初の試行では `FL_WIN64_DIR` を `…/extracted/..` の形で指定したため、IR の PE パスと現 PE が一致せず build が `exit 1` で拒否された (`m11_build.sh` の PE 指紋検査が働いた)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` で IR を作り直して解消した。

## 2. 結果 (ON と OFF の unit 単位比較、942 unit)

| 構成 | ok | oob | abort | halt0 | miss | noproc | other |
|---|--:|--:|--:|--:|--:|--:|--:|
| ON (`M11_OV_CLASSCREATE=1`) | 869 | 15 | 2 | 7 | 47 | 1 | 1 |
| OFF (既定) | 870 | 16 | 0 | 7 | 47 | 1 | 1 |

kind が変わった unit (OFF → ON):

- 190: ok → oob (ok 退行。本 issue の対象)
- 304: oob → abort、555: oob → abort (`function_535c2e` の IR 未定義。#1275 の対象)

## 3. unit 190 の trap 経路 (ON・current main)

`SV_RAW=1 SV_ONLY=190` の生 frame (wasm の関数 index と命令 offset) を `oob_insn.py` で逆引きした。

| 順 | wasm fn (export 名) | offset | 命令 |
|--:|---|---|---|
| 1 | 1873 `function_407a50__lifted` | 0x13ce5c | `i64.load offset=0` (`[ptr-8]` 相当、`ptr = wrap(arg-8)`) |
| 2 | 1871 `function_407a50` | 0x13c7ce | `call 1873` |
| 3 | 1901 `function_409410__lifted` | 0x140eba | `call 1871` |
| 4 | 316 `function_409410` | 0x80ce8 | `call 1901` |
| 5 | 4473 `function_6ced90` | 0x21d263 | (呼出し元。`6ced90` は定数 `1028` を `409410` に渡す: `%m11sf2830 = trunc i64 1028`) |
| 6 | 4479 `function_6cf2a0` | 0x21dc9f | `call 6ced90` |
| 7 | 4482 `function_6cf480` | 0x21df06 | `call 6cf2a0` |
| 8 | 11520 `m11_tr_function_6cf480` | 0x346573 | (trampoline) |

- `410360` (0x41037d の `ICALL` 呼出し) は、この trap の frame に**現れない**。ON で差し替えた `410360` は経由していない。
- 生 frame が示すのは「trap 直前の関数は `407a50`」だけで、`407a50` に渡る引数の**実値は未測定** (probe 未挿入)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `407a50` の `i64.load [arg-8]` が見る実 pointer 値と、ON でその参照先の内容が変わる経路 (ON-only override の書込みか、`6ced90` の定数 1028 側か) | 原因の特定 (受入条件 1) が未達 | #1274 (本 issue、次 run) |
| 既存 DEFECTS 類型への分類 (受入条件 2) | 未達。`407a50` の lift 内容の確認が前提 | #1274 (本 issue、次 run) |
| ON の ok 退行 0 (受入条件 3) | unit 190 の 1 件が残る | #1274 (本 issue、次 run) |
| REPORT_912 §3 の `function_412e40` 記録と、現 main の `function_407a50` の差 | 記録の食い違い。どちらの IR/commit で起きたかは未切り分け | #912 (親 issue へ申し送り) |

## 5. 差分 (測定 commit から本 PR の HEAD まで)

測定 commit `851c342e` から本 PR の HEAD までの `tools/m11` のコード差分は 0 (REPORT_1274.md の追加のみ)。`git diff 851c342e HEAD -- tools/m11 ':(exclude)*.md'` は 0 行。
- `git status --porcelain=v1 -- tools/m11`: 本 commit の時点で 0 行 (作業ツリーに tools/m11 の未コミット変更なし)。
- `find tools/m11/trap_triage -type f -size +20M`: 0 件 (20MiB 超の blob なし)。
