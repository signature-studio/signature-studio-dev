# KH-11b (#249) — snap-in ブラウザ分類 0x180ef7fc0 の lift と EditorModel ctor 47 vs 46 の同定

- 担当 dir: `tools/targets/kilohearts/license/` (`KH11_REPORT.md` は CAB-247 の KH-11 で別物。本報告は issue #249 = `KH249_REPORT.md`)
- 1 コマンド再現: `bash tools/targets/kilohearts/license/run_all.sh` ([4b] 節が本チケット分。初回のみ xref 全走査 ≈ 80 s)
- 素材: `plugins-kilohearts` (Windows installer → `tools/targets/kilohearts/work/winpkg/`)・`toolchain-retdec`・`toolchain-emsdk`
- 既知類型との関係 (規則 44): 本チケットで新規欠陥類型は検出せず。lift 済み範囲の callee 脱落は DEFECTS.md D15 (icall) の既存 pass で 3 サイト復元済み

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 完了条件 2: 47 vs 46 の差 1 製品 | **「差 1 製品」は製品ではない**。47 ctor 呼出元の RTTI を全数解決: **製品 EditorModel 45 + `HostProxyEditorModel` (0x180007a40) + `SnapinGroupEditorModel` (0x180267c50) = 47**。product_index.json の 46 = 45 snapin/plugin + `core` (HeartCore 自体、EditorModel なし)。45 製品の id は ctor と 1:1 (§2)。KH9 §5-5 の「group/host 系の製品追加」推定は **「host proxy と snapin group の 2 つの非製品 EditorModel」** に確定 (差は +1 ではなく、非製品 2 − core 1 = +1) |
| 完了条件 1: ブラウザ分類の lift IR | `0x180ef7fc0` (2,549 B) を含む module F (6 関数) が **emcc を通過** (wasm 47,604 B・undefined import 0・[icall] 3 サイト復元)。入口を node 実行すると最初の未 lift callee `0x180112a30` の fail-fast に到達 (= IR は入口から実行可能。残りの STL/map/shared_ptr 群は未 lift) |
| 分類結果 (stub 定数 9 入力) | lift した実 IR の thunk A/C を status 0..40 で実行しゲート真理値表を再構成: **status 9 → flag 無関係に「一覧に載る・unlocked」**。unlocked 集合 = {5,7,8,9,26}。status 25 は flag=0 で非表示 / flag=1 で locked 表示 (§3) |
| カテゴリ (Essential/Premium/Hosts/Groups) | 無償系 id 列 `egskocskpsdktafkqepkswsktfsk` は **PE から機械読出し**し、7 dword = {ksge,ksco,kdsp,kfat,kpeq,ksws,ksft} (「推定」だった KH9 の解読を**確定**)。product_index の 45 製品中 **Premium 7 / Essential 38**。`grup` → Groups、entry+0x22 が真なら Hosts (§4) |
| 0x180d5f190 | **`UISnapinLaneModel` (RTTI) の vtable slot 23** (vtable 0x181a37e78 + 0xb8)。`kmic`(Snap Heap)/`kmup`(Multipass)/`grup` の id だけを対象に thunk A∧¬thunk C をゲートして lane 一覧を作る関数 (§5) |
| 0x180d52990 | 3 呼出元 (0x18055c060 / 0x1805c6a50 = Phase Plant / 0x1807e3420) はいずれも EditorModel 派生 ctor ではない。closure は §5 の範囲で確認 (関数本体の lift は未実施) |

## 1. 実装

| ファイル | 内容 |
|---|---|
| `lic_config.json` modules.F | ブラウザ分類 0x180ef7fc0 + 表引き 0x18004c780 + 0x180045130 + thunk A/C + getStatus(stub) の 6 関数 lift 設定 |
| `lic_build.py` | `--module F` 追加。`KH_EM_CACHE` で emscripten cache を差替え可能に (Actions runner の /opt/emsdk/.../cache は読取専用で `emcc` が filelock の PermissionError で落ちるため) |
| `kh249_check.mjs` | module F の node 実行検証 (11 項目) |
| `scripts/kh249_ctor_ids.py` | 47 ctor 呼出元の vtable → RTTI(COL→TypeDescriptor) 同定。`work/ctors47.json` も再生成 (旧版は手元 work にしか無く clean HEAD で em_check が再現不能だった = KH11_REPORT §6 の既知未解決を解消) |
| `scripts/kh249_id_scan.py` | .text 全域の製品 id (FourCC) imm32 を持つ関数列挙 |
| `scripts/pe_dis.py` | 解析 PE のパスを `KH_CORE` 環境変数 / repo 相対既定に変更 (旧: 作者環境の絶対パス固定) |

## 2. 47 vs 46 の同定 (完了条件 2)

- 入力: `xrefscan.py 180051af0` = EditorModel ctor 直接呼出 **47 サイト・47 関数** (KH9 §4.3 と一致)
- 各呼出元関数の先頭 24 命令内 `lea rsi,[rip+X]` (派生 vtable) → `[vtable-8]` COL → TypeDescriptor 名を読む (`kh249_ctor_ids.py`、47/47 解決)
- 結果: **45 = 製品**、**2 = 非製品** (`HostProxyEditorModel@hostproxy` 0x180007a40 / `SnapinGroupEditorModel@snapingroup` 0x180267c50)
- 製品 45 の id との対応: 各製品に id (FourCC) を imm32 で持つ関数が 4 本ずつ (`kh249_id_scan.py`)。ctor に最近傍の id 関数で 45 製品 id と対応づけると、`ksbc` への重複 (3 件) は HostProxy / SnapinGroup / Bitcrush で、前 2 者は非製品のため最近傍が偶然 `ksbc` 側に寄っただけ (ctor 自体は id を持たない)。他 44 製品は重複なし・未使用 id なし
- `product_index.json` 46 = `plugins` 配列 46 要素 = 45 製品 + `core` (HeartCore, formats=['heartcore']・dependencies 無し)。`core` は EditorModel を持たない
- **47 = 45 + 2、46 = 45 + 1 (core)**。差 1 は「製品 1 つ」ではなく、非製品 EditorModel 2 (host proxy / snapin group) と core 1 の差

## 3. ブラウザ分類ゲート (完了条件 1・実行検証)

関数 0x180ef7fc0 のエントリ採否 (機械語 0x180ef8710〜0x180ef87c8):
`status = getStatus(...)` → `A(status)` (0x1800b4ac0・許可集合) が偽なら不採用候補、真なら `r13 = !C(status)` (0x1800b4ae0 = status==25)。`r13 != 0` で unlocked 登録、`r13 == 0` のときグローバル flag `[0x182358298]` が非 0 なら locked 登録・0 なら非表示。

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
- 処理: ブラウザと同じ表引き (0x18004c780 → 0x180045130) で各エントリを引き、`grup` なら除外、それ以外は `kmic` (Snap Heap) / `kmup` (Multipass) のみ通し、`getStatus(mgr, id, 3)` を thunk A ∧ ¬thunk C でゲートして lane 一覧に追加。→ **status 9 では常に追加される**。
- ブラウザ 0x180ef7fc0 は 0x180ef7cc0 から 1 サイト呼出、0x180d5e820 (Import メニュー) は 0x180d5dbe0 から 3 サイト。いずれも thunk A/C ゲート (KH9 §4.3 と同一結論)。
- 0x180d52990: 呼出元 3 (0x18055c060 / 0x1805c6a50 / 0x1807e3420)。いずれも ctor 本体の RTTI を持たず EditorModel 派生 ctor ではない。lift は未実施。

## 6. 検証 (規則 36〜41・45)

実行は clean HEAD で行った結果を §6.3 に記録する (作業ツリー変更なし)。

### 6.1 負律対照 (規則 41)
| # | 操作 | 結果 |
|---|---|---|
| 1 | getStatus stub 値を 9 → 25 に変える想定 | `kh249_check.mjs` のゲート式で status 25 は flag=0 hidden / flag=1 locked (実 IR の thunk C が 25 のみ真であることを実行で確認済み) |
| 2 | 入口実行の期待 callee を変える | 期待 0x180112a30 以外なら NG (検査が通過のみを許さないことを確認) |

### 6.2 範囲外 (規則 40)
- ブラウザ関数本体は **入口〜最初の未 lift callee まで**。std::map/string/vector/shared_ptr 等 40 個の callee (`unlifted callees` 40 件) は未 lift で、リスト構築・描画へ進む経路の bit 一致は未検証。
- 分類式・ゲート式は機械語読解の node 再実装 (lift IR のブラウザ本体をカテゴリまで流した結果ではない)。thunk A/C・getStatus は実 IR 実行。
- native oracle (ctx-fuzz) との bit 突合は未実施。

### 6.3 実測 (コミット済み HEAD で再現)
§7 に追記。

## 7. 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ブラウザ本体の STL/shared_ptr 群 (40 callee) 未 lift、native oracle 突合なし | リスト構築〜描画の bit 一致未証明 | #249 (本 issue) 継続 / 親 #15 |
| entry+0x22 の意味 (Hosts 判定) 未同定 | `Effects Hosts` が実際にどのエントリかは不明 | #249 継続 |
| カテゴリ名と無償/有償の対応未確認 | 「無償系」解釈は推定 | #249 継続 |
| 0x180d52990 の本体 lift 未実施 | Phase Plant 等 3 呼出元の closure は呼出元同定まで | #249 継続 |
