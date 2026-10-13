# P0b REPORT — TFruityHost shim (CAB-195)
> 詳細は付録 `tools/plugins/framework/REPORT_P0c9.md` (P0c-9 #610)・`tools/plugins/framework/REPORT_APPENDIX.md` (§10・§12・§13 の検収記録・CAB-269 修正記録)。
> 行数: 本体は 250 行上限内。分割は 2026-10-13 (内容の削除なし・Git 履歴に元の節あり)。

- 検収起点 commit: **9b420bd** (`tools/plugins/framework` ツリーは b8e762d と同一: `git diff b8e762d HEAD -- tools/plugins/` = 0 行)
- 行数目安 (分割前): 実装部 (§0-§9) 187 行 + 検収記録 (§10-§11) 105 行 + CAB-194 検収 (§12) 78 行 + CAB-269 (§13) 118 行 = 488 行
  (実ファイル 476 行)。分割後: 本体 207 行・付録 `REPORT_APPENDIX.md` 318 行。検収記録・修正記録は規則 37〜42
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
| 回帰 (CAB-194) | framework smoke: **unit init ×16 + unit finalize ×16 / dispatch 38 / trap 0 / fail-fast 0** を維持 (**ただし Phase A は stale artifact を再利用していたため実質 38 は再現されていない — §1 訂正・付録 §10**) |
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
> (付録 §10 Ablation)。hostshim.c 追加リンク・`fw_table.py` の slot 登録・decode-miss fail-soft 化は単独では不変。
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

検証済み (ID 一致)。独立照合は付録 §10 の `hs_native_check.py` (8/8 OK)。

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


## 11. 環境前提

- emsdk: `[EMSDK]` の `emsdk_env.sh` を source。node は同梱 `node/24.19.0_64bit/bin/node`
  (既定 PATH に `node` が無い)
- TMPDIR は実ディスク (`tools/plugins/work/hs/tmp`, gitignore)
- 素材 (読取のみ): `docs/REFERENCES.md` `[WIN64]` の `extracted/block18983_PE.bin` (Balance)・
  `block00031_PE.bin` (FLEngine, VMT 照合)
- 中間産物: `tools/plugins/work/hs/` (gitignore, ~360 MB)

---

## 14. stage-2 runner 再構築の検証記録 (PR #803・#195)

- 検証起点 commit: **01544f44** (PR #803 の HEAD)。本 PR の差分は `fw_stage2.sh` (llvm-as → `clang -x ir -c`) と `fw_269_verify.sh` (`git archive` に `tools/shared` 追加) のみ。
  `liftlib/simd/gen.py` の `_stub` 変更は revert 済み (`TAG` の値域は全て `CT` のキーで、旧 `"?" in` と新 `all(t in CT)` は同値。`g224` は `TAG` に無く、到達しない)。
- 実行コマンド (実装 run): `bash tools/plugins/framework/fw_269_verify.sh <tools/plugins/work/fw>` (stage-1 のみの独立 W から stage-2 を再構築)。
- 実測 (実装 run・n 件数を併記):
  - `fw_stage2.sh` exit=0 / 437 s (n=1) / load avg 0.62 1.78 1.02 → 2.36 2.62 1.62
  - smoke ×3: 137 / 135 / 132 ms (n=3・min–max 132–137 ms) / `dispatch=38 units_done=0 va=1 heap=1 ff=0`
  - wasm 15,062,176 B (参照 HEAD 15,061,227 B。HEAD ツリーでは `--size` 未指定のため照合は未実施)
  - 結果: `ALL PASS (e2e + smoke ×3 同値)`
- **この fix run での再現: 未実施**。`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ (`ls` 実測)。`work-fw-stage1` 未展開・`[EMSDK]` (`/opt/emsdk`)・`[RETDEC]` (`/opt/retdec`) とも無いため e2e は実行不能。上の実測値は実装 run の記録であり、独立再現ではない。
- `clang -x ir -c` 回帰ガードの実測 (この fix run・clang 18.1.3): 不正 trunc (i64→i128) exit=1 / 未定義値 `%nope` exit=1 / SSA 再定義 exit=1 / 正しい IR exit=0。
- 未解決 (起票先):
  - 上記 e2e の独立再現 (stage-1 素材と emsdk が揃う run) → #195 残部
  - `fw_stage2.sh` が `[EMSDK]`・`[RETDEC]` を絶対パスで参照 → #270
  - bit-exact 比較 (RTL fold deref 解消後) → #195 残部

---
