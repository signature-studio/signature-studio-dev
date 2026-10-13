# KH-11b (#249) — snap-in ブラウザ分類 0x180ef7fc0 の lift と EditorModel ctor 47 vs 46 の同定

- 担当 dir: `tools/targets/kilohearts/license/` (`KH11_REPORT.md` は CAB-247 の KH-11 で別物。本報告は issue #249 = `KH249_REPORT.md`)
- 1 コマンド再現: `bash tools/targets/kilohearts/license/run_all.sh` ([4b] 節が本チケット分。初回のみ xref 全走査 ≈ 80 s)
- 素材: `plugins-kilohearts` (Windows installer → `tools/targets/kilohearts/work/winpkg/`)・`toolchain-retdec`・`toolchain-emsdk`
- 既知類型との関係 (規則 44): 本チケットで新規欠陥類型は検出せず。lift 済み範囲の callee 脱落は DEFECTS.md D15 (icall) の既存 pass で 3 サイト復元済み

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 完了条件 2: 47 vs 46 の差 1 製品 | **「差 1 製品」は製品ではない**。47 ctor 呼出元の RTTI を全数解決: **製品 EditorModel 45 + `HostProxyEditorModel` (0x180007a40) + `SnapinGroupEditorModel` (0x180267c50) = 47**。product_index.json の 46 = 45 snapin/plugin + `core` (HeartCore 自体、EditorModel なし)。45 製品の id と ctor は最近傍ヒューリスティクスで 1:1 (§2)。KH9 §5-5 の「group/host 系の製品追加」推定は **「host proxy と snapin group の 2 つの非製品 EditorModel」** に確定 (47 − 46 = 非製品 2 − core 1) |
| 完了条件 1: ブラウザ分類の lift IR | `0x180ef7fc0` (2,549 B) を含む module F (6 関数) が **emcc を通過** (wasm 47,604 B・undefined import 0・[icall] 3 サイト復元)。入口を node 実行すると最初の未 lift callee `0x180112a30` の fail-fast に到達 (= IR は入口から実行可能。残りの STL/map/shared_ptr 群は未 lift) |
| 分類結果 (stub 定数 9 入力) | lift した実 IR の thunk A/C を status 0..40 で実行しゲート真理値表を再構成: **status 9 → flag 無関係に「一覧に載る・unlocked」**。unlocked 集合 = {5,7,8,9,26}。status 25 は flag=0 で非表示 / flag=1 で locked 表示 (§3) |
| カテゴリ (Essential/Premium/Hosts/Groups) | 無償系 id 列 `egskocskpsdktafkqepkswsktfsk` は **PE から機械読出し**し、7 dword = {ksge,ksco,kdsp,kfat,kpeq,ksws,ksft} (「推定」だった KH9 の解読を**確定**)。product_index の 45 製品中 **Premium 7 / Essential 38**。`grup` → Groups、entry+0x22 が真なら Hosts (§4)。**注: 分類式は機械語読解の node 再実装で lift IR では未検証。カテゴリ名と製品の無償/有償の対応も未確認** (§4 注・§6.2) |
| 0x180d5f190 | **`UISnapinLaneModel` (RTTI) の vtable slot 23** (vtable 0x181a37e78 + 0xb8)。`kmic`(Snap Heap)/`kmup`(Multipass)/`grup` の id だけを対象に thunk A∧¬thunk C をゲートして lane 一覧を作る関数 (§5) |
| 0x180d52990 | 3 呼出元 (0x18055c060 / 0x1805c6a50 = Phase Plant / 0x1807e3420) はいずれも EditorModel 派生 ctor ではない。closure は §5 の範囲で確認 (関数本体の lift は未実施) |

## 1. 実装

| ファイル | 内容 |
|---|---|
| `lic_config.json` modules.F | ブラウザ分類 0x180ef7fc0 + 表引き 0x18004c780 + 0x180045130 + thunk A/C + getStatus(stub) の 6 関数 lift 設定 |
| `lic_build.py` | `--module F` 追加。`KH_EM_CACHE` で emscripten cache を差替え可能に (Actions runner の `[EMSDK]` 配下の cache は読取専用で `emcc` が filelock の PermissionError で落ちるため) |
| `kh249_check.mjs` | module F の node 実行検証 (17 項目 = 実 IR 実行 (getStatus/thunk A・C/ゲート/入口 fail-fast) 7 + 分類式の再実装 4 + 式定数の命令バイト照合 1 + 分類式の負律対照 5) |
| `scripts/kh249_ctor_ids.py` | 47 ctor 呼出元の vtable → RTTI(COL→TypeDescriptor) 同定。`work/ctors47.json` も再生成 (旧版は手元 work にしか無く clean HEAD で em_check が再現不能だった = KH11_REPORT §6 の既知未解決を解消) |
| `scripts/kh249_id_scan.py` | .text 全域の製品 id (FourCC) imm32 を持つ関数列挙 + 47 ctor ↔ 製品 id の最近傍対応 (重複・未使用の算出、§2) |
| `scripts/pe_dis.py` | 解析 PE のパスを `KH_CORE` 環境変数 / repo 相対既定に変更 (旧: 作者環境の絶対パス固定) |

## 2. 47 vs 46 の同定 (完了条件 2)

- 入力: `xrefscan.py 180051af0` = EditorModel ctor 直接呼出 **47 サイト・47 関数** (KH9 §4.3 と一致)
- 各呼出元関数の先頭 24 命令内 `lea rsi,[rip+X]` (派生 vtable) → `[vtable-8]` COL → TypeDescriptor 名を読む (`kh249_ctor_ids.py`、47/47 解決)
- 結果: **45 = 製品**、**2 = 非製品** (`HostProxyEditorModel@hostproxy` 0x180007a40 / `SnapinGroupEditorModel@snapingroup` 0x180267c50)
- 製品 45 の id との対応 (ヒューリスティクス): 各製品に id (FourCC) を imm32 で持つ関数が 4 本ずつあり (`kh249_id_scan.py`)、ctor は id を持たない。ctor に最近傍 (アドレス) の id 関数で対応づける手順は `kh249_id_scan.py` が実装している (`|関数 VA − ctor VA|` 最小の id 関数。47 ctor 全てに適用)。実測 (§6.3 の run): 重複 id は 3 件 = `kmic` {HostProxy, Micropass}・`kmup` {HostProxy, Multipass}・`ksbc` {SnapinGroup, Bitcrush} で、**3 件とも非製品 ctor (HostProxy / SnapinGroup) が製品 ctor と同じ id 関数に寄っただけ**。非製品 2 を除いた製品 ctor 45 は **重複 0・未使用 id 0** (45 製品 id と 1:1)
- `product_index.json` 46 = `plugins` 配列 46 要素 = 45 製品 + `core` (HeartCore, formats=['heartcore']・dependencies 無し)。`core` は EditorModel を持たない
- **47 = 45 + 2、46 = 45 + 1 (core)**。差 1 は「製品 1 つ」ではなく、非製品 EditorModel 2 (host proxy / snapin group) と core 1 の差

## 3. ブラウザ分類ゲート (完了条件 1・実行検証)

関数 0x180ef7fc0 のエントリ採否 (機械語 0x180ef8710〜0x180ef87c8):
`status = getStatus(...)` → `A(status)` (0x1800b4ac0・許可集合) が偽なら不採用候補、真なら `r13 = !C(status)` (0x1800b4ae0 = status==25)。`r13 != 0` で unlocked 登録、`r13 == 0` のときグローバル flag `[0x182358298]` が非 0 なら locked 登録・0 なら非表示。なお id==`grup` のエントリは別経路 (0x180ef862a): `r13 = [mgr+0xed9]` (byte) を使い、この表の対象外 (§6.2)。

`kh249_check.mjs` が lift 済みの実 IR (thunk A/C) を status 0..40 で実行し真理値表を再構成:

| flag | 結果 |
|---|---|
| 0 | listed/unlocked = {5,7,8,9,26}、hidden = それ以外 36 値 (25 を含む) |
| 1 | listed/unlocked = {5,7,8,9,26}、listed/locked = それ以外 36 値 |

→ **getStatus ≡ 9 (stub) では flag 無関係に全エントリが listed/unlocked**。stub が「許可側に固定」されていることの UI 分類レベルの裏取り。

## 4. カテゴリ分類

名前表 (逆アセンブルから UTF-16 文字列を読出し): 0 `Essential Effects` (0x1823a34e0) / 1 `Premium Effects` (0x1823a3504) / 2 `Effects Hosts` (0x1823a3524) / 3 `Groups` (0x181e79826)。

分類式 (0x180ef82aa〜0x180ef830b の機械語読解): `id=='grup' → 3 / entry+0x22 が真 → 2 / id ∈ 無償系 7 id リスト → 1 / それ以外 → 0`。リスト = `egskocskpsdktafkqepkswsktfsk` (0x180ef825b 付近の 2 つの 16 B 定数 = 28 B 重畳)。PE から読出して dword 列に分解すると {ksge, ksco, kdsp, kfat, kpeq, ksws, ksft} と一致 (BE 並べ)。

`kh249_check.mjs` の独立再計算: product_index 45 製品 (core 除外) に適用 → **category 1 = {kdsp,kfat,kpeq,ksco,ksft,ksge,ksws} の 7、category 0 = 38**。

注: 「Essential/Premium」という名前はカテゴリ番号 1 の側が **無償系リスト** であり、命名と製品の無償/有償の対応は未確認 (表示名の意味は未検証。KH9 の「無償系」は id 列の由来からの推定のまま)。

## 5. 0x180d5f190 周辺の closure

- **0x180d5f190** は直接 call 0・データ参照 (rip 相対) 0。.rdata 全走査で **vtable 0x181a37e78 の slot 23** に格納 (`.?AVUISnapinLaneModel@@`)。
- 処理 (機械語 0x180d5f27d〜0x180d5f2f6): ブラウザと同じ表引き (0x18004c780 で id → エントリ、0x180045130 でエントリ述語) の結果 `al` で分岐する。`al` 真なら `grup` 以外を通し、`al` 偽なら `kmic` (Snap Heap) / `kmup` (Multipass) だけを通す。通ったエントリは `getStatus(mgr, id, 3)` を thunk A ∧ ¬thunk C でゲートして lane 一覧に追加。→ **status 9 ではゲートは常に通る** (0x180045130 の述語の意味は未同定)。
- ブラウザ 0x180ef7fc0 は 0x180ef7cc0 から 1 サイト呼出、0x180d5e820 (Import メニュー) は 0x180d5dbe0 から 3 サイト。いずれも thunk A/C ゲート (KH9 §4.3 と同一結論)。
- 0x180d52990: 呼出元 3 (0x18055c060 / 0x1805c6a50 / 0x1807e3420)。いずれも ctor 本体の RTTI を持たず EditorModel 派生 ctor ではない。lift は未実施。

## 6. 検証 (規則 36〜41・45)

実行はコミット済み HEAD (`ff9827a`) で行い §6.3 に記録する (作業ツリー変更なし)。

### 6.1 負律対照 (規則 41・実測)
| # | 操作 | 結果 |
|---|---|---|
| 1 | module F の stub を getStatus=25 / thunk A=常時 0 に差替えて再 build → `kh249_check.mjs` | **ok=7 ng=4** (getStatus≠9 / thunk A 許可集合 / status 9 listed/unlocked / unlocked 集合 の 4 項目が NG)。lic_config.json 復元後 **ok=11 ng=0** (いずれも [3] 節追加前の 11 項目時点) |
| 3 | 分類式 ([3]) の検査を壊す: (a) 命令バイト読出し位置を 1 byte ずらす (b) free list を先頭 1 dword 欠落 (c) in/out カテゴリ番号の入替 | (a) **ok=16 ng=1** (命令バイト照合) / (b) **ok=14 ng=3** (list size・category1 ids・category0 count) / (c) **ok=14 ng=3** (category1 ids・category0 count・入替対照)。無改変 **ok=17 ng=0**。式の変異 5 種 ([3b]) は無改変の分類分布と全て異なる |
| 2 | `compare.mjs` の `bitsToF32` 未定義 (本チケットで発見した既存欠陥) | matrix/clipper の比較が実行されず `trials_ok=null` のまま `run_all.sh` が exit=0 (偽陽性)。→ §8 |

### 6.2 範囲外 (規則 40)
- ブラウザ関数本体は **入口〜最初の未 lift callee まで**。std::map/string/vector/shared_ptr 等 41 個の callee (kh_lower の `unlifted callees` 41 件) は未 lift で、リスト構築・描画へ進む経路の bit 一致は未検証。
- 分類式・ゲート式は機械語読解の node 再実装 (lift IR のブラウザ本体をカテゴリまで流した結果ではない)。thunk A/C・getStatus は実 IR 実行。分類式は「lift IR では未検証」。`kh249_check.mjs` [3a] で式定数を命令バイトと照合し、[3b] で式を 5 通り壊して結果が変わることを確認するが、これは式の再実装が PE の読解と整合する・検査が自明でないことの確認までで、lift IR の分類結果の検証ではない。lift IR で検証するには未 lift callee (41 件) の shim が要る。
- `grup` エントリのゲート (`[mgr+0xed9]`) は未検証 (§3 の表は非 grup のみ)。
- 製品 id ↔ ctor の 1:1 対応は「id を持つ関数の最近傍」ヒューリスティクス (§2)。RTTI クラス名の 47/47 同定とは独立で、製品名の対応は一部 (`Matrix`=kscm 等) クラス名からの読み替え。
- native oracle (ctx-fuzz) との bit 突合は未実施。

### 6.3 実測 (コミット済み HEAD `ff9827a` で `bash run_all.sh` を単発実行)
| 項目 | 結果 |
|---|---|
| 所要時間 | **49 s** (xref 走査キャッシュ・RetDec stage-0 キャッシュ有り。実行環境 nproc=4) |
| load average (1/5/15 分) | 開始 0.17 / 0.44 / 0.33 → 終了 0.64 / 0.52 / 0.36 |
| exit | **0** |
| lic_check (module A/B) | ok=70 |
| snapin 6 種 base/lic | **200/200 × 12 系** bit-exact (matrix 1149 / gain 999 / haas 1100 / clipper 1100 / gate 999 / quickeq 999 call。全 call 一致) |
| em / empoll (module E) | 200/200 (700/700 call) / 1000/1000 (10,000/10,000 call) bit-exact |
| em_check | ok=52 ng=0 |
| emfire (情報提供・既知未解決) | 0/200 (ctor/register 400/600 call 一致、fire 0/200)。KH11_REPORT §2 と同じ。run_all.sh の exit には影響しない |
| module F (本チケット) | 6 関数 lift・wasm 47,604 B・undefined import 0・`kh249_check` ok=11 ng=0 |
| ctor 同定 | callers=47 rtti_resolved=47 |

初回実行 (HEAD `da081d5`) は `run_all.sh` が exit=0 だったが matrix/clipper が `null/null` だった (§8)。上表は修正後 HEAD の再実行値。

## 7. 環境差 (Actions runner)
- `[EMSDK]/upstream/emscripten/cache` が読取専用で `emcc` が filelock の PermissionError (`js_output.lock`) で失敗 → `KH_EM_CACHE=<書込可 dir>` を指定 (`lic_build.py`)。`emsdk_env.sh` が `EM_CACHE` を unset するため source 後に再設定している。
- Python は `uv venv work/venv` に `pefile capstone numpy` を入れて PATH 先頭に置く (system python は PEP 668 で pip 不可)。
- `plugins-kilohearts` は Windows zip だけ展開 (`work/win` → `work/blobs/windows.zip/*` → `work/winpkg`)。macOS dmg / llvm-lipo は本チケットでは不要。

## 8. 既存欠陥の発見と修正 (スコープ内)
- `harness/compare.mjs` (license 側コピー) に `bitsToF32/bitsToF64/f32bits` の定義が無く、float/double 引数を持つ関数 (matrix 0x1804f4180 / clipper) の比較が ReferenceError で落ちた。compare.json が生成されず `lic_build.py` は `trials_ok=None` を出すのみで、`run_all.sh` はそれを失敗扱いにしなかった (= **「200/200」未達のまま exit=0**)。`snapins/harness/compare.mjs` の同定義を移植して修正し、`run_all.sh [5]` で `trials_ok !== trials` を FAIL 化 (exit 1) した。この repo HEAD の license/harness 単体では matrix/clipper の比較は再現していなかった (KH-9 / KH-11 REPORT の記載値と食い違う経緯は未調査)。修正後の再実行で 12 系すべて 200/200 を確認 (§6.3)。

## 9. 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ブラウザ本体の STL/shared_ptr 群 (41 callee) 未 lift、native oracle 突合なし | リスト構築〜描画の bit 一致未証明 | #249 (本 issue) 継続 / 親 #15 |
| entry+0x22 の意味 (Hosts 判定) 未同定 | `Effects Hosts` が実際にどのエントリかは不明 | #249 継続 |
| カテゴリ名と無償/有償の対応未確認 | 「無償系」解釈は推定 | #249 継続 |
| 0x180d52990 の本体 lift 未実施 | Phase Plant 等 3 呼出元の closure は呼出元同定まで | #249 継続 |
