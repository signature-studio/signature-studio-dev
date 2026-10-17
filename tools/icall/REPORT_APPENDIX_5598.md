# 付録: icall #5598 (ICALL-118) — 書換え後の stack 引数 copy を機械語で直接確認 (部分達成)

> 親: #1023 (ICALL-16)。前付録: `REPORT_APPENDIX_5338.md` §4 (未達の経路)・`REPORT.md` §9 (STKBUF 設計)。
> 測定 commit: `f2bcf3576` (`tools/icall/tests/stk_rewrite_check.py`。以後のコード変更なし)。

## 1. 結論

- 部分達成。`icall_rewrite.build_site` が出す書換え後の呼出し点と `stub_code` の機械語を x86-64 で直接実行し、
  stack 引数 12 語が呼出し点で `BLK+0x100+8k` に copy され、被呼側 (stub) まで届いて合計が一致することを確認した (12/12)。
- ネガティブコントロール (期待値を 1 語ずらす) は 0/12 で FAIL (rc=1)。
- **未達**: wasm 側 `icall_rt.c` の dispatch (`BLK+0x48` の設定・`ICALL_CHECK_STK`) と、実在の 5 引数以上の間接 call 先 (OTT / FLEngine) は通していない。
  これらは `#1023` の範囲。

## 2. 方法

- `tools/icall/tests/stk_rewrite_check.py`: `expansion_template(cfg=True, nstk=12)` と `build_site` で `call [rax]` の書換え後の site を生成し、
  `stub_code` の stub と同じ mmap 領域に置く。SysV 呼出しの trampoline が 12 語を `site` 入口の `[rsp+0x20+8k]` に相当する位置へ積み、
  rcx/rdx/r8/r9/xmm0-3/rax を設定して site を call する。
- 判定: ① `BLK+0x100+8k` に入った 12 語が注入値と一致 (`matched`) ② stub の戻り値 = 注入値の合計 (mod 2^64)。
- BLK の初期値は mmap の 0 なので、① の一致は copy が実行された結果でしか出ない (copy 欠落なら 0 と比べて不一致になる)。

## 3. 実測 (測定 commit `f2bcf3576`)

| 条件 | 結果 | 所要 (real) | load (1 分値) |
|---|---|---|---|
| 正常 | `RESULT PASS matched=12/12` rc=0 | 0.068 s | 0.02 (12:10:39) |
| ネガコン (`NEG=1`) | `RESULT FAIL (negative control) matched=0/12` rc=1 | 0.070 s | 0.02 (12:10:39) |

- 再現: `python3 tools/icall/tests/stk_rewrite_check.py` / `NEG=1 python3 tools/icall/tests/stk_rewrite_check.py`。素材は python3 と capstone のみ。
- 測定 commit 以降のコード差分: `git diff f2bcf3576 HEAD -- tools/icall` は 0 行。
- 途中で判定の欠陥を 1 件直した: 合計の期待値が語の回転に不変なため、ネガコンでも `sum_ok=1` になっていた。
  期待値を注入値 (`stkv`) から求めるよう修正し (`f2bcf3576`)、ネガコンは `matched=0/12` で FAIL を維持。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側 `icall_rt.c` の dispatch で `BLK+0x48` が `BLK+0x100` を指すことと `ICALL_CHECK_STK` の検査 | 受入条件の「被呼側まで」の wasm 側の部分 | #5598 (open のまま `Refs`。受入の未達条件はこの issue が追跡) |
| 実在の 5 引数以上の間接 call 先 (OTT / FLEngine) での値一致 | 実行経路の値一致 | #1023 の既存の受入 (#5598 本文の注記どおり本 issue の範囲外。FLEngine/IPP の実行経路が前提) |
| RetDec (`retdec-decompiler`) が runner に無い | `ott_route.sh` のフル再生成ができない | tools/icall 側の素材定義 (再開時に確認) |
