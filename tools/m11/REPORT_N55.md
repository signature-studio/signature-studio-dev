# REPORT_N55 — #955 [M11-N55]: sigfix 0 詰め site の liftdiff 差分ハーネス検証

親: #131 / 依存: #122 (CLOSED)。対象: `tools/m11/results/sigfix_zeropad_remaining.tsv` (0 詰め site 1,049 行)。
REPORT §9 (#131) の「次の一手」を実施した結果。

**検証 HEAD**: `d38e8961` (origin/main `66487318` 取り込み後) の harness コード。判定表は fix run (2026-10-13) で再生成した (§6)。
環境: 4 vCPU runner, `work-m11` / `work-liftdiff` / `fl-win64` (`block00031_PE.bin`) / `toolchain-emsdk` / `toolchain-retdec` 展開済み, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| 0 詰め site 1,049 件 | **一致 174** / **不一致 289** / **未到達 586** (site 単位, `m11_zeropad_liftdiff.py` の集計) |
| callee の内訳 | 対象 callee 217 件 → 一致 32 / 不一致 67 / 未到達 118 (callee は複数 site に出現する) |
| 再現性 | 同一入力 (217 callee の batch) で 2 回実行 (n=1, n=2)。判定表 TSV は n=1・n=2 でバイト一致 (sha256 `4b77b20f…`)。batch 出力は verdict・tags が 217 行全て一致。`cases` の一部 (`function_df7c00` の wasm 側 timeout 判定、`function_6edf50` の wasm_detail) は実行ごとに揺れる |
| 所要 | batch 1 回 47 秒 (n=1) / 48 秒 (n=2), 217 callee, 4 shards, load 0.66 → 1.62 (n=1 の開始・終了の uptime) |
| 不一致 site のうち tag が引数 k を指すもの | 28 site (17 callee) |
| 適用範囲 | 本表は **217 callee の batch** での結果。全 closure (7,421 関数) での判定ではない (§4・§6) |

受入条件「0 詰め site のうち差分ハーネスで実行されるものを優先順に検証し、結果 (一致 / 不一致 / 未到達) を REPORT に実測値で残す」は、
**全 1,049 site を判定した** (実行される 463 site は一致/不一致、残り 586 site は未到達)。

## 2. 判定の定義

* 対象 callee (`sigfix` が引数を 0 詰めした call の呼出先) の harness 採点 (`function` 単位, 9 pattern) を site に写す。採点は batch 構成に依存する (§4)。
* **一致** = callee の verdict が `match`。
* **不一致** = callee の verdict が `mismatch`。tag が `arg<k>` を指す場合は `arg` 列に記録 (0 詰めした引数そのものの差分を示すか)。
* **未到達** = callee の verdict が `unexec` (native が fault / null deref / hang / 未対応シグネチャ), または batch 対象外 (`not_in_batch`)。
* **入力 status** (`sigfix_zeropad_remaining.tsv` の列, `m11_argrecover.py` L205-209 が付与): `matched` = caller 機械語で callee への直接 call が IR の k 番目と対応づいた (1,004 site)。`unmatched` = caller 内の直接 call 数が IR の call 数と一致しない、または k が範囲外で対応が取れない (22 site)。`no_pdata` = caller が .pdata 区間外で機械語を取れない (23 site)。判定表の status 列はこの値をそのまま写す。
* 優先順: 判定確定 (不一致 → 一致) → 未到達。同順位内は callee の出現数が多い順。

判定表: [results/sigfix_zeropad_liftdiff.tsv](results/sigfix_zeropad_liftdiff.tsv) (1,049 行, 優先順付き)。
再現手順は §6。batch.jsonl は gitignore 対象の `tools/liftdiff/work/` 配下に置き、commit しない。

## 3. 内訳

| 判定 | site | callee 数 | 主な callee (site 数) |
|---|---:|---:|---|
| 不一致 | 289 | 67 | `function_40ae70` (71), `function_40d210` (34), `function_6bed60` (16), `function_65f270` (12), `function_53de80` (9) |
| 一致 | 174 | 32 | `function_418190` (111), `function_60ae30` (12), `function_63a6d0` (7), `function_6774b0` (6), `function_737f70` (4) |
| 未到達 | 586 | 118 | callee 単位: native null deref 50 / native fault 50 / hang 12 / unsupported_sig 6。site 単位: null deref 322 / native fault 231 / unsupported_sig 20 / hang 13 |

不一致 site のうち evidence が引数 k を名指しするもの (28 site, 17 callee): `function_4093f0` arg0 (1), `function_413770` arg0 (1), `function_5b02a0` arg0 (2), `function_651400` arg0 (1), `function_660cc0` arg4 (1), `function_6613b0` arg0 (1), `function_67db00` arg0 (1), `function_6a09b0` arg0 (1), `function_6be4f0` arg0 (3), `function_6bed60` arg0 (5), `function_6c3700` arg0 (4), `function_6c5930` arg0 (1), `function_6ee1a0` arg0 (1), `function_7f2fe0` arg0 (1), `function_9206c0` arg0 (2), `function_bb1ad0` arg0 (1), `function_cc33d0` arg0 (1)。
(残りの不一致 site は callee 単位の差分で、0 詰め引数そのものとの対応は tag から確定できない。)

## 4. 解釈と制約

* **判定は batch の構成に依存する**。217 callee の batch と、全 closure の途中結果 (§6) の両方に現れた 134 callee を比べると、5 callee (`function_9206c0`, `function_d74660`, `function_67db90`, `function_67d9b0`, `function_47b3e0`) で verdict / tag が異なった。batch 内で同居する他の関数の実行が影響している可能性があるが、原因は未切り分け。したがって「callee 単独で決まる」という前提は成り立たず、本表は 217 callee batch の結果として扱う。
* **一致 = 0 詰め引数が意味的に正しいことの証明ではない**。harness は callee 単体の入出力を native と比べるだけで、呼出し元が渡すべき値 (0 詰めで置き換えた値) は検証しない。一致は「callee が 0 詰めされた値を与えられても挙動が native と同じ入力範囲で一致した」ことを示すに留まる。
* 不一致 289 site は 0 詰めの誤りを示し得るが、evidence が arg k を名指しするのは 28 site のみ。残りは callee 本体の lift 欠陥 (`load_dropped` / `callee_divergence` 等) の可能性があり、0 詰め起因とは確定しない。
* 未到達 586 site は native 側で既に実行不能な callee。0 詰めの正否は本 harness では判定できない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未到達 586 site (native fault / null deref / hang / unsupported_sig の callee) | 0 詰めの正否が未判定 | #955 (Refs)。native 側の入力生成を拡充する作業は未起票 (PM へ起票を依頼) |
| 判定の batch 依存 (§4)。全 closure での判定表は未取得 (§6 の closure 実行は 15 分で打ち切り) | 本表は 217 callee batch の結果に限られる | #955 (Refs)。closure 全体の batch 実行 (時間上限の延長または分割) は PM 判断 |
| 不一致 site のうち 0 詰め起因か callee 本体の欠陥かの切り分け (arg 名指し 28 site 以外) | 不一致 289 site の帰属が未確定 | #955 (Refs)。DEFECTS.md への行案は PM 判断 |
| 一致 site の意味的な正しさ (callee 単体の一致 ≠ 呼出し元の 0 詰め値の正しさ) | §4 の通り | #955 (Refs)。未検証 |
| 初回 run の値 (一致 170 / 不一致 293 / 未到達 586, batch 75/173/419, 667 関数, 200 秒) の出所 | 本 fix で再現できず、撤回。出所は不明 | #955 (Refs) |

## 6. 再現手順と実測 (fix run, 2026-10-13)

作業ディレクトリ: `tools/liftdiff/work/m11_955/` (gitignore 対象。commit しない)。

1. 素材: `work-liftdiff` / `work-m11` を `tar --zstd -xf` で展開。`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` に指定。
2. VA 一覧: `cut -f3 results/sigfix_zeropad_liftdiff.tsv | tail -n +2 | sort -u | sed 's/^function_/0x/' > work/m11_955/vas.txt`。217 行 (重複なし), sha256 `b9972fb7…`。
3. build: `python3 liftdiff.py build targets/m11.json` → OK (`sig_mismatch 0`)。
4. batch n=1: `python3 liftdiff.py batch targets/m11.json --set file:work/m11_955/vas.txt --shards 4 --nobuild --out work/m11_955/batch_n1.jsonl`。217 行, sha256 `b43e0608…`, 47 秒。
5. batch n=2: 同条件。217 行, sha256 `191c53ea…`, 48 秒。n=1 とは sha256 が異なり、`cases` の一部のみ差分 (§1)。
6. 判定: `python3 tools/m11/m11_zeropad_liftdiff.py work/m11_955/batch_n1.jsonl` → 一致 174 / 不一致 289 / 未到達 586。callee 一致 32 / 不一致 67 / 未到達 118。TSV 1,050 行 (ヘッダ 1 + 1,049), sha256 `4b77b20f…`。batch_n2 でも TSV はバイト一致。
7. closure 参考: `--set closure` (7,421 関数) は 15 分の timeout (rc 124) で 6,000 行の途中で打ち切り。途中結果の判定は 一致 49 / 不一致 121 / 未到達 879 だが、部分結果のため採用せず、TSV は手順 6 の値に戻した。
8. 初回 run の値の扱い: 旧 REPORT の 170/293/586、batch 75/173/419、「667 関数」、200 秒、旧 TSV sha256 `7ac498d8…` は、いずれも本 fix で再現できなかった。batch.jsonl の sha256・行数が未記録のため出所は不明。「667 関数」は closure (7,421 関数) とも一致せず、誤記として撤回する。
