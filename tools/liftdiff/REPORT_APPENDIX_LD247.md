# liftdiff LD-247 (#4968): OTT 用 x64c clift bridge と ott_clift target

親: #4952 (LD-244)。部分達成: (a) の bridge・target・build と 6 関数の native/wasm 採点まで。受入 (計装版 vs 既定版 12 case の差 0) は未達 (§4)。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| x64c 再 lift (`ld131_lift.sh`) | 29 functions / 952 insns / unsup {} / unlifted callees 0 / imports 11 (前 run の記録 28 / 941 / unlifted 1 と不一致。LD-131 の入力が変わった可能性。未切り分け) |
| `ott_clift` build (`clift.py`) | OK。sigs 234 (defined 178)、lifted 29、instrumented 29、imps 11、nptab 22。link 0.5s、`sig_mismatch 0 / undefined 0`、wasm 743,548 B |
| 計装版 (block_trace) | **未実施**。clift route に IR basic block 計装 (`ld_blk`) は無い (`ld_fle_trace` のみ)。PM 決定 (停止報告の (3)): 計装版 = block_trace 計装。clift 側の block 計装は未着手 |
| 6 関数 native/wasm 採点 (既定版のみ) | verdict: 1801ab258 match / 1801c5e84 mismatch / 1801c621c mismatch / 1801c682c match / 1801c69cc mismatch。1801ab1d0 vm0 = equal (単独 run) |
| 受入 cases=12 diff=0 | **未達**。計装版が無いため compare_blk.py の比較対象が無い |

## 2. 作ったもの

- `tools/liftdiff/rt/ott_ldbridge.c`: `ott_cpu.h` の状態 (`R`/`X`/`XH`/`fZF` 系・`ott_mxcsr`) に合わせた bridge。`fle_ldbridge.c` と同じ構造。case の `fn` は PE VA のため `ld_delta` で wasm 番地へ換算して `ott_dispatch` を呼ぶ。
- `tools/liftdiff/ldlib/clift.py`: CPU 実装 (`clift_cpu`)・dispatch 名 (`clift_dispatch`)・bridge (`clift_bridge`)・追加 C (`clift_extra_c`)・data 生成 (`clift_data_gen`) を target JSON で差し替え可能に。既定値は従来どおり (flelift の target は変更なし)。
- `tools/liftdiff/targets/ott_clift.json`: `clift: true` の OTT target。
- 入力の置き場は gitignore 領域 (`tools/liftdiff/work/ott_clift/lift/`・`work/ott_old/ir_instr.ll`)。大物は commit しない。

## 3. 再現手順

```
LD131_OUT=$RUNNER_TEMP/ld131 bash tools/liftdiff/results/ld131/ld131_lift.sh
cp $RUNNER_TEMP/ld131/lift/{ott_lifted.c,lift_meta.json} tools/liftdiff/work/ott_clift/lift/
python3 tools/ott/lift/data_gen.py <PLUGINS_DIR>/ott/binaries/OTT_vst2_win64.dll tools/liftdiff/work/ott_clift/lift/ott_data.c tools/liftdiff/work/ott_clift/lift/lift_meta.json
cd tools/liftdiff && python3 liftdiff.py run targets/ott_clift.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --nobuild
```

`build` 単体は `ldlib.clift.build(load_target('targets/ott_clift.json'), force=True)` で実行 (`liftdiff.py build` は clift を分岐させるが、`ott_clift.json` の data 生成は `clift.py` 内)。

## 4. 未達と次の一手

| 未解決 | 影響 | 起票先 |
|---|---|---|
| clift route に block_trace (`ld_blk`) 計装が無い | 計装版と既定版の 12 case 差 0 が測れない (受入 1) | #4968 (次 run: clift 側 block 計装を bridge に入れる) |
| 12 case の計装版/既定版 実測と `compare_blk.py` | 受入 1 未達 | #4968 |
| 測定 commit と `git diff` の REPORT 添付 | 受入 2 は、受入 1 の測定後に行う | #4968 |
| x64c 再 lift の 29/952 と前 run の 28/941 の差 | LD-131 の入力の差。clift の lifted 集合 (29) に影響 | #4968 (切り分け) |
