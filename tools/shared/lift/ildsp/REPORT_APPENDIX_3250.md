# ildsp REPORT 付録: CreateInstance の間接 call 4 件の到達実測 (#3250・T-SH-54)

親: #2528 (T-SH-38)。本 issue: #3250 (T-SH-54)。結論は `REPORT_CLOSURE.md` §4.4、本付録は測定の正本。
子: #4230 (到達条件と helper 入口の正の対照)。

### 7.1a 間接 call 4 件の到達 (#3250 / T-SH-54・部分達成)
- 測定 commit: `180307dfc` (ハーネスに直接 call の trace 制御 (`direct` フラグ) を追加。既存の 4 件の hook は変更なし)。`git diff 180307dfc HEAD -- tools/shared/scripts` は本節の commit 時点で空 (差分 0)。
- 素材: `fl-win64.tar.zst` を展開し、`block24360_PE.bin` の sha256 は `f4b23b0f93ee9119…` (issue 記載と一致)。
- 既存照合: `ildsp_native_check.py` ALL OK、`--neg` FAIL (期待どおり)。
- 全件実行 (`ildsp_native <PE>`・n=6): rc 139 ×2 (slot 1 の call 内で SIGSEGV)、rc 124 ×4 (hang)。4 件の hook は 0 件。完走した実行は 1 件も無い。
- 単独 slot 2〜5 (v0): rc 0 ×4。4 件の hook は 0 件。
- trace の正の対照 (直接 call、いずれも `call` 命令の先頭):
  - CreateInstance 先頭 `0x1aa29f` (→`0x1ac9c0`) は各実行で 1 回発火 (create のみ・slot 2〜5 でも 1 回ずつ)。trace 機構は動く。
  - `0x1ac9ce` (→`0x1b6f4c`) は 0 件。`0x1ac9c0` の `0x1ac9da: call 0x1b6ea0; test rax; je 0x1ac9cb` で、戻り値が 0 のときだけ `0x1ac9ce` に進む。0 件は戻り値が非 0 だったことを意味し、trace の不具合ではない。
  - `0x1b6f4c` (間接 call `0x1b6f6c` を含む) は上の分岐の先にしか無いため、CreateInstance の通常経路では届いていない可能性が高い (未確認)。
- 注: hook 0 件は「この実験で到達しなかった」の意味だけを持ち、到達しない根拠ではない。完走実行が無く、helper `0x1aedc0` 入口の正の対照は未実施。
- 扱い: 間接 call 4 件は、現在の入力では到達していない。到達条件 (`0x1b6ea0` の戻り値を 0 にする入力) は未確定で、子 #4230 に移す。
