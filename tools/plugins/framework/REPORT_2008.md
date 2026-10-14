# #2008 REPORT — 0x710030/0x710040 の値確定と Phase B の plug != 0 実測 (3 回目 run で値確定・Phase B は別原因で子へ移管)

- 担当 issue: #2008 `[PLG-P0b-11]` (親 #1935 系列)。**3 回目 run (§8) の結論**: 受入 1 (0x710030/0x710040 の値確定) は**達成** (値・書込み元・動的確認。「FL export table」前提は誤りで §8.1 が正本)、受入 3 (Phase A 回帰の毎回確認と n≥3) は**達成**。受入 2 (Phase B の plug != 0) は **未達**。3 変数が原因であるとは確認されず、有力な候補は RTL 未初期化 (InitUnits の途中停止・§8.3。原因は未確定) のため子 issue へ移管した。
- §2〜§7 は 1・2 回目 run の記録。「FL 本体の export function table」「`[0x710040]==0` の経路を塞ぐ」「0x710040 の書込み元は 0 件」は **§8 で訂正済み** (読むときは §8 を優先)。
- 起点・測定 commit は各節に記載 (1 回目 `c171b9dc`、2 回目 `32d2cedc`、3 回目 §8.4)。
- 既知類型との関係: §2〜§7 の「外部状態不在による soft-miss」は誤り。InitUnits が途中で停止すること自体は実測 (§8.3)。停止原因が lift 欠陥 (RetDec が引数・サイズの定数を `ptrtoint @global` に化かす型) かどうかは候補のまま未確定で、本節では確定しない (`docs/DEFECTS.md` D21 とは別型の候補という位置づけ。同一とは未確認)。

## 1. 実測

素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`・`FL_WIN64_DIR` に設定)、`work-fw-stage1` / `work-liftlib` は repo ルートに展開。`toolchain-*` は既存の `[EMSDK]`・`[RETDEC]` を使用。

| 手順 | 結果 | 所要時間 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 8 分 45 秒 (08:25:53 → 08:34:38) | 1.70 → 2.82 |
| `hs_e2e.sh --fresh` (初回) | exit 1。Phase A PASS (`dispatch=38 ff=0`)。Phase B 例外 `memory access out of bounds`・`plug=0x0`・`rec=8` | 1 分 25 秒 (08:34:46 → 08:36:11) | 2.39 → 1.37 |
| `hs_e2e.sh` (2 回目・3 回目) | 出力は初回と同一 (Phase A PASS・Phase B 同一失敗) | **未計測** (`time` の記録が `0 秒` となり信頼できない) | — |
| `hs_e2e.sh` (4 回目・日付差分計測) | rc=1・Phase A PASS (1 件)・`Phase B: status=0xffffffff plug=0x0` | **0.204 秒** (`date` 差分) | 0.03 → 0.03 |

- n=4 だが、所要時間は 1 回目 (85.5 秒) と 4 回目 (0.2 秒) で桁が違い、同一条件の時間として扱えない。このため所要時間のレンジは **未取得**。Phase A・Phase B の結果 (成否・`dispatch=38 ff=0`・`plug=0x0`) は 4 回とも同一。
- 測定の不整合は未解決 (§4)。

## 2. 0x710030 / 0x710040 の調査結果

| 項目 | 結果 | 根拠 |
|---|---|---|
| PE 上の位置 | `0x710000`〜 は PE の `.bss` (raw サイズ 0・仮想 0x10578)。ファイルに初期値なし | `fw_icall.dll` の section table |
| IR 上の書き込み (0x710030) | `function_417ee0` が `store i64 4213760` (= `0x404c00`) | `fw_flat4_canon3.ll` 72135・72157 行付近 |
| IR 上の書き込み (0x710038) | 同じ関数が `0x710038` (= 7405624) に `0x404c10` (= 4213776) を書く | 同上 (135〜136 行付近) |
| IR 上の書き込み (0x710040) | 定数 `7405632` への直接 store は **見つからない**。読み出しは `function_40d6e0` (33490 行) のみ | `grep 7405632` |
| 呼出元 | `call ... @function_417ee0(` は IR 内に **0 件**。`function_417ee0` の名前は `%ce…` 変数名にも現れるため、単純な名前一致では呼出の有無を判定できない | `grep -c 'call .*@function_417ee0'` = 0 |
| PE の参照 | `0x710040` は PE `.data` (file offset 0x30e1b8) に値 `0x710040` として 1 件あるのみ。`0x710030`・`0x710038` の直接出現は 0 件 | バイナリ検索 |
| `fw_map.json` | `0x417ee0 → 0x7d7fd0` のみ (呼出側情報無し) | `fw_map.json` |

- `function_40d6e0` は `[0x710040] == 0` のとき必ず `dec_label_pc_7b812a` に進む (前 REPORT §3 と同じ構造)。`[0x710040]` の値は、lift 済み IR のどこでも決まっていない。
- `0x710030` の初期化は `function_417ee0` が担うが、この関数は IR 内から呼ばれていない (エントリ・未到達)。FL 本体の起動シーケンスからの呼出は、headless では再現されていない可能性が高い。

## 3. Phase B の状態 (未達)

- `plug=0x0`・`status=0xffffffff`・`slotsCalled=0x0`・`rec=8`。
- 失敗の位置は前回 (#1935) と同じ。`CreatePlugInstance → ctor` の Dispatcher ID prefix は `0x47,0x56,0xd,0x2e,0x10000738,0x47,0x1d` で期待 (`0x47,0x56,0xd,0x2e,0x47,0x1d`) と 1 件ずれる。
- soft-miss は `0x0`・`0xf003f`・`0x657243205d73685b` (文字列由来) など多数。`0x40d807`・`0x4e5fa6` の site で `target=0x0` が繰り返される。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x710040` の書き込み元 (IR・PE のどちらにも無い) | `function_40d6e0` の経路を塞げず、`plug=0` のまま (受入 1・2) | #2008 (本 PR で `Refs #2008`) |
| `function_417ee0` が IR 内から呼ばれない (起動シーケンス未再現) | `0x710030` の値は書かれるが、呼出経路を再現できていない | #2008 |
| Phase B `memory access out of bounds` と ID `0x10000738` の呼出 | ctor 連鎖が途中で落ちる (受入 2) | #2008 |
| 所要時間の測定不整合 (初回 85.5 秒 / 4 回目 0.2 秒) | 時間のレンジが取れない (受入 3 の n≥3 レンジ未達) | #2008 |
| GitHub API のレート上限 (installation 170170783) | 子 issue の重複確認・起票ができなかった | 次 run (#2008 の再起動) |

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst    # repo ルートで展開
tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst      # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh --fresh       # exit 0・SMOKE PASS (8 分 45 秒)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh # Phase A PASS・Phase B 例外 (1 分 25 秒)
```

## 6. コード差分 (測定 commit 以降)

測定 commit `c171b9dc` 以降、コード変更は無し。`git diff c171b9dc HEAD -- tools/plugins/framework` は本 REPORT の追加のみ。

## 7. 2 回目 run の追加調査 (未達のまま・確定事実の追記)

- 測定 commit: `32d2cedc` (origin/main。コード変更なし)。以降のコード差分は本節の追加のみ。
- 実測 (同一 commit・n=1 ずつ):

| 手順 | 結果 | 所要時間 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` (stage-1 再利用) | exit 0・`SMOKE PASS dispatch=38 units_done=0 va=1 heap=1 ff=0` | 13 分 31 秒 (10:16:44 → 10:30:15) | 1.09 → 0.98 |
| `hs_e2e.sh --fresh` | rc=1。Phase A PASS。Phase B `memory access out of bounds`・`plug=0x0`・`rec=8` | 147 秒 (10:31:24 → 10:33:51) | 0.98 → 1.48 |

- n=1 ずつのため、前回 (#2008 §1) と合わせても n≥3 のレンジは未取得。受入 3 の「毎回確認」は Phase A の `dispatch=38 ff=0` で満たした。

### 7.1 `0x710040` の書き込み元の全数検索 (PE の機械語)

`objdump -d` (`fw_icall.dll`・約 196 万行) を全数走査し、直接アドレス (rip 相対・絶対即値) による参照を照合した。走査条件 (照合パターンの正確なコマンド) は本 run の時点で記録が無く、stage-1 成果物 (`fw_icall.dll`) が手元に無いため再実行できていない (未検証)。

| VA | 参照の種類 | 箇所 (PE VA) |
|---|---|---|
| `0x710040` | 読み出し・比較のみ (`cmp` / `call [..]` / `mov r11,[..]`) | `0x40d753`・`0x40d7ea`・`0x7b802e`・`0x7b80c5` |
| `0x710040` | 直接アドレス (rip 相対・絶対即値) による書き込みは **0 件**。レジスタ経由の書き込み (例: `0x710000` を `rcx` に入れて `mov [rcx+0x40],eax`) は **未走査** | — |
| `0x710030` | 書き込み | `0x40dbb4`・`0x417f2e`・`0x7b9188`・`0x7d81d1` |
| `0x710038` | 書き込み | `0x40dbc2`・`0x417f3c`・`0x7b9196`・`0x7d81df` |

- `0x710000`〜 は `.bss` (raw サイズ 0)。`0x710040` の初期値はファイルに無い。
- `0x710030` / `0x710038` を書く `0x40dbb4`・`0x40dbc2` は関数 `0x40db20` 内 (`lea rax,[0x404c00]`・`lea rax,[0x404c10]` の直後)。`0x40db20` への直接 `call` は 0 件、ファイル内の 8 バイト値 `0x40db20` 参照も 0 件。
- `0x417f2e`・`0x417f3c` は関数 `0x417ee0` 内 (IR の `function_417ee0` と同じ書き込み)。

### 7.2 `0x417ee0` の呼出経路の手がかり (未検証)

- `fw_icall.dll` のファイル offset `0x2c0870` に、8 バイト値 `0x417ee0` が 1 件ある (他の `0x40d820`・`0x40db20`・`0x40d6e0` は 0 件)。
- 周辺は `0x4198b0`・`0x419890`・`0x417e40`・`0x41baa0`・`0x41ba90`・`0x41c180`… と関数アドレスが連続する。関数ポインタの表 (Delphi の unit initialization 等) の可能性がある。
- 表を読む走査コードは未特定。**未検証の仮説**: 表が起動時に走査されるなら、headless の `fw_boot` はその走査を経由せず `0x417ee0` が呼ばれないことになる。次 run では、この表を走査する命令 (表の先頭アドレスを参照する rip 相対・即値の箇所) を objdump で全数検索して確定する。

### 7.3 `function_40d6e0` の分岐条件 (IR)

- `fw_flat4_canon3.ll` 33490〜33496 行: `[0x710040] == 0` (`%10`) **または** `ptrtoint ptr @684 to i8 != 0` (`%cenh1547`) で `dec_label_pc_7b812a` に進む。
- `@684` は `"$"` の定数文字列。PE 側に対応する比較は `0x40d753` の `cmp [0x710040],0` のみで、`@684` 由来の条件は lift の再構成由来と見られる (未検証)。前 REPORT (§2) の「`[0x710040] == 0` のとき必ず分岐」は、この `@684` 条件を含めて読むべき。

### 7.4 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x710040` の書き込み元 (PE の直接参照では 0 件・レジスタ経由は未走査) | `plug=0` のまま (受入 1・2) | #2008 |
| `0x417ee0` を含む関数ポインタ表 (`0x2c0870`) の走査元 | `0x710030` の値が確定しない | #2008 |
| `function_40d6e0` の `@684` 条件が lift 由来か | 分岐の正しさが未確定 | #2008 |
| Phase B `memory access out of bounds` と ID `0x10000738` | ctor 連鎖が途中で落ちる (受入 2) | #2008 |
| 所要時間 n≥3 のレンジ未取得 (§7 の実測を参照) | 受入 3 の毎回計測 | #2008 |

## 8. 3 回目 run: 3 変数の値確定と Phase B 未達の原因候補

起点 `origin/main` 14150b46。branch `2008-plg-p0b-11-writer`。素材は `fl-win64`・`work-fw-stage1`・`work-liftlib` を展開 (§5)。

### 8.1 3 変数の値 (受入 1・達成)

`function_40d6e0` (`0x40d6e0`) は Delphi RTL の `raise` (`0x0EEDFADE` = Delphi 例外コード、`0x40d820` は `r8=0` で呼ぶだけの薄い wrapper)。3 変数は FL 本体の export table ではなく、RTL の例外フックである。

| 変数 | native の値 | native の書込み元 (PE VA) | 役割 |
|---|---|---|---|
| `0x710030` | `0x404c00` (`jmp [IAT RaiseException]`) | `_InitLib` `0x40db20` の `0x40dbb4`、System unit Init `0x417ee0` の `0x417f2e` | `RaiseExceptionProc` |
| `0x710038` | `0x404c10` (`jmp [IAT RtlUnwind]`) | 同 `0x40dbc2`、`0x417f3c` | `RTLUnwindProc` |
| `0x710040` | `0x43d940` | unit Init `0x43db30` → `0x43d9a0` の `0x43da31`〜`0x43da3f`: `.data` の変数アドレス表 `0x70edb8` (値 `0x710040`) を `rax` に読み、`lea rcx,[0x43d940]` → `mov [rax],rcx` | 例外通知フック (`0x40d6e0` が組む `0x0EEDFADE` の例外レコードを受け、`0x43d940` は ExceptionInformation の例外オブジェクトを `0x426c20` のクラスで判定して仮想呼出する) |

- `0x710040` の書込みを前 run が 0 件としたのは、rip 相対の直接参照だけを走査し、`.data` の変数アドレス表を介した間接書込みを見ていなかったため。`0x43d9a0` は同じ表引きで `0x70e910` / `0x70ed40` / `0x70eb20` / `0x70ed08` / `0x70ed48` / `0x70f2a8` / `0x70e8c0` が指す変数にも関数ポインタ等を書く (先頭で `0x43c780` を 2 回呼んで `0x7165c0` / `0x7165c8` にオブジェクトも作る)。
- `0x43db30` は InitTable (`0x6c1460`、`0x122` = 290 unit、16 byte/entry = Init,FInit) の idx 16。`0x417ee0` は idx 1、`0x445a40` は idx 18。
- 動的確認: hostfix 適用ビルド (`hs_route.cjs`) で DllMain(attach) を先に走らせると `[0x710030]=0x404c00`・`[0x710038]=0x404c10`・`[0x710040]=0x43d940` になる (`hostshim/hs_preinit.mjs`)。
- バグ修正: `fw_boot.c` の `_InitLib` override は `0x716030` / `0x716038` に書いていた (native は `0x710030` / `0x710038`)。修正前は `[0x716030]=0x404c00` の誤書込みを実測し、修正後は 0。Phase A・B の結果は不変 (§8.4)。

### 8.2 「経路を塞ぐ」前提の訂正

- `[0x710040]==0` は native でも正常 (通知フック無し)。`40d753 cmp [0x710040],0 / je 0x40d7f0` で通知を飛ばし、`call [0x710030]` (RaiseException) に進む。塞ぐ対象ではない。
- **scratch 観測・未再現**: Phase B 単体 (DllMain を呼ばない) に 3 変数を直接書いて `_hs_e2e_run` を実行 (`0x710040` は 0 と `0x43d940` の 2 通り)。`0x40d807` の soft-miss は 4 件 → 0 件 (named import `RaiseException` 未実装 fail-soft 1 件に置換)、soft-miss 総数は 40 → 36 と観測された。status・`plug`・`rec`・OOB は不変 (`plug=0x0 rec=8`)。seed 実験のスクリプトは本 commit に無く、1 コマンドでは再現できない。このため「3 変数は Phase B 失敗の真因ではない」は観測から得た仮説として扱い、確定とはしない。

### 8.3 原因候補: InitUnits が途中で止まり RTL が初期化されない

- Phase B (`hs_e2e_run`) は DllMain も InitUnits も呼ばず、生の image (`.bss` ゼロ) から `CreatePlugInstance` に入る。
- **Phase A の `dispatch=38` は InitUnits の完走ではないと推定する (scratch 観測・未再現)**。`MessageBoxA` を JS 例外にした診断ビルド (scratch・非 commit) の wasm スタックで観測した: idx 16 の Init `0x43db30` → `0x43d9a0` → `0x43c780` → `0x417bc0` → `0x40ea20` → `0x40e5e0` → `_GetMem` `0x407010` → `0x407330` → `0x4072d0` → `0x4072b0` → `Error` `0x40e400` → `Halt0` `0x40e270` → `MessageBoxA "Error: Runtime 268436792 at 0000000010000710"`。コードと番地が fold された global (`0x10000638` / `0x10000710`) で、`fw_hostfix.py` 冒頭が説明する `0x40e5e0`/`0x407010` の fold (文字列長 = `@153` のアドレス) と同じ領域。その後 FInit 16 件 → `RestoreContext` → `exit(0)` を「Halt0 到達 = PASS」と数えた場合に 38 になるという内訳 (16 Init + 16 FInit + 6 other) は、この scratch 観測に基づく解釈で、本 commit の script からは再現できない。
- hostfix の `0x40e5e0`/`0x407010` override を持つ `hs_route.cjs` は idx 16 を越える (`0x710040` が書かれる) が、counter=19 (idx 18、Init `0x445a40`) で OOB: `0x445a40` → `0x415220` → `0x414de0` → `0x414390` (wide string copy)。直前に `decode-miss function_40f833` と `GetNativeSystemInfo` 未実装 fail-soft。OOB 時点のレジスタ (scratch 観測・未再現) は rcx=`0x11a75a96`・rdx=`0x105`・r8=`0x1118a6a0` で、いずれも linear memory 内に見える。OOB の直接原因は未確定。
- `function_415220` は native が入力 rdx (呼出元 `0x445ae6 xor edx,edx` で 0) を `0x414de0` に渡す箇所で `ptrtoint @110` を渡している。これを入力 BLK+0x10 に戻す scratch IR 修正で再ビルドしたが OOB は不変だった (scratch 観測・未再現)。別因が残るとすれば未検証の候補は `0x40ffe0` 経由の `r8` と `GetModuleFileNameW` 相当の戻り。この IR 修正は本 commit に含まれない。

### 8.4 実測

環境: 4 vCPU。load は開始 → 終了の 1 分値 (`/proc/loadavg` または `uptime`)。

| 手順 | commit | 結果 | 所要 (real) | load |
|---|---|---|---|---|
| `fw_stage2.sh --fresh` (stage-1 再利用・n=1) | 14150b46 | rc 0・`SMOKE PASS` `dispatch=38 units_done=0 va=1 heap=1 ff=0` | 10 分 40 秒 (12:18:39 → 12:29:19) | 0.36 → 未記録 |
| `fw_stage2.sh` (増分: `fw_route.cjs` を消し emcc + smoke のみ・n=1) | 34cb8e29 | rc 0・`SMOKE PASS` 同値・`ff=0` | 25 秒 | 0.18 → 0.46 |
| `hs_e2e.sh --fresh` (baseline) | 14150b46 | rc 1。Phase A `dispatch=38 ff=0`。Phase B OOB・`plug=0x0 rec=8`・`E2E FAIL: 3 項目` | 114.47 秒 (診断用 emcc と並行実行) | 未記録 |
| `hs_e2e.sh --fresh` (n=3) | 34cb8e29 | 3 回とも rc 1・Phase A `dispatch=38 ff=0`・Phase B `status=0xffffffff plug=0x0 rec=8`・`E2E FAIL: 3 項目` | 116 / 115.26 / 143.44 秒 (レンジ 115.3〜143.4) | 2 回目 0.52 → 0.93、3 回目 0.93 → 1.00 |
| `hs_e2e.sh` (増分・n=3) | 34cb8e29 | 3 回とも同一結果 | 0.254 / 0.255 / 0.254 秒 | 0.35 → 0.35 / 0.35 → 0.35 / 0.35 → 0.56 |

- §1 の所要時間の不整合 (85 秒と 0.2 秒) は `--fresh` (emcc 再ビルド込み) と増分 (node 実行のみ) の違い。
- Phase B の失敗 3 項目: `memory access out of bounds` / Dispatcher ID 列に `0x10000738` が混入 / `id=0x47` の `a0=0x10000808`。いずれも 14150b46 から不変。
- 測定 commit は 34cb8e29 (`fw_boot.c` の修正。`fw_rt.c` は 882cdac1 でコメントのみ変更)。34cb8e29 から HEAD までのコード差分 (`git diff 34cb8e29 HEAD -- tools/plugins/framework ':!*.md'` の実出力) は次のとおり。コメント 3 行の置換のみで、実行コードは不変。

```diff
diff --git a/tools/plugins/framework/fw_rt.c b/tools/plugins/framework/fw_rt.c
index 33560ff2..a6675587 100644
--- a/tools/plugins/framework/fw_rt.c
+++ b/tools/plugins/framework/fw_rt.c
@@ -59,9 +59,9 @@ void __icall_dispatch(uint64_t site) {
     long long (*f)(void) = lookup((uint32_t)t);
     if (!f || (t >> 32)) {
         /* CAB-195: host shim 連鎖 (CreatePlugInstance → ctor) では, Delphi framework が
-         * FL 本体 (FLEngine) の **export function table** (image 外 VA, 例 0x710030) を
-         * 経由する経路が到達する (0x40d6e0 → 0x710030 = FL 内部 API の函数ポインタ)。
-         * headless では FL 本体がロードされていないので呼出は不能。
+         * Delphi RTL の例外フック (0x710030 = RaiseException thunk 0x404c00, 0x710038 = RtlUnwind
+         * thunk 0x404c10, 0x710040 = 0x43d940: REPORT_2008 §8) が未初期化 (target 0) のまま呼ばれる。
+         * Phase B は DllMain/InitUnits を通らないので呼出は不能。
          * 連鎖検証を止めないため fail-soft (0 を返し記録) にする。
          * fw_ff ではない (exit しない) ので回復可能。 */
         g_dispatch_cnt++;
```


### 8.5 再現

```sh
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh                    # 先に実行 (work/hs/hs_route.cjs を作る)
cd tools/plugins/work/hs && node ../../framework/hostshim/hs_preinit.mjs ../fw/fw_image.bin hs_route.cjs
# 期待 (未実測。本 run では実出力を採取していない。実出力への置換は次の run で行う): DllMain 例外 OOB (function_414390)・unit counter=19・[0x710030]=0x404c00 [0x710038]=0x404c10 [0x710040]=0x43d940
```

静的確認 (native): `objdump -d -M intel fw_icall.dll --section=.text` で `# 0x710030` / `# 0x710040` を grep し、`0x43d9a0` と `0x70edb8` を読む。診断ビルドの手順 (`MessageBoxA` を JS 例外にして wasm スタックを得る) と seed 実験は scratch で行い commit していない (§8.2・§8.3 の scratch 観測)。

### 8.6 受入条件と未解決

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | 3 変数の正しい値の確定 | **達成** (§8.1。export table 由来という前提は誤り・§8.2) |
| 2 | Phase B で `plug != 0` | **未達** (原因は未確定。候補は RTL 未初期化の途中停止・§8.3) |
| 3 | Phase A 回帰 `dispatch=38 ff=0` の毎回確認と n≥3 | **達成** (§8.4)。ただし 38 の意味 (idx 16 の RunError 終端で InitUnits 完走の基準ではない) は scratch 観測で未再現 (§8.3) |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Phase A の `dispatch=38` が「idx 16 の RunError 終端」であること (scratch 観測・未再現)。基準の再定義と、stage-2 ビルドへの `0x40e5e0`/`0x407010` 相当の修復 | InitUnits 完走が検証されていない | #2425 (基準の再定義・idx 16) |
| hs ビルドの InitUnits が idx 18 (`0x445a40` → `0x415220` → `0x414de0` → `0x414390`) で OOB (§8.3)。その先の unit と Phase B の `plug != 0` | 受入 2 の本体 | #2426 (idx 18 の OOB・`plug != 0`) |
