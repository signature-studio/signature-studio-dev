# #2571 REPORT — hs_e2e Phase B に framework 初期化 (TLS 初期化) を通す [PLG-P0b-22]

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID に一致する類型は無い。`0x4181e0` の `return 0` は既存の fail-soft stub (`fw_hostfix.py`)。戻り値の fold 欠陥は既存の #1890 / #2008 系 (CLOSED。追跡先は #2115))。

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
| 2 | 達成 (新基準の FAIL は変わらず) | Phase A `Halt0/RestoreContext dispatch=38 ff=0` (§3 全行)。`fw_stage2.sh` の `SMOKE` 行 `dispatch=38 units_done=0 ff=0` は**旧基準**の値 (RunError 終端。偽 PASS と確定。`REPORT_2425.md` §1)。新基準 (`runerr=0 ff=0 init_reach=288`) では現 build も FAIL (`runerr=1`・`init_reach=16`) で、main `980dfcff` の測定と同じ (`REPORT_2425.md` §5) |
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

- 158 s と 163 s の差は解釈しない (各条件 n=1。変動幅は未測定)。
- 測定の前提: base `80f8844c` は main の `hs_irfix.py` の #2426 変更 (`11096d29`・`a63e33ab`・+64 行) より前。測定 build の BLK は `0x8A1000` (`work-fw-stage1` の `fw_map.json` の `blk`=`9048064`)。BLK 配置を変えた PR #2584 (`ca4945ba`) も base より後で、測定 build には入っていない (§7)。
- Phase B の `rec` 列 (`ID` 序列) は 4 条件で同一: `0x47, 0x56, 0x0d, 0x2e, 0x47, 0x1d` (ctor 連鎖の prefix。GOLDEN と一致)。`plug=0x0` (TFruityPlug 未生成) も同じ。
- `fw_stage2.sh` (canon3 の全生成を含む・`work-fw-stage1` からの再生成): 462 s・load 0.20 0.26 0.12 → 2.33 2.28 1.09。`SMOKE` 行は `dispatch=38 units_done=0 ff=0`。`fw_smoke_check.py` は `runerr 1 (期待 0)`・`init_reach 16 (期待 288)` で FAIL (rc=1)。この FAIL は **main (80f8844c) 上で** 出ており (`REPORT_2425.md` §5 の `980dfcff` 行と同じ判定)、本 issue の変更 (`hs_plug.c`・`fw_hostfix.py`) は `fw_stage2.sh` の入力に入らない (既存の状態。未解決 §7)。

## 4. 方式の選定 (受入 1)

- `function_418120` は引数なしの定義。TLS index を `TlsAlloc` で確保して `[0x6d6e70]` に store する (`REPORT_2115_APPENDIX.md` §10.1)。
- `_StartLib` (`fw_boot.c` の `fw_ov_startlib` L41-50) の reason==1 分岐は、(a) `B(0x716290)=1` と `B(0x7162D8)=1`、(b) `Q(0x716298)`・`Q(0x6D6EA0)`・`Q(0x6D6EA8)`・`Q(0x6D6EB0)`・`Q(0x6D6EC0)` の store、(c) `fw_call_cur(0x418240)` の順に行う。そのあと `fw_ov_InitLib` (L89-91) が `Q(hooks + reason*8)` (reason=1 なら `hooks[1]`) を間接 call する。hooks 表は `fw_ov_startlib` L52 で `0x6d6ef8` を渡す。
- **`hooks[1]` (= `0x418120`) の出典 (実測・2 素材で一致)**: `fl-win64` の `block18983_PE.bin` (PE・ImageBase `0x400000`) の `.data` の VA `0x6d6f00` (RVA `0x2d6f00`) の 8 バイトは `0x418120`。同じ表は `0x6d6ef8` = `0x4181b0` (hooks[0])・`0x6d6f08` = `0x4180d0` (hooks[2])。`work-fw-stage1` の `fw_icall.dll` (`.data`) でも `0x6d6f00` = `0x418120` を確認。`hooks[0]` は `r2.restored.ll` の `@global_var_6d6ef8` 初期値 `4293040` (= `0x4181b0`) とも一致する。
- **採用**: (a) の `[0x7162D8]=1` と、`_InitLib` が呼ぶ `hooks[1]` (= `0x418120`) だけを `hs_plug.c` の `hs_fw_init_tls()` で同じ順序に実行する。`CreatePlugInstance` より前。
- **不採用 (役割は未確認)**: (a) の `B(0x716290)=1`、(b) の 5 個の store、(c) の `fw_call_cur(0x418240)`。`function_418240` は `work-fw-stage1` の `r2.restored.ll` にあるが未読で、store 先 (`0x716290`・`0x716298`・`0x6D6EA0`・`0x6D6EA8`・`0x6D6EB0`・`0x6D6EC0`) の用途も未確認。したがって `0x418120` の結果 (`TlsAlloc` → `[0x6d6e70]`) への影響は**未確認**。本 PR は TLS 初期化を 1 変数として対照に入れる目的で、これらを外している。足すと Phase B の変化を TLS 由来と切り分けられなくなる。
- **不採用**: `_StartLib` 全体 (`fw_call_cur(0x4189c0)`)。`_InitLib` 経由で `InitUnits` (`0x40da80`) まで進むが、Phase B の route で完走を確認していない。Phase A の entry は `Halt0/RestoreContext` (`emscripten_force_exit`) で終わる経路で、Phase B に持ち込むと本体の前に終端する恐れがある (推定)。

## 5. 注釈 `0x4181e0` (return 0) の判定 (受入 4)

- 派生: `fw_hostfix.py` の `0x4181e0` エントリ (L194-197。`store i64 0` を `BLK+0x80` (`0x8A1080`) に書いて `ret i64 0` する stub) を一時的に削除し、lift の body を使わせた。TLS 初期化を入れて `--fresh` で実行 (commit なし・結果のみ記録)。再現: 作業ツリーの `fw_hostfix.py` から当該 1 エントリだけを削除し、§6 の手順を実行する (差分はこの 1 エントリのみ)。
- 結果: Phase B は FAIL のまま (`rec=7`)。ログの最後の soft-miss は、注釈ありでは `0x40d807` (target `0x0`)、注釈なしでは `0x4e5fa6` の間接 target `0x6572432000000000` (文字列バイト列) が連続し、その直後に OOB trap (ログの順序による観測。trap の正確な命令位置は未特定)。
- 判定: **外せない**。`0x4181e0` を実 lift の body に戻すと、TLS block (`0x288` byte の中身) が正しく作られないまま `+568` の deref 系へ進み、OOB の位置が移るだけ (推定。`REPORT_2115_APPENDIX.md` §10.3・§11.5 の E3 と同じ位置)。注釈は残す。

## 6. 検証範囲 / 範囲外

- 範囲: `hs_e2e.sh --fresh` (Phase A/B) を Linux runner で実行。各条件 n=1。
- 範囲外: Phase B の PASS (未達)、n≥3 の min–max、TLS block の中身 (`function_4180a0` の `ecx` fold) の解消。
- 測定 commit `133d8b11` 以降の変更は `hs_plug.c` の注釈 4 行だけ (§4 の記述に合わせた)。`git diff 133d8b11 HEAD -- tools/plugins/framework/hostshim` の出力:

```diff
-/* framework 初期化の TLS 部分 (#2571)。_StartLib (0x4189c0) の reason==1 は [0x7162d8]=1 を立てた後,
- * _InitLib が hooks[1] (= 0x418120) を呼んで TlsAlloc → [0x6d6e70] を設定する。Phase B はこの経路を
- * 通らず CreatePlugInstance に入るため, ここで同じ 2 手を先に実行する。_StartLib 全体 (0x4189c0) は
- * InitUnits (0x40da80) を含むため採らない (Phase B の route では未検証)。 */
+/* framework 初期化の TLS 部分 (#2571)。_StartLib (0x4189c0) の reason==1 は [0x716290]・[0x7162d8] を 1 に立て,
+ * fw_call_cur(0x418240) を呼んだ後, _InitLib が hooks[1] (= 0x418120) を呼ぶ (0x418120 は TlsAlloc → [0x6d6e70])。
+ * 本関数は [0x7162d8]=1 と 0x418120 の 2 手だけを行う。Phase B は CreatePlugInstance に直接入るため, ここで先に実行する。
+ * 他の store と 0x418240 は役割未確認のため採らない (REPORT_2571 §4)。_StartLib 全体 (0x4189c0) は InitUnits (0x40da80) を含むため採らない。 */
```

- 注釈を除いたコードは `133d8b11` と一致 (`/* */` を除去して比較。行数 215 で同一)。コードのトークン列は変わらないため、§3 の測定は `133d8b11` のまま有効とし、e2e は再実行していない。
- 再現: `bash tools/plugins/framework/fw_stage2.sh` → `bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh` (素材: `work-fw-stage1` を `tools/plugins/work/fw/` に展開)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Phase B の OOB (`0x40d807` / `0x4e5fa6`) が残り、E2E は FAIL 1 項目 | 親 #2115 の受入 (Phase B の PASS) | #2115 (継続) |
| TLS block が正しく作られない疑い (`function_4180a0` の `ecx` が `ptrtoint @683`・`LocalAlloc(0x40, 0x10000880)` に fold) | Phase B の OOB 原因の候補 (推定) | #2115 (継続)。旧起票先 #1890・#2008 は CLOSED |
| n=1 のみ。所要の min–max (n≥3) 未実施 | 所要の変動幅が不明 | 本 PR の表で記録 (再測定のみのため子 issue は起票しない) |
| `fw_smoke_check.py` FAIL (main 上で `runerr=1`・`init_reach=16`≠288。`fw_stage2.sh` の rc=1) | stage2 の終了コードのみ。`SMOKE` 行は PASS | #2510 [PLG-P0b-18] (OPEN。`REPORT_2425.md` の未解決表から継続) |
| BLK `0x8A1000` が再配置コードと重なっていた (#2565 の起票理由)。測定 build (base `80f8844c`) はその配置のまま (`fw_map.json` の `blk`=`9048064`=`0x8A1000`)。PR #2584 (方式 (c)) で #2565 は CLOSED (2026-10-14 15:56Z)。(c) 後の build の Phase B は未測定 | Phase B の OOB との関係は未検証 | #2604 (OPEN・親 #2565)。受入 1 を方式 (c) で満たしてよいかは PM 判断 (#2604 の needs-user-input 質問) |
| `0x418240` と store 群の役割 (未確認。§4) | TLS 以外の初期化が Phase B の route に与える寄与は未検証 | #2115 (継続) |
| main の `hs_irfix.py` に 64 行追加 (`11096d29`・`a63e33ab`・#2426 系)。測定は、この変更より前の base `80f8844c` で行った。本 PR HEAD には未取り込み | merge 後の Phase A/B は未測定 | PM 判断 (本 PR では再測定しない。main 取り込みは hostshim の差分を生み、WORKFLOW §6 により再測定が要る) |
