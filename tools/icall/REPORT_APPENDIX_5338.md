# 付録: icall #5338 (ICALL-114) — stack 引数 12 語の値一致の数値確認 (部分達成)

> 親: #1023 (ICALL-16)。前付録: `REPORT_APPENDIX.md` §14 (#1023 の未達の原因)・`REPORT.md` §9 (STKBUF 設計)。
> 測定 commit: `810f1a611` (`tools/icall/tests/stk_value_check.c` の追加。以後のコード変更なし)。

## 1. 結論

- 部分達成。harness から 12 語の stack 引数を 5 引数以上の間接 call に渡し、被呼側で 12 語すべての値が一致することを数値で確認した (正常系 12/12)。
- ネガティブコントロール (注入を 1 語ずらす) は 0/12 で FAIL になり、判定が偽陽性にならないことを確認した。
- **未達**: 書換え後の経路 (`icall_rewrite.py` が呼出し点で `[rsp+0x20+8k]` を `BLK+0x100+8k` に copy し、`BLK+0x48` を指すこと) は通していない。本 harness は `ott_ms_call` で stack 引数を積む経路の検証で、STKBUF の copy と BLK pointer は対象外。

## 2. 方法

- `tools/icall/tests/stk_value_check.c`: `ott_ms_call` (`tools/ott/native/ms_call.S`) が `call *%r12` で MS ABI の被呼側 `callee` を間接 call する。`stk` 12 語は `[rsp+0x28+8k]` 相当の位置 (第 5〜16 引数) に積まれる。
- 被呼側は第 5〜16 引数を受け取り、期待値 `0x1111000000000000 + 0x101·t + 0x40` と語ごとに比べる。
- 注入は `ott_ms_call` の引数配列 (`buf`) をそのまま渡す。NEG=1 のときは `buf[t] = expect[t+1]` (1 語ずらす)。
- 被呼側・注入とも OTT の実行経路には依らない。素材は不要 (ネイティブ gcc のみ)。

## 3. 実測

| 条件 | 結果 | 所要 | load (1 分値, 開始/終了) |
|---|---|---|---|
| 正常 (`stk_value_check`) | `RESULT PASS matched=12/12` rc=0 | real 0.004 s | 0.34 / 0.34 |
| ネガコン (`NEG=1`) | `RESULT FAIL (negative control) matched=0/12` rc=1 | 同上 (同じ計測) | 同上 |

- 再現: `gcc -O1 -g -Wall -Wextra -o tools/icall/work/stk_value_check tools/icall/tests/stk_value_check.c tools/ott/native/ms_call.S && ./tools/icall/work/stk_value_check && NEG=1 ./tools/icall/work/stk_value_check` (警告 0)。
- 測定 commit 以降のコード差分: 無し (本付録の追加のみ)。
- ICALL-115 (#5339) の gate 実測: 測定 commit `73fee519e` (`tools/icall/tests/stk_value_gate.sh` を gcc でビルドして判定)。`bash tools/icall/tests/stk_value_gate.sh` が rc=0 で、正常注入 `RESULT PASS matched=12/12`、ネガコン `RESULT FAIL (negative control) matched=0/12` (rc=1 を期待どおり判定)、`[stk_value_gate] PASS`。real 0.203 s・user 0.067 s・sys 0.042 s、load 1 分値 0.97 (開始時 01:08 の uptime)。素材は gcc のみ。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 書換え後の `BLK+0x48` / `STKBUF` (BLK+0x100) 経路を被呼側まで通す検証 (wasm 側 icall_rt の copy と `ICALL_CHECK_STK` の pointer 検査との接続) | 受入条件 1 の「harness から STKBUF を注入」の残り | 親 #5338 のチェックリスト (次の run。素材 `fl-win64 toolchain-emsdk work-icall` を要する) |
| 被呼側を OTT / FLEngine の実在の 5 引数以上の間接 call 先に置き換える | 実行経路の値一致 (#1023 の元の要件) | 同上 |
