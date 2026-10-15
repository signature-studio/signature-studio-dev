# REPORT_APPENDIX_4088 — 残り x87 leaf 関数の native vs wasm 差分試験 (#4088 / 親 #4065)

既知類型との関係: 該当なし。 x87 の stack underflow は `ott_x87.h` の制限 (4) の範囲 (`REPORT.md` §13) で、類型の追加は行わない (`DEFECTS.md` は編集しない)。

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13。 本付録が測定値の正本。
- 測定 commit: `cb4762d72` (main 取り込みの merge。 `x87_fn_diff.py` の最後のコード変更を含む commit)。 `x87_fn_glue.c`・`x87_fn_native.c` の `ebp` 設定は `e4514bf39` で入った。 §2 の数値はすべてこの commit の実測。
- 検証 HEAD: 本付録を含む PR 末尾の commit (PR 本文の「検証」節に記載)。 測定 commit から検証 HEAD までの、この dir のコード差分 (`*.md` を除く) は 0 行。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と乱数 (seed 2989) で生成した試行のみ。

## 1. 結論

- 判定器 (`x87_fn_diff.py`) の `TARGETS` は **2 本のまま** (`0x10002ee0`・`0x10005400`)。 新しく通せた関数は 0 本。
- 残り 12 本 (#4065 の一覧) を試した結果は §3。 判定を通らない理由は 3 種類。
  1. `ebp` 相対だけを書く 3 本 (`0x1000b6c1`・`0x1000b8a2`・`0x1000b936`): 値は native と wasm で 100% 一致するが、OBJ 窓を書かず非自明性の判定を満たさない → 子 #4146 (PLG-G2-49)。
  2. 空スタックを読む 3 本 (`0x1000b8cd`・`0x1000b8cf`・`0x1000b8f7`): x87 の stack underflow。 native は -qNaN (`ffc00000`)、wasm は 0 を返す → 子 #4146 (PLG-G2-49)。
  3. `ecx` 基底の読みで native が segfault する 6 本 (`0x10003fe0`・`0x100051f0`・`0x100085a0`・`0x100096d0`・`0x1000a95a`・`0x1000ba05`) → 子 #4147 (PLG-G2-50)。
- 既存 2 本の判定は変わらない。 harness の変更 (`ebp` の初期化・§4) を入れた後も、既存 2 本の数字は変更前と一致した。
- ネガコン 2 種は HEAD で検出 (§2)。

## 2. 実測 (測定 commit `cb4762d72`・各試験は単独実行・`lift_text.py` 後に実施)

| 試験 | 結果 | exit | wall | build (native / wasm emcc) | run (native / wasm node) | load1 (run 前) |
|---|---|---|---|---|---|---|
| `python3 x87_fn_diff.py` (TARGETS 2 本・4,000 行ずつ) | 構造 (eax・x87 深さ) 全行一致。 `0x10002ee0` 3,890/4,000 bit 一致 (float32 は 4,000/4,000)、`0x10005400` 3,405/4,000 bit 一致 (float32 は 4,000/4,000) | 0 (PASS) | 5.46 s | 0.03 s / 3.71 s | 0.104 s / 0.184 s | 0.29 |
| `--nega` | bit 一致 7,295 → 7,294 (ST(0) の最下位 bit を反転)。 ネガコン OK | 0 | 1.15 s | (同上) | — | — |
| `--nega-lower` | `fn_10002ee0` の float32 結果が一致しない行 4,000 / 4,000。 演算の取り違えを検出。 ネガコン OK | 0 | 4.65 s | — | — | — |

測定の注記: `--nega` を `x87_fn_diff.py` の通常実行と並列に走らせた試行は、出力ファイル (`work/x87fn/`) の競合で失敗したため採らず、単独で取り直した。 同じ commit で `lift_text.py` は exit 0 (`emcc` 6.0.12 を PATH に置いた状態)。

## 3. 残り 12 本の試行 (#4065 の一覧)

lift 出力 (`work/lift_text/ott_lifted.c`) から、関数ごとの `ecx` 相対の読みと絶対読みを数えた。 試行は各関数 16 行 (`work/probe12`) または 4,000 行 (`x87_fn_diff.py`)。

| 関数 | x87 命令数 | `ecx` 相対の読み | 絶対読み | native (16 行) | 判定 |
|---|---:|---|---|---|---|
| `0x10003fe0` | 56 | あり (`0x80174`・`0x821700` 等) | `0x10013488`〜 | rc 139 (segfault) | 子 #4147 |
| `0x100051f0` | 19 | あり (`0x520cd4`・`0x5a0e64` 等) | `0x1001347c`・`0x100134a4` | rc 139 | 子 #4147 |
| `0x100085a0` | 1 | あり (`0x520cc8`) | なし | rc 139 | 子 #4147 |
| `0x100096d0` | 104 | あり (40 箇所) | `0x100134e4`・`0x100139b8` | rc 139 | 子 #4147 |
| `0x1000a95a` | 4 | なし | `0x100131e0` | rc 139 | 子 #4147 |
| `0x1000ba05` | 2 | なし | なし | rc 139 | 子 #4147 |
| `0x1000b6c1` | 3 | なし (`ebp` 相対) | `0x10024d50` (f80 の定数) | rc 0 (16 行) | 値は 4,000/4,000 一致。 非自明性なし → 子 #4146 |
| `0x1000b8a2` | 4 | なし (`ebp` 相対) | `0x10024dc4` | rc 0 | 値は 4,000/4,000 一致。 非自明性なし → 子 #4146 |
| `0x1000b936` | 5 | なし (`ebp` 相対) | `0x10024db0` | rc 0 | 値は 4,000/4,000 一致。 非自明性なし → 子 #4146 |
| `0x1000b8cd` | 5 | なし (`ebp` 相対) | なし | rc 0 | 空スタック読み。 ST(0) が native -qNaN・wasm 0 → 子 #4146 |
| `0x1000b8cf` | 4 | なし (`ebp` 相対) | なし | rc 0 | 同上 |
| `0x1000b8f7` | 8 | なし (`ebp` 相対) | なし | rc 0 | 同上 |

`x87_fn_diff.py` に 5 本 (既存 2 本 + `0x1000b6c1`・`0x1000b8a2`・`0x1000b936`) を入れた試行では、3 本は構造が一致 (eax・深さ不一致 0) したが、OBJ 窓が変わった行 0 / 4,000 で非自明性の判定が FAIL した。 `0x1000b8cd`・`0x1000b8cf`・`0x1000b8f7` を入れた試行では、ST(0) が `nan-num` (native -qNaN と wasm 0) で FAIL した。 いずれも判定器を緩めて通すことはしていない。

### 3.1 underflow の 3 本 (空スタック読み)

`fn_1000b8cd` の行の出力 (native と wasm。 `d=7` は、関数の中で `fld` を 1 本も積まず、TOP が 7 を指す状態):

```
native: va=1000b8cd eax=00000000 st0=ffc00000 st0d=fff8000000000000 d=7
wasm:   va=1000b8cd eax=00000000 st0=00000000 st0d=0000000000000000 d=7
```

`ott_x87.h` の制限 (4) は「スタックの over/underflow を模型化しない」。 native が返す -qNaN は x87 の stack underflow の不定値で、wasm の模型は 0 を返す。 これは lift の既知の模型化の範囲外の差で、本付録では wasm 側を直さない (子 #4146 で扱いを決める)。

## 4. harness の変更 (測定 commit に含まれる)

- `x87_fn_glue.c` (`ott_call32x`): `R[RBP] = GUEST_STACK_TOP - 0x1000` を設定。
- `x87_fn_native.c` (`call_guest`): `mov $0x10F00000-0x1000,%ebp` を設定。

理由: `ebp` 相対の読みを持つ関数 (`0x1000b6c1` など) が、`ebp` の残値で wasm の境界外 (`memory access out of bounds`) に出るため。 変更前と変更後で、既存 2 本の数字は一致した (3,890/4,000 と 3,405/4,000)。 この変更は既存の判定を変えない。

## 5. 検証の手順 (再現)

emsdk の導入 (REFERENCES の `[EMSDK]` pin。 `tools/m1/flags.sh` の `EMCC_VERSION_PIN=6.0.12`):

```
git clone --depth 1 https://github.com/emscripten-core/emsdk.git /tmp/opencode/emsdk-src
cd /tmp/opencode/emsdk-src && ./emsdk install 6.0.12 && ./emsdk activate 6.0.12
source /tmp/opencode/emsdk-src/emsdk_env.sh   # emcc を PATH に入れる
```

再現手順 (前提: `emcc` が PATH にあること。 無いと `lift_text.py` は末尾の `emcc -c` で終了 1 になる):

```
cd tools/plugins/slayer_engine_ia32
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # fl-win64 の extracted/block22434_PE.bin を展開済みであること
python3 lift_text.py                        # work/lift_text/ott_lifted.c を作る (前提: emcc 要)
python3 x87_fn_diff.py                      # exit 0 (PASS)
python3 x87_fn_diff.py --nega               # exit 0
python3 x87_fn_diff.py --nega-lower         # exit 0
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ebp` 相対だけを書く 3 本の非自明性 (OBJ 窓が変わらない) | 判定器が 3 本を通せない | #4146 (PLG-G2-49) |
| 空スタック読みの 3 本 (native -qNaN と wasm 0 の食い違い) | 3 本の判定が FAIL のまま | #4146 (PLG-G2-49) |
| `ecx` 基底の読みで native が segfault する 6 本 | 6 本が試験できない | #4147 (PLG-G2-50) |
| native ランナーの segfault を exit 非 0 で検出する | 異常終了が exit 0 に見える (#4065 の受入) | #4147 (PLG-G2-50) |
