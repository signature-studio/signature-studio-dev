# REPORT_APPENDIX_1223 — Slayer_Engine.dll (block22434) の native vs wasm 差分試験 (#1223 PLG-G2-11)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合で、新類型は観測していない)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。

## 1. 入口の決め方 (範囲の縮小)

- 入口は **leaf 関数 4 本** (import も未 lift の call も無く、OBJ 領域への store だけを行う)。 export `main` (0x10007ca0) は使わない。 `main` は 6 引数の callback を呼び、CRT の import (38 種) を通るため、native 側に import 実装が要る (未着手)。
- 対象: `0x10001b40` (thiscall: `[ecx+0x1c]←a0`, `[ecx+4]←a1`)、`0x10009300` (thiscall: `[ecx+0x15]←al`)、`0x1000d77e` (`[a0+0x50]←0x100277b0`, `[a0+0x14]←1`)、`0x10008630` (`[a1]←0` byte)。 いずれも `ret N` の stdcall/thiscall。
- 対象外 (未達): export `main`・x87 を含む関数・import を通る関数 (x87 関数は #2989 の範囲)・`.text` 全体 (未被覆 11,348 B は #2814)。

## 2. 方式

| 項目 | native (`native_entry.c`) | wasm (`rt32_glue.c` + lift) |
|---|---|---|
| 実行体 | freestanding i386 ELF (`gcc -m32 -nostdlib -static`)。 32bit libc が runner に無いため `int 0x80` の syscall のみ | `emcc -O1 -ffp-contract=off` で `work/lift_text/ott_lifted.c` (x64c `--arch ia32`、465 関数) + `rt/ott_cpu.c` を wasm 化 |
| guest 配置 | image を mmap で VA `0x10000000` に敷設 (`image.bin` = SizeOfImage) | 同じ image を `HEAPU8` の `0x10000000` へ書く (ia32 lift は恒等写像) |
| 呼出し | esp を保存 → 引数 4 つを push → `ecx`=this → `eax=edx=0` → `call` → esp 復元 | `ott_call32`: `R[RSP]=0x10F00000`、同じ push 順、`R[RCX]`=this、`R[RAX]=R[RDX]=0`、`ott_dispatch(va)` |
| 観測 | eax と OBJ 領域 `0x10F80000` の 128 B | 同じ |
| 入力 | `scen.txt` 256 行 (seed 1223、4 入口 × 64)。 行ごとに OBJ 領域の初期値 128 B と引数を与える | 同じファイルを node (`entry_wasm.mjs`) で読む |

## 3. 実測 (測定 commit は §5)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_entry.py`) | `[compare] PASS: 256 / 256 件が bit 一致、不一致 0 件`・`[diff_entry] PASS`・exit 0 |
| 非自明性 | native 実行で OBJ 領域が変わった行 256 / 256 (`[effect]`) |
| ビルド | native 0.03 s、wasm emcc 3.55 s (n=1、 emcc キャッシュ有り) |
| 実行 | native 0.001 s、wasm (node) 0.037 s (n=1) |
| load average (1 分) | 0.61 (cpu 4、並列 1) |
| ネガコン (`python3 diff_entry.py --nega`) | wasm 出力の 1 行目の eax の 1 bit を壊して判定器に通す → `[compare] FAIL: 255 / 256 件が bit 一致、不一致 1 件` → `[nega] ... ネガコン OK`・exit 0 (判定器は exit 1 で落ちた) |

## 4. 既知の制約 (この試験の意味の限定)

- 初版では `eax` が不一致 (64 行、`0x10009300`)。 原因は**呼出し前の eax の値** (native 側の残値と wasm 側の残値が違う)。 `mov al,…` は上位 24 bit を残すため、harness の既定値に依存した。 両側で `eax=edx=0` に固定して解消 (`native_entry.c` の `call_guest`、`rt32_glue.c` の `ott_call32`)。 これは harness の定義の修正で、lift の挙動の変更ではない。 lift の出力 (`ott_lifted.c`) は変えていない。
- 入口 4 本の意味論は leaf の範囲のみ。 `sahf` の AF 未反映・`fs:` の 0 埋め (`REPORT_APPENDIX_1098.md` §7 の送り先) は、この 4 本では通らない (未検証)。
- wasm の guest stack は `0x10F00000` (image の上の余白)。 native の stack は process 既定 (差は観測されない: 4 本とも stack の内容を返さない)。

## 5. 再現手順と検証

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 EM_CONFIG=... PATH=<emsdk>/upstream/emscripten:<emsdk>/node/…/bin:$PATH
python3 tools/plugins/slayer_engine_ia32/lift_text.py        # work/lift_text/ott_lifted.c を作る (前提)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py       # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py --nega  # ネガコン (exit 0 = 検出)
```

- 測定 commit: 本付録を含む PR の HEAD (`git rev-parse HEAD` を PR 本文に書く)。 `diff_entry.py` と `native_entry.c`・`rt32_glue.c`・`entry_wasm.mjs` は測定 commit で初めて追加される。
