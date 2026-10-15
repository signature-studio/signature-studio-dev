# liftdiff REPORT 付録: LD-261 (#5268) `0x5d19e0` の both 条件 (wasm・native 作り直し) の再確認

親 #3385 (LD-156)。前提は `REPORT_APPENDIX_LD229.md` (wasm `sta` + native `mmap` で match・n=2)。LD-121 の both 条件 (`REPORT_APPENDIX_LD121.md` §3) を、chunk 0 の `0x5d19e0` 1 件で driver に入れて再確認した。

測定 commit: **`ed6919759`** (`ld156_chunk0_carryover.py` に `--wasm-restart` を追加した commit)。後続の変更は help 文字列 1 行の修正だけ (§7)。

## 結論

- `both` (native 作り直し + wasm 作り直し・RESET なし) は `0x5d19e0` で **match**。n=2 (r1・r2) とも 11/11 `equal`。
- 対照 `none` (作り直しなし・RESET なし) は **mismatch**。11/11 `diff`。
- 受入条件 2 (`both` の match を先に確認し、対照は `none`) は満たした。
- 受入条件 1 (持ち越しの中身の特定) は **未達**。本付録は作り直しの両側で消えることを再確認しただけで、どの mapping・どの変数が持ち越しの実体かは切り分けていない (§4)。

## 1. 測定条件

- 素材: `fl-win64` (展開先 `$RUNNER_TEMP/fl-win64` = `FL_WIN64_DIR`)・`toolchain-emsdk` (`/opt/emsdk`)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)。`$ARTIFACTS_DIR` に 4 件の実在を確認して展開した。
- wasm は `build_wasm.build(t, force=True)` で `rt/ld_wasm.c` から作り直した (`wasm_size` 4464620・`sig_mismatch` 0・`undefined` 0。LD-229 と同じ値)。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。
- 機: 4 vCPU。各 run は 1 本ずつ逐次で流した (並列は使っていない)。run 中の load average は 0.8〜0.9。

## 2. 方法

- `ld156_chunk0_carryover.py` に `--wasm-restart 0|1` を追加した。`--native` と組み合わせると、対象関数の直前に作り直す側を指定できる。
  - `--native 1 --wasm-restart 1 --reset none` = `both` (LD-121 の both と同じ)
  - `--native 0 --wasm-restart 0 --reset none` = 対照 (LD-121 の none と同じ)
- `--wasm-restart 1` は `--reset` と併用しない (作り直しと RESET を重ねない)。
- 出力 JSON に `wasm_restart` を追加した。

## 3. 結果 (`results/ld268_raw/`)

| 条件 | n | verdict | case equal | 所要 (s) |
|---|---|---|---|---|
| both (native 1・wasm 作り直し) | 2 | **match** (×2) | 11/11 (r1・r2) | 179・179 |
| none (作り直しなし) | 1 | mismatch | 0/11 (diff 11) | 171 |

- `both` の 11 case の status は両回とも `equal`/`ok`/`ok` (`z` を含む。LD-229 の `sta_mmap` で見えた `z` の hang/crash の揺れは今回は出ていない)。
- `none` の 11 case は `diff`/`ok`/`ok`。

## 4. 未確認 (受入条件 1 の残り)

- どの mapping・どの変数が持ち越しの実体かは未切り分け。作り直しの両側・`sta` + `mmap` で消えることまでは分かっているが、持ち越しの中身そのものは特定していない。
- LD-229 §4 と同じく、mapping 単位の切り分け (stdio buffer・malloc 用 mmap 等) は未実施。
- `none` は今回 n=1。LD-156 の `none` (n=2・mismatch) と合わせると 3 回 mismatch。
- `both` の r1 と r2 の所要は同一条件で揃えたが、load を各 run で記録していない (上の 0.8〜0.9 は run 中の値)。

## 5. 子 issue

- 受入条件 1 (中身の特定) は本 issue の範囲に残す。`Refs #5268` とし、issue は open のまま残す。mapping 単位の切り分けが必要なら、次 run が同じ issue の続きとして扱う。

## 6. 再現

```sh
# 環境変数は docs/REFERENCES.md §4 を参照 ([WIN64] の展開先を FL_WIN64_DIR に指定する)
cd tools/liftdiff
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld156_chunk0_carryover.py --native 1 --wasm-restart 1 --reset none --out results/ld268_raw/both_r1.jsonl
python3 ld156_chunk0_carryover.py --native 1 --wasm-restart 1 --reset none --out results/ld268_raw/both_r2.jsonl
python3 ld156_chunk0_carryover.py --native 0 --wasm-restart 0 --reset none --out results/ld268_raw/none_r1.jsonl
```

## 7. 測定 commit 以降の差分

- `git diff ed6919759 HEAD -- tools/liftdiff/ld156_chunk0_carryover.py` = `--wasm-restart` の help 文字列の 1 行 (`LD-268` → `LD-261` の誤記修正)。測定の挙動には影響しない。
- HEAD 側の追加は本付録・`results/ld268_raw/` のみ。
