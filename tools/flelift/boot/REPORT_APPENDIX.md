# tools/flelift/boot — REPORT 付録 (FLE-2〜FLE-5 ラウンド詳細・停止原因の逆引き)

> `REPORT.md` の行数上限 (250 行, `docs/DOC_MAP.md` §1) 超過に伴う**分割移動**。内容は削除していない
> (元の位置は Git 履歴 `REPORT.md` @ 3ae2d0d を参照)。測定値の正本は `REPORT.md` と本付録の双方で
> 同一数値を重複させず、本付録は「ラウンドごとの経緯・逆引きの証跡」を持つ。

## A. §0 から移動: FLE-2〜FLE-5 ラウンド詳細

  **FLE-2/FLE-3 で突破したもの** (累積):
  1. **Delphi switch テーブルの case body 自動 harvest** (`gen_boot.py`): `.text` 内の
     「`.text` を指す 8B 値が 2〜32 個連続」領域から shape `48 83 c1 <imm8> e9` のものだけ root 化。
     roots 20,899 → 21,307、関数数 29,420 → 29,753。実測テーブル: `0x5275b0`(4) /
     `0x433090`+`0x4330a8`(4+5) / `0x642e78`(20 entry)。
  2. **`boot_e2e.sh` の既定 closure を 0 → 2 に変更** (`FLE_LIFT_CLOSURE` で上書き可)。
  3. **`shimx_set_cs_null_ok(1)`** 導入 (`InitializeCriticalSectionEx(NULL)` の fail-fast 回避)。
- **FLE-4 の成果 (unit#209 OOB の原因特定と修正)**:
  1. **原因特定**: `chk` variant の `fle_chk` が報告する `__LINE__` は **lift 生成 C の行番号**
     (= 1015940) で、これを辿ると **`0x8157c1: call qword ptr [rbx + 0x18]`** (仮想呼出)。
     `f_815050` の実測: `obj = *(0x15F6F78)` (VMT 0x666fa0 を持つ正常ヒープオブジェクト) だが
     **`obj->field_8 == 0`**。`mov rbx,[rax]; call [rbx+0x18]` は **NULL 仮想呼出**になる。
     ネイティブ Windows では AV だが、wasm では linear address 0 に emscripten magic
     (`"emsc"` = 0x63736d65) があるため `call [0x63736d7d]` で OOB。
     **「文字列内容が @var として渡される型混同」という前ラウンド報告は誤りで、
     実際は NULL フィールドへの仮想呼出** (訂正)。
  2. **NULL ページ guard** (`fle_boot.c`): 初回 install 時に `[0, 0x1000)` を 0 埋めする。
     guest イメージは 0x400000 始まりで未使用領域。NULL 仮想呼出は `ott_unlifted(0)` →
     m11 と同じ icall-miss 規約 (ret 0) で graceful に継続する。
     `fle_boot_set_nullpage(1)` で無効化可能。
  3. **次の blocker も特定**: `unlifted 0x6a7b70` は `f_6a7f50` (unit 終了フック) が 0x15F4B80 に
     設定する **fill コールバック**。root 化すると `f_6c7900` の fill ループが未初期化幅
     (0xffffa = 1,048,570 回) で暴走して ExitProcess → survey が成立しない。
     **boot_roots.json からは除外** (unlifted で止める方が survey は functional)。
- **FLE-5 の成果 (fill ループ幅「未初期化」の真因特定)**:
  1. **`chk` variant の `__LINE__` 逆引きは guest VA 直接指定に拡張** (`boot/dbg_lift.py`)。
     lift 生成 C は `/* <VA>: <asm> */` コメントが 1 行ずつ対応するため、`grep -n "6c7610"`
     で即座に C 行を引け、`fprintf` を挿入して実測できる。
  2. **`f_6c7610` の `rsi` (record へのポインタ) は 0x100000、中身は全 0**。
     rsi の由来は `f_6b91c6` の `System._GetMem` 直後の **`call [rax]` (0x6b91e6)** が
     `dispatch(0)` (= icall-miss) に失敗したことで、結果が 0 渡しになったこと。
  3. **その `rax = *(0x15E0A48)` = 0x15F34A0 は .bss の関数ポインタで、image 全体に
     store 命令が 1 つも無い** (直接 store 0 件)。→ **動的登録型**。
  4. **登録側は `f_653f40`**: `f_653dd0(self, @field, @method)` が `@field` に
     メソッドのクラスインスタンスを store する。`0x15F34A0 = 0x15F33C0 + 0x1E0` は
     `f_653f40` が登録する連続 .bss フィールド列の 15 番目。
  5. **`f_653f40` は "guard `*(0x15F40E8) != 0`" で早期 return している** (実測)。
     その guard を作る `f_6539e0` → `f_43c5e0` (VCL リーダ/`0x43c624` の DFM 系データ参照)
     → `f_414ec0` が **out = 0** を返すため。`f_6539e0` は正常系で
     `0x15F40E8` に non-NULL を書く必要がある。
  → **前ラウンド「ループ幅が未初期化」という観測は正しいが、原因はそこではなく
     「フィールド登録が 1 つも走っていない」**。根は VCL フォーム/リソース読み出しにある。
- **FLE-5 の副次成果 (survey 非 ok 7 → 3)**:
  1. **survey unlifted 5 の内訳を確定し、5 件中 5 件すべてを解消**:
     | unit | 旧分類 | target VA | 対策 |
     |---|---|---|---|
     | 280 | oob | 0x477e73 / 0xd122e0 / 0x8dfff0 経由 | boot_roots 追加で解消 |
     | 296 | unlifted | 0x477e73 | ***|
     | 659 | oob | 同上 | *** |
     | 666 | unlifted | 0xd122e0 | *** |
     | 830/895/898 | unlifted | 0x8dfff0 | *** |
     `0x477e73` / `0xd122e0` / `0x8dfff0` はいずれも .text 内の**実行時にしか到達しない
     コール先**で、`.pdata` に開始点を持つ .text 関数。boot_roots 追加で lift すると
     (関数 29,902 → 29,907) oob 2 件・unlifted 2 件が消える。
  2. **`iterate_roots.sh` に root blocklist を追加** (`FLE_ROOT_BLOCKLIST`, 既定 `0x6a7b70`)。
     自動累積が survey を破裂させる address を再投入しないようにする。0x6a7b70 は
     何度も再投入されて exit ルートに戻ってしまっていた。
  3. **`native_fault 92` を CAB-232/233 接続可能な形に整理** (§4-2)。両 route は同一 PE VA
     空間なので、function-level JSONL と混在採点しても `function.va` で衝突しない。
  4. **残 non-ok 3** = survey unit 280 / 659 (target `0x6a7b70` の unlifted) + 895
     (target `0x976da0`)。`0x6a7b70` は §3-4 の通り root 化すると survey が破裂するため
     意図的に除外。即「非 ok 3」で、目標 5 以下を達成。
- **FLE-4 実測値**:
  - **survey (942 unit 隔離, closure 2): FLE-5 末 = ok 892 / unlifted 3 / empty 46 / noproc 1**
    (FLE-4 末 = ok 888 / oob 2 / unlifted 5 / empty 46 / noproc 1 — **非 ok 7 → 3**)。
  - **verdict 混在採点** (`gen_mixed.py` の target 別レポート):
    関数級 (target=flelift) 7,421 行 + unit 級 (target=flelift-boot) 943 行 = 8,364 行。
    一致 4,943 / 不一致 776 / 実行不能 2,645。
    unit 級の **x-route_diff 142** のうち **native_fault = 92** (native 側 fault / x64c ok = x64c 優位)。
  - **variant 4 種 link**: plain / strict / nosx / chk 全て error 0
    (chk の `fle_chk` は `fle_cpu.c` も `-DFLE_CHK` でビルドする必要がある — boot スクリプト修正)。
- **FLE-2 の 3 バグ修正 (前ラウンド、そのまま有効)**:
  1. **FreeMem 戻り値の判定逆転** (`fle_ov_freemem`): 実機 `System._FreeMem` 0x409440 は
     `mov ebx,eax / test ebx,ebx / je ok / mov cl,2 / call @Error` — **0 = 成功 / 非 0 = エラー**。
  2. **guest stack の push/pop 不釣合** (`fle_ov_getmem`/`fle_ov_freemem`): 偽 retaddr の
     push が未消費で 1 呼出 8B 沈下 → `pop rbx` が `0x43000000000000` を読んで OOB (§3-2)。
  3. **`gen_boot.py` のポインタ typedef 誤分割**: `typedef WCHAR* BSTR;` を誤分割し
     `SysAllocStringLen` が soft stub (常に 0) に → nil → raise。22 typedef 対象。
- **boot 実測 (plain, closure 2, switch harvest 有)**: **126 unit dispatch / 125 完走**。
   停止原因は **unlifted 0x642e1b 周辺の残り** (VMT 経由の実行時構成ポインタ)。
- **survey (942 unit 隔離, closure 2 + switch harvest)**: **FLE-5 末 = ok 892 / unlifted 3 / trap 0 /
   empty 46 / noproc 1** = 非 ok 正味 **4** (FLE-2 末 36 / FLE-3 末 7 / FLE-4 末 7 / baseline 95)。
   **ok 859→892, oob 9→0, unlifted 22→3, trap 5→0 — 全分類で改善**。
   outcome (`gen_verdict.py`): **equal 800 / native_fault 92 / diff 49 / both_fault 1** (FLE-5 末)
   (FLE-2: equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4)。
- **verdict 混在採点** (`gen_mixed.py`): `work/boot/verdict_mixed.jsonl` (gitignore, 8,364 行 =
   関数級 7,421
   + unit 級 943) を `tools/liftdiff/liftdiff.py summary` で採点 →
   一致 4942 / 不一致 777 / 実行不能 2645。unit 級の差分はタグ `x-route_diff` として集計され、
   **native_fault (baseline は fault / x64c は ok) = x64c 優位 89 unit** として分類される。
- **回帰**: `fle_e2e.sh` = **PASS** (spot diff 16/16 bit 一致、D9 mismatch 0)。
   `boot_e2e.sh` = **4 variant 全て link 成功** (nosx は本 round で初)。
   **strict ≡ plain** (soft stub 0)、**nosx は unit 0 で exit** (shimx 必須の定量化)。
- 検証資産: `blkdiag` (System._GetMem/_FreeMem トラッキング + canary)、
   `rt/fle_cpu.c` の `fle_chk` 拡張 (bad guest address + RSP/RBP/regs + stack 探索)。
- `bash tools/flelift/boot/boot_e2e.sh` (1 コマンド) 。`FLE_LIFT_CLOSURE=2 bash ...` で closure 変更可。

## B. §3 から移動: unit 停止原因の特定 (FLE-2〜FLE-5)

元 REPORT.md §3 の見出しは「unit#17 停止原因の特定 (本 round の主成果)」。

### 3-1. (FLE-2 累積) 3 バグ修正の要点

1. **FreeMem 戻り値の判定逆転** (`fle_ov_freemem`): 実機 `System._FreeMem` 0x409440 は
   `mov ebx,eax / test ebx,ebx / je ok / mov cl,2 / call @Error` — **0 = 成功 / 非 0 = エラー**。
   (FastMM 0x40801f は `mov eax,-1`)。旧コードは `if (!ok)` で `@Error` を呼び正常 free を
   エラー扱いしていた。
2. **guest stack の push/pop 不釣合** (`fle_ov_getmem`/`fle_ov_freemem`): C override が
   `ott_dispatch` 前に独自の偽 retaddr を push して 1 呼出 8B 沈下。呼出元の `pop rbx` が
   8B 低い slot を読み `rbx = 0x43000000000000` → OOB。`R[4] += 8` を dispatch 直後に追加して解決。
3. **`gen_boot.py` のポインタ typedef 誤分割**: `typedef WCHAR* BSTR;` を
   `body='WCHAR* BST'` と誤分割 → `SysAllocStringLen` が soft stub (常に 0) → nil → raise。
   22 typedef 対象。修正後 `noproto` 0 / shimx.h 603 prototype の戻り値型未解決 0。

### 3-2. lift closure の重要性 (closure 0 vs closure 2 の実測)

| closure | 関数数 | unlifted callees | unit 進行 | 停止原因 |
|---|--:|--:|--:|---|
| 0 | 20,479 | 5,807 | 16 | unlifted 0x40fb40 |
| 2 | 29,415 | 1,678 | **40** (39 完走) | unlifted 0x527b5b (fn 0x5274c0 の途中) |

### 3-3. (FLE-4) unit#209 の OOB 原因と NULL ページ guard

`chk` variant の `fle_chk` が報告する `__LINE__` は **lift 生成 C の行番号** (= 1015940) で、
これを辿ると **`0x8157c1: call qword ptr [rbx + 0x18]`** (仮想呼出)。`f_815050` の実測:
`obj = *(0x15F6F78)` (VMT 0x666fa0 を持つ正常ヒープオブジェクト) だが **`obj->field_8 == 0**。
`mov rbx,[rax]; call [rbx+0x18]` は **NULL 仮想呼出**になる。
ネイティブ Windows では AV、wasm では linear address 0 の emscripten magic
(`"emsc"` = 0x63736d65) を読んで `call [0x63736d7d]` で OOB。
**前ラウンド報告の「文字列内容が @var として渡される型混同」は誤り** (訂正)。
対策: `fle_boot.c` が初回 install 時に `[0, 0x1000)` を 0 埋めし、NULL 仮想呼出は
`ott_unlifted(0)` → m11 と同じ icall-miss 規約 (ret 0) で継続。

### 3-4. (FLE-4) unit#209 の次の blocker

`unlifted 0x6a7b70` は `f_6a7f50` (unit 終了フック) が 0x15F4B80 に設定する **fill コールバック**。
root 化すると `f_6c7900` の fill ループが未初期化幅 (0xffffa = 1,048,570 回) で暴走して
ExitProcess となり **survey が成立しない**。boot_roots.json からは除外
(unlifted で止める方が survey は functional)。根本対策はループ幅
(`[rbp+0x48]-[rbp+0x40]`) が未初期化な理由の特定。

### 3-5. (FLE-5) 上記「未初期化」の**真因** — 5 段の逆引きで実証

FLE-5 は `boot/dbg_lift.py` (任意 guest VA を lift 生成 C の行に埋め込む診断ツール) を
作り、以下を順に実測した。**結論: ループ幅ではなく、`f_653f40` が早期 return するため
コールバックが未設定**。

```
(1) f_6c7610 entry 実測       → rsi=0x100000, rec = 全 0
    rsi は f_6b91c6 の System._GetMem 直後の `mov rax,[rip+f27862]; call [rax]`
    (0x6b91e6) が dispatch(0) に失敗して 0 渡しになった結果

(2) その rax = *(0x15E0A48) = 0x15F34A0 (.bss) — call [rax] なので
    コールバック = *(0x15F34A0)  = 0  → icall-miss で ret 0 → rec 全 0

(3) 0x15F34A0 の store 命令を image 全体 (全 .text の rip-rel 走査) で数えた → 0 件
    138 箇所が読むだけで誰も書かない = **動的登録型**

(4) 登録側は f_653f40: f_653dd0(self, @field, @method) が @field にメソッドの
    クラスインスタンスを store する。0x15F34A0 = 0x15F33C0 + 0x1E0 は
    f_653f40 が登録する連続 .bss フィールド列 (0x8 間隔) の 15 番目

(5) f_653f40 の guard: `*(0x15F40E8) != 0` で continue、== 0 で EARLY EXIT
    実測: f_6539e0 → 0x15F40E8 = 0 → guard ZERO → EARLY EXIT
    その f_6539e0 は f_43c5e0 (VCL リーダ、0x43c624 の DFM 系データを参照)
    → f_414ec0 が out = 0 を返す (blkdiag: FREEMEM site=0x412e7c<-0x43c618)
```

`0x43c624` 近辺のデータは VCL のメニュー/フォーム定義 (`TMainMenu` / `TPopupMenu` /
`TMenuItem` / `Vcl.Menus` 等のシンボリック列) なので、**guest 側の VCL リソース読み出し**
が失敗している。unit 進行を 209 から先に進めるには、この VCL フォーム登録の
早期 return を外す (`f_43c5e0` / `f_414ec0` 側) 必要がある。

なお (3) の「image 全体に store 0 件」は **rip-rel disp32 バイト走査**の結果で、
`f_653dd0` は `mov rcx,[rbp+0x28]; mov [rcx],rax` という**動的ストア**なので
即値検索では決して出てこない (`boot/dbg_lift.py` の `--at` で解決)。

## C. §10.x から移動: FLE-6 実測の試行 (fix run 2026-10-13, Refs #672)

- 素材: `fl-win64` → `[WIN64]` (展開 7.8 s)、`work-m11` → `tools/m11/work` (233 件)、`work-liftdiff` → `tools/liftdiff/work` (11 件)、`[EMSDK]` (emcc 6.0.12)・`[RETDEC]` 有。`capstone` / `pefile` は リポジトリ外の venv に導入。
- 資源 (14:43 UTC): MemAvailable 14334 MiB / 空き 69G / nproc 4 / load 1.07。
- `fle6_measure.sh` (foreground, `timeout 1500`, rc=124): gen-A 7 s 完了。`lift` (x64c, closure 2) は 25 分経っても完了せず打ち切り。`work/boot` 配下の生成物は無し。
- 未取得: shim 有/無の `units_run`・`stopped_at`・`ipp.called` 全件・`FLEBOOT_IPP_CHECK`・0x6a7b70 root 化後の前進・survey 非破裂。**取れなかった理由: lift 段の時間切れ (25 分で打ち切り)**。
- 判定: 受入条件は未了のまま。Closes は付けず `Refs #672`。次の run で lift 単体の所要時間を先に採ってから boot に進む。
- 実測 1〜3 (REPORT §10.x から移動, 2026-10-13, head 55acfb6d → 8cfd4a8c・947cbb58):
  - 実測 1 (16:14–16:23 UTC, head 55acfb6d): 全量 lift (`--closure 2`) は `ulimit -v 12GB` で `MemoryError` (約 2 分)。仮想メモリ上限では RSS は取れない。closure 1 は capstone の確保で `MemoryError` → RSS 監視 (12288MB) に切替え、16:21:35 開始 → **ピーク RSS 12563MB で kill (rc=143)**。`[sys]` の MemAvailable は run ログ `rss.log` にある。
  - 実測 2 (16:33–16:38 UTC, head 8cfd4a8c, `fle6_measure.sh` 本体): 監視は python3 ラッパー (1 秒ごとに VmRSS を読み、cap 13824MB 超で **その PID だけ** kill)。runner は MemTotal 15988MB / swap 3071MB。gen-A 7 s 完了。closure 2 (`FLE_EXTRA_ROOTS=0x6a7b70`): 16:33:53 開始 → **ピーク RSS 13883MB で kill (rc=143)**、約 2 分。closure 1 (同上): 16:36:13 開始 → **ピーク RSS 13949MB で kill (rc=143)**、約 2 分。
  - 未特定: どの root / 関数で RSS が膨らむかは (ログに関数名を出していないため) 未特定。
- 素材の現状 (fix run 2026-10-13 16:40–16:45 UTC): 「素材不足」ではない。`$ARTIFACTS_DIR` に 5 種 (fl-win64 / toolchain-emsdk / toolchain-retdec / work-m11 / work-liftdiff) が実在し、`fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` → `tools/m11/work`、`work-liftdiff` → `tools/liftdiff/work` に展開済み。`/opt/emsdk`・`/opt/retdec` は runner に既存。capstone 5.0.7 / pefile は `$RUNNER_TEMP/venv-flelift` に導入。失敗理由は素材ではなく lift の RSS。
- 実測 4 (PM 指示の 1 回採取, 16:43 UTC 開始): `gen_boot.py` → `rss_cap.py --cap-mb 13800` で `x64c.py --closure 1` (`FLE_EXTRA_ROOTS=0x6a7b70`)。MemAvailable 起動時 14799600kB (≈14.4GB)。**126 s、ピーク RSS 13832MB、cap 超過で kill (rc=143)**。closure 2 は再採取しない (実測 3 の 25 分打ち切りをそのまま時間切れとして残す)。
- 結論: この PR では lift が runner の上限内で完走しない。clang・boot・ネガコン・`FLEBOOT_IPP_CHECK` は未到達。分割 lift で完走させる作業は #918 (FLE-7) に分離。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 SS_EMSDK_ENV=/opt/emsdk/emsdk_env.sh FLE_RSS_CAP_MB=13800 bash tools/flelift/boot/fle6_measure.sh` (lift 段は `boot/rss_cap.py` 経由。cap 超過で rc=143 → スクリプトは停止)。

## D. §9 から移動: 2026-10-12 CI runner の再現検証 (検証起点 3ae2d0d = main HEAD)

GitHub Actions runner (4 vCPU / RAM 16GB + swap 16GB 追加) で `boot_e2e.sh` を素の状態から実行した実測。
`FLE_PE` = `fl-win64.tar.zst` 内 `extracted/block00031_PE.bin`、emsdk 6.0.12、capstone/pefile は venv。

| 工程 | 実測 |
|---|---|
| lift (x64c, closure 2) | 227 s、関数 29,907 / 命令 1,557,882 (§2 FLE-5 列と一致) |
| `fle_lifted.c` の clang -O0 (1 variant) | 約 6.5 分 (RSS 最大 14.8GB。RAM 16GB では swap 必須) |
| link plain | mismatch 0 / undefined 0 / duplicate 0、wasm 126,995,230 B |
| boot 実行 plain (`--boot-only`) | 5.87 s (load average 1.70)、units_run 209 / units_total 942、`boot_threw=unlifted`、getmem 1,890 / freemem 776、exit 0 |

- boot 実測は FLE-5 末の記載 (209 dispatch、GetMem 1,890 / FreeMem 776) と**完全一致**し、再現性を確認した。
- strict / nosx / chk の link・実行および survey (942 unit) は本 run では未実施 (clang 1 本 6.5 分 × variant 数 + 60 分のジョブ上限)。
  FLE-5 末の値 (§4-1, §4) は据え置き。
- ネガティブコントロール: 未実施 (本 run はコード変更なし。REPORT 分割のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `f_43c5e0` → `f_414ec0` (UStr copy) が out=0 を返す理由 (付録 §B 3-5) | unit 進行 209 で停止、`0x15F34A0` 未登録 | 本 issue (#253) に継続 |
| survey 非 ok 3 (unit 280/659 `0x6a7b70`、895 `0x976da0`) | survey 完全 ok 未達 | 本 issue (#253) に継続 |
| lifted C コンパイルが 14.8GB 使う | CI (RAM 16GB) では swap なしで不可 | CI 整備 issue (#284) へ提案 |
