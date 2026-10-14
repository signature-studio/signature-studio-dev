# #2571 REPORT — hs_e2e Phase B に framework 初期化 (TLS 初期化) を通す [PLG-P0b-22]

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID に一致する類型は無い。`0x4181e0` の `return 0` は既存の fail-soft stub (`fw_hostfix.py`)。戻り値の fold 欠陥は既存の #1890 / #2008 系)。

親: #2115。前提の経緯は `REPORT_2115.md` と `REPORT_2115_APPENDIX.md` §10〜§11 (PR #2572)。

## 1. 結論

- **方式**: `hs_e2e_run` (hostshim/hs_plug.c) の `CreatePlugInstance` の前に、`_StartLib(reason=1)` の TLS 部分だけを実行する。(a) `[0x7162d8] = 1` を立てる、(b) `fw_call_cur(0x418120)` (TLS 初期化) を呼ぶ。`_StartLib` 全体 (0x4189c0) は採らない (理由は §4)。
- **結果**: TLS 初期化は実行される (`rax=0x0`・`[0x6d6e70]=0x1`・`[0x7162d8]=1`)。ただし Phase B は従来どおり `memory access out of bounds` で FAIL (`rec=7`)。OOB は解消しない。
- **注釈 `0x4181e0` (return 0)**: 外せない。外すと OOB の位置が変わるだけで Phase B は FAIL のまま (§5)。注釈は残す。
- Phase A (framework smoke) は変化なし (`dispatch=38 ff=0`)。

## 2. 受入条件の判定

| # | 判定 | 根拠 |
|---|---|---|
| 1 | 達成 | 方式を §4 に記録。`CreatePlugInstance` の前に TLS 初期化を通す (コミット `133d8b11`) |
| 2 | 達成 (回帰なし) | Phase A `Halt0/RestoreContext dispatch=38 ff=0` (§3 全行)。`fw_stage2.sh` の `SMOKE` 行 `dispatch=38 units_done=0 ff=0` |
| 3 | 達成 (n=1) | 対照 (現 main・初期化なし) と並べて実測 (§3)。PASS/FAIL は両方 FAIL。min–max (n≥3) は未実施 (§7) |
| 4 | 達成 (判定) | 注釈を外した派生で失敗位置が `0x4e5fa6` に移る。外せないと判定 (§5) |

## 3. 実測 (n=1・`hs_e2e.sh --fresh`・nproc 4)

測定 commit: **`133d8b11`** (コードを変えた最後の commit。`feat(plugins): hs_e2e Phase B に TLS 初期化 (0x418120) を通す (#2571)`)。

| 条件 | 結果 | 所要 (real) | load average (1/5/15 分: 開始 → 終了) |
|---|---|---|---|
| 対照: 現 main (80f8844c・初期化なし) | Phase A `dispatch=38 ff=0` / Phase B `memory access out of bounds` / `rec=7` / `E2E FAIL: 1 項目` | 158 s | 1.97 2.20 1.08 → 1.06 1.70 1.06 |
| 採用: TLS 初期化あり (作業ツリー・内容は `133d8b11` と同一) | Phase A 同上 / `framework init: 0x418120 -> rax=0x0, [0x6d6e70]=0x1, [0x7162d8]=1` / Phase B 同じ OOB・`rec=7` | 163 s | 0.72 1.54 1.03 → 1.20 1.35 1.03 |
| **HEAD `133d8b11` で再現** | 採用と同じ (Phase B OOB・`rec=7`・FAIL 1 項目) | 158 s | 0.50 1.04 0.98 → 0.97 1.02 0.99 |
| 未採用: TLS 初期化あり + 注釈 `0x4181e0` を外す | Phase B OOB・`rec=7`・FAIL 1 項目。失敗位置は §5 | 158 s | 1.02 1.31 1.02 → 1.08 1.24 1.04 |

- Phase B の `rec` 列 (`ID` 序列) は 4 条件で同一: `0x47, 0x56, 0x0d, 0x2e, 0x47, 0x1d` (ctor 連鎖の prefix。GOLDEN と一致)。`plug=0x0` (TFruityPlug 未生成) も同じ。
- `fw_stage2.sh` (canon3 の全生成を含む・`work-fw-stage1` からの再生成): 462 s・load 0.20 0.26 0.12 → 2.33 2.28 1.09。`SMOKE` 行は `dispatch=38 units_done=0 ff=0`。`fw_smoke_check.py` は `runerr 1 (期待 0)`・`init_reach 16 (期待 288)` で FAIL (rc=1)。この FAIL は **main (80f8844c) 上で** 出ており、本 issue の変更 (`hs_plug.c`・`fw_hostfix.py`) は `fw_stage2.sh` の入力に入らない (既存の状態。未解決 §7)。

## 4. 方式の選定 (受入 1)

- `function_418120` は引数なしの定義。TLS index を `TlsAlloc` で確保して `[0x6d6e70]` に store する (`REPORT_2115_APPENDIX.md` §10.1)。
- `_StartLib` reason==1 は `[0x7162D8]=1` を立てた後、`_InitLib` が `hooks[1]` (= `0x418120`) を間接 call する (`fw_boot.c` の `fw_ov_startlib` / `fw_ov_InitLib` の転記。hooks 表 `0x6d6ef8`)。
- **採用**: TLS 部分だけを `hs_plug.c` の `hs_fw_init_tls()` で同じ順序 (フラグ → `0x418120`) に実行する。`CreatePlugInstance` より前。
- **不採用**: `_StartLib` 全体 (`fw_call_cur(0x4189c0)`)。`_InitLib` 経由で `InitUnits` (`0x40da80`) まで進むが、Phase B の route で完走を確認していない。Phase A の entry は `Halt0/RestoreContext` (`emscripten_force_exit`) で終わる経路で、Phase B に持ち込むと本体の前に終端する恐れがある (推定)。

## 5. 注釈 `0x4181e0` (return 0) の判定 (受入 4)

- 派生: `fw_hostfix.py` の `0x4181e0` エントリを一時的に削除し (commit なし・結果のみ記録)、TLS 初期化を入れて `--fresh` で実行。
- 結果: Phase B は FAIL のまま (`rec=7`)。ログの最後の soft-miss は、注釈ありでは `0x40d807` (target `0x0`)、注釈なしでは `0x4e5fa6` の間接 target `0x6572432000000000` (文字列バイト列) が連続し、その直後に OOB trap (ログの順序による観測。trap の正確な命令位置は未特定)。
- 判定: **外せない**。`0x4181e0` を実 lift の body に戻すと、TLS block (`0x288` byte の中身) が正しく作られないまま `+568` の deref 系へ進み、OOB の位置が移るだけ (推定。`REPORT_2115_APPENDIX.md` §10.3・§11.5 の E3 と同じ位置)。注釈は残す。

## 6. 検証範囲 / 範囲外

- 範囲: `hs_e2e.sh --fresh` (Phase A/B) を Linux runner で実行。各条件 n=1。
- 範囲外: Phase B の PASS (未達)、n≥3 の min–max、TLS block の中身 (`function_4180a0` の `ecx` fold) の解消。
- 再現: `bash tools/plugins/framework/fw_stage2.sh` → `bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh` (素材: `work-fw-stage1` を `tools/plugins/work/fw/` に展開)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Phase B の OOB (`0x40d807` / `0x4e5fa6`) が残り、E2E は FAIL 1 項目 | 親 #2115 の受入 (Phase B の PASS) | #2115 (継続) |
| TLS block が正しく作られない疑い (`function_4180a0` の `ecx` が `ptrtoint @683`・`LocalAlloc(0x40, 0x10000880)` に fold) | Phase B の OOB 原因の候補 (推定) | #1890 / #2008 (既存の fold 系) |
| n=1 のみ。所要の min–max (n≥3) 未実施 | 所要の変動幅が不明 | 本 PR の表で記録 (再測定のみのため子 issue は起票しない) |
| `fw_smoke_check.py` FAIL (main 上で `runerr=1`・`init_reach=16`≠288。`fw_stage2.sh` の rc=1) | stage2 の終了コードのみ。`SMOKE` 行は PASS | 既存 (`REPORT_2425.md` の未解決表。PLG-P0b-18 系) |
