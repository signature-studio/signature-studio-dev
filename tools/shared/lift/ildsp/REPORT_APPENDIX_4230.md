# ildsp CreateInstance 間接 call 4 件の到達 (T-SH-103 / #4230)

親: #3250 (T-SH-54 の後続)。`REPORT_CLOSURE.md` §4.4 の 4 件 (`0x1aedf6`・`0x1aee04`・`0x1aee4a`・`0x1b6f6c`) の到達条件を、正の対照つきで実測した。

測定 commit (コードを変えた最後の commit): `68bf86737` (`ildsp_native.c` に正の対照・alloc 失敗注入・`--rdx` を追加。既定経路は変えていない)。
`git diff 68bf86737 HEAD -- tools/shared/scripts` は本付録の commit 時点で空。

issue 本文の測定 commit `180307dfc` は repo に存在しない (`git cat-file -t` で not found)。直前の harness は `8f643a8c` 以降の `ildsp_native.c` (§7)。

## 結論
- **`0x1b6ea0` が 0 を返す経路は 2 つ**: (a) `HeapAlloc` が NULL を返す (b) 要求サイズが `0xffffffe0` 超 (`0x1b9c25` の `ja` → `0x1b9c67` で `xor eax`)。`0x1ac9ce` (new handler 呼出し) は (a) (b) のどちらかの 0 返却の後にだけ実行される。
- **正の対照 (決定的)**: 1 回目の slot 内 `HeapAlloc` を失敗させると、slot 1 (v0〜v3) の全 4 設定で `0x1ac9ce`・`0x1aedc0` (helper 入口)・`0x1aee04`・`0x1aee4a`・`0x1b6f6c` が各 1 回発火する (B_k1v0〜v3)。
- **注入なし (非決定的)**: slot 1 v0 は 6 回中 2 回で `0x1ac9ce`・`0x1b6f6c` が約 230 万回発火し、15 秒で timeout する (A_k1v0)。残り 4 回は発火 0。巨大 `rdx` (`0x100000`) は 6 回中 3 回で全 5 点が発火 (C)。発火の有無を決める要因は未特定 (ASLR・未初期化値・ヒープ位置のいずれか。未検証)。
- **`0x1aedf6` は未発火**: helper 入口で `testb $0x10,(%rdx)` (`rdx` は呼出し引数) が真の枝に入ると `call [0x268260]` に進む。本測定の入力では一度も真の枝に入らなかった (B・C)。真にする入力は未特定。
- **`0x1aedf6` 以外の 3 件は、到達は示せた**。ただし到達は「全 slot 入力の通常経路」ではなく、alloc 失敗 (例外 path) または巨大サイズでだけ確認した。
- **trap 化か stub 化か**: 本測定は判断を下さない。4 件は alloc 失敗・巨大サイズの例外 path でのみ到達し、既定入力の決定的な到達は確認できなかった。扱いの決定は PM 判断 (下の未解決)。

## 方法
- 素材: `fl-win64.tar.zst` から `extracted/block24360_PE.bin` を展開 (sha256 `f4b23b0f93ee9119…`、issue の値と一致)。
- harness の変更 (`68bf86737`):
  - `--heap-fail-from N --heap-fail-n M`: N 回目以降の `HeapAlloc` を M 回 NULL にする (slot 呼出しの間だけ)。
  - `--newh-zero`: `0x1b6f6c` (new handler の thunk) の戻り値を 0 にする。`REPORT_APPENDIX_3276` の alloc_fail 設定と同じ。
  - `--rdx V`: slot 1〜3 の `rdx` を固定する。
  - 正の対照: `0x1ac9ce` (直接 call・入口で発火を記録し、実体は実行) と `0x1aedc0` (関数入口・先頭 1 byte を int3 にして単歩で戻す)。
- 再現 (repo 直下・`FL_WIN64_DIR` は `fl-win64` の展開先):
  `FL_WIN64_DIR=<展開先> bash tools/shared/scripts/ildsp_reach_matrix.sh`
  全体 (A・B・C の 30 実行) は 21.4 s (wall)・load average (1 分) 0.09 → 0.20 (nproc=4)。
- 既定 checker: `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_native_check.py` は `ALL OK` (rc 0)。create の vptr `0x1803dfcf8` 一致。

## 実測 (測定 commit `68bf86737`)

| 区分 | 設定 | 結果 |
|---|---|---|
| A (注入なし) | slot 1 v0 (6 回) | 2 回で `0x1ac9ce`・`0x1b6f6c` が約 230 万回 (rc 124)。4 回は発火 0 |
| A | slot 1 v1〜v3・slot 2・slot 4・slot 5 | 発火 0 (rc 0) |
| A | slot 3 v1〜v3 | rc 139 (SIGSEGV)。発火 0 |
| B (1 回目の alloc 失敗) | slot 1 v0〜v3 | `0x1ac9ce`・`0x1aedc0`・`0x1aee04`・`0x1aee4a`・`0x1b6f6c` が各 1 回 (rc 96 = RaiseException で停止) |
| B | slot 2・slot 4・slot 5 | 発火 0 (rc 0) |
| B | slot 3 v1〜v3 | rc 139。発火 0 |
| C (`rdx` 巨大・注入なし) | `0x100000` (6 回) | 3 回で全 5 点が発火 (rc 96)。3 回は発火 0 |
| C | `0x4000000` (1 回) | 発火 0 (rc 0) |

`0x1aedf6` は全 A・B・C で 0 件。`0x1aee04`・`0x1aee4a`・`0x1aedc0` は B と C の発火時のみ。

## 注記
- A_k1v0 の timeout (rc 124) は、`--newh-zero` なしで `0x1b6f6c` の戻り値が非 0 のとき、`0x1ac9c0` の new handler 再試行ループが回り続ける harness 上の挙動。実機の動きではない。
- B で発火するのは `--heap-fail-n 1` (1 回だけ失敗) のとき。全件失敗 (`--heap-fail-n` なし) は `0x1ac9c0` のループで timeout するため使わない。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 注入なしで発火の有無が非決定的 (slot 1 v0 で 6 回中 2 回・巨大 rdx で 6 回中 3 回)。要因 (ASLR・未初期化値・ヒープ位置) は未検証 | 既定入力での到達の確定 | PM 判断 (本 run では子は未起票) |
| `0x1aedf6` (`testb $0x10,(%rdx)` が真の枝) を真にする入力が未特定 | 4 件のうち 1 件の到達 | PM 判断 (本 run では子は未起票) |
| trap 化か stub 化かの最終判断 (既定入力での到達が未確定のため) | lift の扱い | PM 判断 |
