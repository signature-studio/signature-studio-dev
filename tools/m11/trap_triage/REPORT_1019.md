# #1019: unit 149 の oob 最上位 frame `412e40 ← 653660` と、`M11_FIX_652500=1` 時の unit 888 退行

**判定: 受入条件 1〜4 は未達** (原因特定・修復・ネガコンのいずれも完了せず)。本 run は、gate ON 時の退行を n=3 で再現し、切り分けの材料を揃えた。**Refs #1019** (Closes しない)。残りは子 issue に分割。

親: #748 (M11-N41) / 前提: PR #1018 (merged, gate `M11_FIX_652500` 既定 0)。

## 0. 検証環境

- HEAD = `origin/main` `a5adb2fc` から切った `1019-m11-unit149-oob-412e40`。
- 素材: `fl-win64` (展開先は `FL_WIN64_DIR` 配下)、`toolchain-emsdk` (`[EMSDK]`)、`toolchain-retdec` (`[RETDEC]`)、`work-m11`、`work-liftdiff` を `tar --zstd -xf` で展開 (計 16 秒)。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl` (展開先の直下。`.../extracted/extracted` にすると ldfix が skip して fail-closed する)。
- `m11_gen_ir2.sh`: rc=0, 43.95 s, `ldfix=applied`, `ir_sha256=f5b27a23…`, `boot_final.ll` 490693 行。

## 1. gate OFF/ON の survey (n=3, `trap_triage/survey_units.mjs`)

build は `M11_FIX_652500={0,1} m11_build.sh` (6 回 rc=0、全体 3m24s、load 1 分値 0.77〜1.01)。

| 構成 | ok | oob | halt0 | miss | other | noproc | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (gate=0) n=3 | 869 | 16 | 8 | 47 | 1 | 1 | 942 |
| ON (gate=1) n=3 | 869 | 15 | 9 | 47 | 1 | 1 | 942 |

n=3 の OFF/ON 間で kind の遷移は 3 回とも同一 (min = max):

- 368: halt0 → ok
- 659: oob → halt0
- 888: **ok → halt0** (退行)

issue 本文の「unit 888 の ok → halt0 退行 (ON)」は再現した。

**注意**: 同じ build 上で `m11_survey.mjs` (`M11_SURVEY_STACK=149,888`) を実行すると、888 は OFF/ON とも `returned 1` (ok 相当) になり、退行しない。2 つの survey の間で 888 の判定が一致しない。原因は未確認 (§3)。

## 2. unit 149 / 888 の trap 情報

- **unit 149** (`0x264260`, OFF/ON とも oob)。最上位 frame `412e40 ← 653660 ← 6539e0`。`m11_survey.mjs` の stack (ON) は `wasm-function[75]` を最上位とし、`[3903] → [3904] → [3982] → [3984] → [10985] → [14848] → [14864]` を経由する。関数名への解決は未実施。
- **unit 888** (`0xeaea40`, ON): `survey_units.mjs` では `growMemory: Attempted to grow heap from 1908473856 bytes to 2083979264 bytes ... Maximum memory size exceeded` が 2 回出て halt0。OFF 側は同じ unit が `[m11][VA-big] ... live=1280.7MB` で ok。ON 側は `live=1626.9MB` で、wasm memory 上限に当たる。**論理差ではなく、ON で VA 使用量が増えて上限を超えた可能性がある** (未確認)。

## 3. 機械語・IR の突合 (途中まで)

- `653660` (機械語 `0x653660`) の `0x65394d` / `0x65395e` で、`rcx = [rbp+0x40]` / `[rbp+0xb0]`、`edx = 0xc` / `2` を渡して `412e40` を呼ぶ。
- `412e40` (IR `boot_final.ll` 115662 行) は第 1 引数を `ptr` として `load i64` する (`%1 = load i64, ptr %0`)。`653660` 側の渡し値 (`[rbp+0x40]` / `[rbp+0xb0]`) が stack slot のアドレスか、deref 脱落で値のままかは **未判定**。
- `652500` (gate ON で置換される側) は機械語 `652500..65257c` を転記済み (`m11_ov.c` 723 行以降)。`653660` は `0x653725` で `652500` を呼ぶ。

**未判定の理由**: 時間切れ。IR 側の `653660` 内の `412e40` 呼出 (`%` の値の出どころ) と、機械語 `[rbp+0x40]` の初期化 (`0x65367b` 以降で 0 クリア) の突合を最後まで終えていない。

## 4. ネガコン

- gate OFF/ON の切替で unit 149 は oob のまま (OFF = ON)。ネガコンは「修復を外すと oob が復帰する」だが、149 は修復の有無にかかわらず oob のため、現時点では効果を示せない。
- 退行 (888) はネガコンで確認済み: gate OFF で ok、ON で halt0 (n=3)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 149 `412e40 ← 653660` の原因 (IR `%` の値の出どころと機械語 `[rbp+0x40]` の突合) | 受入条件 1・2 未達 | 子 issue #1230 ([M11-N75]) |
| unit 888 の退行: ON で `WebAssembly.Memory.grow` 上限超過 (live 1626.9MB) か、論理差か | 受入条件 2 未達。gate を既定 ON にできない | 子 issue #1231 ([M11-N76]) |
| `survey_units.mjs` と `m11_survey.mjs` で 888 の判定が不一致 | survey 数値の信頼性 | 子 issue #1231 (同上) |
| 修復 (受入条件 3) とネガコン (受入条件 4) | 本 run では未着手 | 原因特定後に #1019 で継続 |
