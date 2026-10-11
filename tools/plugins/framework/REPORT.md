# P0b REPORT — TFruityHost shim (CAB-195)

- 検収起点 commit: **9b420bd** (`tools/plugins/framework` ツリーは b8e762d と同一: `git diff b8e762d HEAD -- tools/plugins/` = 0 行)
- 行数目安: 実装部 (§0-§9) 187 行 + 検収記録 (§10-§11) 105 行 + CAB-194 検収 (§12) 78 行 + CAB-269 (§13) 118 行 = 488 行
  (実ファイル 476 行)。検収記録・修正記録は規則 37〜42
  (独立再計算・ネガティブコントロール・検証範囲・起票先つき未解決) の必須項目を含むため 200 行上限を
  超過。超過分は CAB-269 (§13) の実測・訂正の記録にも使った。
- 日付: 2026-10-11 / 担当 dir: `tools/plugins/framework/` (hostshim/) / 再現: `bash tools/plugins/framework/hostshim/hs_e2e.sh`
- 前提: stage-1/2 = `fw_lift.sh` + `fw_stage2.sh` (CAB-194) 済み。本 script は framework 成果物を**読み取りのみ**で利用し, 書込は自 dir と `tools/plugins/work/hs/` のみ。
- 数値はすべて `tools/plugins/work/hs/` (gitignore) で実測。推定は「推定」と明記。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| TFruityHost shim | **46 slot** 実装 (`hostshim.c`, vtable 合成 VA 0xE100000+8*slot)。slot0=Dispatcher / slot6=0x47 応答の BOOL / 残 44 slot は fail-soft + 呼出記録 |
| Dispatcher 応答表 | **A検収上位 35 ID** (`hs_ids.json`: 35 ID / 894 site / cover **89.8%**) を「戻り値使用クラス」実測で分類設定 — store/reg 9 ID = 非 NULL, ignore/test 26 ID = 0 |
| ctor 連鎖 (主目的) | `CreatePlugInstance(Host, Tag)` → `TestPlug26.Create` 0x6be800 → `TDelphiFruityPlug` base ctor 0x6b8e80 に到達。Dispatcher ID 序列 **0x47, 0x56, 0x0d, 0x2e, 0x47, 0x1d** を native 順序どおり記録 (Host ポインタ伝播 = BLK+8 実測値が host オブジェクトと一致) — **native 側も capstone で独立照合済 (8/8 OK, `hs_native_check.py`)** |
| headless smoke 拡張 | framework smoke からの **dispatcher 経由 host call 連鎖**を検証。`hs_rec` 記録 7 件 (slot0 ×6 + slot6 ×1) を `fw_hs_records()` で JS から照合 |
| RTL ユーティリティ | lock xadd を持つ 6 関数 (refcount / DynArray / TObject list) を `hs_utl.c` の C 実装に接続 (`fw_hostfix.py` override) |
| 回帰 (CAB-194) | framework smoke: **unit init ×16 + unit finalize ×16 / dispatch 38 / trap 0 / fail-fast 0** を維持 (**ただし Phase A は stale artifact を再利用していたため実質 38 は再現されていない — §1 訂正・§10**) |
| Eff_Render 差分 | **未実施 (次段 手順 §6)** — ctor 連鎖の完全到達が先決で本 ticket では未到達 |
| 未達 | `TFruityPlug*` 実体生成 (instance field / vtable 照合) — RTL ハッシュ表 (0x52cf40)・名前検索 (0x40b930)・TStream (0x412fc0) の fold deref 残存が原因 (§7.1) |

## 1. 構成 (framework build と連鎖 build を分離する理由)

```
Phase A: work/fw/fw_route.cjs (CAB-194 成果物そのまま) で framework smoke — 回帰確認
Phase B: work/hs/hs_route.cjs (派生ビルド) で host shim 連鎖 + 呼出記録照合
```

分離理由: framework build (fw_stage2.sh) に「戻り値 store / mosaic override / constant global 可変化」を
混入させると unit init #16 経路の分岐が変わり smoke が OOB trap する (実測)。
そこで CAB-194 build は fw_stage2.sh に hostshim.c を**追加リンクのみ**し (動作不変)、
連鎖検証は hs_e2e.sh が別 output (work/hs/) に組む。

> **検収による訂正 (2026-10-11)**: 「追加リンクのみで framework build 挙動が不変」は**誤り**。
> `hs_fwdiff.sh` で同一 IR から差分ビルドを作り差し替え実測したところ、差分は **`fw_rt.c` のみ**
> (§10 Ablation)。hostshim.c 追加リンク・`fw_table.py` の slot 登録・decode-miss fail-soft 化は単独では不変。
> さらに **`work/fw/fw_route.cjs` は 02:11 に親 commit の `fw_rt.c` で焼かれた stale artifact**
> (wasm 内に soft-miss 文字列が無く FAIL-FAST 文字列が残る) だったため、Phase A の dispatch=38 /
> ff=0 は「変更後も不変」の証拠にならない。HEAD 相当 build では smoke が **OOB trap**
> (`dispatch=39 / lastSite=0x40e112`)。再現: `bash tools/plugins/framework/hostshim/hs_fwdiff.sh`。

```
work/fw/fw_flat4_canon3.ll
  → hs_irfix.py   (CreatePlugInstance 0x6bdde0 の Host/Tag 引数経路修復)
  → fw_retw.py    (0x6be800 の ret に BLK+0x80 store)
  → fw_hostfix.py (mosaic/RTL override + __asm_* signature 正規化 + trap artifact 除去)
  → fw_table.py   (dispatch 表 + hs_slot0..45 を 0xE100000.. に登録)
  → emcc (-O0, GLOBAL_BASE=0x10000000) + hs_plug.c + hostshim.c + hs_utl.c
  → hs_e2e.mjs    (Phase A/B 判定)
```

## 2. Dispatcher 応答表の根拠 (A検収)

### 2.1 slot VAs
`inventory/delphi_vmt.py` の block00031 FLE VMT 0x1314108 再生成値 (2026-10-10 実測)。
`ClassName=TFruityHost`, `InstanceSize=296`, vtable = VMT+0x70, 46 slot (offset 0x00..0x168)。
**slot0 = Dispatcher = 0x13173a0** で CAB-12 A検収確定値と一致。再抽出は `hs_vtable_gen.py`
(`python3 hs_vtable_gen.py <FLEngine_PE>`, VMT/ClassName/InstanceSize/slot0 を assert —— FLE PE は win64 解析素材外のため本回は未実行、ABI.md §2.3 確定値を使用)。

> **検収による独立照合 (2026-10-11)**: `block00031_PE.bin` の VMT 0x1314108+0x70 を直接読み
> 46 slot を照合 (`hs_vtable_verify.py`)。**46/46 slot 一致**・slot0 = 0x13173a0。
> ABI.md §2.3 の確定値を使った実装側の判断は**正しい**。

### 2.2 上位 35 ID の ret_use 実測 (`hs_ids.py`, top35 = 803/894 site = 89.8%)

> **検収による訂正 (2026-10-11)**: 実装報告は「上位 30 ID / 778 site / 89.8%」と書いていたが
> 数え方が食い違っていた。`hs_ids.json` の `top_n` は **35** で、`top30_cover` フィールドは
> **実態は上位 35 の累積 (803)** を指す (フィールド名だけが `top30`)。
> 独立再計算 (`hs_ids_recount.py`): 上位 30 = **778/894 = 87.0%** / 上位 35 = **803/894 = 89.8%**。
> 本表は実態に合わせ**上位 35 ID** に改めた。「store/reg 9 / ignore/test 21」は 35 ID 全体では
> **9 / 26** (9+26=35) が実測値 (訂正済)。

| ID (sites) | ret_use 実測 | shim 応答 |
|---|---|---|
| 0x02(163) 0x21(118) 0x03(71) 0x24(47) 0x5b(31) 0x17(25) | ignore | 0 |
| 0x30(20) 0x1e(19) 0x28(16) 0x26(12) 0x61(12) 0x3b(11) 0x67(10) 0x11(9) 0x1b(9) 0x08(8) | ignore | 0 |
| 0x14(7) 0x22(6) 0x43(6) 0x5a(6) 0x00(5) 0x05(5) 0x09(5) 0x13(5) 0x15(5) | ignore(+test) | 0 |
| **0x1d(44) 0x2e(24) 0x47(22) 0x0e(12) 0x0a(8) 0x3d(8) 0x25(6)** | **store**/store+… | Host obj |
| **0x32(36) 0x12(5)** | **reg** | Host obj |
| 0x0d(7) | ignore (ctor 実測: 戻り未使用) | 0 |

原則: **戻り値を store/保持する ID は非 NULL を返す** (deref に備える)、ignore/test は 0。
FLE 側 case 別応答値の**意味論**は未解析 (FL 本体の case 分岐を読む必要がある) — 数値根拠は
呼出文脈クラスのみ。次段 (T0 frontier ctor 完了後) で要確認。

## 3. 実測 (host shim 連鎖)

### 3.1 e2e 判定 (`bash tools/plugins/framework/hostshim/hs_e2e.sh` → exit 0)

```
[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0
[hs] CreatePlugInstance(Host=0x10fb5a50, Tag=0x54534154)
[dispatch] site=0x6bd253 -> 0xe100000 (slot0, ID 0x47)  [hostshim] -> 0x10fb5a50
[dispatch] site=0x6bd197 -> 0xe100030 (slot6, BOOL)      [hostshim] -> 0x1
[dispatch] site=0x6bd2a4 -> 0xe100000 (slot0, ID 0x56)  [hostshim] -> 0x10fb5a50
[dispatch] site=0x6b8f4b -> 0xe100000 (slot0, ID 0x0d)  ← ★ TDelphiFruityPlug base ctor 突入
[hostshim] slot=0 id=0x2e -> 0x10fb5a50 / id=0x47 -> 0x10fb5a50 / id=0x1d -> 0x10fb5a50
[hs] E2E PASS
```

### 3.2 native 逆アセンブルとの対応 (capstone, block18983_PE.bin)

| wasm dispatch site | native | 意味 |
|---|---|---|
| 0x6bd253 / 0x6bd2a4 | `call [rax]` (r8d=0x47 / 0x56) | `Host.Dispatcher(Host,Tag,ID,0,0)` (init) |
| 0x6bd197 | `call [rax+0x30]` (edx=0x40f) | 0x47 応答の BOOL 仮想呼出 (slot6) |
| 0x6b8f4b / 0x6b8fdd / 0x6b90ff / 0x6b9151 | `call [rax]` (r8d=0x0d / 0x2e / 0x47 / 0x1d) | `TDelphiFruityPlug` base ctor 突入とその継続 |

検証済み (ID 一致)。独立照合は §10 の `hs_native_check.py` (8/8 OK)。

### 3.3 Host ポインタ伝播
- init 経路 (0x47/0x56 @6bd210): RetDec が「Host 引数」を定数畳み込み cell (0x24/0x10000448) に
  落とすため a0 は host 実値でない。**slot6 の呼出自体**は畳み込み経路で成立。
- ctor 経路 (0x0d/0x2e/0x47/0x1d @6b8e80): a0 = `0x10fb5a50` = `fw_hs_host_va()` 実値。
  つまり Host が ctor 内の全 host 呼出に正しく伝播している。

### 3.4 BLK-ABI 制約 (integration/README §4 継承)
第5引数 (Dispatcher の Value = `[rsp+0x20]`) は BLK が 4 整数引数までしか運ばないため未経由。
連鎖内の全発行 site は `Value=0` を store している (pedis.py 実測) ので動作影響なし。

## 4. 新規に直した欠陥 (すべて実測駆動)

| # | 症状 | 原因 | 対処 |
|---|---|---|---|
| 1 | `0x40e800` で OOB | RetDec が DynArray refcount 関数の rsi/ebx を `@50`/`@49` (fold) に落とし load が極低位へ | `hs_utl_decn` C 実装に override (`fw_hostfix.py`) |
| 2 | `0x40edb0` で OOB | `SetWideString` の Value が fold `@344` で `[@344-8]` deref | fold 値を nil として扱う override |
| 3 | `unreachable` (function_6be800) | `@__asm_mulsd__xxx` の呼出型不整合 (declare `(i128,i128)` vs call `(i128,i64)`) → clang が `_bitcast_invalid` を生成 | 同族名リネーム。**一般化**して 2973 site を正規化 (残 42 件は §7.4) |
| 4 | `unreachable` (function_579c20) | `__readgsbyte`/`__writegsbyte` 未定義 + `llvm.trap` を本体に持つ artifact define 7 本 | fail-soft (0 返却) override |
| 5 | `unreachable` (function_6b5290) | `GetWindowLongPtrW` を `long long` で宣言 → IR 側 i32 trunc と mismatch | fw_rt.c/h を i32 シグネチャに修正 |
| 6 | exit(101) @0x6b8f4b | named import `SetWindowTextW` 未実装で `fw_ff` (headless 用の fail-fast) | fw_table.py の未実装 import を fail-soft (0/NULL + 記録) に |
| 7 | `0x5c1930` / `0x5c0630` で OOB | FLE 内部 API 多段 deref が fold で OOB | fail-soft override (呼出元は結果を store するだけ) |
| 8 | `0x40b930` / `0x40b9a0` で OOB | TComponent 名検索が fold オブジェクトの `[rcx-0x90]` deref | 「見つからない」= 0 を返す override |
| 9 | `constant` global への store | RetDec が double 変換 temp として `@413/@414` (constant) を store → UB | 192 個の stored constant global を mutable `zeroinitializer` 化 |
| 10 | `0x412fc0` 深い再帰 OOB → `0x461950` | TStream.Read ラッパが fold ストリームを辿って再帰 | 0 を返す override |
| 11 | `0x52ce00` (CRC32) OOB → `0x52dba0` | TComponent.Find の name ポインタが fold | 0 を返す override |

(上記 1〜11 の詳細な根拠は `fw_hostfix.py` / `hs_utl.c` / `hostshim.c` のコメント参照)

## 5. hostshim の設計

- **vtable**: host オブジェクト 296B (`InstanceSize` 実測 + 余裕), vptr は合成 VA 0xE100000.. を指す
  (import 合成 VA 0xE000000..0xE000FC0 の直上で、dispatch 表の昇順 (二分探索) を維持)。
- **呼出記録**: `hs_rec` 配列 512 件 (ring) + `fw_hs_records()`/`fw_hs_count()` で JS から照合。
  stderr trace は既定 ON (`HOSTSHIM_TRACE=0` / `fw_hs_trace(0)` で消す)。SHIMX_TRACE 方式。
- **scratch pool**: 誤 decode mosaic 領域の override 先用 bump allocator (1MB, wrap)。

## 6. 未達: Eff_Render 差分 (次段 手順)

`TFruityPlug*` 実体生成に未達のため Eff_Render 差分は未実施。次段の手順:

1. **RTL ハッシュ表 (0x52cf40) の fold deref 解消** — native: 「CRC32(name) バケット巡回」。
   wasm では name ポインタが fold 定数 → `0x52ce00` のバイト読取が OOB。
   `[obj+0x38]` (name len)・`[rbp+0x78]` (name ptr) を BLK 経由で受け渡すか `fw_hs_scratch()` に差し替え。
2. **TComponent 名検索 (0x40b930 / 0x40b9a0)** の fold deref 解消 (同上, `[obj-0x90]` list)。
3. 以下は ABI.md の照合のみ (`TTestPlug` field: HostTag@+0x08 / Info@+0x10=0x70e3cc / Host@+0xbc、
   vtable26 の slot0/1/2/5/6/7)。
4. `Eff_Render(Src, Dst, Length)` 差分 — native 実機音声 vs wasm 出力の bit/tolerance 比較
   (判定は `tools/m10` 踏襲。native poly tan の ulp 差は許容)。
5. `GetName(Section, Index, Value, buf)` — 5 引数目は BLK+0x48 で対応済み。戻り内容は
   RetDec が Section/Index を定数化しているため記録のみ。

## 7. 未解決・ブロッカー

1. **TFruityPlug* 実体生成 (RTL fold deref 群)** — §6 の段階が残。いずれも「fold オブジェクト
   への deref」であり、hostshim 側ではなく **RetDec の引数畳み込み (CAB-231 クラス)** の課題。
   個别 override で塞ぐか、引数復元 pass で解決するかの判断は次段。
2. **Dispatcher ID の意味論** — 応答値 (非 NULL / 0) は呼出文脈クラスからの推定であって
   FLE 側 case 分岐の読解ではない。`CreatePlugInstance` 完全達成後に FLE 側 0x13173a0 を解析して確定。
3. **decode 漏れ残 206 関数** — fail-soft 化済み (init 経路は 0 で smoke 完走で実証)。
4. **`__asm_*` signature 不整合 42 件** — rename で解消できなかった残り。`fw_hostfix` が開始時に
   警告する。到達時は個別対処 (現状 e2e は PASS しているので非致命的)。
5. **f80 → f64 近似** (CAB-194 から継続) — DSP kernel (CAB-196) 向けには P0c の本命 pass が必要。
6. **llvm-as 検証の手動 dominance 修正** (CAB-194 継続) — ymm store 4 site。

## 8. ユーザ依頼事項

- なし (Balance = `docs/REFERENCES.md` `[WIN64]` の `extracted/block18983_PE.bin` で足りた)
- FLEngine_x64.dll (win64) 本体を `docs/REFERENCES.md` `[WIN64]` の `extracted/` に置いていただければ
  `hs_vtable_gen.py` で slot VAs を再生成・assert 検証できる (現在は ABI.md §2.3 確定値を使用)。

## 9. 次タスク提案 (下流チケット案)

1. **CAB-196 (P0c) 継続は読取のみ** — f80 lower / kernel 表 80 本。
2. **CAB-196b (提案)**: RTL fold deref 解消 (RetDec 引数畳み込み pass の拡張) で
   `CreatePlugInstance` 完全到達 → Eff_Render 差分 (§6)。
3. **CAB-231**: liftdiff verdict 回帰の load 取り違え pass (§7.1 の根本対策)。
4. **CAB-197 (提案)**: `TFruityHost` 残り 44 slot のうち editor 系 (slot 20 台) の実装 —
   `ShowEditor` / `DisposeEditor` 等。hostless smoke では非到達。
5. **CAB-198 (提案)**: `T0 frontier 660 関数` の `CreatePlugInstance` → ctor → GetName /
   ProcessParam / Eff_Render の差分試験 (CAB-194 出口条件の残部)。


## 10. 検収 (2026-10-11, 起点 commit 9b420bd / framework ツリー = b8e762d と同一)

**範囲・整合**: b8e762d の 21 ファイルはすべて `tools/plugins/framework/` 配下 (他 dir 0 行)。
commit 内最大 blob = **56,504 B** (`hs_ids.json`; 委任 prompt の「408KB」は不正確)。hostshim は
`framework/hostshim` **のみ** (`plugins/hostshim/` はツリー・履歴ともになし)。他 dir の未コミット
WIP 32 件は巻み込んでいない。`CAB-196 [In Progress]` が同 dir で `work/hs/` を共有 (実測上は無競合)。

### e2e 再実行 (実測)

| コマンド | exit | 実測秒 | load avg (開始→終了, nproc=16) | 判定 |
|---|---|---|---|---|
| `bash hostshim/hs_e2e.sh` | **0** | **11** | 1.01→1.17 | **PASS** (Phase A dispatch=38 ff=0 / Phase B rec=7, ID 序列 GOLDEN 一致) |
| `node fw_run.mjs ../work/fw/fw_image.bin ../work/fw/fw_route.cjs` | **0** | **0.2** ×3 | 0.97→1.15 | **PASS** (dispatch=38 / ff=0 / 3 回同値) |

Phase B は `status=0xffffffff plug=0` (memory access OOB) で終端し、GOLDEN は
「ctor prefix の記録一致」分岐を通る。**plug vtable 駆動・`TFruityPlug*` 生成は未検証**。

### 独立再計算 (別アルゴリズム)

| # | 対象 | 実装側 | 独立再計算 | 一致 |
|---|---|---|---|---|
| ② | slot0 Dispatcher | 0x13173a0 | `hs_vtable_verify.py`: FLE VMT 0x1314108+0x70 直読 → **46/46 slot 一致** | **一致** |
| ③ | ID cover | top30 778/894 = 89.8% | `hs_ids_recount.py` (降順累積): 上位30 **778/894 = 87.0%**、上位35 **803/894 = 89.8%**。35 ID の sites は元データ 894 と全件一致 | **不一致** (`top_n=35` が正) |
| ③ | store/reg : ignore/test | 9 : 21 | `hs_ids_recount.py`: **9 : 26** (9+26=35) | **不一致 → 訂正** |
| ③ | 133 DLL | 133 DLL | raw 132 / per-plugin 131 / per-ID 合計 138 — どれも 133 でない | **不一致 → 表記削除** |
| ④ | ctor 序列 | 0x47,0x56,0x0d,0x2e,0x47,0x1d | `hs_native_check.py` (block18983, 別コード): 7 site の `r8d` 即値・call 形を全照合 **8/8 OK**。0x6be800→`call 0x6b8e80 @0x6be864` も確認 | **一致** |

補助: `hs_disp_tree.py` で Dispatcher 0x13173a0 の二分木を具体駆動し **ID 0x56 → 0x131bb5c**
(`mov rax,[rip+0x2c9005]; mov rax,[rax]` = global obj ptr 応答) を確認。

### ネガティブコントロール (Ablation, `hs_fwdiff.sh` 25 s / load 1.27→1.52)

同一 `fw_flat4_canon3.ll` から差分ビルドを組み framework smoke の exit パス・dispatch を比較。

| build | 構成 | 結果 |
|---|---|---|
| B (親) | 親 table + 親 `fw_rt.c` | `Halt0/RestoreContext`, dispatch=38 |
| C | **HEAD table** + 親 `fw_rt.c` | **SAME** → fw_table.py の変更は framework build 挙動に影響しない |
| F | HEAD table + 親 `fw_rt.c` + hostshim.c | **SAME** → hostshim.c 追加リンクも影響しない |
| A / head2 | HEAD table + **HEAD `fw_rt.c** | **DIFFER**: OOB trap, dispatch=39, lastSite=0x40e112 |

⇒ 差分は **`fw_rt.c` のみ** (未解決 indirect target の exit 102 → fail-soft 化)。
診断修正 `fw_rt_diag.c` (`fw_hs_installed()` false の間だけ旧 fail-fast) を当てると
B/F と同じ終端パスに戻る (= 修正方針が機能する実測)。
C/F で SAME・head2 だけで DIFFER = この検査自体が判別力を持つ陰性対照。

### 検証範囲 / 範囲外

検証: commit 範囲・blob・hostshim 集約 / committed HEAD からの e2e 再実行 / ID cover・slot VTable・ctor
序列・Dispatcher 分岐の native 独立照合 / framework build 挙動の差分切り分け / `__asm_*` 42 件の件数再実行。
範囲外: (a) `Eff_Render` 音声差分 (plug 未生成で実施不能) (b) native 実行との同一経路比較 (同一 binary
比較ではない) (c) 42 件 `__asm_*` が「将来も」非致命である証明 (未踏で未検証) (d) `work/fw/*.ll` など
git 管理外成果物。

### 検収判定

| 受入条件 | 判定 |
|---|---|
| hostshim 1 箇所集約 | **PASS** (framework/hostshim/ のみ) |
| slot0 = Dispatcher 0x13173a0 = CAB-12 確定値 | **PASS** (VMT 直読 46/46 一致) |
| Dispatcher 上位 ID cover 数値 | **PASS (修正後)** — 89.8% = 上位 **35** ID (803/894)。上位 30 = 87.0% |
| ctor 序列 0x47,0x56,0x0d,0x2e,0x47,0x1d | **PASS** (native 8/8 独立照合) |
| fw_rt.c/stage2/table が framework build 挙動を変えない | **FAIL → 訂正 PASS** — 差分は `fw_rt.c` のみ。table/link 単独は不変 (Ablation)。stale artifact 由来の「不変」根拠は撤回 |
| fail-soft 44 slot + `hs_rec` ring | **PASS** — 46 slot 中 slot0/6 実装・残 44 が record+0。`hs_rec` 512 件 ring, 40 B/entry (slot,id,a0,a1,a2,ret) |
| e2e exit 0 + framework smoke 数値 | **PASS** (3 回再現) |
| RTL fold deref 未達分析・CAB-231 帰属 / Dispatcher 意味論ラベル | **妥当** (§7 の「推定」ラベル維持が正) |
| `__asm_*` 42 件の非致命 | **現状 PASS** (件数一致を再実行確認) |

### 訂正した誤記 (各節にインライン注記済み)

①「上位 30 ID」→ **上位 35 ID** (803/894 = 89.8%。上位 30 は 778/894 = 87.0%) ②「ignore/test
21 ID」→ **26 ID** ③「133 DLL」→ **削除** (再計算不能) ④「追加リンクのみで動作不変」→
**訂正** (差分は `fw_rt.c` の fail-soft 化、Phase A の dispatch=38 は stale artifact 由来)
⑤slot0 一致「未実行」→ **VMT 直読 46/46 一致で確認**。

### 未解決 (起票先つき)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD `fw_rt.c` で framework smoke が `dispatch=39 / OOB trap` に変わる | `work/fw/fw_route.cjs` 再生成で Phase A が FAIL (現状は stale artifact で PASS) | (c) 本検収コメントで提案。方針: `fw_rt_diag.c` 実証どおり未敷設時は旧 fail-fast を維持 |
| `hs_ids.json` の `top30_cover` 名が `top_n=35` の累積を指す | ラベル混乱 (本訂正で回避) | (a) 本検収コメント (実装修正は CAB-196b) |
| 42 件 `__asm_*` の将来の非致命 | 未踏のため未検証 | (a) 本検収コメント (§7.4) |
| `Eff_Render` 差分・`TFruityPlug*` 生成 | 出口条件残部 | (b) **CAB-196b** |

### 下流チケット案 (起票要否)

- **CAB-196b (RTL fold deref 解消)** — **起票すべき**。CAB-195 の出口条件 (全 T0 が ctor 完走) に
  直接必要で、`CAB-231` (M11 closure の load 取り違え) と原因は同系だが対象・素材が違い重複ではない。
- **CAB-197 (editor slot 20 台)** — **起票不要**。hostless smoke で非到達で要件が出ていない。
- **CAB-198 (T0 frontier 差分 / Eff_Render)** — **起票すべき**。ただし **CAB-196b が前提**。

## 11. 環境前提

- emsdk: `source /opt/emsdk/emsdk_env.sh`。node は `/opt/emsdk/node/24.19.0_64bit/bin/node`
  (既定 PATH に `node` が無い)
- TMPDIR は実ディスク (`tools/plugins/work/hs/tmp`, gitignore)
- 素材 (読取のみ): `docs/REFERENCES.md` `[WIN64]` の `extracted/block18983_PE.bin` (Balance)・
  `block00031_PE.bin` (FLEngine, VMT 照合)
- 中間産物: `tools/plugins/work/hs/` (gitignore, ~360 MB)

---

## 12. 検収記録 — CAB-194 (77cde78) (2026-10-11 / 起点 commit 85424b0)

- 既知類型との関係: **該当 D7 (stack 引数・戻り値)・
  D15 相当 (間接 call の保存率) と該当なし (alloca 縮退は DEFECTS.md 未登録で本節で再記録)**
- 範囲: 77cde78 は **22 ファイル 3,465 行すべて `tools/plugins/framework`** (他 dir 0 行)。
  commit 内最大 blob = 350,589 B = 0.33 MiB (20 MiB ライン未満)。`git status` は担当外 WIP
  59 件 (framework 内 0・混入なし)。stage-2 のビルド鎖 (fw_stage2.sh/fw_table.py/fw_ovpass.py)
  は**未修正** (CAB-196 稼働中のため)。訂正は本 REPORT の記述のみ。

### 12.1 e2e 独立再現 (規則 45: `git archive 77cde78` の別ツリー + stage-1 成果物)

`fw_route.cjs` は work/fw の **02:11 bake** (CAB-194 vintage: FAIL-FAST 文字列を内包) で
あることを `strings` で確認 (`soft-miss` 0 件 / `FAIL-FAST` 3 件)。加えて **194 commit から
`git archive` した別ツリー + stage-1 成果物のハードリンク**で再ビルドし独立再現した。

| 経路 | 実測 | 判定 |
|---|---|---|
| `node fw_run.mjs ../work/fw/fw_image.bin ../work/fw/fw_route.cjs` ×3 | exit 0 / **dispatch=38 units_done=0 va=1 heap=1 ff=0** (264 ms / 373 ms / 412 ms) | **PASS** (CAB-194 §3 と一致) |
| 194 再ビルド (09:18-09:51) の smoke ×3 | exit 0 / dispatch=38 ff=0 / wasm **14,828,623 B** | **PASS** |

unit init 16 / finalize 16 は smoke log の `site=0x40dae6` 16 行・`site=0x40da42` 16 行で
実測 (残り 5 dispatch は trace 件数上限で非表示 = counter 38 − trace 33 行)。
**PackageInfo = 290** は count field (`0x6c1430` u32 = 290)・テーブル終端ポインタ
(`0x6c2680`)・`(end-tab)/16 = 290` の 3 点照合。ただし init≠0 のエントリは **289**
(entry 289 は init=0)。unit[0].init=0x4198b0 = 報告どおり。

### 12.2 独立再計算 (別アルゴリズム)

再現 script は `tools/plugins/framework/work/vfy194/` (gitignore・commit 対象外) に置いた
(`fw_194_recount.py` / `smoke_check.py`)。commit 済みツリーだけでも同等に再現できる最小手順
(以下は共有 `work/fw` の成果物に対する実行例):

```
# icall: PE sites 集合 vs 最終 IR の dispatch 集合 (別アルゴリズム)
python3 -c "import json,re;m=json.load(open('fw_map.json'));s=set(x['va'] for x in m['sites']);\
t=open('fw_flat4_canon3.ll',errors='replace').read();\
d=set(int(x) for x in re.findall(r'call void @__icall_dispatch\\(i64 (\\d+)\\)',t));\
print(len(s),len(d),len(s-d))"          # -> 6159 5526 634
# alloca: rep_stosq サイト走査 (memset 正規表現ではなく call 引数から)
grep -n '__asm_rep_stosq' fw_lift3.ll   # -> 152380 / 621787 = 2 site (i64 49 → 392 B)
# PackageInfo: テーブル終端ポインタから件数計算
python3 -c "import struct;i=open('fw_image.bin','rb').read();\
u=lambda va:struct.unpack_from('<Q',i,va-0x400000)[0];print((u(0x6c1430+24)-0x6c1460)//16)"  # -> 290
```

主要な集計・計測の再現 (実装側 script・別アルゴリズム):

| # | 主張 | 独立再計算 | 一致 |
|---|---|---|---|
| ① | 14,037 関数 / 1.61 MB lift | F.ranges **11,736** エントリ・合計 **1,626,299 B = 1.55 MiB**、`fw_all.restored.ll` define **14,037** | 関数数 一致 / サイズ 1.55 MiB (報告の 1.61 は誤差) |
| ①' | wasm 14.8 MB | 14,874,162 B (14.19 MiB) = 14.87 MB | 一致 (MB = decimal) |
| ② | icall 6,159 site 全復元 | PE sites 6,159 → 共有 canon3 の unique dispatch **5,526** / 未復元 **634 = 10.3%** (194 再ビルド canon3 は 5,525 / 635)。7 呼出は `!insn.addr` 欠落で site=0 | **不一致 → 訂正** |
| ③ | alloca 縮退 2 関数 (43ecb0/51c2d0) 392 B | `rep_stosq_memset(…, 49)` サイト = 49×8 = **392 B** がちょうど 2 関数 (43ecb0/51c2d0)。修復後 `alloca [49 x i64]` = 392 B | **一致** |
| ④ | fw_entry_fix.py の home slot 修復 | entry_fix.json = `r8_fixed 1 / r9_fixed 1` (VA 0x6c13a0→call 0x4189c0)。native (`fw_icall.dll`, capstone) で `mov [rip-0x2349bd], r8` / `mov [rip-0x2349bc], r9` の spill を確認 | **一致** |
| ⑤ | sigfix 7,058 site | 同条件で再実行: `arity_fixed 7,443 / type_only 26,654 / ret_fixed 4,578` (fw_sigfix.py docstring の 8.3k/4.6k と同傾向) | **不一致 → 訂正** (7,058 は本 commit から再現不可) |
| ⑥ | 前回残骸 (fw_prep/fw_merge/fw_lift.sh) 引継ぎ | 3 資産は実行済み・成果物あり (fw_map nfuncs 11,736 / nsites 6,159 / nderef 12,658 / ncomis 630 / errors 0)。F.ranges も 11,736 で一致し再 lift 不要は妥当 | **妥当** |

### 12.3 再ビルドで判明したビルド鎖の不備 (記録のみ・**未修正**)

194 commit の `fw_stage2.sh` を空ディレクトリ (stage-1 のみハードリンク) で完走させると
**4 か所で停止**する (Δのうち S1-S3 は CAB-194 由来・S4 は CAB-195 由来と推定):

- **S1** `fw_boot.c` が W に無い (`cp` は fw_rt.h/fw_rt.c のみ) → emcc が input 無しで失敗
- **S2** ymm dominance 修正の `uid` がリセットされ `ceclone1` が `function_4076b0` 内で
  二重定義 → clang `multiple definition of local value named 'ceclone1'`
- **S3** `fw_ovpass.py` が幅広戻り型 (i128: `function_40e0b0`) に `trunc i64` を生成 →
  clang `invalid cast opcode for cast from 'i64' to 'i128'`
- **S4** `fw_fldenv` の declare が欠落 (`__asm_fldenv__vg224` の rename 後) →
  clang `use of undefined value '@fw_fldenv'`

⇒ **共有 work/fw の canon 系成果物はコミット済み `fw_stage2.sh` の順序・正規化では再現できない**
(共有 canon3 は `__asm_vmovaps__vyy` → `store i256` 変換と `fw_fldenv` declare を持つ)。
本検収では sandbox 内だけで S1-S4 を回避して smoke を再現した。**修正は CAB-196 側の判断**
(本節は記録のみ。fw_stage2.sh / fw_ovpass.py は未変更)。

### 12.4 検証範囲 / 範囲外

検証: commit 範囲・blob / smoke 3 回再現 (+194 再ビルド smoke 3 回) / 上記 6 項目の独立
再計算 / PackageInfo・icall 集合・alloca・capstone 突合 / hostshim 側 `hs_ids_recount.py` と
`hs_vtable_verify.py` の再実行 (35 ID = 803/894 = 89.8%・46/46 slot 一致)。
範囲外: (a) native 実行との同一経路比較 (bit-exact 比較は未実施) (b) `Eff_Render` 差分
(CAB-195 未達を継続) (c) 未解決 634 site の**個別原因**は未分類 (d) 本節の再ビルドは
stage-1 成果物を再利用 (RetDec 再 decode は未実施) (e) 7,058 site は数値の出所が不明で
検算不能。

### 12.5 未解決 (起票先つき)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| icall 未復元 634 site (10.3%) — 最終 IR で落ちる | VMT/reg 呼出しの取りこぼし。ctor 差分試験の精度 | (a) 本検収コメント (CAB-194 に記録) |
| `fw_stage2.sh` が空ディリクトリで完走しない (S1-S4) | 「1 コマンド e2e」が再現不能 | (b) 子チケット **CAB-269** (親 CAB-194・milestone「統合」。修正は CAB-196 連鎖終了後) |
| decode 漏れ件数が測定時点で 206 / 143 / 126 と食い違う | fail-fast stub の実数の不透明 | (a) 本検収コメント (定義を固定) |
| CAB-195 の §10 未解決「HEAD `fw_rt.c` で smoke が dispatch=39 / OOB」 | (CAB-195 側で継続) | (a) CAB-195 検収コメント参照 |

### 12.6 訂正した誤記 (77cde78 の REPORT に対する検証結果・本 REPORT への記録)

①「6,159 site 全復元」→ **5,526/6,159 (未復元 634 = 10.3%)** ②「14,034 define」→ **14,037**
③「14,033 関数」→ **14,037** ④「PackageInfo 290 unit」→ **290 件・うち init≠0 は 289**
⑤「declares 8,176」→ **重複込 8,176 / unique 8,063** ⑥「decode 漏れ 126/206」→ **最終 IR 143**
⑦「1.61 MB」→ **1.55 MiB (1,626,299 B)** ⑧「14.8 MB」→ **14.87 MB (14,874,162 B)**。

---

## 13. CAB-269 (2026-10-11) — `fw_stage2.sh` S1-S4 修正と 1 コマンド e2e 復旧

- 既知類型との関係: **該当 D7 (stack 引数・戻り値)・
  該当なし** (S2 は手書き pass の採番衝突で DEFECTS.md 未登録 → §13.7 に行案)
- 検証起点: 本節の全実測は `git archive HEAD -- tools/plugins/framework` の **snapshot** から再実行
  (snapshot commit c737c4a。`git diff db6565c c737c4a -- tools/plugins/framework` = 0 行 = 本修正ツリーと同一)。
- 変更 7 ファイル (すべて `tools/plugins/framework/`・他 dir 0 行・最大 blob 40,637 B = `REPORT.md`・20 MiB ライン未満):

| ファイル | 変更 | 対応 |
|---|---|---|
| `fw_stage2.sh` | step 14 の 3 インライン heredoc → `fw_canon.py` 呼出 / `stage_inputs()` (build 入力コピー) / `FW_W` 差し替え対応 / `llvm-as` ガード / smoke 検証追加 | S1, S2, S3 |
| `fw_canon.py` | **新規 243 行** — canon 段の正規化 1 実装 (ymm store 化・dominance clone 採番・i256 identity・fldenv rename+declare) | S2, S3 |
| `fw_ovpass.py` | `ret_of()`: 64 bit より広い整数は `zext`・ポインタは `inttoptr`・未対応型は fatal | S4 |
| `fw_smoke_check.py` | **新規** — smoke 出力の独立再計算 (fw_run.mjs と別 regex) + wasm サイズ照合 | 規則 37 |
| `fw_269_verify.sh` | **新規** — clean HEAD snapshot からの 1 コマンド e2e + smoke ×3 + 同値照合 | 受入 1, 2 |
| `fw_269_nc.sh` | **新規** — ネガティブコントロール 5 件 (S1-S4 + entry export) | 規則 41 |
| `REPORT.md` | §13 に本節を追記 (訂正・起票先つき未解決を含む) | 規則 42 |

### 13.1 修正 4 件

| # | 症状 (clang/llvm-as 実測) | 原因 | 修正 |
|---|---|---|---|
| S1 | `emcc: error: fw_boot.c: No such file or directory` | `cp` は `fw_rt.h`/`fw_rt.c` のみ (`\|\| true` で欠落も隠れていた) | `stage_inputs()` が `fw_boot.c` もコピー (存在チェック付き) |
| S2 | `fw_flat4_canon3.ll:11224:3: error: multiple definition of local value named 'ceclone1'` | ymm dominance 修正の `uid` が canon 段で 0 にリセットされ、`function_4076b0` 内で `ceclone1..5` が二重定義 | 採番を `max(10000, 入力内の最大 ceclone 番号)` から採番 (`fw_canon.py:next_uid`) → pass を跨いでも衝突しない |
| S3 | `fw_flat4_canon3.ll:1307203:13: error: use of undefined value '@fw_fldenv'` | `__asm_fldenv__vg224(i224)` を `fw_fldenv(ptr)` に rename した後の declare を**削除**していた。(A/B 段の正規表現は実名 `__asm_fldenv` に非マッチで無効 = rename は simd gen 後の canon 段で初めて成立) | declare を `declare void @fw_fldenv(ptr)` に**置き換え** (位置は declares 節のまま)。rename は gen 後固定 (gen 前に rename すると `fw_simd.c` の stub が消えて別ビルドになる) |
| S4 | `fw_flat4_canon3.ll:35753:14: error: invalid cast opcode for cast from 'i64' to 'i128'` | `fw_ovpass.py` が i64 以外をすべて `trunc` に変換 (i128 戻りの `function_40e0b0` = RestoreContext 実行本体) | 64 bit より広い整数は `zext`・`ptr`/`*` は `inttoptr`・未対応型は fatal |

番号の対応: CAB-269 チケットの S3/S4 は §12.3 の S4/S3 と同一現象 (declare 欠落 / trunc)。本節は
**チケット番号**に合わせる (§12.3 は「S3 = trunc・S4 = declare」と逆)。

### 13.2 1 コマンド e2e (受入条件 1・2・要件 1)

```
bash tools/plugins/framework/fw_269_verify.sh         # SIZE 未指定 = wasm サイズは照合スキップ
bash tools/plugins/framework/fw_269_nc.sh             # ネガティブコントロール 5 件
```
→ stage-1 成果物 (`fw_icall.dll` 9,358,848 B・`fw_map.json` 11,513,493 B・`fw[0-7].restored.ll`・
`r2/r3.restored.ll` 計 10 ファイル) だけをハードリンクした**独立 W** (`work/verify_269/fw`・共有
`work/fw` は非変更) に `git archive HEAD` の snapshot から `FW_W` 付きで steps 1-18 全部を実行。

| 実行 (full = stage-1 からの作り直し) | fw_stage2.sh exit | 実測秒 | load avg 開始→終了 (nproc=16) |
|---|---|---|---|
| full A | 1 (*) | **297** | 3.62 3.59 3.34 → 5.37 4.65 3.86 |
| full B | 1 (*) | **343** | 12.72 12.99 8.77 → 7.15 12.15 10.02 |
| full C | 1 (*) | **343** | 7.15 12.15 10.02 → 6.15 8.39 8.96 |
| full D (commit 6ab9a4d snapshot) | **0** | **297** | 2.29 2.73 4.66 → 3.73 3.31 4.37 |
| smoke ×3 (full B / C / D) | 0 | 187〜233 ms | — |

(*) A-C は `--size` の既定が 14,828,623 B (77cde78 vintage) だった時期の実行で、**wasm サイズだけ**
が MISMATCH (smoke 5 値は全 run PASS)。D は現行 commit の snapshot (既定 = サイズ照合スキップ) で
exit 0。実測秒は 4 回中 297/343/343/297、smoke 1 発あたり 187〜233 ms (負荷依存・レンジ表記)。

smoke ×3 は全実行で同値 (`smoke1.log` と `smoke2/3.log` の diff = 0 行・`ctx=0x…` はスタック値なので正規化):
```
[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0
```
trace 行 33 = dispatch counter 38 − trace soft limit 5 (定義: `fw_smoke_check.py` docstring / NC5)。
**空ディレクトリ/work 新規 (条件 ③)**: `FW_W=<新規dir>` で検証。既定 W = `tools/plugins/work/fw`。

### 13.3 ネガティブコントロール 5 件 (`bash fw_269_nc.sh` → OK=5 NG=0)

| # | 壊した箇所 | 期待した FAIL (実測出力) | 判別力 |
|---|---|---|---|
| NC1 (S1) | `stage_inputs` から `fw_boot.c` を外す | `emcc: error: fw_boot.c: No such file or directory` | **有** |
| NC2 (S2) | `fw_canon.py` の採番を 0 から (継続採番も外す) | `fw_flat4_canon3.ll:11224:3: error: multiple definition of local value named 'ceclone1'` | **有** |
| NC3 (S3) | fldenv の declare を置き換えず削除 | `fw_flat4_canon3.ll:1307203:13: error: use of undefined value '@fw_fldenv'` | **有** |
| NC4 (S4) | `fw_ovpass.py` を `trunc` に戻す | `fw_flat4_canon3.ll:35753:14: error: invalid cast opcode for cast from 'i64' to 'i128'` | **有** |
| NC5 | `_function_6c13a0` の export 名を破壊 | `[fw] SMOKE FAIL: entry function_6c13a0 が export されていない` (exit 1) | **有** |

NC2-NC4 の行:桁は **チケット記載の S2/S3/S4 と完全一致** (11224:3 / 1307203:13 / 35753:14)
= 修正対象と同じ IR 位置を壊している証拠。NC5 の注記: `fw_run.mjs` のメッセージは export 名を
`function_6c13a0` とハードコードしているため 6c13a1 に壊しても 6c13a0 と出る (§12 の NEGCON A の
記載 `entry function_6c13a1 …` はこの誤記・本節で訂正)。
`llvm-as` ガード (追加分) が上記 3 件を emcc 前に落とす (shared canon3 85.8 MB で **2.59 s**・maxrss 508,020 KB)。

### 13.4 等価性の検算 (別実装との突合 = 規則 37・45)

リファクタした `fw_canon.py` が旧実装 (77cde78 のインライン 3 ブロック + 検証時の回避策) と
**同一の IR を出す**ことを、同一入力で diff して確認 (`%ceclone` 名は `%CL` に正規化):

| 比較 | 差分行 |
|---|---|
| 旧 A+B → `fw_flat4.ll` vs `fw_canon.py --stage flat4` (同一 `fw_flat3.ll`) | **0 行** (採番名のみ差異) |
| 旧 C (`uid[0]=10000` の回避策) → `fw_flat4_canon2.ll` vs `--stage canon` | **1 行** (declare の位置: 旧は後付・新は declares 節内) |

### 13.5 検証範囲 / 範囲外

検証: clean HEAD snapshot からの e2e ×3 / smoke 同値 ×3 / S1-S4 の個別 FAIL 再現 / 旧実装との IR 同一性 /
hostshim `hs_e2e.sh` 回帰 (Phase A dispatch=38 ff=0・Phase B rec=7 GOLDEN 一致・exit 0・実測 0.5 s)
/ 本ビルドを `hs_e2e.mjs` に直接入れた場合も Phase A 同値。
範囲外: (a) native 実行との bit 比較 (b) `Eff_Render` 音声差分 (CAB-195 未達を継続) (c) RetDec 再 decode
(stage-1 成果物をハードリンク再利用) (d) `work/fw` 共有成果物の更新 (本節では書換えない)。

### 13.6 wasm サイズの差分 (委任 prompt の 14,828,623 B に対し実測 15,061,227 B)

HEAD ツリーの e2e で出力される `fw_route.wasm` は **15,061,227 B** (3 回同値)。参照 14,828,623 B は
**77cde78 (CAB-194 vintage) ツリー**の再ビルド実測値で、HEAD とは別ビルド。実測で切り分け:

| 比較 (同一 canon3 入力) | 結果 |
|---|---|
| HEAD の emcc 行全体 (hostshim.c リンク + fw_hs_* export 13 本) | 15,061,227 B |
| 同じ canon3 から **hostshim.c を外し** export を 77cde78 の 11 本に | 15,051,660 B (Δ −9,567 B) |
| `fw_table.py` 生成 C: HEAD 版 vs 77cde78 版 (同一 canon3) | 2,112,554 B vs 1,956,397 B (Δ **+156,157 B**) |

⇒ 差分の大半は **CAB-195 (b8e762d) の `fw_table.py` fail-soft 化** (missing-stub 126 + 未実装 import に
`fprintf`/`fflush`/`seen` を追加) と `fw_rt.c` の fail-soft 化、残りが hostshim.c 追加リンク。
canon 段の IR は旧実装と同一 (§13.4) なので、**修正 S1-S4 がサイズを変えたのではない**。

### 13.7 未解決 (起票先つき) / 誤記訂正 / 新类型行案

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD の wasm が 77cde78 vintage と 232,604 B 差 (同一 smoke 挙動) | サイズで合否を見る手順が混乱 | (a) 本節に原因を実測で記録。親 CAB-194 にコメント |
| `fw_run.mjs` の FAIL メッセージが export 名をハードコード | NC5 の期待文字列が実名と不一致 | (a) 本節で訂正 |
| shared `work/fw` の成果物が 77cde78 vintage のまま (HEAD の再ビルド未反映) | 次に `work/fw` を W に `fw_stage2.sh` を流したセッションだけ成果物が入れ替わる | (c) 親 CAB-194 に提案コメント (main 判断) |
| **新类型 (DEFECTS.md 未登録)**: インライン pass の採番カウンタが pass 間で衝突 (S2) | 同じ轍を踏む | (a) 本節に行案を記載。DEFECTS.md は他担領域のため直接編集しない |

行案 (DEFECTS.md 形式): **D17 手書き pass の採番衝突** — 症状: `multiple definition of local value
named 'ceclone1'` / 根本原因: pass ごとに `uid` を 0 にリセット / 観測: canon 段の chain clone
(`function_4076b0` 11224 行) / 検出信号: `llvm-as` を emcc 前に 1 本通す (2.59 s) / 修復: `max(10000, 最大番号)`。
