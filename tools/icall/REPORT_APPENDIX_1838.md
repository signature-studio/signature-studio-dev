# icall #1838 (ICALL-41): CHAININFO 断片による Fresh Air 関数範囲の伸長

REPORT §15 から参照。修正の本体は `tools/icall/prep_targets.py` の `chain_parents` / `chain_end` (`chained=True` の時だけ適用)。

## 1. 原因 (issue #1838 の調査結果)

`1803de190` は PE の `.pdata` で 3 断片に分かれる (`190-1b7` 親、`1b7-20d`・`20d-260` は CHAININFO の hot/cold 断片で親を参照)。
`fa_ranges.txt` は先頭の RUNTIME_FUNCTION (`190-1b7`) だけを RetDec に渡していたため、`je` の飛び先と call が範囲外になり、IR は分岐・call 0 の未初期化戻り値になった。

## 2. 修正の条件 (#1884 差し戻しへの対応)

- 断片の UNWIND_INFO 末尾の親 RUNTIME_FUNCTION (`chain_parents`) が `va` 本人の断片だけを辿る。親が別関数なら伸ばさない。
- 伸ばした範囲に、親の断片以外の関数開始 VA (`img.bounds`) が入る場合は伸ばさない。
- 境界条件は `tools/icall/tests/test_chain_end.py` (PE 不要・4 件) で固定。

## 3. 実測 (測定 HEAD `16f7f452`)

コードの測定 commit は `77be6b71` (最後にコードを変えた commit)。`git diff 77be6b71 HEAD -- tools/icall/prep_targets.py tools/icall/chain_ranges_diff.py tools/icall/tests` の出力は 0 行。以下の測定は `16f7f452` の worktree で行った (コード差分は上記の通り 0)。

| 項目 | 結果 |
|---|---|
| `tests/test_chain_end.py` (合成データ・境界 4 条件) | PASS 4/4 |
| `chain_ranges_diff.py` (実 PE・131 entries) | `chained=False` と `True` の差分 12 行。伸長 12 件。`leak 件数 0`。PASS |
| 伸長 12 件 | `1803b5500` `1803de190` `18040c950` `180829930` `180829c20` `180c97f20` `180c98240` `180c99430` `180ca1480` `180da4030` `180da5f20` `180da6720` |
| `1803de190` の範囲 | `chained=False` `0x1803de190-0x1803de1b7` / `chained=True` `0x1803de190-0x1803de260` |
| `1803de190` decode 直後 (`--select-decode-only`) | `chained=False` br 0・call 0 / `chained=True` br 6・call 2 |
| `1803de190` roundtrip after (`after.0.restored.ll`) | `chained=False` br 2・call 5 / `chained=True` br 8・call 14 |
| audit `call_lost` (after) | `chained=False` 6 / `chained=True` 6 (before は両方 87。after の 6 は非 IAT 残 6 件で不変) |
| sweep (`fa_sweep.sh 8 60`) | 未実施 (子 #1886) |

### 3.1 素材の扱い

- `plugins-freshair` を展開し `fetch.sh` で `SlateCore.core_64` (`tools/targets/freshair/work/win/...`) を得た。
- `clo_freshair_all.json` は素材に無い。`work-icall` 内の `fa_ranges.txt` (`chained` 修正前の範囲、131 entries) の VA から `{"funcs":[{"va":...}]}` を再構成して `tools/icall/work/clo_freshair_all.json` に置いた (`work/` は gitignore 対象で commit しない)。
  元の JSON は手元に無いため、元の VA 集合との一致は確認していない。再構成した JSON は `work-icall` の範囲と同じ 131 VA を持つ。
- 現 HEAD の範囲 (`chained=True`) は `work-icall` の `fa_ranges.txt` と比べて 12 件だけ異なる (`chained` 修正による伸長)。

## 4. 再現手順 (素材 `plugins-freshair` + `work-icall` が必要)

```sh
python3 tools/icall/tests/test_chain_end.py                                  # PE 不要
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
PE="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
python3 tools/icall/chain_ranges_diff.py "$PE" tools/icall/work/clo_freshair_all.json
```

`chain_ranges_diff.py` は範囲の差分 (`chained=False` と `True`)・伸長件数・伸長後の範囲に他関数の開始 VA が入るかを出す。`leak` が 1 件でもあれば FAIL。
roundtrip は `bash tools/icall/roundtrip.sh "$PE" <範囲ファイル> <label> <outdir>` (範囲は `prep_targets.ranges_with_ends(..., chained=True/False)` で作る)。
