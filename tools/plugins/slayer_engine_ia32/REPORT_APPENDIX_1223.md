# REPORT_APPENDIX_1223 — Slayer_Engine.dll (block22434) の native vs wasm 差分試験 (#1223 PLG-G2-11)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合で、新類型は観測していない)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。

## 1. 入口の決め方 (範囲の縮小)

- 入口は **leaf 関数 4 本** (import も未 lift の call も無く、 OBJ 領域への store だけを行う)。 export `main` (0x10007ca0) は使わない。 `main` は 6 引数の callback を呼び、 CRT の import (38 種) を通るため、 native 側に import 実装が要る (子 [PLG-G2-26] #3127)。
- 対象: `0x10001b40` (thiscall: `[ecx+0x1c]←a0`, `[ecx+4]←a1`)、 `0x10009300` (thiscall: `[ecx+0x15]←al`)、 `0x1000d77e` (`[a0+0x50]←0x100277b0`, `[a0+0x14]←1`)、 `0x10008630` (`[a1]←0` byte)。 いずれも `ret N` の stdcall/thiscall。
- 対象外 (未達): export `main` (子 #3127)・x87 を含む関数 (#2989 の範囲)・import を通る関数・`.text` 全体 (未被覆 11,348 B は #2814)・leaf 外の実行時の論点 3 点 (§4、子 #3128)。

## 2. 方式

| 項目 | native (`native_entry.c`) | wasm (`rt32_glue.c` + lift) |
|---|---|---|
| 実行体 | freestanding i386 ELF (`gcc -m32 -nostdlib -static`)。 32bit libc が runner に無いため `int 0x80` の syscall のみ | `emcc -O1 -ffp-contract=off` で `work/lift_text/ott_lifted.c` (x64c `--arch ia32`、465 関数) + `rt/ott_cpu.c` を wasm 化 |
| guest 配置 | image を mmap で VA `0x10000000` に敷設 (`image.bin` = SizeOfImage) | 同じ image を `HEAPU8` の `0x10000000` へ書く (ia32 lift は恒等写像) |
| 呼出し | esp を保存 → 引数 4 つを push → `ecx`=this → `eax=edx=0` → `call` → esp 復元 | `ott_call32`: `R[RSP]=0x10F00000`、同じ push 順、`R[RCX]`=this、`R[RAX]=R[RDX]=0`、`ott_dispatch(va)` |
| 観測 | eax と OBJ 領域 `0x10F80000` の 128 B | 同じ |
| 入力 | `scen.txt` 256 行 (seed 1223、4 入口 × 64)。 行ごとに OBJ 領域の初期値 128 B と引数を与える | 同じファイルを node (`entry_wasm.mjs`) で読む |

## 3. 実測 (測定 commit は §5、 n=3)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_entry.py`) | `[compare] PASS: 256 / 256 件が bit 一致、不一致 0 件`・`[diff_entry] PASS`・exit 0 (3 回とも同一) |
| 非自明性 | native 実行で OBJ 領域が変わった行 256 / 256 (`[effect]`) |
| ビルド (min–max) | native build 0.04–0.13 s、wasm emcc 5.20–5.62 s。 emsdk 6.0.12 (repo の pin、 `toolchain-emsdk` を展開せず上流から導入。 `lift_text.py` の実行後に emcc キャッシュ有り) |
| 実行 (min–max) | native 0.002 s (3 回とも)、wasm (node) 0.042–0.051 s |
| load (cpu 4、 並列 1) | load1 0.69–0.76 (`diff_entry.py` の run 直前の出力) |
| ネガコン (`python3 diff_entry.py --nega`) | wasm 出力の 1 行目の eax の 1 bit を壊して判定器に通す → `[compare] FAIL: 255 / 256 件が bit 一致、不一致 1 件` → `[nega] 1 bit 壊した出力を検出 (FAIL, exit 1)。 ネガコン OK`・exit 0 (判定器は exit 1 で落ちた) |

## 4. 既知の制約 (この試験の意味の限定)

- 初版では `eax` が不一致 (64 行、`0x10009300`)。 原因は**呼出し前の eax の値** (native 側の残値と wasm 側の残値が違う)。 `mov al,…` は上位 24 bit を残すため、 harness の既定値に依存した。 両側で `eax=edx=0` に固定して解消 (`native_entry.c` の `call_guest`、 `rt32_glue.c` の `ott_call32`)。 これは harness の定義の修正で、 lift の挙動の変更ではない。 lift の出力 (`ott_lifted.c`) は変えていない。
- 入口 4 本の意味論は leaf の範囲のみ。 次の 3 点は 4 本では通らず未検証 (`REPORT_APPENDIX_1098.md` §7 から #1223 へ送られた項目。 子 [PLG-G2-27] #3128 に送る):
  - 実行時の間接 call 先 (`ott_dispatch`) と native との差分
  - `sahf` の AF 未反映 (runtime に fAF が無い)
  - `fs:` (TEB) の読みが `ott_teb_blk` (0 埋め模型) を指す
- wasm の guest stack は `0x10F00000` (image の上の余白)。 native の stack は process 既定 (差は観測されない: 4 本とも stack の内容を返さない)。

## 5. 再現手順と検証

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst で展開
source <emsdk>/emsdk_env.sh                 # emsdk 6.0.12 (toolchain-emsdk → [EMSDK])
python3 tools/plugins/slayer_engine_ia32/lift_text.py        # work/lift_text/ott_lifted.c を作る (前提・約 7 s)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py       # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py --nega  # ネガコン (exit 0 = 検出)
```

- 測定 commit: `0a376e91` (コードを変えた最後の commit。 `diff_entry.py`・`native_entry.c`・`rt32_glue.c`・`entry_wasm.mjs` はこの commit で初めて追加された)。 §3 の n=3 はこの commit の内容 (`git status` が空の worktree) で測った。
- 鮮度の証跡 (WORKFLOW §6): 測定後に変えたのは本付録と REPORT の文書のみ。 `git diff 0a376e91 <検証 HEAD> -- tools/plugins/slayer_engine_ia32/diff_entry.py tools/plugins/slayer_engine_ia32/native_entry.c tools/plugins/slayer_engine_ia32/rt32_glue.c tools/plugins/slayer_engine_ia32/entry_wasm.mjs tools/plugins/slayer_engine_ia32/lift_text.py tools/ott/rt tools/ott/lift` の出力は 0 行 (差分 0)。 検証 HEAD は PR 本文の『検証 HEAD』欄が正 (付録の commit 自身では hash を書けないため)。
