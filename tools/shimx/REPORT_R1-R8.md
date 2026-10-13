# REPORT (R1〜R8 / R2・R3 実体接続) — shimx M11 リンク フィードバック対応 (CAB-211 / CAB-177)

> 正本: `tools/shimx/REPORT.md` §9・§10 から分割移動した付録 (内容は無変更、§ 番号 9.x / 10 は維持)。親: `tools/shimx/REPORT.md`。
> 分割理由: `docs/DOC_MAP.md` §1 の 250 行上限 (#584)。

## 9. M11 リンク フィードバック対応 — R1〜R8 (CAB-211)

出典: `tools/m11/shimx_link/REPORT.md` §6 (CAB-166, commit 8170eee)。テスト: `test/test_link.c` (`bash tools/shimx/test.sh` の MT/ST で実行)。既存検収 (M4 53/53, MT/ST, 署名突合 0, OTT t1 SHA 一致 `b5a91b9b…`) は **全て維持**。

### 9.1 対応表

| # | 要求 (M11 REPORT §6) | 対応 | 実装 |
|---|---|---|---|
| R1 | 「ポインタ < 0x10000 は序数/整数」判定の閾値設定 or image 敷設 ≥64KB | **実装** | `shimx_set_intptr_limit(lim)` / `shimx_get_intptr_limit()` (既定 0x10000)。判定箇所は 5 か所 (GetProcAddress 序数 / FindResourceA name,type / AddAtom・FindAtomW の MAKEINTATOM / CharUpper・LowerW 単一文字) を共通ヘルパ `shx_is_iptr()` に統一。**lowbase は LB_BASE=0x10000 敷設で既定値のままで整合** (guest ポインタ全て ≥ lim)。LVA=0 敷設 (M11 旧式) では `shimx_set_intptr_limit(0x4000)` 等に下げる — `kernel32.dll!#39682` (Delphi 文字列 LVA 0x9b02) は lim<0x9b02 で文字列扱いになり、序数 shell32 #16..155 (<0x4000) は引き続き有効。デフォルト不変のため M11 の miss 挙動自体は変わらない (harness 側の設定が必要) |
| R2 | 関数ポインタ引数の変換フック | **実装** | `shimx_set_callback_translator(fn)` (型: `void* (*fn)(const char* api, void* cb)`)。適用 API: EnumSystemLocalesW / EnumCalendarInfoW / CreateThread / FlsAlloc / CreateTimerQueueTimer / CreateThreadpoolWork / InitOnceExecuteOnce の **計 7 API** (同期 3 = Enum*・InitOnceExecuteOnce + 非同期 4 = CreateThread・FlsAlloc・タイマ・スレッドプール; REPORT 要求を網羅)。翻訳結果 NULL は元値にフォールバック (呼出側の NULL 判定を保護)。未設定時は恒等 → 既存挙動不変。**VA→トランポリン変換の実体は hostbridge (T2/CAB-177)** がこのフックに接続する |
| R3 | GetProcAddress 組込み表追加 (kernel32 UI言語 3 本, shell32 序数 9 個) | **実装** | kernel32: `GetThreadPreferredUILanguages` / `SetThreadPreferredUILanguages` / `GetThreadUILanguage` を機能実装 (en-US 固定, multi-sz "en-US\0\0", GetProcAddress 名前解決は自動生成 proctable に反映)。shell32 序数は Windows 10/11 の序数表と突合して **同定**: 16=ILFindLastID, 17=ILRemoveLastID, 18=ILClone, 19=ILCloneFirst, 21=ILIsEqual, 25=ILCombine, 152=ILGetSize, 153=ILGetNext, 155=ILFree (既知 190=ILCreateFromPathW も登録)。IL* 8 本を shimx 自前 PIDL 形式で実装し、序数直指定用の新表 `shx_ordtable` (src/module.c, 手書き) から解決。74 (SHCreateStdEnumFmtEtc) は未実装のまま miss |
| R4 | LoadLibrary 失敗方針 (Msctf.dll/avrt/PowrProf.dll を擬似 DLL 登録するか) | **実装** (選択式) | `shimx_set_pseudo_load(1)`: 未知 DLL 名を擬似モジュール (最小 PE ヘッダ画像, 組込み扱い) として登録し LoadLibrary を成功させる。**既定 0 = 従来どおり失敗** (M11 survey で失敗のまま起動が進む実績があるため既定は不変)。失敗/擬似登録は `SHX_TRACE` に出力 |
| R5 | SysFreeString が管理外ポインタを受けたときの挙動 | **実装** | SysAlloc* が確保したベースポインタの所有表 (オープンアドレス法ハッシュ, mutex 保護) を導入。`SysFreeString`: 所有済み→従来どおり free / 管理外→**strict=1 で fail-fast (`SysFreeString (管理外ポインタ)`), strict=0 (既定) で無視 + trace**。二重 free も同一経路で無害化。M11 REPORT §3-#1 の lift 誤り (`_WStrClr` がスタック番地を渡して free で abort) は **この変更だけで abort しなくなる** (--fix の `sx_liftfix.c` C 転記は論理修復として並行維持) |
| R6 | `ir_undef.py --emit-stubs` の構造体 by-value 展開 + `NAME.1` 重複 declare 正規化 | **実装** | (a) `--emit-stubs` が `%name = type {...}` 表から by-value 構造体引数を wasm32 規則で展開 (`WindowFromPoint(%tagPOINT)` → `(int, int)` — M11 REPORT §1 の signature mismatch 1 の再発防止)。(b) 新オプション `--normalize-dup out.ll`: `NAME.<d>` / `NAME_D<d>` (基名が shimx 定義) を基名 declare へ正規化 — 重複 declare 削除 + 呼出siteの引数 0/null 補間 + 戻り値型差の変換命令 (trunc/zext/inttoptr/ptrtoint/fpext/fptrunc)。実測: boot_final2/3 とも 1 名 1 site 正規化され **emcc 通過**。(c) 分類に `shimx_dup` を新設 (§9.3 の再計測参照) |
| R7 | EnterCriticalSection(NULL) の方針 | **実装** (方針決定 + 選択式) | **既定 = fail-fast のまま** (= Win32 実機のアクセス違反相当。survey unit 115 は旧 M4 shim でも同一 unit で abort する lift 側ポインタ不正であり、黙って成功させると lift 誤りを隠す)。許容モード `shimx_set_cs_null_ok(1)` を追加: Enter/Leave は no-op、TryEnter=FALSE、Initialize 何もしない、SleepConditionVariableCS=FALSE。null_ok モード自体も fail-fast モード (`node x.cjs csnull`) で検査 |
| R8 | 未検証 133 名の実機検証 | **手順整備** (実検証は unit 完走後) | `scripts/reach_check.py` (M11 `reach.json` の `static_reach_but_never_called` 133 名と実行トレースの差分集計) + `scripts/rem11_check.sh` (§9.2)。現時点の純リンク実行では 133 名の呼出 0 (起動経路は 17 unit まででレジストリ・ファイル系大半に未到達) — REPORT のとおり T9 (CAB-176) の unit 完走後の後続 |

### 9.2 「CAB-129 修正後、--fix なし純リンクで 17 unit 再測」の再現手順 (1 コマンド)

```
bash tools/shimx/scripts/rem11_check.sh
```

1. `tools/m11/shimx_link/build.sh --trace --soft` — **IR 無改変・--fix 一切無し** のトレース付き純リンク (signature mismatch 0 / undefined 0 / duplicate 0 を build ログで確認)
2. `run_trace.mjs` で起動実行 (`SHIMX_TRACE=1`) → `tools/shimx/work/rem11/m11_sx_trace_soft.run.json`
3. 判定基準 (M11 REPORT §0/§3-#2 の実測と対応):
   - **真の 17 unit 完走** = `init_count >= 18` (unit #18 に進入) かつ `longjmp_hit == 0` (unit #18 OOB で停止するのが期待値)
   - **偽の DllMain 完走** (CAB-129 未修正の現状) = `init_count == 17` かつ `longjmp_hit == 1` かつ `boot_rc == 1` — shadow stack 破壊による Halt0
   - **2026-10-10 実測 (CAB-129 未修正)**: `init_count=17, longjmp_hit=1, boot_rc=1, threw=null` = 偽の完走 (既知到達点どおり。shimx 呼出 17 種 / 27 回)。CAB-129 修正後に同コマンドを再実行し判定行が「真の 17 unit 完走」に変わることを確認する
4. 同スクリプトが `reach_check.py` で R8 進捗 (133 名のうち本実行で呼ばれた名) を `tools/shimx/work/rem11/reach_progress.md` に出力

前提: `bash tools/m11/m11_e2e.sh` 済みの M11 成果物 (`tools/m11/work/boot_final3.ll` 等)。`tools/m11/shimx_link/` の tracked ファイルは読取のみ (成果物は同 dir の work/ = gitignore)。

### 9.3 ir_undef.py 変更の M11 外部参照数への影響 (再計測)

| IR | 旧分類 (変更前実測) | 新分類 (本変更後) | 差分 |
|---|---|---|---|
| boot_final2.ll (557) | shimx 183 / lifter 203 / win_other 171 / unknown 0 | shimx **182** / **shimx_dup 1** (`SHGetFolderPathW.1`) / lifter 203 / win_other 171 / unknown 0 | shimx 183→182+dup1 (合計不変)。`NAME.1` が署名不一致の恐れがある別シンボルとして明示化され、`--emit-stubs` がスタブを吐く/`--normalize-dup` で正規化できるように |
| boot_final3.ll (570) | shimx 184 / lifter 214 / win_other 171 / unknown 1 (`SHGetFolderPathW_D1`) | shimx **184** / **shimx_dup 1** / lifter 214 / win_other 171 / unknown 0 | unknown 1→0 (同上の rename 後形式も同一扱い)。合計不変 |

外部参照総数 (557/570)・GUI 171・lift 由来は不変。`--emit-stubs` は `win_other + unknown + shimx_dup` を対象に変わったため、旧版で取りこぼしていた重複 declare 分のスタブが生成される (172 本 @boot_final3, 旧 171 本相当 + 1)。

### 9.4 CAB-166 `--fix` の取り込み状況

| --fix 構成要素 | 取り込み | 補足 |
|---|---|---|
| `cb_adapt.c` (列挙コールバック変換) | **置換完了 (CAB-177)** | R2 の `shimx_set_callback_translator` が恒常フック口。VA→トランポリン変換の実体は **`src/cbtrans.c` (§10)** として shimx 側に恒久実装し、link 側は `sx_cbboot.c` (constructor で invoke+translator+resolver を登録) だけになった。**tools/m11/shimx_link/cb_adapt.c は削除** (--wrap=Enum* も廃止)。M11 純リンクへの接続実測は §10 |
| `fix_alloca.py` (alloca 拡幅) | **意図的保留** | lift IR の縮退 alloca 修復で shim の担当外 (CAB-129 の本修正待ち)。`--emit-stubs`/`--normalize-dup` は IR を書くが構造体署名の正規化のみで alloca 構造には触れない |
| `sx_liftfix.c` (`_WStrClr` C 転記) | **部分取り込み (症状緩和)** | 論理修復 (2 段 deref) は lift 側のまま保留。ただし R5 の所有表により、誤ったポインタを `SysFreeString` に渡しても abort しなくなり、純リンク時の同症状は無害化される (次回 §9.2 の再測で確認) |

## 10. R2/R3 実体接続 — cbtrans (CAB-177 / SHX-T2 hostbridge 接続)

CAB-211 のフック口の**変換実体**を `src/cbtrans.c` として恒久実装し、M11 純リンク (CAB-129 ビルド) と
検証ハーネスへ接続した。**詳細 (設計/寿命契約/接続手順/実測/未対応・CAB-101 引継ぎ) は
`tools/hostbridge/cb/REPORT.md`** と `src/cbtrans.c` 冒頭コメント、往復検証は `test/test_cbtrans.c` (MT/ST)
+ `tools/hostbridge/cb/cb_e2e.sh` (MT 15 / ST 12 checks, exit 0)。

- **R2**: guest VA (≥intptr_limit) → 型付き slot トランポリン (6 形 × 64 slot) → **invoke 契約**
  `u64 invoke(u64 va, u64 a0..a7)` (= `m11_icall` 或いは `__icall_dispatch` 関数表+BLK 方式) で lift 側関数表へ。
  未知 va は 0 返し (closure 外でも trap しない)。`cb < intptr_limit` は実 C 関数ポインタの恒等通過 (M4 互換)。
  **寿命契約**: 翻訳は 7 API の登録時に 1 回 / slot は**プロセス寿命で解放しない** → 非同期系
  (CreateThread/FlsAlloc/タイマ/スレッドプール) も安全 (同一 VA = 常に同一トランポリン)。
- **R3**: shell32 IL* 10 本 + kernel32 UI言語 3 本を **lift ABI トークン** (0x7F000000+index) 化する
  `shimx_lifttab_*`。proc_resolver 接続で GetProcAddress がトークンを返し、lift dispatch 側は
  `shimx_lifttab_trampoline(token)` (u64×8 → 実 C 署名 thunk) で実体呼出 (M11 = `--wrap=m11_icall`)。
- **接続手順**: `shimx_cbtrans_set_invoke(<m11_icall 相当>)` → `shimx_cbtrans_install()` →
  `shimx_set_proc_resolver(shimx_lifttab_proc_resolver)`。実装例 = `tools/m11/shimx_link/sx_cbboot.c`。

**M11 純リンク実測**: init_count=18 / longjmp_hit=0 維持、threw が **"table index is out of bounds" →
"memory access out of bounds"** (CAB-231 既知 OOB に進行, 後退なし)。icall_ok/miss = 19/**1**。ビルド 5 variant
とも mismatch/undefined/duplicate **0**。survey 942 unit は **800/41/53 不変**。R3 の 13 名は survey で
**トークン解決** (GetProcAddress miss 消滅)。

