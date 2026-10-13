# #737 (LD-15): LSF 脱落修復 66e080・806740・666a60 の liftdiff 動的確認 (修復前後・native 比較)

**判定: 受入条件達成 (測定は完了し n=3 で記録)。ただし結論は 1 関数のみ判定可能で、806740 と 666a60 は両側で比較不能 (unexec)。**
親: #509 (LD-9) / REPORT_509.md §6 の起票依頼 5。前任の動的確認 (REPORT_509.md §4.4) は wasm 直接呼びで、liftdiff (native PE 比較) は未実施だった。

実測の起点: `061eadd6` (`ls737_liftdiff.sh` を追加した commit。§3 の初回実測はこの版で取得)。以降 `8cfbb222` までで、本測定の経路 (`tools/liftdiff/` と `ls737_liftdiff.sh` の実行部) は変わらない。`8cfbb222` で `ls737_liftdiff.sh` のコメント行のみ変更 (repo 外パスの除去)。`tools/m11/` の他スクリプトの差 (main 取り込み由来) は本スクリプトから呼ばれない。再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/m11/ldfix/ls737_liftdiff.sh`。
HEAD `8cfbb222` での再実行は §7 の通り実施済み (verdict 一致)。

## 1. 結論 (受入条件別)

| 受入条件 | 結果 |
|---|---|
| 66e080・806740・666a60 の修復前後を liftdiff で native と比較し、結果を実測で記録 (min–max、n≥3) | **達成**。修復前後それぞれ 3 回 (§3)。判定は 66e080 のみ比較可能 |
| 起動: `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` + numpy | **達成**。`fl-win64` / `toolchain-emsdk` / `work-m11` / `work-liftdiff` を展開し、numpy・capstone・pefile を pip で導入して実行 |

## 2. 方法

- **修復後**: `work-m11` の `boot_final3.ll` (ldfx 名 3335 件) を `tools/liftdiff/targets/m11.json` でそのまま使う。
- **修復前**: `boot_final3.ll` の 3 関数 (66e080・806740・666a60) の本体だけを `boot_final2.ll` の本体 (ldfx 名 0 件) に差し替えた IR (`tools/liftdiff/work/ls737_pre.ll`)。他の関数は修復後と同一。
  `boot_final2.ll` は修復前の正確な生成物ではなく近似である (修復前 IR の再生成は #351 の範囲)。
- **native**: `block00031_PE.bin` (fl-win64 の FLEngine_x64.dll)。
- **状態**: `work/m11/boot_state.json` (work-liftdiff 同梱) を両側に与える。boot state を与えない単独実行では 806740 と 666a60 が両側で fault したため、状態ありで揃えた。
- **パターン**: liftdiff 既定の 11 パターン (`cases.PATTERNS`)。関数ごとに 11 case。
- **IR の出所**: `work-m11` の `boot_final2.ll` / `boot_final3.ll` (snapshot の `.ll`) を直接使用。`m11_build.sh` の `ir_conditions` ゲートは通していない。`work-m11` は `docs/WORKFLOW.md` §11 で #516 以前の生成とされ survey の基準には使わない。本測定は修復前後の比較専用で、絶対的な基準にはしない。

## 3. 実測 (n=3)

所要 (1 batch、3 関数) は run ごとに異なる。`061eadd6` 当時の初回 run: post 7.755〜7.783 s、pre 6.781〜7.095 s (`load1` 0.55〜1.14)。`8cfbb222` の再実行 run (§7): post 8.734〜8.786 s、pre 7.631〜7.996 s (`load1` 0.70〜1.21)。両 run の値は別 runner の計測で、比較には使わない。

| 関数 | 修復前 (3 回とも同一) | 修復後 (3 回とも同一) |
|---|---|---|
| 66e080 | mismatch。`both_fault` 3 / `wasm_trap` 8。tags: xmm_arg_drop, fp_flag_unreflected, wasm_trap | mismatch。`native_fault` 3 / `diff` 8。tags: xmm_arg_drop, zero_init_drop, fp_flag_unreflected |
| 806740 | unexec (native_null_deref_all_patterns)。`both_fault` 11 | unexec (native_null_deref_all_patterns)。`both_fault` 11 |
| 666a60 | unexec (native_fault_all_patterns)。`both_fault` 11 | unexec (hang)。`both_fault` 8 / `hang` 3 |

各 batch の 3 回は verdict・case 分布が完全に一致した (min–max で幅 0)。

## 4. 解釈

- **66e080**: 修復前は wasm が 8 パターンで trap (`wasm_trap`)。修復後は trap が消え、値の差 (`diff`) になった。残るのは `xmm_arg_drop` と `zero_init_drop` で、修復で直したのは脱落の一部だけ。判定は mismatch のまま。
  実測した差分 (修復後): arena `0x1030` の native 値 `0x22476000` / wasm `0xffffffff` など。
- **806740**: native が全パターンで null deref し、wasm も trap するため、差分判定に入れない。修復の効果は測れない。
- **666a60**: 修復前は両側 fault。修復後は native 側が 3 パターンで hang (wasm 側は `both_fault` 8 / `hang` 3 の内訳を含む)。
  native が hang するため、比較不能。REPORT_509.md §1 の残存誤り (ループ内 store) は本測定の対象外。

## 5. 未解決 (起票先は PM 判断、本 run では起票しない)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 66e080 の `xmm_arg_drop` / `zero_init_drop` が修復後も残る (mismatch) | 66e080 は脱落修復後も一致しない | PM 判断 (xmm 引数の脱落は REPORT_509 の範囲外) |
| 806740 は native 側が全パターンで null deref し、判定不能 | 修復の効果が測れない | PM 判断 (native 側の入力状態の作り直し) |
| 666a60 は native が hang (修復後) し、判定不能。REPORT_509 §6 のループ内 store 残存誤りとは別に確認が要る | 修復の効果が測れない | #735 (LD-13。666a60 のループ内 store と同型の誤りを扱う) |

## 6. 成果物

| パス | 役割 |
|---|---|
| `tools/m11/ldfix/ls737_liftdiff.sh` | 修復前後 IR の作成・build・3 回ずつ batch・判定の一覧 (1 コマンド再現) |
| `tools/m11/ldfix/REPORT_737.md` | 本書 |

生成物 (`tools/liftdiff/work/`) は gitignore 対象で commit しない。

## 7. 再実行 (HEAD `8cfbb222`、差し戻し対応 run)

- 素材 `fl-win64` / `toolchain-emsdk` / `work-m11` / `work-liftdiff` が `ARTIFACTS_DIR` に実在することを確認して展開した。`FL_WIN64_DIR` は fl-win64 の展開先。`toolchain-emsdk` は runner 上の既存 `/opt/emsdk` (emsdk 6.0.12、`[EMSDK]` と同じ pin) を使い、上書きしていない。numpy 2.5.4・capstone 5.0.7・pefile 2024.8.26 を pip で導入した。
- `bash tools/m11/ldfix/ls737_liftdiff.sh` を foreground で実行: rc 0、`LS737_LIFTDIFF DONE`、所要 1 分 8 秒。
- verdict は §3 の表と全 6 batch で一致した (下の出力は script の出力そのまま)。

```
[ls737] post r1 8768 ms  load1=0.70
[ls737] pre r1 7889 ms  load1=1.18
[ls737] post r2 8786 ms  load1=1.08
[ls737] pre r2 7996 ms  load1=0.99
[ls737] post r3 8734 ms  load1=1.21
[ls737] pre r3 7631 ms  load1=1.11
[ls737] pre r1 function_66e080 verdict=mismatch reason=None cases={'both_fault': 3, 'wasm_trap': 8} tags=['xmm_arg_drop', 'fp_flag_unreflected', 'wasm_trap']
[ls737] pre r1 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] pre r1 function_666a60 verdict=unexec reason=native_fault_all_patterns cases={'both_fault': 11} tags=[]
[ls737] pre r2 function_66e080 verdict=mismatch reason=None cases={'both_fault': 3, 'wasm_trap': 8} tags=['xmm_arg_drop', 'fp_flag_unreflected', 'wasm_trap']
[ls737] pre r2 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] pre r2 function_666a60 verdict=unexec reason=native_fault_all_patterns cases={'both_fault': 11} tags=[]
[ls737] pre r3 function_66e080 verdict=mismatch reason=None cases={'both_fault': 3, 'wasm_trap': 8} tags=['xmm_arg_drop', 'fp_flag_unreflected', 'wasm_trap']
[ls737] pre r3 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] pre r3 function_666a60 verdict=unexec reason=native_fault_all_patterns cases={'both_fault': 11} tags=[]
[ls737] post r1 function_66e080 verdict=mismatch reason=None cases={'native_fault': 3, 'diff': 8} tags=['xmm_arg_drop', 'zero_init_drop', 'fp_flag_unreflected']
[ls737] post r1 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] post r1 function_666a60 verdict=unexec reason=hang cases={'both_fault': 8, 'hang': 3} tags=[]
[ls737] post r2 function_66e080 verdict=mismatch reason=None cases={'native_fault': 3, 'diff': 8} tags=['xmm_arg_drop', 'zero_init_drop', 'fp_flag_unreflected']
[ls737] post r2 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] post r2 function_666a60 verdict=unexec reason=hang cases={'both_fault': 8, 'hang': 3} tags=[]
[ls737] post r3 function_66e080 verdict=mismatch reason=None cases={'native_fault': 3, 'diff': 8} tags=['xmm_arg_drop', 'zero_init_drop', 'fp_flag_unreflected']
[ls737] post r3 function_806740 verdict=unexec reason=native_null_deref_all_patterns cases={'both_fault': 11} tags=[]
[ls737] post r3 function_666a60 verdict=unexec reason=hang cases={'both_fault': 8, 'hang': 3} tags=[]
LS737_LIFTDIFF DONE
```

- 所要 (本 run の batch): post 8.734〜8.786 s、pre 7.631〜7.996 s (§3 の初回 run とは別 runner の値)。
- 初回 run のログは gitignore 対象の work/ 配下のため commit しない。本 run のログは上記の貼り付けが正。
