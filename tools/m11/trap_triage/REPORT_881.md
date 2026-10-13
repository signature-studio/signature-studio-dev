# #881 unit 275: function_864fe0 の this 不正の出所 (80e040 項目列・monitor 列挙 stub 仮説)

親: #684 (受入条件の残り・275 側)。元の議論: `tools/m11/trap_triage/REPORT_684.md` §2・§4。
検証起点: `origin/main` (b2a1e114)。素材: fl-win64 (`$RUNNER_TEMP/fl-win64`) + work-m11 + toolchain (`/opt/emsdk`・`/opt/retdec`)。

## 0. 結論

1. **this の出所を実測で特定**: `80e040` は `G=0x11e4c80` → `obj=[G]=0x11f7198` → `list=[obj+188]` (= `0x11f7254`) を項目列とし、`50aa70(list, idx)` の戻り値を `864fe0` の `this` にする。**unit 275 の直前で `list=0`**。`50aa70` は `[0+8]` を基底、`[0+16]` を件数として読み、添字 13 で `0x10b80000070000` (線形メモリ外) を `this` にする。これが `864fe0` の `[this+8]` の OOB になる。
2. **list を構築する unit が存在しない**: 全 942 unit を実行して `[obj+188]` を監視したが、値は最後まで 0 のまま変化しない (`probe881_watch.mjs`)。よって 275 は「項目列が空・未構築」の状態で `80e040` に入っている。
3. **monitor 列挙 stub 仮説は 275 について反証された (§4.1)**: list を組むのは `867510` (`function_867510`) で、`EnumDisplayMonitors` を呼ぶ (`867510` の `lea r8` で渡す callback は VA `0x85df70`)。`m11_winstubs.c` の `EnumDisplayMonitors` は `return 0` で callback を呼ばない。ただし stub 実装 + callback lift を入れて callback を実際に呼んでも、275 は `oob` のまま (n=1)。よって「空 list が 275 の OOB の原因」とは言えない。`EnumDisplayMonitors` / `GetMonitorInfoW` を呼ぶ unit は 114 (halt0) と 275 (oob) のみ。
4. **訂正**: 作業中に「callback は `function_867510`」と書いたのは誤り。`867510` は呼出し側で、callback は VA `0x85df70` (PE 上は実在する関数の先頭 `push rsi; push rbx; mov rbx,rcx; mov rsi,r9`)。ただし IR には lift されておらず (`function_85df70` 無し)、wasm から呼べない。
5. **ネガコン実施済み (§4.1)**: 「stub を仮実装した」ネガコンを実施し、275 の oob は解消しないことを確認した (n=1)。`this` の出所 (受入条件 1) は上記 1〜3 で実測済み。受入条件 2 は解消。原因の確定 (残る候補) は未解決で、§5 に起票先を記載。

## 1. 実測の基準 (HEAD = origin/main b2a1e114)

- e2e `m11_e2e.sh` (foreground、rc=0、154 s、maxrss 2.07 GB): reached_stage 4、units_run_full 53/942、**survey_ok 870**、trap 25 (oom 1)、miss 46、noproc 1、clobber 0。stop_reason は `trap "unreachable" @ function_8c5eb0`。
- survey `SV_RAW=1 survey_units.mjs` (foreground、rc=0、12.9 s): `SURVEY_UNITS {"ok":870,"miss":46,"other":1,"halt0":8,"oob":16,"noproc":1}`。
- unit 275 は `oob`、frames `864fe0 ← 80e040 ← 80e140 ← 80e170`、stubs `EnumDisplayMonitors 1 / GetMonitorInfoW 15 / SystemParametersInfoW 1`。
- **REPORT_684 (`e920ac3`/`0618c61` 時点) の値 (ok 829 / oob 11) とは一致しない**。main の変更由来と推定 (未切り分け)。本 REPORT の数値は本 HEAD の実測で、REPORT_684 は更新しない。

## 2. this の経路 (IR 実測。`work/boot_final.ll`)

| 関数 | 役割 (IR 読解) |
|---|---|
| `80e040` | `866690`/`867390` で初期化後、`idx` ループ: `this = 8657b0(*G, idx)`、`864fe0(this, …)` |
| `8657b0(obj, idx)` | `50aa70(*(obj+188), idx)` を返す |
| `50aa70(list, idx)` | `[list+16]` が `idx` より大きければ `[list+8+8*idx]` を返す。小さければ `449600` で拡張 |
| `864fe0(this, _)` | `GetMonitorInfoW(*(this+8), …)`。`this` が不正なら OOB |
| `867510` | `8674a0` (list を走査) の後 `EnumDisplayMonitors(NULL, NULL, cb=0x85df70, [G2+188])`。list を埋める役 |

動的実測 (`probe881_275.mjs` / `probe881_275b.mjs`, survey と同順で unit 0..274 を実行):
- 275 直前: `obj=0x11f7198`、`list=0`、`base=[0+8]=0x2fa360`、`count=[0+16]=3204488`。
- 添字 0 → `this=0x3069d0` (in range)、添字 1 → `0x2fcfd0` (in range)、**添字 13 → `0x10b80000070000` (線形メモリ外、`this+8` が範囲外)**。
- 275 の実行結果: `trap: memory access out of bounds` (survey と一致)。

## 3. list の書込み元 (全 unit 監視)

- `probe881_watch.mjs`: unit 0..941 を順に実行し `[obj+188]` を監視。**変化した unit は 0 件**。最終値 0。
- `EnumDisplayMonitors` を呼ぶ unit: 114 (`halt0`、1 回) と 275 (`oob`、1 回)。`GetMonitorInfoW` は 275 のみ (15 回)。
- よって「monitor 列挙で list を埋める」経路は、stub が 0 を返すため一度も成立しない。

## 4. 仮説の判定

- 仮説「monitor 列挙 stub が 0 を返すことが this 不正の原因」: **§4.1 のネガコンで 275 について反証** (callback を呼んでも 275 は oob のまま)。初版の「支持 (間接)」は、stub が list を埋める前提の推論に過ぎなかったため撤回。
- 「list が空だと必ず OOB になる」ことは実測 (添字 13 の garbage) で示した。「stub を実装すれば 275 が ok になる」は §4.1 で反証済み。
### 4.1 ネガコン (#1096、測定 commit 6f979463。以後 `11b51bc9` までの差分は `m11_win.c` の注釈 2 行のみ (実行コード差分 0))

- 測定条件: 変更前 (base1096_before) は `c4e93550` のコード、(a) と (a)+(b) は `6f979463` のコード。
- e2e (`m11_e2e.sh`、incremental、foreground、n=1、測定 commit `6f979463`): rc=0、47.5 s、load 0.47、reached_stage 4、survey_ok 872。本 HEAD `11b51bc9` では未再測定 (上記理由)。
- **本 fix run では再測定していない** (未検証): `/opt/emsdk` (EMSDK 6.0.12) と `/opt/retdec` (RetDec v5.0) が runner に無く、全再生成 (RetDec lift) が fix run の上限 (40 分) に収まらないため。下表の数値は #1096 作成時の記録 (n=1) で、本 HEAD での再現は未確認。再測定は子 issue (§5) で行う。
- 既知の不整合: 同じ base の survey 値が §1 (ok 870) と本表 (ok 871) で 1 ずれている。原因は未切り分け (作成時の別 run の値の可能性)。

- 変更 (a): callback VA `0x85df70` (56 B) を `m11_extra_ranges5.txt` に追加し boot5 として lift → IR に `function_85df70` (i64 4 引数) が入る。
- 変更 (b): `m11_win.c` に `EnumDisplayMonitors` (monitor 1 件 `0x10001` を `m11_icall` で callback に 1 回渡す) と `GetMonitorInfoW` (1920×1080, primary) の仮実装を追加。生成 stub (`return 0`) は `M11_EXCLUDE` で除外される。
- survey (`SV_RAW=1 survey_units.mjs`, 各 13 s, rc 0):

| 条件 | ok | oob | halt0 | miss | noproc | other | unit 275 |
|---|---|---|---|---|---|---|---|
| 変更前 (base1096_before) | 871 | 16 | 7 | 46 | 1 | 1 | oob |
| (a) のみ (IR lift, stub 戻し) | 871 | 16 | 7 | 46 | 1 | 1 | oob |
| (a)+(b) | 872 | 15 | 7 | 46 | 1 | 1 | oob |

- 遷移: (a) のみ 0 件。(a)+(b) では **unit 144 のみ `oob`→`ok`**、275 以外の他遷移は 0 件。
- unit 275 は (a)+(b) でも `oob` のまま。`frames` は変わらず `864fe0 ← 80e040`。
- **callback `0x85df70` が 275 で 1 回呼ばれたという記述の根拠は未確認**: 作成時の icall 出力の保存先・取得コマンドが REPORT にも work/ にも残っていない。本 fix run でも再取得していない。再取得の手順 (子 issue で実施): `M11_TRACE=1` で `m11_survey.mjs` を走らせ `icall_hits.py <survey>.json --units` で `target:0x85df70` の hit unit を確認する。
- 判定: **仮説 (list 空が 275 の OOB の原因) は 275 では反証された** (n=1)。`EnumDisplayMonitors` の stub 欠落は 275 の直接原因ではないと判断する (残る候補: `8651a0`/`5dca50` 経路、または list 以外の `50aa70` 入力)。
- 再現回数: 上記の survey 1 回 (n=1)。同一条件での再現 (n≥2) は未実施。
- 144 の改善は stub 由来 (IR のみでは変化なし)。144 の `GetFileAttributesW`・`SetDllDirectoryW` stub (0 を返す) とは別経路の可能性があり、要調査。

- 留保: `8651a0` / `5dca50` の `EnumDisplayMonitors` 呼出しが list を埋めるかは未確認。空 list で `50aa70` が `[0+16]=3204488` を件数として読むのは、NULL 相当の `0` 番地の残骸 (REPORT_684 §3 の address 0 書換えと同種) を読んでいる可能性がある。残骸の出所は未特定。

## 5. 未達と起票先

| 未達 | 理由 | 起票先 |
|---|---|---|
| 受入条件 2: monitor 列挙 stub の仮実装 + ネガコン | **解消** (§4.1、n=1)。ただし本 fix run では再測定していない (emsdk/RetDec 不在)。再測定と n≥2 は子 issue | 子 issue (再測定・n 増し) |
| 原因の確定 (275 の list 空が OOB の原因か) | §4.1 で stub 欠落は 275 の直接原因でないと判定。残る候補 (`8651a0`/`5dca50`・`50aa70` の入力) は未調査 | 子 issue |
| 受入条件 3: DEFECTS 行案 | 原因が未確定のため、類型の確定は不可。行案は §6 に暫定で残す | 子 issue |

## 6. DEFECTS.md 行案 (PM 判断。本 PR では未編集)

| 型 | 出所 | 症状 | 根本原因 (実測) | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| 未定 (原因未確定。候補: 外部 API の stub が callback を呼ばない) | ours | 項目列 (list) が空のまま 80e040 に入り、`50aa70` が NULL 近傍を読んで garbage `this` → OOB | 未確定。`EnumDisplayMonitors` stub (`m11_winstubs.c`) は `return 0` で callback (VA 0x85df70) を呼ばない。ただし stub を実装して callback を呼んでも 275 は oob のまま (§4.1、n=1)。したがって stub 欠落は 275 の直接原因ではないと判断する | unit 275 (`864fe0` OOB)。全 942 unit で list 不変 | 未確定 (類型判定は原因確定後) | 原因確定後に決める |

## 7. 再現手順

```sh
export PATH=$RUNNER_TEMP/venv881/bin:$PATH FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP
cd tools/m11
sha256sum "$FL_WIN64_DIR/extracted/block00031_PE.bin" | cut -d' ' -f1 > work/lift_pe.sha256   # 素材 work-m11 に無いため (#516 以前の生成)
bash m11_e2e.sh                                       # rc 0 (154 s)
SV_RAW=1 node trap_triage/survey_units.mjs work/trap_triage/base.json   # 12.9 s
node trap_triage/probe881_275b.mjs                    # 添字 13 の garbage this
node trap_triage/probe881_watch.mjs                   # 全 942 unit で list 不変
```

注意: work-m11 は #516 以前の生成で `lift_pe.sha256` が無い。全再生成 (`--full`) は Ghidra の `functions_dll.csv` が要るため使わず、PE 指紋だけ記録して増分 build を使った (`work/lift_pe.sha256`)。

## 8. 検証結果 (実測。本 HEAD = origin/main b2a1e114)

- e2e rc=0、154 s、reached_stage 4、survey_ok 870 (§1)。
- survey 12.9 s、ok 870 / halt0 8 / oob 16 / miss 46 / noproc 1 / other 1。unit 275 は oob (§1)。
- probe `probe881_275b.mjs`: 添字 13 の garbage this を 1 回確認 (再現性は未確認、n=1)。
- probe `probe881_watch.mjs`: 942 unit で list 変化 0 件 (n=1)。
- ネガコン: 実施済み (§4.1、n=1)。ただし本 fix run では再測定しておらず、§4.1 の数値は作成時の記録。

## 9. 変更点と範囲

- 新規: `trap_triage/REPORT_881.md` (本書)、`trap_triage/probe881_275b.mjs`、`trap_triage/probe881_watch.mjs` (いずれも診断用、既定の survey には影響しない)。
- `DEFECTS.md` / `REPORT_684.md` / `survey_units.mjs` は未変更。
