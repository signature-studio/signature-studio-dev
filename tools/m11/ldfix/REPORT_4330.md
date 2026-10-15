# LD-210 (#4330): 対照と区別できるネガコン (glk=False)

親 #4204 (LD-204) の §5 で、ネガコン 2 種 (`--negctl-glk`・`--negctl-nosync`) が対照と全件一致した問題の解消。
区別できるネガコンとして、対照で glk=True の関数を glk=False に落とす `--negctl-noglk` を追加した。

## 1. 結論

- `--negctl-noglk` は対照と **区別できる**。関数 verdict 34 件 / 48、site verdict 36 件が変わる (§3)。
- 対照の 45/48 関数が glk=True で、`--negctl-glk` (全関数 True) は対照と全件一致していた。今回は逆向きの 45 関数を落とす条件で、差が出た。
- 判定器の規則は変えていない。変えたのは CLI に `--negctl-noglk` を足す 3 行だけ (既定の動作は不変)。
- 判定器が glk を使う点は確認できた。ただし `5cb210` (LD-204 の対象) は noglk でも判定は UNDETERMINED のまま (§4)。

## 2. 測定条件

- 測定 commit: `2fa0d85c5` (判定器の `--negctl-noglk` 追加と結果 JSON。以降のコード変更なし)。作業ツリーは `2fa0d85c5` と同一。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#4204 と同じ)。
- PE: `[WIN64]` の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#4204 と同じ)。
- 実行: `python3 audit_frame_store_alias_2211.py PE audit.json f4.json OUT [--negctl-noglk]`。対照・noglk・glk のいずれも rc 0、約 0.3 秒。load average 0.25 (4 vCPU)。
- 再現: 対照の出力 `results/frame_store_alias_4330_ctl.json` を `2fa0d85c5` の判定器で再実行し、`cmp` で一致 (`REPRO_OK`)。
- 注意: 対照の出力は #4204 の `results/frame_store_alias_4204.json` と **バイト一致しない**。差は `nonframe_stores` キー (#4166 で追加。#4204 の JSON はそれ以前の版)。判定値 (関数・site の verdict と why) は全件一致する。

## 3. 結果 (受入 1・2)

| 条件 | 関数 DROP / LIVE-IN / UNDETERMINED | site DROP / LIVE-IN / UNDETERMINED / PTR_READ | glk=True の関数数 | 結果 JSON |
|---|---|---|---|---|
| 対照 (規則変更なし) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | 45 | `results/frame_store_alias_4330_ctl.json` |
| `--negctl-noglk` (全関数の glk を False) | 4 / 34 / 10 | 4 / 36 / 10 / 1 | 0 | `results/negctl_alias_4330_noglk.json` |
| `--negctl-glk` (全関数の glk を True) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | 48 | `results/negctl_alias_4330_glk.json` |

- 対照と noglk の差: 関数 verdict 34 件 (`fn_info` の `verdict` で比較)、site verdict 36 件。
- 変わった関数の例: `1006ec0`・`103aa50`・`11e6e20`・`12cb2e0`・`4078c0`・`418b40` (いずれも UNDETERMINED → LIVE-IN)。
- 変わった site の例: `1006fb6`・`1007021` (`1006ec0`)・`103ab59` (`103aa50`) は UNDETERMINED → LIVE-IN (`NO_DEF_ON_ANY_PATH`)。
- glk 規則が効いている: glk=True の 45 関数を落とすと、判定が LIVE-IN に変わる関数がある (対照と区別できる)。

なお `--negctl-glk` は対照と全件一致するままである (`results/negctl_alias_4330_glk.json` は `results/negctl_alias_4204_glk.json` と byte 不一致だが、差は `nonframe_stores` キーのみ。判定値は全件一致)。

## 4. 5cb210 の扱い (受入 2 の補足)

- `5cb210` は対照で glk=True。noglk で glk=False になる (`fn_info.glk`)。
- site `5cb4aa` の判定は対照・noglk とも **UNDETERMINED (`BARRIER(ALIAS_FRAME_PTR)`)** のまま。
- したがって `5cb4aa` の判定を変えるのは glk の規則ではなく、`5cb47d` の `ALIAS_FRAME_PTR` (glk に依存しない) である。この打ち切りは #3225 (LD-150) の範囲。

## 5. 差分 (WORKFLOW §6)

- 測定 commit: `2fa0d85c5`。
- 測定 commit から HEAD までのコード差分: なし (本 REPORT と `REPORT_4204.md` の更新は docs のみ)。
- `git diff 2fa0d85c5 HEAD -- tools/m11/ldfix` の出力: `REPORT_4330.md` と `REPORT_4204.md` の追加・更新のみ。判定器は変わらない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `5cb47d` の `ALIAS_FRAME_PTR` (5cb210 の `5cb4aa` が閉じない根) | 5cb210 が UNDETERMINED のまま | #3225 [LD-150] |
| 呼出し先 `407a50` の戻り値規則 | `409410` の戻り値が閉じない | #4238 [LD-205] |
