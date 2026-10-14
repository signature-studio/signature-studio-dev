# REPORT 付録 — #829 (HB-H20): x64c wasm build と CreatePlugInstance 入場の実測

> **正本 (測定値)**: 本付録。`tools/hostbridge/wrapper_lift/REPORT.md` §14 は結論と表のみ。

測定 commit: `a55fd489` (harness コードを追加した commit)。測定は `a55fd489` の harness で行った。`a55fd489` から HEAD までの `.py`・`.sh`・`.mjs`・`.c` の差分は 0 行 (`cpi_reach.sh` は測定後に変更していない)。
検証起点: `origin/main` @ `9b352bd7` (作業ブランチ `829-wrapper-cpi-reach`、worktree `ws-829`)。
環境: `[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP/r829/extracted`)・node v22.23.3。4 vCPU。全段直列 (並列 1)。load average は各段の開始・終了時の 1 分値 (`/proc/loadavg`)。

## 1. build (受入条件 1)

手順: `x64c_wrapper.py` → `emcc -c -I tools/ott/rt` → `emcc -Wl,--export-all -Wl,--allow-undefined`。

| 段 | block19091 | block23676 |
|---|---|---|
| 生成 `x64c_wrapper.py` | exit 0・**67 s**・load 1.13 → 1.08 | exit 0・**67 s**・load 0.21 → 0.76 |
| `ott_lifted.c` | 66,774,883 B | 66,784,597 B |
| `emcc -c` | exit 0・**45 s**・error 0 行・load 0.99 → 1.04 | exit 0・**45 s**・error 0 行・load 0.76 → 0.93 |
| `ott.o` | 57,837,396 B | 57,844,748 B |
| wasm link | exit 0・**11 s**・load 1.03 → 1.49 | exit 0・**1 s**・load 0.93 → 0.93 |
| wasm | **43,828,879 B** | **43,833,146 B** |

- block19091 の link 11 s は emscripten の sysroot (system library) を初回生成した時間を含む。block23676 の link (1 s) は生成済みキャッシュを使う。
- 生成の unsup は 81 種・3,629 件 (両 block 同値)。未解決 callee 47・import 570 (`lift_meta.json`)。
- AC1 の link は rt (`tools/ott/rt/ott_cpu.c`・`ott_glue.c`・`ott_ovr.c`) を含まない。wasm の import に `ott_missing_import`・`ott_unsup`・`ott_unlifted` の 3 件が残る (計 14 import)。build 段の exit 0 はこの状態での値。

## 2. CreatePlugInstance 入場 (受入条件 2、block19091)

### 2.1 harness

- `cpi_reach.sh`: (1) `cpi_image.py` で PE の mapped image (`pefile.get_memory_mapped_image`) を取り出す。ImageBase = `0x400000`、image 6,094,848 B 相当。(2) 生成 C の複製に probe を入れる。`f_86ab10` 先頭に `cpi_enter(0x86ab10)`、各命令コメント行 (`/* 86ab10: push rbp */`) の後に `cpi_at(VA)`。直近 256 件を wasm メモリの ring に残す。(3) `emcc -c` → `ott_cpu.c`・`ott_glue.c`・`ott_ovr.c` と共に node 用 MODULARIZE で link (`-sGLOBAL_BASE=268435456`・initial/max memory `0x36000000`)。
- `cpi_reach.mjs`: image を `HEAPU8` の ImageBase に敷き、`_ott_run(0x86ab10, a0, a1, 0, 0, 0,0,0,0)` を呼ぶ。a0 = RCX (host)、a1 = RDX (tag)。`entered` = stderr に `[cpi] enter 0x86ab10` が出たか。trap 後は ring を読み、直近命令 VA を出す。
- 呼出経路 (実測の C ソース): `f_86ab10` は `0x86ab5e` で `f_77fbb0` を直接 call する (`R[RSP] -= 8; ST64(R[RSP], 0x86ab5eULL); f_77fbb0();`)。
- 所要: `cpi_reach.sh` 全体 58 s wall (probe 複製の `emcc -c`・link・node 1 回を含む。段ごとは未計測)。load 0.22 → 0.69。

### 2.2 結果

| 条件 | entered | 命令数 (cpi_at 件数) | 最後の VA (命令) | 停止理由 (stderr / trap) |
|---|---|---|---|---|
| a0 = 0 (NULL) | **true** | 49 | `0x77fbf3` (`call qword ptr [rax]`、`f_77fbb0` 内) | `RuntimeError: memory access out of bounds` |
| a0 = `0x30000000` (ゼロ埋めの guest 領域) | **true** | 49 | `0x77fbf3` (同左) | `[ott] call to UNLIFTED function 0x63736d65 (RVA 0x33736d65) ret=0x77fbf5` → abort |
| NC: 別 VA `0x86abc0` を入場 (a0 = 0) | false | 7 | (`ott_unlifted(0)` で停止) | 入場タグ不一致 |

- **入場ログ**: `[cpi] enter 0x86ab10` を両 run で確認 (`entered: true`)。CreatePlugInstance の本体先頭 (`f_86ab10`) に入ったことの実測。
- **最初に失敗する関数**: `f_77fbb0` (VA `0x77fbb0`)、命令 VA `0x77fbf3` の `call qword ptr [rax]` (C 行 1162331 付近)。直前の `0x77fbec` `mov rax, [rbp+0x30]`・`0x77fbf0` `mov rax, [rax]` で得たポインタを間接 call の先頭に使う。
- **理由 (推定)**: host 引数 (RCX) が実体の object を指していない。NULL と zero 領域のどちらでも vtable 相当の値が得られず、間接 call 先が不正になる。この推定は「host object を与えると先へ進む」ことを確かめていないため未検証。
- 命令数 49 は `cpi_at` の総件数 (ring は直近 256 件を保持するので全件保持)。
- 検収時の再実行 (測定時の `cpi.cjs` を流用し、a0 = `0x30000000`): `entered: true`・最後の VA `0x77fbf3`・trap は `ott_unlifted` の abort。上表の 2 行目と一致。

### 2.3 ネガティブコントロール (弱い)

- 入場判定 (`entered`) の入力を 1 件変える (タグ VA `0x86ab10` → 呼出 VA `0x86abc0`) と `entered` は true → false に変わる。判定が常に true になっていないことの確認。
- 強い NC (probe 行 `cpi_enter` を消した複製を再コンパイルして `entered` が false になる確認) は未実施。

## 3. 未検証・注意

- CreatePlugInstance の完走 (host 付きで戻り値を得る)・Dispatcher の実行・wasm の bit 一致は未検証。
- block23676 の入場 (VA `0x86a970`) は未実施。build (§1) のみ。
- `[ott]` 系の abort は `ott_unlifted`・`ott_unsup`・`ott_missing_import` の stderr を根拠とする (lift 側の silent miscompile の証拠ではない)。
- DEFECTS の類型: 該当なし。`ULLULL` は構文エラーとして検出される類型で、本 run では生成後の `ULL` 置換 (`x64c_wrapper.py`) 後に 0 行。

## 4. 再現コマンド

```sh
export EM_CONFIG=$RUNNER_TEMP/r829/emsdk/.emscripten PATH=$RUNNER_TEMP/r829/emsdk/upstream/emscripten:$PATH
export FL_WIN64_DIR=$RUNNER_TEMP/r829/extracted
# 1. build (受入 1)
python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py block19091_PE.bin $RUNNER_TEMP/r829/x64c19091
emcc -c -I tools/ott/rt $RUNNER_TEMP/r829/x64c19091/ott_lifted.c -o $RUNNER_TEMP/r829/ott19091.o
emcc $RUNNER_TEMP/r829/ott19091.o -Wl,--export-all -Wl,--allow-undefined -o $RUNNER_TEMP/r829/link19091.wasm
# 2. CreatePlugInstance 入場 (受入 2)
mkdir -p $RUNNER_TEMP/r829/cpi19091/x64c && ln -sf $RUNNER_TEMP/r829/x64c19091/ott_lifted.c $RUNNER_TEMP/r829/cpi19091/x64c/ott_lifted.c
bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin $RUNNER_TEMP/r829/cpi19091
node tools/hostbridge/wrapper_lift/cpi_reach.mjs $RUNNER_TEMP/r829/cpi19091/cpi.cjs $RUNNER_TEMP/r829/cpi19091/image.bin 0x400000 0x86ab10 0x30000000 0x0
```

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CreatePlugInstance 入場後の完走: host object (TFruityPlug 側) の再構成が要る。NULL・ゼロ領域では `f_77fbb0` の 1 回目の間接 call で停止 (§2.2) | 完走・Dispatcher 実行は未検証 | #2653 (HB-H46) |
| 入場の経路: 本 harness は VA を直接呼ぶ (`_ott_run`)。Wrapper の LoadLibrary → GetProcAddress 経路は未通過 | 起動経路からの到達は未検証 | #2653 (HB-H46) |
| block23676 の入場 (VA `0x86a970`) | build のみ検証 | #2653 (HB-H46) |
| wasm の実行結果 (bit 一致) | 未検証 (完走後に判定) | #2653 (HB-H46) |
