# icall #1838 (ICALL-41): CHAININFO 断片による Fresh Air 関数範囲の伸長

REPORT §15 から参照。修正の本体は `tools/icall/prep_targets.py` の `chain_parents` / `chain_end` (`chained=True` の時だけ適用)。

## 1. 原因 (issue #1838 の調査結果)

`1803de190` は PE の `.pdata` で 3 断片に分かれる (`190-1b7` 親、`1b7-20d`・`20d-260` は CHAININFO の hot/cold 断片で親を参照)。
`fa_ranges.txt` は先頭の RUNTIME_FUNCTION (`190-1b7`) だけを RetDec に渡していたため、`je` の飛び先と call が範囲外になり、IR は分岐・call 0 の未初期化戻り値になった。

## 2. 修正の条件 (#1884 差し戻しへの対応)

- 断片の UNWIND_INFO 末尾の親 RUNTIME_FUNCTION (`chain_parents`) が `va` 本人の断片だけを辿る。親が別関数なら伸ばさない。
- 伸ばした範囲に、親の断片以外の関数開始 VA (`img.bounds`) が入る場合は伸ばさない。
- 境界条件は `tools/icall/tests/test_chain_end.py` (PE 不要・4 件) で固定。

## 3. 実測 (現 HEAD `d64c86c5`・コード差分 0)

- コードの測定 commit は `77be6b71` (最後にコードを変えた commit)。`git diff 77be6b71 HEAD -- tools/icall/prep_targets.py tools/icall/chain_ranges_diff.py tools/icall/tests` の出力は 0 行 (測定は `d64c86c5` の worktree で実施)。
- ただし PR 本文の「`git diff 3cdf8cf3 HEAD -- tools/icall` は差分 0」は成り立たない。`3cdf8cf3..HEAD` では `tools/icall` の 13 files が変わっている (`audit_icall.py` 35 行・`rt/icall_rt.c` 1 行・`diff/fa_imports.py` 追加など。`chain_end` 本体の変更は `77be6b71`)。`3cdf8cf3` の旧測定値は使わない。

| 項目 | 結果 (実測) |
|---|---|
| `tests/test_chain_end.py` (合成データ・境界 4 条件) | PASS 4/4 |
| `chain_ranges_diff.py` (入力: 下記 3.1 の 1213 件) | `entries 1213`・`chained=False` と `True` の差分 **931 行**・全行が伸長 (縮小 0)・`PASS leak 件数 0` |
| `1803de190` の範囲 | `chained=False` `0x1803de190-0x1803de1b7` → `chained=True` `0x1803de190-0x1803de260` |
| `1803de190` decode 直後 (`before.0.drc.ll`) | `chained=False` br 0・call 0 / `chained=True` br 6・call 2 |
| `1803de190` roundtrip after (`after.0.restored.ll`) | `chained=False` br 2・call 5 / `chained=True` br 8・call 8 |
| audit `call_lost` (`roundtrip.sh`) | `chained=False` before 0 → after 0 (`ir_call_dir_total` 0 → 1) / `chained=True` before 0 → after 0 (`ir_call_dir_total` 2 → 2) |
| sweep (`fa_sweep.sh 8 60`) | 未実施 (子 #1886) |

数え方: br / call は `^\s+br ` と `^\s+(%[^ ]+ = )?call ` の行数 (LL の命令行)。`audit_*.json` の `ir_call_dir_total` は別の集計で、before/after で値が違う。前回の付録にあった「`chained=True` after call 14」は、この数え方では再現しない (8)。

### 3.1 入力・素材

- 素材: `plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開し、`FA_DL=... bash tools/targets/freshair/fetch.sh` で `SlateCore.core_64` (36,285,952 B) を得た。
- `clo_freshair_all.json` は素材に無い。差し戻しの指定どおり、同じ PE の CHAININFO 親の VA 集合 (`chain_parents` の値の一意集合 = **1213 件**。断片は 2557 件) を入力にした。`tools/icall/work/clo_freshair_all.json` (gitignore 対象・commit しない)。
- 元の `clo_freshair_all.json` (1213 件以外の VA を含む可能性) とは一致を確認していない。`work-icall` の `fa_ranges.txt` (131 entries) を入力にした旧測定は、この付録では使わない。

### 3.2 対象 VA の注意

- 伸長 931 行の一覧は `chain_ranges_diff.py` の出力 (`PASS leak 件数 0`) を正とする。`3cdf8cf3` 時点の「伸長 12 件」一覧 (131 entries 入力) は、今回の入力 (1213 件) とは対象が違うため、現 head では再現できない。

## 4. 再現手順 (素材 `plugins-freshair` が必要)

```sh
python3 tools/icall/tests/test_chain_end.py                                  # PE 不要
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
PE="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
# 入力: chain_parents の値の一意集合 (1213 件) を JSON 化する (clo_freshair_all.json は素材に無い)
python3 -c 'import json,sys; sys.path.insert(0,"tools/icall"); import audit_icall as A, prep_targets as P; img=A.Image(sys.argv[1]); json.dump({"funcs":[{"va":hex(v)} for v in sorted(set(P.chain_parents(img).values()))]}, open("tools/icall/work/clo_freshair_all.json","w"))' "$PE"
python3 tools/icall/chain_ranges_diff.py "$PE" tools/icall/work/clo_freshair_all.json
# roundtrip (1803de190): 範囲ファイルは chained=False `0x1803de190-0x1803de1b7` / chained=True `0x1803de190-0x1803de260`
bash tools/icall/roundtrip.sh "$PE" <範囲ファイル> <label> <outdir>
```

`chain_ranges_diff.py` は範囲の差分 (`chained=False` と `True`)・伸長件数・伸長後の範囲に他関数の開始 VA が入るかを出す。`leak` が 1 件でもあれば FAIL。
