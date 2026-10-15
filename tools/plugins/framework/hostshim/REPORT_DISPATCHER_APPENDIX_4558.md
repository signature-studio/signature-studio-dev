# PLG-P0b-52 (#4558) — P56 0x9dec3f の書込み到達と 6 ID の値

親 #4385。前提: `REPORT_DISPATCHER_APPENDIX_4130.md` §4 (Phase A 実施不能) と `REPORT_DISPATCHER_APPENDIX_3673.md` §4.1 (6 ID の格納元 VA)。

## 1. 測定条件

- 基準 commit: `origin/main` (`7033a7bad`)。測定 commit: `4913e3cc1` (`hs_p56_callers.py` を rel32 E8 走査に直した最後の commit。コードを変えた最後の commit)。以降の実測はすべてこの commit で行った (`git rev-parse --short HEAD` = `4913e3cc1`)。
- 素材: `fl-win64` (`[WIN64]`) の `extracted/block00031_PE.bin` (22,227,016 B) を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開。`work-fw-stage1` と `[EMSDK]` は本 run では使っていない (下記 §4)。
- Python: `uv` で venv を作り `unicorn 2.1.4`・`pefile`・`capstone 5.0.7` を入れた。
- load: 実測時 0.05〜0.58 (`uptime`)。実行は n=1。
- 鮮度: `git diff --stat 286ceee5e HEAD -- tools/plugins/framework/hostshim` の出力は次のとおり。
  ```
  .../hostshim/REPORT_DISPATCHER_APPENDIX_3673.md    |  2 +-
  .../hostshim/REPORT_DISPATCHER_APPENDIX_4385.md    | 71 ++++++++++++++++++++++
  .../hostshim/REPORT_DISPATCHER_APPENDIX_4558.md    |  4 +-
  tools/plugins/framework/hostshim/hs_p56_callers.py | 23 ++++---
  tools/plugins/framework/hostshim/hs_val_probe.py   | 34 +++++++++++
  5 files changed, 119 insertions(+), 15 deletions(-)
  ```
  `REPORT_..._3673.md`・`REPORT_..._4385.md` の差分は main 取り込み由来 (`44f5c68bb`・`f2d120aa7` は `origin/main` の祖先)。PR 自身が変えたコードは `hs_p56_callers.py` (`4913e3cc1`) と `hs_val_probe.py` の新モード (`g18caller`・`p45caller`) の 2 つ。既存の `disp` 経路は変わっていない。
- 同区間で `hostshim.c`・`hs_e2e.sh`・`tools/liftlib`・`tools/icall/*.py`・`tools/m5`・`tools/plugins/framework/fw_stage2.sh` の差分は 0 行 (`git diff --stat 286ceee5e HEAD -- <範囲>` の出力は空)。

## 2. 受入 1 (到達の実測) — 達成。格納元には未到達。0x9dec3f の経路と 0x40f9e0 の戻り値は未達 (#4595)

### 2.1 Dispatcher 単独 (`disp`)

- `hs_val_probe.py disp 0x18 0x45 0x54 0x56 0x64 0x65` @ `4913e3cc1`: 6 ID とも `stop=ended`・`rax=0x0`・path 855〜880 件。格納元 VA (0x41d919・0x11fc2b3・0x9dec3f) には届かない。実測 6.4 秒。
- 観測点 0x1318730 は全 6 ID で到達 (計装が動いている証拠)。

### 2.2 呼出し元の走査 (`hs_p56_callers.py` @ `4913e3cc1`)

- rel32 `E8` を `.text` 全バイトで走査する方式に直した。前版は capstone の線形走査を使い、`.text` 内のデータでずれて実在する call を取りこぼしていた。
- 0x41d8f0 ← 0x1376870 (1 件)、0x11fba90 ← 0x124e621 (1 件)。両方とも逆アセンブルで命令境界を確認した (`call 0x41d8f0`・`call 0x11fba90`)。前版の「直接 call 0 件」は誤り。
- 0x9dec3f ← 0 件。直接 call は無い。0x41d919・0x11fc2b3 ← 0 件 (store 命令のアドレスで call の対象ではない)。
- 0x40f9e0 ← E8 候補 2139 件。候補は未検証のため件数は参考値。

### 2.3 G18 の書込み関数 (`g18caller` @ `4913e3cc1`)

0x41d8f0 を単独で実行 (実測 6.4 秒)。

| ID | r9=1 で 0x41d919 到達 (書込み直前の r8) | r9=0 で 0x41d919 到達 |
|---|---|---|
| 0x18 | 到達 (r8=0x18) | 未到達 |
| 0x45 | 到達 (r8=0x45) | 未到達 |
| 0x54 | 到達 (r8=0x54) | 未到達 |
| 0x56 | 到達 (r8=0x56) | 未到達 |
| 0x64 | 到達 (r8=0x64) | 未到達 |
| 0x65 | 到達 (r8=0x65) | 未到達 |

- G18 の書込みは `r9≠0` の分岐でのみ起きる。0x1376870 が `r9` に何を入れるかは未確定 (#4557 の子で扱う)。

### 2.4 P45 の書込み関数 (`p45caller` @ `4913e3cc1`)

0x11fba90 を this=HOST・`[this+0x34a8]=0` で単独実行 (実測 6.5 秒)。

- 0x11fbaef (`[this+0x34a8] <= 0` の入口): 到達
- 0x11fbb4f (`cmp eax,0xb`): 未到達
- 0x11fc2b3 (`mov [P45], rax`): 未到達
- 分岐 0x11fbb4f に届くには `[[rbp+0x140]+0x10]` の前提が要る。その値の経路は未確定 (#4557 の子で扱う)。

### 2.5 6 ID の値

- 格納元 (0x41d919・0x11fc2b3・0x9dec3f) に届いた ID は無い。格納値は未確定。
- 観測点の値 (到達したもののみ):

| ID | 観測点 | 観測値 |
|---|---|---|
| 全 6 ID | 0x1318730 (`[rbp+0x1880]`) | 0 |
| 0x54 | 0x13226dd (`[rbp+0x1880]`) | 0 |
| 0x64 | 0x1322a07 (`[rbp+0x1880]`) | 0 |
| 0x65 | 0x1322b47 (`[rbp+0x109c]`・`[rbp+0x1168]`) | 0・`0x54534154` (Tag "TAST") |

## 3. 受入 3: hostshim.c の応答表 — 未実施

確定値が無いため `hostshim.c` は変更していない。

## 4. Phase A 回帰 (`hs_e2e.sh --fresh`) — 本 run では再実行していない

- 再実行しなかった理由: `fw_stage2.sh` と `hs_e2e.sh` の入力 (`work-fw-stage1` の stage-2 出力、`toolchain-emsdk`) を展開して再生成する時間が本 run の上限に収まらないと判断した。
- 鮮度の根拠: §1 のとおり、e2e が使う `hostshim.c`・`hs_e2e.sh`・`tools/liftlib`・`tools/icall/*.py`・`tools/m5`・`fw_stage2.sh` は `286ceee5e` から変わっていない。変わったのは e2e から呼ばれない Python 計測スクリプトだけ (`grep` で `hs_val_probe`・`hs_p56_callers` の呼出し元が tools 配下の `*.sh`・`*.mjs`・`*.cjs`・`*.js`・`*.ts`・`*.yml`・`*.json` に無いことを確認)。
- 前回実測 (測定 commit `286ceee5e` 時点、PR 作成時): Phase A `dispatch=38 ff=0` 一致。Phase B は既知の `memory access out of bounds` で E2E FAIL (`REPORT_P0c9.md` で既知・#1229)。実測 2 分 28 秒、load 1.34。
- `fw_smoke_check` (`fw_stage2.sh` 末尾): `runerr=1` (expect 0)・`init_reach=16` (expect 288) の不一致で EXIT=1。main `7033a7bad` 上での再現は**未確認**。hostshim の変更とは別件として扱う。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x41d8f0 の呼出し元 0x1376870 の経路と、`r9≠0` になる条件 (G18 の実値) | 受入 1・3 (G18) | 子 #4557 `[PLG-P0b-51]` |
| P45 の分岐 0x11fbb4f の前提 (`[rbp+0x140]` の値) と 0x11fc2b3 の到達 | 受入 1・3 (P45) | 子 #4557 `[PLG-P0b-51]` |
| 0x9dec3f の書込み経路と 0x40f9e0 の戻り値、6 ID の残り (0x54・0x64・0x65) | 受入 2・3 | #4595 `[PLG-P0b-53]` |
| hostshim.c の応答表の更新 (値が確定した後) と Phase A 回帰 | 受入 3・4 | #4595 `[PLG-P0b-53]` |
| Phase B の `memory access out of bounds` | Phase B の PASS | #1229 (既存) |
| `fw_smoke_check` の `runerr=1`・`init_reach=16` 不一致 | smoke ゲートの判定 | 既存の framework 側の問題。PM 判断 |
