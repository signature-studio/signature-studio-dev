# REPORT — hostbridge/cb: shimx R2 コールバック変換の実体接続 (CAB-177 / SHX-T2)

- 日付: 2026-10-10 / 環境: emcc 6.0.12, node 24.19 (emsdk 同梱) / 検収: **`bash tools/hostbridge/cb/cb_e2e.sh` = exit 0** (MT 15 checks + ST 12 checks)
- 関連: CAB-211 (フック口, Done) / CAB-89 (`__icall_dispatch` 関数表+BLK = VA→関数解決の正本) / CAB-129 (純リンク init_count 18) / shimx REPORT §10
- 書込範囲: `tools/hostbridge/cb/` (新規) + `tools/shimx/` (cbtrans 実体・テスト) + `tools/m11/shimx_link/` (接続 boot)。`tools/icall` `tools/liftlib` `tools/m11/alloca` `tools/m11/ldfix` は読取/実行のみ (改変 0 行)

## 0. 結論 (先出し)

| 項目 | 実測 |
|---|---|
| R2 トランポリン実体 | `tools/shimx/src/cbtrans.c` (新規)。`shimx_set_callback_translator` の変換実装: guest VA → **型付き slot トランポリン** (6 形 × 64 slot) → **invoke 契約** `u64 invoke(u64 va, u64 a0..a7)` で lift 側関数表 (`__icall_dispatch` 関数表+BLK 方式 或いは `m11_icall`) へ。未設定時は恒等 (既存挙動不変) |
| EnumCalendarInfoW 正式化 | 暫定 `cb_adapt.c` (--wrap=Enum* 2 API・単一 global) を**削除**し、フック経由の恒久機構に置換。M11 純リンク unit 18 の実測コールバック `0x4476d0` が trampoline 経由で実呼出され **"table index is out of bounds" trap が消滅** |
| 純リンク回帰 (CAB-129 ビルド) | init_count **18** / longjmp_hit **0** 維持、threw は **"memory access out of bounds"** (= CAB-231 の既知 `_UStrAsg` OOB に進行, 後退なし)。ビルド 5 variant とも **mismatch 0 / undefined 0 / duplicate 0**。survey 942 unit = **ok 800 / oob 41 / halt0 53 (不変)** |
| R3 実体接続 | `shimx_lifttab_*`: shell32 IL\* 10 本 (序数 16/17/18/19/21/25/152/153/155/190) + kernel32 UI言語 3 本を **lift ABI トークン** (0x7F000000+index) 化。proc_resolver 接続で GetProcAddress がトークンを返し (survey 実測: unit 2 = `0x7f00000a`.. / unit 239 = `0x7f000000`..)、lift dispatch 側 `--wrap=m11_icall` + `shimx_lifttab_trampoline(token)` (u64×8 → 実 C 署名 thunk) で実体呼出 |
| 往復検証 | cb ハーネス (模擬 lift closure + shimx 実リンク): R2 7 API 全種の VA 登録→trampoline→lift fn→復帰、closure 外 VA の graceful、実 C ポインタ恒等、invoke の BLK 方式差し替え、非同期 4 種 (MT)、R3 トークン 3 往復 (ILGetSize=14 / ILIsEqual=1 / GetThreadUILanguage=0x409) |
| shimx test.sh | **exit 0 維持** (MT/ST/fail-fast 8 モード/M4 53/53/署名突合 0/OTT t1 SHA 一致)。公開 604 + フック **53** (exports.txt 658) |

## 1. 成果物

| パス | 役割 |
|---|---|
| `tools/shimx/src/cbtrans.c` | R2 実体 (slot トランポリン + invoke 契約) + R3 lifttab。`shimx_cb_translator` / `shimx_cbtrans_{set_invoke,install,slots,calls,reset}` / `shimx_lifttab_{token,proc_resolver,trampoline}` |
| `tools/shimx/test/test_cbtrans.c` | 模擬 lift closure (VA 関数表 + uniform u64×8 ABI + BLK 方式) による単体検査 (MT/ST) |
| `tools/m11/shimx_link/sx_cbboot.c` | **M11 純リンクへの接続 boot** (constructor): invoke=m11_icall + install + proc_resolver + `__wrap_m11_icall` (token→thunk→`__real_m11_icall`) |
| `tools/m11/shimx_link/build.sh` | `-Wl,--wrap=m11_icall` 追加 / cb_adapt 廃止 (全 variant で R2/R3 接続が有効) |
| `cb_mod.c` / `cb_harness.mjs` / `cb_e2e.sh` | 本ハーネス: shimx 全ソース + 模擬 lift closure の実リンク module を MT/ST ビルドし node で駆動 |

`tools/m11/shimx_link/cb_adapt.c` は git から削除 (置換完了)。`tools/shimx/pathreg/` には他担当 (CAB-213) の未コミット変更があるため本チケットのコミット対象外。

## 2. R2 設計と寿命契約 (確定版)

```
lifted コード (guest)              shimx (cbtrans)                      lift 側関数表
EnumCalendarInfoW(0x4476d0) ─► shx_translate_cb ─► shimx_cb_translator
                                   cb=0x4476d0 ≥ 0x10000 (intptr_limit)
                                   → slot 割当 (同一 VA は同一 slot)
                                   → 型付きトランポリン返却 (i1 形)      m11_icall / __icall_dispatch(BLK)
                                   shimx がトランポリンを呼ぶ ────────► invoke(va, a0..a7) → lift fn 本体
                                 戻り値が shimx API を通って guest へ ◄┘
```

- **invoke 契約**: `u64 invoke(u64 va, u64 a0..a7)`。tools/icall の `__icall_dispatch` (関数表+BLK, FLEngine
  closure の正本) も M11 の `m11_icall` も同形に載る。**未知 va は 0 返し** (= 列挙の穏当な打切り。closure 外
  コールバックで trap しない — M11 の 0x4476d0 がまさにこの経路)。登録は link 側 1 行
  `shimx_cbtrans_set_invoke(m11_icall)`。
- **判別**: `cb < shimx_get_intptr_limit()` (R1 と共通の 1 変数, 既定 0x10000) = 実 C 関数ポインタ
  (wasm テーブル index は小整数) → **恒等通過** (M4 互換テスト・既存直接 C 呼出を壊さない)。
  `≥ limit` = guest VA → トランポリン。M11 のコード VA は 0x401000〜、lowbase 敷設は LB_BASE=0x10000〜 で分離。
  隣接する構成では `shimx_set_intptr_limit()` で調整 (R1 と同一操作)。
- **型付き 6 形**: shimx がコールバックを呼ぶ wasm 署名に一致させる (Enum*・CreateThread = (i32)→i32、
  EnumCalendarInfoW = shimx typedef により 1 引数、FlsAlloc = (i32)→void、タイマ = (i32,i32)→void、
  スレッドプール = (i32,i32,i32)→void、InitOnce = (i32,i32,i32)→i32)。形状不明 API は fail-fast
  (誤った形状を返すと call_indirect 署名不一致 trap になるため)。

### 寿命契約 (tools/shimx/REPORT.md §5 の前提を以下のとおり実装で固定)

| 項目 | 契約 |
|---|---|
| 翻訳タイミング | shimx がコールバック引数を取る **全 7 API の登録時に 1 回** (CAB-211 検収コメントの契約どおり)。shimx は戻り値 (トランポリン) を保持し以後使う |
| **slot 寿命 = プロセス** | 割当てた slot は解放しない (同一 VA は常に同一トランポリン)。よって同期系 (Enum*・InitOnceExecuteOnce = 呼出中のみ有効) はもちろん、**非同期系 (CreateThread / FlsAlloc / CreateTimerQueueTimer / CreateThreadpoolWork = shimx オブジェクトが保持し続ける) でもトランポリンが無効化されない** |
| コスト | 登録 distinct VA 数 × slot (上限 64, 単調増加)。満杯は fail-fast。実測: M11 起動 + survey 942 unit で **2 slot** / cb ハーネス MT で 9 slot |
| スレッド | slot 割当は専用 futex mutex (MT の任意スレッドから登録可)。invoke 差し替えは登録前に推奨 (実行中差し替えも動作 — cb ハーネス `g_route_switch` で検証) |
| 解放 | `shimx_cbtrans_reset()` はテスト専用 (運用で呼ぶと非同期系の保持中トランポリンが無効化される) |

## 3. R3: lift ABI トークン表

- **トークン** = `0x7F000000 + index`。wasm メモリ上限 (M11 ビルド max 0x72000000) の外側で実ポインタと
  非衝突。guest には「コード VA のように見えるが実体は lifttab のエントリ番号」として渡る。
- **resolver**: `shimx_set_proc_resolver(shimx_lifttab_proc_resolver)`。shell32 は序数/名前両方、kernel32 は
  名前 (モジュール判定は新設内部ヘルパ `shx_mod_name()`)。対象外は NULL を返し従来経路 (組込み表 = C ポインタ)。
- **dispatch 側**: `shimx_lifttab_trampoline(token)` が **u64×8 → 実 C 署名の marshal thunk** を返す
  (IL* 9 種 + UI言語 3 種 + ILFree)。M11 純リンクでは `-Wl,--wrap=m11_icall` (sx_cbboot.c) で
  token → thunk → 実体、それ以外は `__real_m11_icall`。
- **現行 M11 IR の制約**: RetDec 系 lift は間接 call を IR に残さないため、トークンの実呼出は現状発生しない
  (値が格納されるのみ)。icall 復元 route (CAB-89) を採用する lift では `__icall_dispatch` の lookup 失敗後に
  `shimx_lifttab_trampoline` を引く 1 行で接続できる。**往復の実証は本ハーネスと test_cbtrans で完了済み**。

## 4. 実測

### 4.1 cb ハーネス (`bash tools/hostbridge/cb/cb_e2e.sh`, 常時 exit 0)

| 検査 | MT | ST |
|---|---|---|
| constructor boot / R2 EnumCalendarInfoW 往復 (VA 0x4476d0) / EnumSystemLocalesW 往復 / closure 外 VA graceful / InitOnce (2 度呼びで fn 1 回) / 実 C ポインタ恒等 / BLK route (`__icall_dispatch` 形) 差し替え / FlsAlloc 往復 | OK ×8 | OK ×8 |
| CreateThread (start VA, rc=42) / CreateTimerQueueTimer (≥2 回発火) / CreateThreadpoolWork (第3引数=work 自身) | OK ×3 | SKIP |
| R3 トークン 3 往復 (ILGetSize=14 / ILIsEqual=1 / GetThreadUILanguage=0x409) | OK | OK |
| 統合 (slot 数 = distinct VA / calls = invoke ok+miss / lifttab 13 entries) | OK ×4 | OK ×4 |
| **合計** | **15/15** | **12/12** |

### 4.2 M11 純リンク (CAB-129 ビルド; `tools/shimx/scripts/rem11_check.sh` + `tools/m11/shimx_link/e2e.sh`)

| 項目 | 接続前 (CAB-129 検収時) | 接続後 |
|---|---|---|
| 純リンク起動 (`--trace --soft`) | init_count=18 / threw=**table index is out of bounds** | init_count=**18** / longjmp_hit=**0** / threw=**memory access out of bounds** |
| 停止点 | EnumCalendarInfoW 内の call_indirect trap | `function_4133f0` (_UStrAsg) OOB = **CAB-231 の既知停止点** (44bb70→446400→4133f0。スタックに `__wrap_m11_icall` が見える) |
| icall_ok / miss | 19 / 0 | 19 / **1** (closure 外 0x4476d0 graceful skip) |
| ビルド 5 variant | mismatch/undefined/duplicate 0 | **0 (全 variant 不変)** |
| survey (trace_soft_fix) | ok 800 / oob 41 / halt0 53 | **800 / 41 / 53 (不変)** |
| 17 unit 区間の shimx 呼出 | 25 種 41 回 | 25 種 **91 回** (unit 18 が trap 無しで先へ進んだ分。旧 --fix ビルド 94 回と同水準。`GetLocaleInfoW` 48 回含む = shimx_link REPORT §4.2 と一致) |
| R3 (SHIMX_TRACE) | GetProcAddress miss: UI言語 3 名 + shell32 序数 9 名 | **13 名がトークン解決** (`[shimx] lifttab: … -> token 0x7f00000x`)、miss 消滅。残 miss は既知の `kernel32.dll!#39682` / 空名のみ |
| cbtrans トレース | — | `[shimx] cbtrans: EnumCalendarInfoW VA 0x4476d0 -> trampoline slot 0` / `VA 0x4477a0 -> slot 1` |
| --fix の fix_alloca | 23 関数拡幅 | **0 関数** (CAB-129 pass が boot_final3.ll に適用済みで拡幅対象が残っていない = 正常。survey 不変) |

## 5. 接続手順 (下流ビルド共通 — 3 行 + wrap 1 個)

```c
shimx_cbtrans_set_invoke(<m11_icall 或いは __icall_dispatch(BLK) 相当>);  // lift 側 VA→関数解決の正本
shimx_cbtrans_install();                                                 // translator フックに実体を取付
shimx_set_proc_resolver(shimx_lifttab_proc_resolver);                    // R3: IL*/UI言語 → トークン
// + リンク: -Wl,--wrap=<invoke 関数> の wrapper 冒頭で shimx_lifttab_trampoline(token) を引く
```

実装例: `tools/m11/shimx_link/sx_cbboot.c` (constructor, 全 variant) / `tools/hostbridge/cb/cb_mod.c` `cb_boot()`。
確認: `SHIMX_TRACE=1` で `[shimx] cbtrans: … trampoline slot N` と `[shimx] lifttab: … -> token 0x7f0000xx`。

## 6. 未対応範囲 / 制限

1. **トークン実呼出 (現行 M11 IR)**: 間接 call 未 lift のため発生せず (icall 復元 route 採用時に 1 行で有効化)。
2. **lifttab 13 本のみ**: 対象拡大は 1 thunk/本の機械作業 (組込み表の全 604 本自動生成は未着手)。
3. **EnumCalendarInfoW の CALID 第 2 引数**: shimx の `CALINFO_ENUMPROCW` typedef が 1 引数 (実装簡略)。
   実影響は現状なし (コールバック本体が closure 外のため)。
4. **COM vtable / 一般 i64↔i32 規約ブリッジ**: 本チケットは R2/R3 の関数ポインタ経路のみ。COM vtable は
   lowbase/h2 の構造マーシャリング経路 (別担当)。
5. **64 slot 上限**: distinct コールバック 64 で fail-fast (実測最大 9)。FL 実機で溢れる場合は定数増加のみ。

## 7. CAB-101 (startup glue) への引継ぎ

- **初期化列に 3 行** (`tools/m11/shimx_link/sx_cbboot.c` が完全な雛形): invoke 登録 (そのビルドの lift 関数表
  解決関数) → `shimx_cbtrans_install()` → `shimx_set_proc_resolver(shimx_lifttab_proc_resolver)`。
- **タイミング制約なし**: slot は登録時解決なので boot 前の登録でも動く (constructor 実績)。ただし
  invoke は「lift 関数表が解決可能になった後」に呼ばれるので、boot 順序は lift IR 初期化より後を推奨。
- **回帰手順**: `bash tools/shimx/test.sh` (exit 0) + `bash tools/hostbridge/cb/cb_e2e.sh` (exit 0) +
  `bash tools/shimx/scripts/rem11_check.sh` (init_count≥18 判定)。

## 8. 再現

```sh
bash tools/hostbridge/cb/cb_e2e.sh            # 本ハーネス (MT 15 + ST 12 checks, exit 0)
bash tools/shimx/test.sh                      # shimx 全検収 (test_cbtrans.c 含む, exit 0)
bash tools/shimx/scripts/rem11_check.sh       # M11 純リンク回帰 (init_count≥18 判定)
bash tools/m11/shimx_link/e2e.sh              # 5 variant + survey + 集計
node tools/hostbridge/cb/cb_harness.mjs tools/hostbridge/cb/work/cb_mt.cjs --out tools/hostbridge/cb/work
```

前提: emsdk 6.0.12、`bash tools/m11/m11_e2e.sh` 済みの M11 成果物 (rem11/e2e のみ)。
ユーザ依頼事項: なし。
