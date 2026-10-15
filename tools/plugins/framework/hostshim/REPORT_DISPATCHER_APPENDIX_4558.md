# PLG-P0b-52 (#4558) — P56 0x9dec3f の書込み到達と 6 ID の値

親 #4385。前提: `REPORT_DISPATCHER_APPENDIX_4130.md` §4 (Phase A 実施不能) と `REPORT_DISPATCHER_APPENDIX_3673.md` §4.1 (6 ID の格納元 VA)。

## 1. 測定条件

- 基準 commit: `origin/main` (`7033a7bad`)。測定 commit: 本 PR の最後の commit (`hs_p56_callers.py` 追加。コードを変えた最後の commit)。
- 素材: `fl-win64` (`[WIN64]`) の `extracted/block00031_PE.bin` (22,227,016 B) を展開して使用。`work-fw-stage1` を展開し、`fw_stage2.sh` を走らせて stage-2 の 8 件 (`fw_flat4_canon3.ll` 等) を再生成した。`toolchain-emsdk` は `[EMSDK]` (emcc 6.0.12。`tools/m1/flags.sh` の pin と一致) として使用。
- Python: `uv` で venv を作り `unicorn 2.1.4`・`pefile`・`capstone 5.0.7` を入れた。
- load: 測定中 1.3 前後 (`uptime` 10:02 時点で 1.34)。実行は n=1。

## 2. 受入 1: 0x9dec3f の到達と 0x40f9e0 の戻り値 — 未達

- `hs_val_probe.py disp 0x18 0x45 0x54 0x56 0x64 0x65` (Dispatcher 単独・観測点は既存の DISP_PROBES): 6 ID とも `stop=ended`・`rax=0x0`・path 855〜880 件。観測点 `0x41d919`・`0x11fc2b3`・`0x9dec3f` のいずれにも到達しなかった。
- `hs_p56_callers.py` (`.text` を capstone で走査): `0x9dec3f`・`0x40f9e0`・`0x41d8f0`・`0x11fba90`・`0x41d919`・`0x11fc2b3` への**直接 call は 0 件**。書込みは間接 call か上位関数内の store と考えられるが、本 run では特定していない。
- よって 0x40f9e0 の戻り値は記録できなかった。

## 3. 受入 2: 0x54・0x64・0x65 の値 — 未確定

到達した観測点の値のみ記録する (格納直前の値ではない):

| ID | 観測点 | 観測値 |
|---|---|---|
| 全 6 ID | 0x1318730 (`[rbp+0x1880]`) | 0 |
| 0x54 | 0x13226dd (`[rbp+0x1880]`) | 0 |
| 0x64 | 0x1322a07 (`[rbp+0x1880]`) | 0 |
| 0x65 | 0x1322b47 (`[rbp+0x109c]`・`[rbp+0x1168]`) | 0・`0x54534154` (Tag "TAST") |

0x18・0x45・0x56 は格納元 (0x41d919・0x11fc2b3・0x9dec3f) に届かないため、観測値は無い。格納値 (G18・P45・P56 と 0x54・0x64・0x65) は**未確定**。

## 4. 受入 3: hostshim.c の応答表 — 未実施

確定値が無いため `hostshim.c` は変更していない。

## 5. Phase A 回帰 (`hs_e2e.sh --fresh`)

- `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` — 回帰値と一致。
- Phase B は `memory access out of bounds` で `E2E FAIL` (`status=0xffffffff plug=0x0 rec=7`)。同一の Phase B 例外は `REPORT_P0c9.md` で既知 (#1229 で追跡)。本 PR の変更 (なし) とは無関係。
- 実測時間: 2 分 28 秒 (`time` の real 148.4 秒)。
- `fw_smoke_check` (`fw_stage2.sh` 末尾): `runerr=1` (expect 0)・`init_reach=16` (expect 288) の不一致。`fw_stage2.sh` の EXIT=1 はこれによる。hostshim 変更とは別件。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x9dec3f の書込み経路 (間接 call 経由の上位関数) の特定と 0x40f9e0 の戻り値 | 受入 1。6 ID の格納値が決まらない | 本 issue #4558 (Refs。残りは PM が子を切る) |
| Phase B の OOB と `hs_e2e.mjs` の PASS 判定の不整合 | Phase A の判定には影響しない | #1229 (既存) |
| `fw_smoke_check` の `runerr=1`・`init_reach=16` 不一致 | smoke ゲートの判定 | 既存の framework 側の問題。PM 判断 |
