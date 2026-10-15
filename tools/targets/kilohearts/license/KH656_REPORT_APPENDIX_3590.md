# KH-57 (#3590) 付録: 閉包展開の収束試行と各ラウンドの実測

本体 `KH656_REPORT.md` §10 の詳細。`scripts/kh656_closure.py` の round 6 失敗の切り分けと、修正後の閉包の実測。

測定 commit: `0b487d4f2` (`kh656_closure.py` の修正と module F の memset shim 登録。以後の commit は REPORT のみ)。
`git diff 0b487d4f2 HEAD -- tools/targets/kilohearts/license ':!*REPORT*'` の出力は 0 行。

環境: nproc=4・MemTotal 15,989 MB・load average 0.6〜0.7 (実行中)。素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` (3,833,108,300 B) → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `work/winpkg/HeartCore.core_64` (76,642,304 B。§0 と同一)。`toolchain-emsdk` ([EMSDK])・`toolchain-retdec` ([RETDEC]) は既設を使用。`KH_EM_CACHE=$RUNNER_TEMP/emcache`。emcc RSS 上限は既定 11000 MB。

## 1. 各ラウンドの実測

実行: `python3 scripts/kh656_closure.py --rounds 14` を 1 回 (開始 05:49:26・終了 05:51:29、所要 2 分 03 秒)。round 9 の build で停止。各行は閉包が出力した JSON の値。

| ラウンド | lift | 未 lift callee | 新規 lift | wasm B (sha256 先頭 8 桁) | emcc peak RSS MB | undefined import | 入口 `function_180ef7fc0` | kh249_check |
|---|---|---|---|---|---|---|---|---|
| 1 (HEAD 相当) | 8 | 40 | 34 | 54,394 (`7ba79e65`) | 5 (※) | 0 | `unlifted callee 0x180112a30` | ok=17 ng=0 |
| 2 | 42 | 44 | 38 | 192,136 (`0dac597b`) | 90 | 0 | `unlifted callee 0x1801d3b60` | ok=16 ng=1 |
| 3 | 80 | 92 | 86 | 436,971 (`907a34bc`) | 110 | 0 | `unlifted callee 0x180138750` | ok=16 ng=1 |
| 4 | 166 | 154 | 147 | 876,174 (`2478acfb`) | 203 | 0 | `unlifted callee 0x180138a30` | ok=16 ng=1 |
| 5 | 313 | 144 | 137 | 1,543,853 (`8935ad14`) | 312 | 0 | `memory access out of bounds` | ok=16 ng=1 |
| 6 | 450 | 147 | 140 | 2,203,485 (`bc0a4d88`) | 414 | 0 | `memory access out of bounds` | ok=16 ng=1 |
| 7 | — | — | — | build 失敗 | — | — | — | — |
| 8 | 589 | 144 | 136 | 2,824,976 (`008d739d`) | 534 | 0 | `memory access out of bounds` | ok=16 ng=1 |
| 9 | — | — | — | build 失敗 (kh_lower) | — | — | — | — |

※ round 1 は直前の build で emcc キャッシュが温まっていたため 5 MB。round 2 以降は新規の C 生成で peak が増えた。

- round 5 の wasm 1,543,853 B は `KH656_REPORT.md` §7.2 の表の値と一致した (同じ lift 集合・memset shim 版)。
- 注 (既存の不一致): 同じ lift 集合は `KH656_REPORT.md` §7.6 (`9d491eb4`) で 1,543,901 B と記録されており、今回の 1,543,853 B と 48 B 異なる。差の原因は未解明 (`KH656_REPORT.md` §7.2 注と同じ扱い)。受入 3 の wasm 指紋は今回の測定値 (1,543,853 B) を正とし、不一致は既存記録のまま残す。
- round 7: `gen_simd.py` が `KeyError: 'ptr'` で失敗。宣言 `declare void @__asm_rep_stosq_memset(ptr, i64, i64)` を `kh_180fd157c` (lift 内) が呼んでいた。`excluded_i256` に `180fd157c` を加えて再 build し、round 8 が通った。
- round 9: `kh_lower.py` が `stage0 に関数が無い: ['0x180f88488']` で失敗 (gen_simd 由来ではないため、`lic_config.json` は書き換えず停止)。この直前の round 8 の `set_key` で書かれた lift 725 件は未検証のため commit していない。commit 対象の config は HEAD の lift に戻した。
- ラウンド 8 までの emcc peak は 534 MB (cap 11000 MB の 5% 弱)。cap には達していない。

## 2. round 6 失敗 (旧 `kh656_closure.py`) の切り分け

round 6 の再現 (修正前の `kh656_closure.py`・HEAD の config・memset shim 無し) の実測:

- `n1.ll` は 904 個の `define` を持つ。452 関数が `function_<hex>` と `kh_<hex>` の 2 名で出るため。
- 旧 `i256_defs()` は、関数本体に `i256` の語を含むかで判定した。904 定義のうち 652 が該当し、大半は `load i256, ptr @ymm0` (ymm レジスタ状態の global の load) だった。AVX2 命令ではない。
- 旧 `build()` は `i256_defs() & lift` を `dropped_i256` として除外した。round 6 では lift 全件 (452) が返ったため、`modules.F.lift = []` (空) と `excluded_i256` = 452 件が `lic_config.json` に書き込まれた。
- **真の失敗**: `gen_simd.py` の `KeyError: 'ptr'`。宣言 `declare void @__asm_rep_stosb_memset(ptr, i8, i64)` を `kh_1813846d0` (lift 集合内) が呼んでいた。この集合には memset `1813846e0` が shim されずに入っていた (memset shim 登録の動機)。`1813846d0` が閉包に入った経路は未確認。

修正 (`scripts/kh656_closure.py`):

1. `unsupported_defs()`: `final.ll` の `declare @__asm_*` で引数・戻り値に `i256` か `ptr` を持つ宣言を集め、それを**直接呼ぶ**関数だけを除外対象にする。
2. `build()`: 失敗ログに `gen_simd` が含まれ、かつ除外対象が lift にある場合だけ除外して再試行する。それ以外は `lic_config.json` を書き換えずに終了する。
3. 各ラウンドの record に `emcc_peak_rss_mb` を加えた。

`lic_config.json` (module F): `shims` に `"1813846e0": "memset"` を追加 (module E の `shims` と同一。`KH656_REPORT.md` §8 の指摘どおり)。HEAD の lift 8 件・excluded_i256 は変えていない。

注: AVX2 の 2 件 (`0x180f89cf0`・`0x180fb6124`) は HEAD の `excluded_i256` に既にあり、今回の判定 (呼び先の宣言) で再判定はしていない。

## 3. 収束判定

- round 8 で新規 136 件が残る (未収束)。round 9 は `kh_lower` の stage0 欠落で停止した。閉包は `todo == []` に届いていない。
- 受入 1 (`todo == []` で収束) は未達。受入 3 (各ラウンドの実測を REPORT に残す) は本付録 §1 で達成。

## 4. 検証 (commit 済み HEAD の config)

コマンド: `python3 lic_build.py --module F`・`node kh249_check.mjs` (`license/` で実行)。

| 項目 | 結果 |
|---|---|
| wasm | 54,394 B・sha256 `7ba79e65ec158a711646316579e6f8bc3d8c12f47c61851710a5e2077b8c7707` (HEAD と同一) |
| undefined import | 0 |
| emcc peak RSS | 5 MB (emcc キャッシュ warm) |
| `kh249_check.mjs` | ok=17 ng=0。入口 `unlifted callee 0x180112a30` (HEAD と同一) |
| 所要 (build) | 3 s (`date` 差・n=1) |

負律対照 (KH249 §6.1): 今回の変更は閉包スクリプトと module F の memset shim 1 件。F の lift 集合は HEAD と同一のため、変化なし。

## 5. 手順上の記録

- PM 指示の「1 ラウンドごとに commit・push」は満たしていない。閉包を 1 回の連続実行で回し、結果を REPORT に 1 回で追記した。途中の commit は無い。round 6 の原因の切り分けを、同じ閉包の実行系で行うため。
- 本付録の数値はすべて上記 1 回の実行 (closure4) と、その直後の `lic_build.py --module F` (§4) から取った。`work/kh656_rounds.json` は `work/` (gitignore) にあり commit していない。

## 6.1 KH-86 (#4025): round 9 の stage0 欠落の解消と収束

原因: RetDec の `--select-ranges` で、範囲の終端が次の関数の先頭と一致する (隣接する) とき、後ろの関数が stage-0 に定義されない。`0x180f88468-0x180f88488` の直後の `0x180f88488` が単独範囲では定義されるのに、隣接させると欠落する (実験: 隣接 2 範囲で `function_180f88488` 無し・単独で有り・逆順でも無し)。隣接は 725 件の lift 集合に 23 組あった。終端を 1 byte 縮める案は不採用 (`0x18020e070` は末尾 `ret` を落として本体が変わった)。

対応 (`lic_build.py` の `fill_missing_stage0`): stage-0 に定義の無い VA だけを単独範囲で再取得し、定義と未宣言の declare を追記する。既存の stage-0 にも適用される (欠落が無ければ no-op)。

実行: `python3 scripts/kh656_closure.py --rounds 14` (開始 08:57:08・終了 09:21:56・exit 0・todo == [] で収束)。環境: nproc=4・MemTotal 15,988 MB。素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip` → `work/winpkg/HeartCore.core_64` (76,642,304 B)。`KH_EM_CACHE=$RUNNER_TEMP/emcache`。

| ラウンド | lift | 未 lift callee | 新規 lift | wasm B (sha256 先頭 8 桁) | emcc peak RSS MB | undefined import | 入口 | kh249_check |
|---|---|---|---|---|---|---|---|---|
| 1 | 725 | 90 | 82 | 3,390,073 (`ea72f54b`) | 624 | 0 | `memory access out of bounds` | ok=16 ng=1 |
| 2 | 807 | 83 | 75 | 4,164,693 (`b73a4366`) | 726 | 0 | 同上 | ok=16 ng=1 |
| 3 | 882 | 77 | 69 | 4,537,575 (`86d45ef5`) | 785 | 0 | 同上 | ok=16 ng=1 |
| 4 | 951 | 71 | 63 | 4,891,138 (`7c5e46e6`) | 864 | 0 | 同上 | ok=16 ng=1 |
| 5 | 1014 | 115 | 107 | 5,311,243 (`23cb03fb`) | 932 | 0 | 同上 | ok=16 ng=1 |
| 6 | 1121 | 87 | 79 | 5,867,984 (`26abd0f0`) | 1026 | 0 | 同上 | ok=16 ng=1 |
| 7 | 1200 | 38 | 30 | 6,216,513 (`6f618cc6`) | 1058 | 0 | 同上 | ok=16 ng=1 |
| 8 | 1230 | 30 | 22 | 6,430,862 (`cb233a82`) | 1126 | 0 | 同上 | ok=16 ng=1 |
| 9 | 1252 | 27 | 19 | 6,561,757 (`200d3fe8`) | 1141 | 0 | 同上 | ok=16 ng=1 |
| 10 | 1271 | 27 | 19 | 6,645,024 (`7ee82779`) | 1126 | 0 | 同上 | ok=16 ng=1 |
| 11 | 1290 | 19 | 11 | 6,681,422 (`18190893`) | 1160 | 0 | 同上 | ok=16 ng=1 |
| 12 | 1301 | 12 | 4 | 6,715,174 (`d9a18ec4`) | 1136 | 0 | 同上 | ok=16 ng=1 |
| 13 | 1305 | 8 | 0 | 6,726,292 (`e4b45344`) | 1138 | 0 | 同上 | ok=16 ng=1 |

- 収束: round 13 で `new_lift == []`。各 round の build は成功しており、未検証の lift は commit していない (`lic_config.json` は round 13 の集合)。
- 入口 (受入 3・範囲外): 全 round で `memory access out of bounds`・ng=1。#1821・#3866 の既存事象で、本 PR では変えていない。
- 出発点 (注意): round 1 は HEAD の 589 件ではなく、再現実行 (round 9 で停止した閉包) が worktree の `lic_config.json` に残した 725 件から始まった。各ラウンドの build は成功 (`lic_build` 戻り 0・kh249 実行済み) しており、収束時の 1,305 件は round 13 で build・検査済み。HEAD からの再現 (589 件開始) は未実施。
- 再現実行 (修正前・round 9 で停止) の round 8 の wasm は `e2b1a776` で、§1 の `008d739d` と一致しなかった。出発点が §1 と違う (§1 は 589 件) ため直接比較はできない。差の原因は未切り分け。
- emcc peak は最大 1,160 MB (cap 11,000 MB の約 11%)。cap には達していない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~round 9: `kh_lower` の stage0 に無い関数 `0x180f88488`~~ → §6.1 で解消 (RetDec の隣接範囲による欠落。D26) | 解消済み | #4025 [KH-86] |
| `kh_180fd157c` が `__asm_rep_stosq_memset(ptr, i64, i64)` を呼ぶ。gen_simd は ptr を扱えないため閉包から除外 (未 lift のまま fail-fast)。除外後の RDI/RCX の状態の扱いは未確認 | 閉包の完全性が未確認。除外関数は呼ばれると停止 (loud) | 子 issue #4026 [KH-87] (本 run で起票) |
| 入口 OOB (round 5 以降の `memory access out of bounds`) | `kh249_check` ng=1 (受入 2 未達) | #1821・#3866 (既存) |
| ymm (AVX2) 2 件 `0x180f89cf0`・`0x180fb6124` の lift | 閉包の対象外 | 子 issue #4061 [KH-89] (本 run で起票。#709 は CLOSED のため再起票) |
