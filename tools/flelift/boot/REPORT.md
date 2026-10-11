# tools/flelift/boot — FLE-2〜FLE-5: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

## 0. 結論 (先出し)

- **判定 (累積, FLE-5 末): unit 進行は 209 止まり、survey は全 942 unit で functional**
  (FLE-1 17 → FLE-2 40 → FLE-3 209 → FLE-4 OOB 修正 → FLE-5 **survey 非 ok 7 → 3**)。
  **unit 進行は 209 で横ばい** — ただし FLE-5 で unit 進行の blocker は
  `f_6c7900` の fill ループ幅「未初期化」ではなく、
  **`f_653f40` (VCL フォーム登録ルーチン) が早期 return して
  fill コールバック `0x15F34A0` が未設定** であることを 5 段の逆引きで実証 (§3-5)。
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

## 1. 成果物 (tools/flelift/boot/)

| パス | 役割 |
|---|---|
| `boot_e2e.sh` | 1 コマンド検証: gen → lift (boot entries + override) → data gen → shimx obj → 4 link variant (plain/strict/nosx/chk) → 実行 |
| `build.sh` | **単一 variant 再 build** (診断・反復用。lift 済み C を再利用し fle_boot.c 等の差分だけ link) |
| `gen_boot.py` | entries (+entry 0x1376820 / longjmp 断片 / boot_roots 累積 / VMT harvest)、`.text` 全域データ窓 (#embed 16.4MB)、imp bridge (shimx thunk / soft stub / curated)。**FLE-2: ポインタ typedef 解析を修正** |
| `fle_boot.c` | boot ドライバ: 敷設 + shimx wiring (cbtrans/resolver/LB_BASE=0x10000) + 計数 + `--override` C 実装 (longjmp/GetMem/FreeMem/InitUnits) + curated import。**FLE-2: FreeMem 判定と RSP 釣合を修正** |
| `fle_boot.mjs` | runner: boot 実行 + 分類 + survey (942 隔離, FLE_SURVEY_FROM/TO) + summary/JSONL 出力 |
| `blkdiag` (fle_boot.c 内) | System._GetMem/_FreeMem トラッキング (alloc/free 時系列・16B snapshot canary・二重解放/未追跡/header dump・FastMM dispatch カウント)。`fle_boot_set_blkdiag(int)` / `fle_blkdiag_stat(int)` で外部操作 |
| `boot_roots.json` | 実行時発見 roots **110 本** (累積)。0x403579/0x403582/0x40358b (jump table thunk)・0x40fb40/0x40f960・0x527b5b 等を追加。**0x6a7b70 は意図的に除外** (§3-4) |
| `survey_drive.sh` + `merge_survey.py` | survey を 180s セグメント実行 (timeout 再開) → results/survey.json に統合 |
| `gen_verdict.py` | survey 差分 → liftdiff FORMAT v1 JSONL (results/verdict_boot.jsonl) |
| `gen_mixed.py` | **関数級 (liftdiff) + unit 級 (boot) verdict を 1 ファイルに混在**させて `liftdiff.py summary` で採点。32MB 超のため JSONL は work/boot/ (gitignore)、採点結果は results/mixed_summary.md |
| `iterate_roots.sh` / `dbg_u18.mjs` | root 収束ループ (`FLE_ROOT_BLOCKLIST` で root 化禁止 address を除外) / boot 停止点の guest stack 復元 (再ビルド不要) |
| `dbg_lift.py` | **FLE-5: 任意 guest VA を lift 生成 C の行に埋め込む診断ツール** (`--at 0x8157c1,f_6c7610`)。`/* <VA>: <asm> */` コメントの 1 行対応を利用し `grep -n` で即座に C 行を引き、`fprintf` を挿入して実測する (FLE-4 の `__LINE__` 逆引きを汎用化) |
| `results/` | boot_summary*.json / survey.json / survey.jsonl / verdict_boot.jsonl |

link 実績 (4 variant 全て): signature mismatch 0 / undefined 0 / duplicate 0。wasm 145.8MB (chk) / 126.1MB (その他) (work/, gitignore)。
**全 import が shimx/curated で応答 (soft stub 発火 0)** — `soft_uniq=0`。

## 2. boot 連鎖 実測 (plain variant, closure 2 + switch harvest)

| 項目 | FLE-2 | FLE-3 | FLE-4 | **FLE-5** |
|---|---|---|---|---|
| unit 進行 | 40 dispatch / 39 完走 | 209 dispatch / 208 完走 | 209 / 208 | **209 / 208 (横ばい)** |
| 停止原因 | unlifted 0x527b5b | oob @ `f_816e80` | unlifted `0x6a7b70` | **unlifted `0x6a7b70` (真因は §3-5)** |
| 関数数 | 29,420 | 29,902 | 29,902 | **29,907** |
| unlifted callees | 1,678 | 1,684 | 1,684 | **1,681** |
| roots (entries) | 20,899 | 21,307 | 21,307 | **21,309** |
| GetMem / FreeMem | 662 / 209 | 1,886 / 776 | 1,890 / 776 | 1,890 / 776 |
| import 数 | 680 | 680 | 680 | 680 |

unit 進行の推移 (FLE-3 中の実測): 40 (FLE-2 末) → **43** (0x403579/582/58b jump table root 化)
→ **93** (0x433051/075/07e/087 系) → **111** (0x527592/59b/5a4/589 系 + closure) →
**126** (0x5274c0 + `cs_null_ok`) → **197** (0x642e* 20-entry table) → **209** (0x707000 + harvest 32 化)。

## 3. unit#17 停止原因の特定 (本 round の主成果)

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

## 4. survey (942 unit 隔離) — baseline との unit 単位照合

boot 1 回実行後、同一インスタンス上で unit を 1 本ずつ `fle_run` (新 stack) で隔離実行して分類。
baseline = `tools/m11/work/shimx_link/baseline/m11_boot.survey.json`。照合は `gen_verdict.py`。
**closure 2 lift + switch harvest (29,902 関数) で 942/942 完走**。

| 分類 | 前ラウンド (f555629) | FLE-2 | **FLE-3** | baseline (m11 sx 純リンク) |
|---|--:|--:|--:|--:|
| ok | 808 | 859 | **888** | 800 |
| oob | 66 | 9 | **2** | 50 |
| halt0 (raise 0xEEDFADE) | 9 | 0 | **0** | 44 |
| unlifted | 12 | 22 | **5** | — |
| trap | — | 5 | **0** | — |
| empty | 46 | 46 | **46** | closure外 46 (同一 46 unit) |
| noproc (i=941) | 1 | 1 | 1 | 1 |
| abort | 0 | 0 | 0 | 1 (unit#115 EnterCriticalSection) |
| **非 ok 合計 (empty/noproc 除く)** | **88** | **36** | **7** | **95** |

outcome (`gen_verdict.py`): **equal 800 / native_fault 92 / diff 49 / both_fault 1** (FLE-5 末)
(FLE-2: equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4)。
native_fault 89 = 「baseline は fault / x64c は ok」= x64c 優位の unit 数。

### 4-1. variant 対照 (`boot_e2e.sh` が `results/boot_summary_*.json` に出力)

| variant | link | boot 到達 | 所見 |
|---|---|---|---|
| plain | mismatch 0 / undef 0 / dup 0 | **209 dispatch** / oob (`f_816e80`) | 本命 |
| strict | 同上 | **93 dispatch / soft** | unit 93 の未実装 import で fail-fast。FLE-2 では plain と同一だったが、unit が伸びたことで**初の soft 発火**を検出 |
| nosx | 同上 (**FLE-2 で初 link 成功**) | **unit 0 で exit** (`Runtime error 226`) | shimx 無しでは CRT/序数系が機能せず boot 不可 |
| chk | 同上 | **209 dispatch / abort** | **`FLE_CHK` の住所ガードが unit#209 の OOB を捕捉** (下記 4-3)。診断 variant として本領発揮 |
| trace | 同上 | 209 dispatch / oob | plain と同一 |

**`-DFLEBOOT_NOSX=0` は `#ifdef` では真になる**ため `#if FLEBOOT_NOSX` に修正
(FLE-3 で実測: chk が nosx パスに入り shimx wiring が落ちていた)。

### 4-2. verdict 混在採点 (`gen_mixed.py`)

混在 JSONL (`work/boot/verdict_mixed.jsonl`, gitignore) = 関数級 `tools/liftdiff/work/flelift/batch_closure.jsonl`
(7,421 行, target=flelift) + unit 級 `boot/results/verdict_boot.jsonl` (943 行, target=flelift-boot)。
`function.va` が同じ PE VA 空間 (恒等写像) なので `tools/liftdiff/liftdiff.py summary` が
そのまま混在集計できる:

```
関数数 8364: 一致 4943 / 不一致 776 / 実行不能 2645   (FLE-5 末)
  unlifted_callee  主因 379   <- 関数級 (closure 残り)
  x-route_diff     主因 142   <- unit 級 (native baseline が fault / x64c が ok = x64c 優位)
  callee_divergence 主因 119
  callsite_arg_drop 主因 66
  ...
```

**`x-route_diff` が native_fault 92 の内訳** (FLE-4 末は 89) で、unit 級の差分として
liftdiff の summary に混在する。`native_fault` = 92 は **x64c が ok / native 側が fault**
なので x64c 優位の証拠で、CAB-232/233 の本格採点にそのまま接続できる。

### 4-4. survey 非 ok の内訳と FLE-5 での解消

`boot/results/survey.json` の `details` = 非 ok unit の全明細。FLE-5 の変更前後:

| unit | FLE-4 末 (7 件) | target VA | FLE-5 末 | 備考 |
|---|---|---|---|---|
| 280 | oob | — | **unlifted `0x6a7b70`** | boot_roots 3 件追加で oob 解消 |
| 296 | unlifted | 0x477e73 | **ok** | root 化 (.pdata 開始点) |
| 659 | oob | — | **unlifted `0x6a7b70`** | 同上 |
| 666 | unlifted | 0xd122e0 | **ok** | root 化 |
| 830 | unlifted | 0x8dfff0 | **ok** | root 化 (3 unit が同一 target) |
| 895 | unlifted | 0x8dfff0 | **ok** | 同上 |
| 898 | unlifted | 0x8dfff0 | **ok** | 同上 |

FLE-5 末の残 3 件は `unlifted 280 / 659` (`0x6a7b70`, blocklist 対象) と `unlifted 895`
(`0x976da0`, 新たに露出)。
**手段: 実行時 unlifted target を boot_roots.json に追加 → 再 lift**。ただし
`FLE_ROOT_BLOCKLIST` に載る address は root 化すると survey が破裂するため除外する。

## 5. 未解決・限界 (実測ベース)

1. **unit#209 の次の blocker は `unlifted 0x6a7b70`** (fill コールバック、§3-4)。
   root 化しても `f_6c7900` の fill ループが暴走 → ExitProcess → **survey が成立しない**
   ため `FLE_ROOT_BLOCKLIST` (既定 `0x6a7b70`) で自動累積から除外している。
   真因は §3-5 の通り **`f_653f40` が `f_53c5e0` 側の VCL リソース読み出し失敗で
   早期 return し、fill コールバック `0x15F34A0` を登録できない**こと。
2. **unit 進行 209 で横ばい**。前ラウンド目標の 250+ には未達。
   次の一手は §3-5 の `f_43c5e0` / `f_414ec0` が out = 0 を返す理由の特定
   (VCL リーダのクラス解決 or リソース未検出)。
3. **残 survey 非 ok 3** = unit 280 / 659 (`0x6a7b70`, blocklist 対象) + unit 895
   (`0x976da0`、未調査)。`0x976da0` は次の調査対象。
3. **VMT slot の自動 root 化 (RTTI/COL walk) は非適用**: 対象 0x6a7b70 は `.pdata` 整齊の
   実関数だが **image 内のあらゆるセクションに qword 参照を持たない** (実行時構築)。
   `.text` 内の連続 .text 参照 (VMT メソッド配列) の scan も実装したが拾えず、
   boot_roots.json への実行時累積が有効な手段と確認。
4. **chk variant のビルド**: `fle_chk` は `fle_cpu.c` の `A_()` マクロから呼ばれるため
   `fle_cpu.c` も `-DFLE_CHK` が必要 (boot_e2e.sh / build.sh で修正済み)。
5. `shimx_set_cs_null_ok(1)` の副作用: lock 依存 unit の survey 判定が実機とずれる可能性
   (CRITICAL_SECTION が no-op になるため)。実測 survey は FLE-3 末と同一値。

## 6. CAB-129/231 (RetDec route 修正) の x64c での要否

**m11 の unit#18 OOB の直接原因 (0x188B record の alloca 縮退) は x64c に構造的に存在しない。**
x64c は `rep stosq` を正しく展開し定数折畳みを持たないため 8B alloca への潰れが発生し得ない。
CAB-129 / CAB-231 の適用は x64c route では不要。D7/D10/D11 も x64c 非依存。

## 7. 引継ぎ (次ラウンド)

1. **最優先: `f_43c5e0` / `f_414ec0` が out = 0 を返す理由の特定** (§3-5)。
   VCL リーダのクラス解決 or リソース未検出のいずれか。ここが外れれば
   `f_653f40` がコールバック `0x15F34A0` を登録し、unit 進行が 209 を超える。
2. **`boot/dbg_lift.py --at 0x...` を常用** — guest VA を直接指定して lift C に
   トレースを埋め込める。FLE-4 の `__LINE__` 逆引きより汎用的。
3. **`FLE_ROOT_BLOCKLIST` を尊重** — `0x6a7b70` は root 化すると survey が破裂する。
   自動累積で再投入されても除外される。
4. **verdict 混在** (`gen_mixed.py`) — unit 級 `x-route_diff 142` / `native_fault 92` を
   CAB-232/233 の本格採点に接続 (両 target は同一 PE VA 空間)。
5. **残 survey 非 ok 3** — unit 280 / 659 (`0x6a7b70`, blocklist) + unit 895 (`0x976da0` 未調査)。

## 8. 再現

```sh
bash tools/flelift/boot/boot_e2e.sh          # 全 variant + 実行 (既定 closure 2)
FLE_LIFT_CLOSURE=0 bash tools/flelift/boot/boot_e2e.sh   # 旧 closure 0
bash tools/flelift/boot/boot_e2e.sh --fast   # lift 済なら skip
bash tools/flelift/boot/survey_drive.sh      # survey 942 (セグメント + 再開)
python3 tools/flelift/boot/merge_survey.py   # survey 統合
python3 tools/flelift/boot/gen_verdict.py    # baseline 突合 → verdict_boot.jsonl
python3 tools/flelift/boot/gen_mixed.py      # 関数級 + unit 級の混在採点 → work/boot/verdict_mixed.jsonl
node tools/flelift/boot/dbg_u18.mjs <boot.cjs>   # 停止点の guest stack 復元
# FLE-5 診断: 任意 guest VA を lift C に埋め込んで実測 (dbg variant link で実行)
python3 tools/flelift/boot/dbg_lift.py --src work/boot/lift/fle_lifted.c     --out work/boot/dbgout/fle_lifted_dbg.c --at 0x6c7610,f_653f40
bash tools/flelift/fle_e2e.sh                # 親チケットの回帰 (PASS)
```
前提: tools/flelift/fle_lift.sh と同一 (python3 capstone/pefile, emsdk 6.0.12, node)。
PE = block00031_PE.bin。生成物は work/boot/ (gitignore)。20MB 超 blob は git に入れない。
