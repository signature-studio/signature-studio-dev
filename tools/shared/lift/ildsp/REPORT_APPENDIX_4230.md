# ildsp CreateInstance 間接 call 4 件の到達 (T-SH-103 / #4230)

親: #3250 (T-SH-54 の後続)。`REPORT_CLOSURE.md` §4.5 の 4 件 (`0x1aedf6`・`0x1aee04`・`0x1aee4a`・`0x1b6f6c`) の到達条件を、正の対照つきで実測した。

測定 commit (コードを変えた最後の commit): `52cbf1762` (main 取り込み merge)。
`git diff 52cbf1762 HEAD -- tools/shared/scripts` は 0 行 (測定後の HEAD と一致)。
測定は `52cbf1762` の `tools/shared/scripts` で行った (main 取り込みで変わった `Fn1F`/`Fn2F` と直接 call 対照 kind 1 を含む)。

issue 本文の測定 commit `180307dfc` は repo に存在しない。直前の harness は `8f643a8c` 以降の `ildsp_native.c` (§7)。

## 結論
- **`0x1b6ea0` が 0 を返す経路は 2 つ**: (a) `HeapAlloc` が NULL を返す (b) 要求サイズが `0xffffffe0` 超 (`0x1b9c25` の `ja` → `0x1b9c67` で `xor eax`)。`0x1ac9ce` (new handler 呼出し) は (a) (b) のどちらかの 0 返却の後にだけ実行される。
- **正の対照 (決定的)**: 1 回目の slot 内 `HeapAlloc` を失敗させると、slot 1 (v0〜v3) の全 4 設定で `0x1ac9ce`・`0x1ad022`・`0x1aedc0` (helper 入口)・`0x1aee04`・`0x1aee4a`・`0x1b6f6c` が各 1 回発火する (B_k1v0〜v3)。
- **注入なし (既定入力) では発火 0**: HEAD `52cbf1762` の A・C は 2 回の matrix 実行と、slot 1 v0 の 6 回連続実行のいずれでも、間接 call 4 件・`0x1ac9ce` の発火は 0 件だった。
- **`0x1aedf6` は未発火**: helper 入口で `testb $0x10,(%rdx)` (`rdx` は呼出し引数) が真の枝に入る入力を、本測定では作れなかった。真にする入力は未特定。
- **`0x1aedf6` 以外の 3 件は、到達は示せた**。ただし到達は alloc 失敗 (例外 path) でだけ確認した。
- **trap 化か stub 化か**: 本測定は判断を下さない。扱いは PM 判断 (下の未解決)。

## 方法
- 素材: `fl-win64.tar.zst` を展開し `extracted/block24360_PE.bin` を得た (sha256 先頭 16 桁 `f4b23b0f93ee9119`、issue の値と一致)。
- harness (`52cbf1762` 時点):
  - `--heap-fail-from N --heap-fail-n M`: N 回目以降の `HeapAlloc` を M 回 NULL にする (slot 呼出しの間だけ)。
  - `--newh-zero`: `0x1b6f6c` (new handler の thunk) の戻り値を 0 にする。`REPORT_APPENDIX_3276` の alloc_fail 設定と同じ。
  - `--rdx V`: slot 1〜3 の `rdx` を固定する。
  - 正の対照: `0x1ac9ce` (直接 call・入口で発火を記録し、実体は実行) と `0x1aedc0` (関数入口・先頭 1 byte を int3 にして単歩で戻す)。`0x1aa29f` は直接 call の対照で、毎回 2 回発火するのが正常 (発火 0 の判定には含めない)。
- 再現 (repo 直下・`FL_WIN64_DIR` は `fl-win64` の展開先):
  `FL_WIN64_DIR=<展開先> bash tools/shared/scripts/ildsp_reach_matrix.sh`
- 既定 checker: `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_native_check.py` は `ALL OK (neg=False)` (rc 0)。

## 実測 (測定 commit `52cbf1762`・nproc=4)

| 測定 | 内容 | 結果 |
|---|---|---|
| matrix 1 回目 | A・B・C の 30 実行 | wall 1.04 s・load average (1 分) 0.66 (開始時) |
| matrix 2 回目 | A・B・C の 30 実行 (同 HEAD) | wall 1.09 s・load average (1 分) 0.51 (開始時) |
| checker | `ildsp_native_check.py` | wall 0.56 s・`ALL OK (neg=False)` (rc 0) |
| slot 1 v0 連続 | 注入なし・6 回 | 6 回とも rc 0・発火は `0x1aa29f`×2 のみ |

| 区分 | 設定 | 結果 (両 matrix 実行で同一) |
|---|---|---|
| A (注入なし) | slot 1 v0〜v3・slot 2 v0〜v3・slot 4 v0・slot 5 v0 | rc 0・発火は `0x1aa29f`×2 のみ (間接 call 4 件・`0x1ac9ce` は 0) |
| A | slot 3 v0 | rc 0・同上 |
| A | slot 3 v1〜v3 | rc 139 (SIGSEGV)・発火は `0x1aa29f`×2 のみ |
| B (1 回目の alloc 失敗) | slot 1 v0〜v3 | rc 96 (RaiseException で停止)。`0x1ac9ce`・`0x1ad022`・`0x1aedc0`・`0x1aee04`・`0x1aee4a`・`0x1b6f6c` が各 1 回 |
| B | slot 2・slot 4・slot 5 | rc 0・発火は `0x1aa29f`×2 のみ |
| B | slot 3 v1〜v3 | rc 139 (SIGSEGV)・発火は `0x1aa29f`×2 のみ |
| C (`rdx` 巨大・注入なし) | `0x100000`・`0x4000000` | rc 0・発火は `0x1aa29f`×2 のみ |

`0x1aedf6` は全 A・B・C で 0 件。

## 注記
- B で発火するのは `--heap-fail-n 1` (1 回だけ失敗) のとき。全件失敗 (`--heap-fail-n` なし) は `0x1ac9c0` の new handler 再試行ループで timeout するため使わない。
- 前回 (`68bf86737` 時点) の付録にあった「注入なしで slot 1 が約 230 万回発火して timeout」「巨大 rdx で 3 回発火」は、`52cbf1762` の harness では再現しなかった。main 取り込み後に slot 1 の呼出し (`Fn1F`/`Fn2F`) と直接 call 対照が変わったため、旧測定の値は本測定の根拠にしない。旧値の由来 (測定 commit `68bf86737`・`98ff44f13`) は未検証。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 注入なしの既定入力では間接 call 4 件が一度も発火しない (旧測定と食い違う。原因未検証) | 既定入力での到達の確定 | [T-SH-111] #4289 |
| `0x1aedf6` (`testb $0x10,(%rdx)` が真の枝) を真にする入力が未特定 | 4 件のうち 1 件の到達 | [T-SH-111] #4289 |
| trap 化か stub 化かの最終判断 (既定入力での到達が未確定のため) | lift の扱い | #3250 [T-SH-54] (受入 3 の判断) |
