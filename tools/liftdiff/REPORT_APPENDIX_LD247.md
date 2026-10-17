# liftdiff LD-247 (#4968): OTT 用 x64c clift bridge と ott_clift target・計装版

親: #4952 (LD-244)。PR #6074 (a) の続き: 計装版 (block_trace) を clift route に入れ、既定版と 12 case で比較した (b1・b2)。

## 1. 結論 (実測)

測定 commit: `ed474437f` (`feat(liftdiff): clift route の block_trace 計装 (LD-247 b1)`)。
測定後の差分: `git diff ed474437f HEAD -- tools/liftdiff` は本 REPORT ファイルのみ (コード 0 行)。PR 全体の差分は `git diff 7cb5df311 HEAD -- tools/liftdiff` (base = origin/main): `clift.py` +31、`ott_ldbridge.c` +13、`ott_clift_blk.json` +24、REPORT の更新。

| 項目 | 実測 |
|---|---|
| x64c 再 lift (`ld131_lift.sh`) | 29 functions / 952 insns / unsup {} / unlifted callees 0 / imports 11。PR #6074 の記録 (29/952) と一致。前々 run の 28/941 の入力差は未確認 (切り分けていない) |
| `ott_clift` build (既定版) | OK。sigs 234 (defined 178)、lifted 29、instrumented 29、imps 11、nptab 22。link 0.4s、`sig_mismatch 0 / undefined 0`、wasm 744,292 B |
| `ott_clift_blk` build (計装版) | OK。block 入口 136 箇所 (`L_<VA>:;`)。link 0.4s、`sig_mismatch 0 / undefined 0`、wasm 754,903 B |
| 既定版 6 関数の採点 (HEAD) | 6 関数すべて `verdict=match`。1801ab1d0・1801ab258・1801c5e84・1801c621c・1801c682c・1801c69cc |
| **受入 cases=12 diff=0** | **達成**。`results/ld67/compare_blk.py` で既定 (`ott_clift`) と計装 (`ott_clift_blk`) が `cases=12 diff=0`。全 12 case `equal`。計装版の blk 件数は 7〜288 (非 0) |
| 測定時間 | 既定版 run 7.6s (作業ツリー)・HEAD 測定の既定版 + 計装版 run 計 15.9s (`time`) |

### 採点結果 (HEAD `ed474437f`・vm0/u16)

| 関数 | 既定版 | 計装版 | blk 件数 (計装版) |
|---|---|---|---|
| 1801ab1d0 | equal / equal | equal / equal | 7 / 7 |
| 1801ab258 | equal / equal | equal / equal | 7 / 7 |
| 1801c5e84 | equal / equal | equal / equal | 18 / 22 |
| 1801c621c | equal / equal | equal / equal | 277 / 282 |
| 1801c682c | equal / equal | equal / equal | 26 / 26 |
| 1801c69cc | equal / equal | equal / equal | 283 / 288 |

(表の順は vm0 / u16。`compare_blk.py` の出力 `cases=12 diff=0`。)

比較キーは `compare_blk.py` の `key()` で、outcome・wasm_status・diffs・wasm の rax/x0 の一致を見る。blk 列 (block 入口の記録) は比較キーに入っていない。既定版は `ld_blk_on = 0` のため blk 列が空で、計装版だけに出るため比較できない。表の blk 件数は計装版の記録件数の参考値。

### 前 run との差 (注意)

PR #6074 の報告では `1801c5e84`・`1801c621c`・`1801c69cc` が `mismatch` だった。今回は作業ツリーでも HEAD でも 6 関数すべて `match`。原因は未特定。今回の測定は同じ `ott_clift` target の build を `--force` で作り直して行った。前 run の mismatch の再現条件 (入力・build の差) は切り分けていない。

## 2. 作ったもの

- `tools/liftdiff/rt/ott_ldbridge.c`: `ott_cpu.h` の状態 (`R`/`X`/`XH`/`fZF` 系・`ott_mxcsr`) に合わせた bridge (PR #6074)。本 commit で、block 入口の同期 `ott_blk_sync` (`ld_wasm.c` の `ld_blk_sync` と同一規則) と `ld_blk_n`/`ld_blk_arr` の定義を追加。既定版でも定義は残るが、`ld_blk_on = 0` のため記録されない。
- `tools/liftdiff/ldlib/clift.py`: `block_trace` 指定時だけ `instrument_clift_blocks` が `L_<VA>:;` の直後に `ld_blk_arr` へ volatile store を入れる。既定 target は出力が変わらない。
- `tools/liftdiff/targets/ott_clift.json` (PR #6074): 既定版。
- `tools/liftdiff/targets/ott_clift_blk.json` (本 commit): 計装版。`block_trace: true`。

## 3. 再現手順

```
export PLUGINS_DIR=$RUNNER_TEMP/analysis/plugins
LD131_OUT=$RUNNER_TEMP/ld131 bash tools/liftdiff/results/ld131/ld131_lift.sh
mkdir -p tools/liftdiff/work/ott_clift/lift && cp $RUNNER_TEMP/ld131/lift/* tools/liftdiff/work/ott_clift/lift/
cd tools/liftdiff && FN=0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc
python3 ldlib/build_wasm.py targets/ott_clift.json --force
python3 ldlib/build_wasm.py targets/ott_clift_blk.json --force
mkdir -p work/ld247
python3 liftdiff.py run targets/ott_clift.json     --fn $FN --pattern vm0,u16 --notrace -v --json work/ld247/def2.json
python3 liftdiff.py run targets/ott_clift_blk.json --fn $FN --pattern vm0,u16 --notrace -v --json work/ld247/blk2.json
python3 results/ld67/compare_blk.py work/ld247/def2.json work/ld247/blk2.json   # cases=12 diff=0
```

素材: `plugins-ott` と `analysis-ott-binaries` を `$RUNNER_TEMP/analysis` に展開 (DLL は `plugins/ott/binaries/OTT_vst2_win64.dll`)。lift 産物は `ld131_lift.sh` の出力を `work/ott_clift/lift/` に複写。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PR #6074 の 3 関数 mismatch の原因 | HEAD の既定版は全 match。前 run の条件を再現できていない | #4952 (親 LD-244 の本文チェックリストに追記。次 run で切り分け) |
| x64c 再 lift の 28/941 (前々 run) の入力差 | 現在の入力 (29/952) は PR #6074 の記録と一致。28/941 の入力差は未確認 | #4952 (同上) |
| `liftdiff.py run --nobuild` の既定 `work/` 出力先 | `--json` の親 dir が無いと失敗する (本 run で 1 回失敗・dir 作成で解消) | 既存挙動のため本 PR では変えない |
