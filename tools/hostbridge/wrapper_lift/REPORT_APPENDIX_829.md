# REPORT 付録 — #829 (HB-H20): x64c wasm build と CreatePlugInstance 入場の実測

> **正本の分担**: 数値 (exit・秒・load・wasm サイズ) の正本は `tools/hostbridge/wrapper_lift/REPORT.md` §14 の表。本付録は表に無い値 (中間生成物のサイズ・unsup 内訳・入場の実測・再現手順) の正本。表の値は本付録に繰り返さない。

測定 commit: `a55fd489` (harness コードを追加した commit)。測定は `a55fd489` の harness で行った。`a55fd489` から検証 HEAD までの差分は `cpi_reach.mjs` のヘッダコメント 1 行のみ (判定ロジックは不変。差分の出力は §6)。
検証起点: `origin/main` @ `9b352bd7` (作業ブランチ `829-wrapper-cpi-reach`、worktree `ws-829`)。
環境: `[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP/r829/extracted`)・node v22.23.3。4 vCPU。全段直列 (並列 1)。load average は各段の開始・終了時の 1 分値 (`/proc/loadavg`)。

## 1. build (受入条件 1)

手順: `x64c_wrapper.py` → `emcc -c -I tools/ott/rt` → `emcc -Wl,--export-all -Wl,--allow-undefined`。exit・秒・load・wasm サイズは REPORT §14 の表。

| 中間物 | block19091 | block23676 |
|---|---|---|
| `ott_lifted.c` | 66,774,883 B | 66,784,597 B |
| `ott.o` (`emcc -c`・error 0 行) | 57,837,396 B | 57,844,748 B |

- 生成の unsup は 81 種・3,629 件 (両 block 同値)。未解決 callee 47・import 570 (`lift_meta.json`)。
- block19091 の wasm link は emscripten の sysroot (system library) の初回生成を含む。block23676 の link は生成済みキャッシュを使う。
- AC1 の link は rt (`tools/ott/rt/ott_cpu.c`・`ott_glue.c`・`ott_ovr.c`) を含まない。wasm の import は全 14 件で、そのうち `ott_*` が 3 件 (`ott_missing_import`・`ott_unsup`・`ott_unlifted`)。build 段の exit 0 は「未解決 import を許容したリンク成功」の値。
- 所要秒は各段 n=1。差し戻し対応 run で x64c 生成を 2 回再実行した (61 s・60 s。いずれも `ott_lifted.c` は 66,774,883 B で同じ)。変動の min–max (WORKFLOW §5 の n≥3) は未実施。

## 2. CreatePlugInstance 入場 (受入条件 2、block19091)

### 2.1 harness

- `cpi_reach.sh`: (1) `cpi_image.py` で PE の mapped image (`pefile.get_memory_mapped_image`) を取り出す。ImageBase = `0x400000`。image.bin は **6,093,824 B** (最後のセクション末端 RVA `0x5CFC00` まで)。PE の SizeOfImage は `0x5D0000` (6,094,848 B) で、image.bin のサイズとは別の値。(2) 生成 C の複製に probe を入れる。`f_86ab10` 先頭に `cpi_enter(0x86ab10)`、各命令コメント行 (`/* 86ab10: push rbp */`) の後に `cpi_at(VA)`。直近 256 件を wasm メモリの ring に残す。(3) `emcc -c` → `ott_cpu.c`・`ott_glue.c`・`ott_ovr.c` と共に node 用 MODULARIZE で link (`-sGLOBAL_BASE=268435456`・initial/max memory `0x36000000`)。
- `cpi_reach.mjs`: image を `HEAPU8` の ImageBase に敷き、`_ott_run(0x86ab10, a0, a1, 0, 0, 0,0,0,0)` を呼ぶ。a0 = RCX (host)、a1 = RDX (tag)。`entered` = stderr に `[cpi] enter 0x86ab10` が出たか。trap 後は ring を読み、直近命令 VA を出す。
- 呼出経路 (実測のバイト列と C ソース): VA `0x86ab59` の命令は `e8 52 50 f1 ff` (call rel32) で、転送先は `0x77fbb0` (`f_77fbb0`)。戻り先 `0x86ab5e` は、C で `ST64(R[RSP], 0x86ab5eULL); f_77fbb0();` として push される値。
- 所要: `cpi_reach.sh` 全体 58 s wall (測定時・n=1。probe 複製の `emcc -c`・link・node 1 回を含む。段ごとは未計測。再実行の値は §2.2)。load 0.22 → 0.69。

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
- `0x63736d65` の正体: wasm の address 0 に入る emscripten のマーカー ("emsc"・リトルエンディアン)。`cpi.cjs` の起動時初期化が `HEAPU32[0] = 1668509029` (= `0x63736d65`) を書き、stack cookie 検査 (`checkStackCookie`) が同じ値を確かめる (`cpi.cjs` の 374・394 行)。wasm の data segment は 2 件で、いずれも address 0 を覆わない。NULL 経路では host 自体が 0 なので、`mov rax,[rax]` が address 0 の `0x63736d65` を読み、`call [rax]` がその値を番地として読んで OOB になる。`0x30000000` 経路では `[0x30000000]` が 0 なので、`call [rax]` は address 0 の `0x63736d65` を call 先として読み、UNLIFTED function として abort する。
- 差し戻し対応 run の再実行 (2026-10-14、検証 HEAD `47ecd893`、x64c 生成から `cpi_reach.sh` まで §4 の手順・いずれも n=1): NULL は entered=true・49 命令・最後 `0x77fbf3`・OOB、`0x30000000` は entered=true・49 命令・最後 `0x77fbf3`・`0x63736d65` の abort、NC `0x86abc0` は entered=false・7 命令。上表と一致。所要: x64c 生成 59.7 s、`cpi_reach.sh` 全体 41.0 s (load 0.15 → 0.84)。

### 2.3 ネガティブコントロール (弱い)

- 入場判定 (`entered`) の入力を 1 件変える (タグ VA `0x86ab10` → 呼出 VA `0x86abc0`) と `entered` は true → false に変わる。判定が常に true になっていないことの確認。
- 強い NC (probe 行 `cpi_enter` を消した複製を再コンパイルして `entered` が false になる確認) は未実施。#2653 の受入条件に追加した。

## 3. 未検証・注意

- CreatePlugInstance の完走 (host 付きで戻り値を得る)・Dispatcher の実行・wasm の bit 一致は未検証。
- block23676 の入場 (VA `0x86a970`) は未実施。build (§1) のみ。
- `[ott]` 系の abort は `ott_unlifted`・`ott_unsup`・`ott_missing_import` の stderr を根拠とする (lift 側の silent miscompile の証拠ではない)。
- 所要秒の反復 (n≥3 の min–max) は未実施 (§1)。
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

## 6. 測定 commit からの差分

`git diff a55fd489 47ecd893 -- tools/hostbridge/wrapper_lift/*.py tools/hostbridge/wrapper_lift/*.sh tools/hostbridge/wrapper_lift/*.mjs tools/hostbridge/wrapper_lift/*.c` の出力 (コード差分。REPORT・付録の差分は除く)。`cpi_reach.mjs` のヘッダコメント 1 行のみで、判定ロジックと測定に使った経路は変わらない:

```diff
-// 判定は JSON 1 行で出す: entered = 入場ログ "[cpi] enter <entry VA>" を受けたか。false なら err の末尾が最初に失敗した地点。
+// 判定は JSON で出す (null, 1 で整形するため複数行): entered = 入場ログ "[cpi] enter <entry VA>" を受けたか。false なら err_tail の末尾が最初に失敗した地点。
```

検証 HEAD `47ecd893` の再実行 (§2.2) は、このコード状態で行った。以降の commit は文書のみ。
