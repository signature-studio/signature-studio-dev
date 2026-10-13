> **正本**: `tools/plugins/f2/REPORT.md` §7.7b。本書は §7.7b の全文 (#529 追補: 例外経路の一次スキャン) の付録。

## 1. #529 追補: 例外経路の一次スキャン (`raise_scan.py`・`raise_reach.py`)

- **目的**: waiver の前提「DSP 経路に例外を投げる箇所が無い」を機械的に確認する。pad は waiver 関数 W の unwind 時に走るので、W から閉包内の直接 call で到達する関数に trap 命令・例外 API があるかを見る。
- **実測 (HEAD 986e7415 の上に作業・`batch_lift.sh` 7 本 64 秒・7/7 lift_rc 0・`emcc -c` rc 0、`icall_gate.py` exit 0・機械語 640 / IR 636 / waived 4 / F1 0 (8.3 秒))**:

| block | 閉包関数 | trap 命令 (div/idiv/int) | 例外 API (IAT 名) | W から閉包内直接 call で到達する関数 | trap 関数のうち到達するもの |
|---|--:|--:|--:|--:|--:|
| 19148 | 84 | 6 (idiv 6 件・4 関数) | 0 | 0 | 0 |
| 19245 | 65 | 0 | 0 | 0 | 0 |

  - 19148 の idiv は 0x83f010・0x841340・0x843c90・0x851c30 の 4 関数。waiver 関数 0x780d00・0x78a660 からの直接 call では到達しない。
  - 閉包の `call qword ptr [rip+…]` 2 件 (0x83b39f・0x83b434) は import 表に無い slot (0x8d0018・0x8d0020) への間接 call で、IAT 名では判定できない。
- **判定 (部分)**: 直接 call の範囲では、W の unwind 元になる trap は閉包内に見つからない。ただし次が未確認で、「無い」の証明にはなっていない。
  1. W の間接 call (vtable / 関数ポインタ、閉包内 128 件) の先。
  2. 閉包外 (framework frontier) への直接 call の先 (`raise_scan` の `direct_out_of_closure`・19148 は 118 件) に `_RaiseExcept` 系 helper が無いか。
  3. 閉包外からの AV・SEH (`RtlRaiseException` 経由でない hardware 例外) の扱い。
- 再現: `python3 tools/plugins/f2/raise_scan.py <block>` → `raise_reach.py <block>` (前提: `work/closure/`・`FL_WIN64_DIR`)。結果は `work/f2/raise_scan_<block>.json`・`raise_reach_<block>.json` (gitignore)。

### 1b. #1056 追補: 閉包外を含む PE 全体の直接 call 追跡 (`raise_reach_frontier.py`)

- **方法**: 根は waiver 関数 (W = 0x780d00・0x78a660 @19148、0x77a550・0x783eb0 @19245)。`.pdata` の関数範囲で閉包外も含めて直接 call/jmp を辿る。IAT thunk (`jmp [rip+slot]`・`.pdata` 無し) は import 名に解決して例外 API を判定する。間接 call は辺にせず、その site を列挙する。
- **実測 (commit 5de92a12・19148/19245 とも 1.5 秒以内・truncated=False)**:

| block | 根 | 到達関数 | trap 命令 | 例外 API | 未解決 direct target | 間接 call site |
|---|--:|--:|--:|--:|--:|--:|
| 19148 | 2 (W) | 31 | 0 | 1 (`ExitProcess`) | 1 (0x407190) | 23 (18 関数) |
| 19245 | 2 (W) | 31 | 0 | 1 (`ExitProcess`) | 1 (0x407190) | 23 (18 関数) |

- **`ExitProcess`**: 0x411a80 → 0x411bdd で呼ばれる。経路は `W 0x780d00 → 0x40f530 → 0x411190 → 0x411c30 → 0x411c10 → 0x411a80`。プロセス終了で例外 unwind は起きないため、pad が走る経路にはならない (waiver の前提は崩れない)。
- **0x407190**: `jmp [rip+0x4d00ca]` の slot が IAT に無い (間接ポインタ)。到達先は未解決。
- **未解決 (= 受入条件の残り)**: W から到達する 31 関数の間接 call 23 件 (vtable・関数ポインタ) の実値。子 issue **#1305** で扱う。この段階では waiver の reason を書き換えない。
- 再現: `python3 tools/plugins/f2/raise_reach_frontier.py <block>` (前提: `work/closure/`・`work/winfuncs/` = `plugin_closure.py` 出力・`FL_WIN64_DIR`)。
- 閉包全体を根にした結果 (`--roots closure`・実測 commit 5de92a12): 19148 は 1278 関数到達・trap 関数 15 件 (div/idiv)・例外 API 関数 1 件。19245 は 1096 関数到達・trap 関数 10 件・例外 API 関数 1 件。閉包の関数は W から到達しない (上の表が waiver 判定の対象)。

## 2. §7.9 未解決 (§7.7 から継続)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `icall_rewrite.py` の配置修正を OTT 素材で回帰していない (`icall_e2e.sh` の 89 scenario、`test_icall.py` pe 部) | 連続しない配置はバイト一致のはずだが未実測 | **#530** `[ICALL-7]` |
| restored IR の wasm リンク・実行 (BLK、`__icall_dispatch` の VA→関数表、`ir_flatten --table`)、Host shim、差分試験 | 出口条件 (#199 手順 2〜4)。本 PR は IR 上の被覆まで | 既存 #195 / #196 / #197、#199 に残す |
| `closure_stats.py` の leaf 定義: 復元後は `__icall_dispatch` 呼出しが外部呼出しになり leaf が減る (18953: 8 → 1)。ABI も `i64 f(void)` (引数は BLK 経由) | #515 の leaf 23 関数の選定は `PLUG_ICALL=0` (`f2_step1.sh`) の IR か機械語側 (`icall_summary.py`) を使うこと。native ms_abi との差分には BLK 経由の harness が要る | 既存 **#515** にコメント |
| 18979 の waiver は手作業の到達不能推定 (前提: `[rbp+0x40]` が書換わらない) | 1 site。誤りなら F1 を隠す | waiver の `evidence` に根拠を残した。反証が出たら waiver を削除すれば FAIL に戻る (NC5) |
