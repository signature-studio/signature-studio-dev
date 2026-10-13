# #1317 M2p ON survey: unit 880 の停止位置の特定 (2026-10-13)

**判定: 部分達成 (Refs #1317)。** 受入 2 (停止した命令・wasm frame の特定) と受入 4 (再現の確認) は一部。停止の必要条件 (830 が先行し 880 が走る) は REPORT_1076 の結果を再確認した。停止を起こす状態 (受入 1)・修正案 (受入 3) は未達。

既知類型との関係: 該当なし (survey の停止位置の調査のみ。lift 変換の類型には触れていない)。

## 1. 測定の基準

- 検証 HEAD: `851c342e` (`origin/main`)。本ファイルを追加する commit 以外にコード差分は無い。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin`, 22 MB)。`toolchain-retdec` を `$RUNNER_TEMP/tc/retdec`、`toolchain-emsdk` を `$RUNNER_TEMP/tc/emsdk` に展開 (`RETDEC_ROOT` で指定。emsdk は runner の `/opt/emsdk` を使用)。`work-m11` を `tools/m11/work/` (233 entries)、`work-liftdiff` を `tools/liftdiff/work/` (11 entries) に展開。
- IR: `m11_gen_ir2.sh` 43 s rc=0 (OFF)。`M11_M2P=1` でも rc=0 (`[ir11][M2p] decimal inttoptr instr VA remap: 4364`)。ldfix は OFF/ON とも `F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0`。
- build: `m11_build.sh` 26 s rc=0 (OFF・ON とも `wasm-ld signature mismatch: 0, undefined symbol: 0`)。
- load average: 実行中 0.95〜0.99。

## 2. 再現 (repro_1076.sh, M2p ON, 60 s 上限)

| 条件 | 結果 | rc |
|---|---|---|
| `880` 単独 | `oob 1` | 0 |
| 0..941 から 880 を除いた全 unit (skip880) | `ok 871 / oob 14 / miss 47 / halt0 5 / abort 2 / other 1 / noproc 1` | 0 |
| `0..830` + `880` (prefix_0_830_880) | 60 s 超で打ち切り | 124 |
| `0..829` + `880` | `ok 765 / oob 13 / miss 46 / halt0 4 / abort 2 / other 1` | 0 |
| `830,880` | `oob 2` | 0 |
| `0..830` (880 なし) | `ok 765 / oob 13 / miss 46 / halt0 4 / abort 2 / other 1` | 0 |

REPORT_1076 §3 の境界 (`0..829`+880 完走 / `0..830`+880 停止) と一致。ただし run 所要秒は未計測 (60 s 上限のみ)。

対照 (OFF build の IR を再生成して build し直した後): `0..830` + `880` は `ok 764 / miss 46 / halt0 6 / oob 15 / other 1` で **完走 (rc=0)**。停止は M2p ON に固有。(REPORT_1076 §7 の「未実施」項目の裏取り。)

## 3. 停止位置 (trace, `SV_PROG=1` + `SV_TRACE_AT=880`)

- `SV_PROG` で unit 830 の完了後に `unit 880` を表示し、そのまま出力が止まる。例外・abort の表示は無い (rc=124 で打ち切り)。
- 880 の中で最後に出る trace は次の順 (`diag880p.log` 末尾):
  1. `[m11][icall] 0xe63540`
  2. `[m11][icall] 0xf960`
  3. `[m11][stub-notimpl] GetFileVersionInfoSizeW called`
  4. `[m11][UStrAsg] dest=0x10a9b188 src=0x0 old=0x0`
  5. `[m11][UStrAsg] dest=0x10a9b648 src=0x0 old=0x0`
  その後の trace は無く、ループまたは長い計算で止まっている可能性が高い。
- `[m11][VA-big] size=2143354880 (2044.1 MB)` が 2 回と `OOM want=2143.4MB used=76.3MB` が出る (`diag880p.log` の 185〜201 行)。これは `unit 830` の marker (895 行) より前、つまり unit 0〜829 の実行中の出力で、880 の停止の直接原因とは断定できない。
- `Runtime error 215` / `unresolved function call: function_535c2e` の fail-fast は unit 830 以前の出力で、880 の内部ではない。

**未解決 (受入 1・2 の残り)**:
- `icall 0xe63540` / `0xf960` は PE の VA ではなく wasm 側の icall 値。`disasm_fn.py` は PE VA (`0x400000` 基準) しか引けず、解決先の特定は未了 (`0xe63540` は PE の範囲内だが関数先頭ではない)。
- 880 の停止命令 (wasm frame) は `SV_RAW=1` の `e.stack` が trace 無しの run で取れていない (本 run では `SV_RAW` のみの run は未実施)。
- 830 が残す状態 (メモリ領域・間接 call 先・store 先) は未特定。

## 4. 未達・未実施 (起票先)

| 未解決 | 起票先 |
|---|---|
| 880 の停止命令・wasm frame の特定 (`SV_RAW=1` 単独 run、icall 0xe63540/0xf960 の wasm→PE 対応付け) | 本 issue #1317 へのコメント |
| 830 が残す状態の特定 (受入 1)・修正案 (受入 3) | 本 issue #1317 |
| 所要秒 (n≥3) と REPORT_1076 の未検証 6 件 | #1076 へのコメント |

## 5. 再現コマンド

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP RETDEC_ROOT=$RUNNER_TEMP/tc/retdec M11_M2P=1
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh
SV_ONLY="$(seq -s, 0 830),880" SV_PROG=1 SV_TRACE_AT=880 timeout 20 node tools/m11/trap_triage/survey_units.mjs out.json
```

`work/` は gitignore 対象で commit しない。
