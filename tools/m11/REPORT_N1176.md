# M11-N71 (#1176): work-m11 同梱の古い obj/rt.o・win.o が build を落とす件

## 1. 症状の再現

素材: `work-m11` (R2 `artifacts/work-m11.tar.zst`) を `tools/m11/` 直下に展開 (tar の中身は `tools/m11/work/` 始まり)、
`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開。ベース commit `916d9932` (origin/main)。

| 手順 | rc | 所要 | 結果 |
|---|---|---|---|
| `m11_e2e.sh` (既定。`work/lift_pe.sha256` 無し → 全再生成へ) | 1 | 0.6 s | `m11_bounds` が `tools/m2/work/ghidra_dll/functions_dll.csv` 不在で fail-closed (Ghidra 未導入。素材に無い) |
| `m11_gen_ir2.sh` (素材の lift 成果物から IR 生成) | 0 | 44 s | `ldfix=applied`・`boot_final.ll` 490,693 行 |
| `m11_build.sh` (1 回目。snapshot の rt.o が mtime で古く判定される) | 0 | 25 s | `m11_rt.c` が source 側で新しく再コンパイルされた |
| `touch work/obj/{rt,win}.o` して `m11_build.sh` (修正前) | **1** | - | `emcc: error: undefined exported symbol: "_m11_set_va_bigtrace" [-Werror]` (issue の症状と一致) |
| 同 (修正後) | 0 | 18.5 s | `m11_rt.c` `m11_win.c` を再コンパイル、`rt.o` に `set_va_bigtrace` 1 件、undefined 0 |

## 2. 原因 (確認できた範囲)

`m11_build.sh` の `cc <src> <obj>` は mtime (`src -nt obj`) だけで再コンパイルを判定する。
そのため、同梱 obj (2026-10-10 06:40 の古い snapshot) が source (`m11_rt.c`・`m11_win.c`) の mtime 以上に新しいと、
古い `rt.o` が残って `m11_set_va_bigtrace` 欠落の link 失敗になる。

- 素材を通常どおり展開した場合 (§1 の 1 回目): source は checkout 時刻で新しく、rt.o は再コンパイルされ rc 0。
  つまり通常の展開では発症しない。
- 発症条件は「obj mtime ≥ source mtime」。§1 の再現は `touch` で作った人工的な条件。
  #928 の `--full` で実際に発生した経路 (obj の mtime が source より新しくなった経緯) は未特定。
- 既存の `neg_413060.stamp` は `M11_NEG_413060`・`M11_DEST_READ`・`M11_INSTR_413060` の変更時にしか rt.o を消さない。
  snapshot 由来の obj は、この stamp の一致判定をすり抜ける。

## 3. 修正

`tools/m11/m11_build.sh`: `m11_rt.c` と `m11_win.c` の連結 sha256 を `work/rtwin.sha256` に記録し、
一致しなければ `rt.o`・`win.o` を消して作り直す (mtime に依存しない)。

## 3a. 修正後の測定 (commit `841aced7`・コミット済み HEAD で再現)

- `touch work/obj/{rt,win}.o` 後の `m11_build.sh`: rc 0・18.5 s・`rt.o` の `set_va_bigtrace` 1 件・undefined 0。
- 直後の無変更再実行: rc 0 (`cc` は winstubs/fnstubs のみ。`rt.o`・`win.o` は stamp 一致で再利用)。
- 測定 commit `841aced7` からのコード差分 (`git diff 841aced7 HEAD -- tools/m11/*.sh tools/m11/*.c`): 本節の追記 commit で
  `tools/m11/REPORT_N1176.md` のみ変わり、コードは無変更。

## 4. 未達・残り

- 受入条件 1 (`m11_e2e.sh --full` が work-m11 展開直後に build を通る): **この runner では未検証** (未解決は #1396 [M11-N89])。`--full` は Ghidra の
  `functions_dll.csv` (`tools/m2/work/ghidra_dll/`) が前提で、素材 (fl-win64 / toolchain-* / work-m11 / work-liftdiff) に含まれず、
  `/opt/ghidra` も無い。build 段の修正は上記 §1 の通り実測済み。`--full` の通し確認は Ghidra 素材 (または `functions_dll.csv` を含む素材) を用意して行う必要がある。
- 受入条件 2 (再現手順の REPORT 実測): 本ファイル §1 に記録 (rc・所要)。
