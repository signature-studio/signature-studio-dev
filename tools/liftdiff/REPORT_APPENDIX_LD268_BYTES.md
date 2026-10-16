# liftdiff REPORT 付録: LD-261 (#5268) k=0 領域 (`0x555555564000`・3,108,864 B) のバイト範囲切り分け

成果物の名前 (`ld268_*`・`results/ld268_*`) は付番時の仮番号 LD-268 のまま。本付録の題名・issue (#5268) の番号は LD-261。

前提は `REPORT_APPENDIX_LD268.md` (wasm `sta` 固定で native の k=0 だけ戻すと match・k=0 を外すと mismatch)。本付録は k=0 の中をバイト範囲で割り、持ち越しが入っている範囲を絞った。

## 結論

- `[0x0, 0x2f600)` (約 194 KB) は単独で match (十分条件・2 回測定と HEAD 再現で同一結果)。
- `[0x17b000, 0x2f6000)` (1,552,384 B) も単独で match (n=1)。
- `[0x0, 0x2f600)` と `[0x17b000, 0x2f6000)` は互いに交わらない。両者の関係 (持ち越しが 2 箇所に分かれるか、同じ変数の別の読みか) は未確定。
- 同じ先頭範囲の外、`[0x2f600, 0x5ec00)` 単独では mismatch (n=1)。
- 受入条件 1 は **部分達成**。k=0 の末尾 `[0x2f6000, 0x2f7000)` (4 KB) は未測定。`[0, 0x2f600)` の中の変数・構造体もまだ切り分けていない。

## 1. 測定条件

- 素材: `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開・`FL_WIN64_DIR`)。`work-m11`・`work-liftdiff` は worktree 内へ tar で展開。`toolchain-emsdk` は `$RUNNER_TEMP/emsdk` にも展開したが、build は `[EMSDK]` (エントリ ID) の上流 emsdk を使った。
- wasm は `build_wasm.build(t, force=True)` で作り直した (`wasm_size` 4464620・`sig_mismatch` 0・`undefined` 0。LD-261 と同値)。
- native は `ensure_native()` で rt/ の現版から作り直した。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。各 run は 1 本逐次 (2 本並列は行わず)。load 0.5〜1.0 (4 vCPU)。
- 基点 commit: `961b565cb` (origin/main)。
- 戻し方: `rt/ld_native.c` の `NRESETB k off len` (k 番目の NRST_MMAP 領域の `[off, off+len)` だけを SNAPSHOT 時点の値へ戻す)。driver は `ld156_chunk0_carryover.py --native-reset-bytes k:off:len`。wasm は `--reset sta` (mask 2) 固定。

## 2. 結果 (`results/ld268_bytes/`)

k=0 の範囲 `[0, 0x2f7000)` (3,108,864 B) のうち、`[0, 0x2f6000)` 以内を戻した結果 (末尾 `[0x2f6000, 0x2f7000)` 4 KB は未測定・§3):

| 戻す範囲 (k=0 の内側) | 長さ | verdict | native diff (B) | skip | 所要 (s) | ファイル |
|---|---|---|---|---|---|---|
| 対照: 何も戻さない (`sta` のみ) | 0 | mismatch | — | — | 144 | `ctrl_sta_none.jsonl` |
| `[0x0, 0x17b000)` (前半) | 1,552,384 | match | 39275 | 0 | 144 | `front_sta.jsonl` |
| `[0x17b000, 0x2f6000)` (後半) | 1,552,384 | match | 2126 | 0 | 144 | `back_sta.jsonl` |
| `[0x0, 0xbd800)` (前半の前半) | 774,144 | match | 39276 | 0 | 144 | `q1_sta.jsonl` |
| `[0xbd800, 0x17b000)` | 774,144 | mismatch | 0 | 0 | 144 | `q2_sta.jsonl` |
| `[0x0, 0x5ec00)` | 388,096 | match | 39276 | 0 | 144 | `h1_sta.jsonl` |
| `[0x5ec00, 0xbd800)` | 388,096 | mismatch | 0 | 0 | 144 | `h2_sta.jsonl` |
| `[0x0, 0x2f600)` | 193,536 | match | 1854 | 0 | 144 | `g1_sta.jsonl` (r1) / `g1_r2_sta.jsonl` (r2) / `head_g1_sta.jsonl` (HEAD) |
| `[0x2f600, 0x5ec00)` | 193,536 | mismatch | 37422 | 0 | 144 | `g2_sta.jsonl` |

- `[0, 0x2f600)` は 2 回とも match・native diff 1854 B で一致 (決定的)。
- `[0x2f600, 0x5ec00)` は n=1 (再測定なし)。
- 半分割りの判定: `[0, 0x5ec00)` が match・`[0x5ec00, 0xbd800)` と `[0xbd800, 0x17b000)` が mismatch。`[0, 0x17b000)` が match・`[0x17b000, 0x2f6000)` も単独で match。
- `[0x17b000, 0x2f6000)` は `[0, 0x2f600)` と交わらない。したがって後半の match は前半 `[0, 0x2f600)` では説明できず、両者の関係は未確定。

## 3. 未確認 (受入条件 1 の残り)

- k=0 の末尾 `[0x2f6000, 0x2f7000)` (4 KB) は未測定。
- `[0, 0x2f600)` と `[0x17b000, 0x2f6000)` の関係 (持ち越しが 2 箇所か、同じ変数の別の読みか) は未確定。
- `[0, 0x2f600)` の中の変数・構造体 (どのオフセットがどの識別子か) は未切り分け。さらに二分する必要がある。
- `[0x2f600, 0x5ec00)` の mismatch は n=1。
- `NMMAPN` は SNAPSHOT 直後の値。対象関数直前での領域番号・lo の一致は未確認 (LD-268 と同じ)。
- 対照 `sta` のみ・各半分割りの条件は n=1 (ただし `[0, 0x2f600)` は r2 で再現)。

## 4. 子 issue

- 受入条件 1 の残りは #5268 の範囲に残す。`Refs #5268` とし、issue は open のまま残す。次 run は `[0, 0x2f600)` の二分から続ける。

## 5. 再現

```sh
cd tools/liftdiff
export FL_WIN64_DIR=<fl-win64 展開先>
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset none --native-reset-bytes 0:0:2f600 --out results/ld268_bytes/g1_sta.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset none --native-reset-bytes 0:2f600:2f600 --out results/ld268_bytes/g2_sta.jsonl
```
