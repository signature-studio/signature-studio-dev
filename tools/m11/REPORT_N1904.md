# REPORT N1904 — 新規 12 site (引数 20) の発生段の切り分け (#1904, 親 #1702)

既知類型との関係: 該当なし (測定と切り分けのみ。コード変更なし)。
親: #1702 → #1532 (`REPORT_N1532.md` §6)。残りの二分探索は子 issue に分離 (§6)。

## 1. 結論

- `m11_post.py` (sigfix 段) は犯人では**ない**。測定 commit `7e149974` と `392d8ba5` の `m11_post.py` に同一の入力 IR を与えると、0 詰め site 1,049 / 引数 2,064 の pad 一覧が**完全一致**した (`cmp` 一致)。
- 新規 12 site の caller (`function_442320`・`function_4441c0`・`function_4441f0`・`function_457340` 系) は、素材の `work-m11` (`boot_final.ll`・`boot0..3.lift.ll`・`pilot.lift.ll`) のどこにも**定義が無い**。post 段は関数を増やさないので、差は関数の発見・リフト範囲 (lift 段より上流) にある。
- `392d8ba5` の ldfix (F4 含む) を素材 IR に当てても 0 詰め数は動かなかった (1,049 / 2,064、pad 一覧一致)。ただし素材 IR は旧 ldfix 適用済みなので、これは F4 段の完全な再現ではない (§7)。
- したがって原因 commit は**未特定**。特定には `lift → merge → passes → ldfix` を含む full 再生成を commit ごとに回す必要があり、1 run に収まらない (§6 の子 issue)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 比較 commit | `7e149974` (旧) / `392d8ba5` (新)。両者の `tools/m11` と `tools/shared` を `git archive` で別 dir に展開 |
| 入力 IR | `work-m11` の `tools/m11/work/boot_final.ll` (md5 `31f82201…`、10 Oct 生成)。両 commit で同一入力 |
| PE | fl-win64 `extracted/block00031_PE.bin` (`$RUNNER_TEMP/fl-win64` に展開) |
| 実行環境 | 4 vCPU、`~/.local/agent-py` の python (capstone / pefile)、load 0.10〜0.12 |
| 所要時間 | `m11_post.py` 1 回 0.86 s (旧) / 0.92 s (新)。`ldfix.py` (392d8ba5 版) 1 回 34.4 s (rc 0) |

## 3. 実測値

| 項目 | 旧 `7e149974` | 新 `392d8ba5` | 差 |
|---|---|---|---|
| `m11_post.py` 0 詰め call site | 1,049 | 1,049 | 0 |
| 0 詰め引数 | 2,064 | 2,064 | 0 |
| pad 一覧 (`--pads`) | — | — | `cmp` 一致 (IDENTICAL) |
| post 出力 IR (`final3_base.ll` 相当) | — | — | `cmp` 一致 (IDENTICAL) |
| `392d8ba5` ldfix 適用後に post (`--pads`) | — | 1,049 / 2,064 | 旧 pad 一覧と完全一致 (`only_new` 0 / `only_old` 0) |

`ldfix.py` (392d8ba5) の末尾行: `F1=0 F1v=0 F2=0 F3a=2 F3b=0 F3c=33 F4=10 (errors=0)`。

## 4. 新規 12 site の caller の所在

| caller | 素材 IR での定義 |
|---|---|
| `function_442320` | 無し (`boot_final.ll`・`boot*.lift.ll`・`pilot.lift.ll` の全てで grep 0 件) |
| `function_4441c0` / `function_4441f0` | 無し (同上) |
| `function_457340` 〜 `function_457860` (9 site) | 無し (同上) |
| callee `function_412d60` | 有り (`boot0.lift.ll` の `define`、`boot_final.ll` L115569) |
| callee `function_441fc0` / `function_443f90` | 有り (`boot0.lift.ll`) |

`REPORT_N1532.md` §5 の観察 (新規 caller は旧 `boot_final.ll` に定義が無い) は、素材でも同じく再確認できた。

## 5. 切り分けの根拠と限界

- 段ごとの入力 IR が素材に揃うのは `lift`・`boot_final`・`boot_final3` のみ。`merge` / `asmfix` / `passes` / `genstubs` は `boot_all.ll` (11:14) と `boot_allfix.ll` (02:34) が残るが、旧版・新版の両方が無いので比較できない。
- `boot5.lift.ll` / `boot6.lift.ll` は素材に無い (`m11_gen_ir2.sh` で条件付き追加)。`m11_extra_ranges5.txt` と `m11_wndclass_scan.py` (WNDPROC 閉包) は 7e149974..392d8ba5 の間で変わっていないか、変わっているかの確認が未了。
- `m11_tail.py` の反復 (`tail_extra.json`) は素材にあるが、旧版の反復結果が無いので比較できない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 新規 12 site の caller (`function_442320` ほか) を生む段の特定。lift 範囲 (boot0〜6) と tail 反復の commit 単位の二分探索 | 旧 1,963 と新 1,983 の差の説明が無い | 子 issue #1997 `[M11-N131]` (本 PR で起票) |
| `392d8ba5` の full 再生成 IR が素材に無い | 段ごとの比較が IR 単位でできない | 上と同じ子 issue #1997 |

## 7. 検証

- `m11_post.py` 旧版・新版の pad 一覧と post 出力 IR の `cmp` 一致 (§3)。
- `ldfix.py` (392d8ba5) の rc 0・`errors=0` (§3)。
- 素材 md5: `boot_final.ll` = `31f82201…` (REPORT_N1702 と一致)。

## 8. 差分

- 測定 commit: `392d8ba5` (新) と `7e149974` (旧)。両者の `tools/m11` を `git archive` で別 dir に展開して実行 (作業ツリーの `tools/m11` は変更していない)。
- 本 REPORT の commit 以外に、`tools/m11` のコード差分は無い。
