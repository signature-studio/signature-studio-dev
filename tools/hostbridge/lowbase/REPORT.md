# REPORT — lowbase (CAB-90 / HB-H1): lift 済みコードの VA 敷設 base を plugin 毎に低位・小 memory へ可変化

## 0. 結論 (先出し)

- **判定: 完了条件を満たす。** `bash tools/hostbridge/lowbase/lowbase_e2e.sh` = **ALL PASS (約 65 秒, 全ビルド込みでキャッシュ不要)**。
  OTT の V-shift 先を引数 `LB_BASE` (既定 `0x10000`) 化し、wasm の **initial memory を 864 MiB → 16 MiB (x64c 版) / 24 MiB (RetDec 版 = hostbridge の OTT module)** に低下 (x64c は 8 MiB でも 89/89 通過)。max は 64 MiB。
- **方式: (a) lift 時定数 shift を採用** (+ (b) の GLOBAL_BASE 配置で image 用の低位 hole を確保)。(c) 実行時 MemBase 相対は全 load/store に加算が要り不採用 (§2)。
- **bit-exact 側 (tools/ott の自作 lifter x64c)**: base `0x10000`(16 MiB) と `0x1230000`(40 MiB) の 2 通りで **native 実機械語 vs wasm の 89 scenario・全 cell bit-exact (max_ulp 0, 最終 heap/obj state 差 0 qword・正本 `tools/ott/REPORT.md`)**。8 MiB probe も同値 (計 3 構成 × 89 scenario = 267 run・全 cell 一致, 不一致 0)。
- **hostbridge 側 (RetDec chain = 既存 PoC の OTT module)**: 検収 65 項目相当 (evidence 21 + PE stub 3 + marshal 13 + **PoC 28 を lowbase module で実行**) = **65/65 PASS**。
  `[0x248]=0` 条件は M10 の 864 MiB module (再配置前) と **512/512 bit 一致** (T4c)。自然経路 (`[0x248]=1`) は 500 blk × 256 cell = 128,000 cell 中 **2 cell のみ差分 (|v|≤7.3e-34 の junk-tiny)**。
  image/arena だけ低位化し heap/stack 位置を旧のままにすると **0/128,000 差分** (§4.3) = 差分は VA 再配置ではなく RetDec chain の junk (未初期化読み) が stack/heap 絶対位置に依存するため。x64c 版は address 非依存で bit-exact。
- **複数同時ロード**: 同一 hostbridge ホスト + HostBridge 1 つに **OTT×4 (各専用 memory) + Balance kernel (別 DLL・別 lift 系統)** を同居。linear memory 合計 **3,456 MiB → 96 MiB (+4 MiB)**、プロセス VmData(commit) 増分 **3,465 MB → 105 MB**。出力: 4 module の 500 blk × 128f sha256 が全一致、Balance は native 機械語と 768/768 cell 一致。
- **SAB ring → AudioWorklet と Worker の `Atomics.wait` RPC による `VSTPluginMain` 往復も Chrome で通過** (#1174, §10)。消費量・総和・先頭出力ビットが node 参照と一致。
- **headless Chrome (154) の dedicated Worker** でも同一 module がロードでき、OTT 出力 sha256 が node と一致。追加 100 instance を 684 ms で生成 (計 105 Memory)。上限 probe: 追加 118 個 (計 123 Memory) で `Out of memory: Cannot allocate Wasm memory` = CAB-124 の約 124 個上限と同じ (initial/max に依存しない仮想予約制約)。
- **同居方式も実証**: 同一 DLL を base A=`0x10000` / B=`0x400000` + 接頭辞 `a_`/`b_` で **1 wasm・1 linear memory (24 MiB)** に載せ交互駆動し 512/512×2 一致 (Memory 個数上限を回避する経路)。

## 1. 現状把握: 絶対 VA の焼き込み箇所 (実測)

| 層 | x64c (tools/ott/lift) | RetDec chain (m6〜m10 → hostbridge) |
|---|---|---|
| 命令中の VA | `sh()` が ea/imm/jump table/`ott_dispatch` case に適用。x64c は `SHIFT` を module 変数で持つ (**無改変で差替可**)。lift C 中の image 範囲リテラル 769 件 (distinct 628) | IR の `@global_var_<va>` 名 **582 件** + `i64` 直値 **37 件** (全て address と手確認: inttoptr 21 / store 12 (関数ポインタ値・image base) / call 引数 4) |
| 関数ポインタ・vtable | `.rdata/.data` の **DIR64 reloc 13,000 件** (rdata 12,329 + data 671) を data_gen が補正 | 同左 (m6_data.c を `--m6` モードで再生成, 旧 m6_data.c と 0x30000000 指定で **バイト同一** を確認) |
| 関数名 | `f_<va>` は元 VA (ラベルのみ。image 位置と無関係) | `function_<va>` 178 define も元 VA。image 位置と無関係 → 衝突回避は prefix (§3) |
| IAT スロット | **375 スロット全て VA を持たない** (RVA)。import は `imp_*` 直呼出に落ちる | 同左 |
| 固定アドレス直書き (C ランタイム) | `ott_cpu.c` の alloc log `0x35f00000` → 静的配列化。ハーネスの `0x3031xxxx` → ARENA 相対 | `M6base`/`M8BASE`/hand stub の `0x30000000`、`m8_ptr_ok` 上限 `0x36000000`、`m10_boot` scratch `0x35e00000`、`plugin_ott_entry.c` の `HB_ARENA 0x30400000` |
| reloc 外の image 範囲 qword | 2 件 (`0x1_80000029` の bitfield 対。PE ローダも触らない非ポインタ) | 同左 |
| 取りこぼし | audit_va.py: DIR64 先 image 外 0 / IAT に VA 0 / 診断専用の 0x18… リテラル 554 件は全て `ott_unsup`/`ott_badjump` 引数 | 同左 |

元の V-shift は `0x180000000→0x30000000` (SizeOfImage 0x308000)。image は 0x30000000..0x30308000 にあり、ARENA/heap/stack も 0x30400000+ に置いたため initial=max=0x36000000 (864 MiB) だった。

## 2. 方式比較

| 候補 | 内容 | 評価 |
|---|---|---|
| **(a) lift 時 shift (採用)** | 全 VA 定数/名/data 内ポインタを `LB_BASE+RVA` に平行移動。x64c は SHIFT 差替のみ、RetDec 版は最終 IR/C のリテラル再配置 (`lb_reloc.py`) | 実行時コスト 0。base の変更は再 lift 不要 (再配置 + emcc のみ, いずれも数秒)。per-plugin に別 base を割当てれば 1 memory 同居も可 (§3.2)。欠点: base は build 時固定 |
| (b) emcc GLOBAL_BASE / wasm-ld 配置 | 単独では不可: GLOBAL_BASE は emscripten の静的データ先頭を決めるだけで、コード中の即値 VA は動かない | 補助として採用: `LB_GLOBAL_BASE` を image+arena の後ろに置き、`[0, GLOBAL_BASE)` の hole に PE image を install (§3.1 レイアウト) |
| (c) 実行時 MemBase 相対 | 全 load/store/inttoptr に `+membase` を足す IR pass、または base 毎に wasm を再生成 | x64c は `LD64(R[RSP])` 等の全メモリ操作に加算 → 速度低下、IR pass 規模が (a) より大。DLL 1 本 = 1 Memory では base を動的に変える利点が無い (どの DLL も同じ 0x10000 でよい) |
| PE 全体敷設型 (m11) | FLEngine は ImageBase 0x400000 / SizeOfImage 0x18c0000 (24.75 MiB) で 4 GiB 内。m11 は LVA=RVA (base 0) + GLOBAL_BASE 256 MiB。 | shift 不要だが **LVA=RVA だと DIR64 reloc 278,531 件中 55,929 件 (20%) の対象が <0x10000** になり shimx の序数判定 (<0x10000=整数) と衝突しうる (audit_va.py 実測, m11 未実行)。`LB_BASE=0x10000` (LVA=RVA+0x10000) を推奨 (integration.md) |

## 3. 実装 (成果物)

### 3.1 レイアウト (`lb_layout.py`: 全ビルド/ハーネスの唯一の定義)
`0..LB_BASE` 未使用 (≥0x10000 → shimx の序数誤認回避, assert) / `LB_BASE..+SizeOfImage` PE image / `LB_ARENA` (固定アリーナ) / `LB_GLOBAL_BASE` 以降 static→stack→heap。
例 (OTT, 既定): image `0x10000..0x318000`, arena `0x320000`, GLOBAL_BASE `0x420000`(x64c) / `0x440000`(RetDec), initial 16/24 MiB, max 64 MiB。

### 3.2 スクリプト
| パス | 役割 |
|---|---|
| `x64c/lb_x64c.py` | tools/ott/lift/x64c.py を **無改変 import** し `SHIFT` を差替え。`--prefix P` で `f_<va>`→`P_f_<va>`・`ott_dispatch`→`P_dispatch` |
| `x64c/lb_data_gen.py` | data_gen の BASE 引数版 (DIR64 補正 13,000 件)。`--m6` で RetDec chain 互換 (`m6_data_install`, rdata/data のみ) |
| `x64c/build_x64c.sh` | x64c 版 1 コマンドビルド (`LB_BASE`/`LB_INIT_MIB`/`LB_MAX_MIB`/`LB_PREFIX`)。`-sINITIAL_MEMORY` で `initial-heap` 既定 16 MiB を無効化 |
| `x64c/rt/ott_cpu.c` | alloc log 固定アドレス → 静的配列 + `ott_alog_addr()` (他は tools/ott/rt を直接参照) |
| `x64c/diff/*` | tools/ott/diff の matrix/scen2_* を base・arena 引数化。native は python が低位 VA (0x400000..) を占有するため **heap/arena を一様に +0x40000000 平行移動して再生** し `nq()` で逆変換 (像ポインタも V-shift 逆変換) |
| `x64c/build_x64c_coresident.sh`, `coresident_test.mjs` | 2 DLL 同居 (別 base + prefix) |
| `retdec/lb_reloc.py` | 既存最終 IR (`ott_m10.ll`) と C ランタイムのリテラル再配置 + prefix + 監査 JSON。m6〜m10 の中間パス (SHIFT_BASE が散在) は触らない |
| `retdec/build_m10_lb.sh` | hostbridge の OTT module (m10 chain + `plugin_ott_entry.c` surrogate) を再配置コピーから emcc。`HB_ARENA` は `-DLB_ARENA_ADDR` |
| `retdec/build_bal_lb.sh`, `multi/plugin_bal_entry.c` | Balance mix kernel (tools/plugins t0_balance の IR) + VST2 facade = 2 つ目の module。image 非参照なので shift 不要 (GLOBAL_BASE 64 KiB, initial 4 MiB) |
| `hb/derive_poc.py` | `poc/run_poc.mjs` から lowbase 版を **機械派生** (固定 VA→ARENA 相対のみ置換, 当らなければ失敗) |
| `multi/multi_load.mjs`, `chrome_worker.mjs`, `run_chrome.mjs`, `compare_dumps.py` | 同時ロード試験 (node / Chrome Worker) と比較 |
| `audit_va.py` | VA 整数の静的監査 (DIR64 / IAT / base≥64KiB) |
| `lowbase_e2e.sh` | 1 コマンド再現 |

## 4. 実測

### 4.1 メモリ (before → after; `wasm-objdump` / `memory.buffer.byteLength` / `/proc/self/status`)
| module | initial memory 前 → 後 | 備考 |
|---|---|---|
| OTT x64c (tools/ott) | 864 MiB (0x36000000) → **16 MiB** (8 MiB でも通過; リンク下限 8.3 MB) | max 864 → 64 MiB, 別 base `0x1230000` は 40 MiB |
| OTT RetDec (hostbridge) | 864 MiB → **24 MiB** | STACK 8 MiB は旧と同一 (純再配置)。max 64 MiB |
| Balance kernel (t0_balance) | 288 MiB (0x12000000) → **4 MiB** | PE image 非参照 |
| OTT×4 + Balance (node, 1 host) | linear 合計 3,456 MiB → **96 MiB (+4)**; VmData 増分 **3,465 → 105 MB**; RSS はほぼ同等 (≈96〜99 MB; touched page のみ計上されるため元々小さい) | VmSize は module 当り約 8 GiB 増 (guard 領域; initial/max 非依存) |
| 同居 (OTT×2, 1 wasm) | **24 MiB** (別 memory 2 個なら 32 MiB) | Memory 個数を 1 に |
| Chrome Worker | OTT 100 instance 追加 = 2,400 MiB を 684 ms で生成 | 旧 864 MiB×100 = 84.4 GiB の commit が必要 (未試行) |

### 4.2 出力一致 (件数 / 試行数)
| 検査 | 結果 |
|---|---|
| x64c vs native 実機械語 (matrix.py), base 0x10000 / 0x1230000 / 0x10000-8MiB | 各 89/89 scenario・全 cell bit-exact (計 3 構成, max_ulp 0, state_diff 0 qword・正本 `tools/ott/REPORT.md`) |
| x64c 4 module 同時 (base 0x10000×3 + 0x1230000) 標準 scenario | 512/512 ×4 (native 一致済み単体出力と比較) |
| x64c 同居 1 memory (base 0x10000 / 0x400000) | 512/512 ×2 |
| hostbridge 検収相当 (lowbase module) | evidence 21 + stub 3 + marshal 13 + PoC 28 = **65/65** (PoC 28 には T4a「bridge=直接 512/512」、T4c「M10(864 MiB) と 512/512」、T5 A/B 交互 2×128、T6〜T8 を含む) |
| OTT×4 の module 間 (500 blk×128f) | sha256 全 4 module 一致 (1/1) |
| Balance kernel vs native 機械語 (3 gain set, hostbridge 経由) | 768/768 cell |
| Chrome Worker vs node | OTT sha256 一致, Balance block0 sha256 一致 (C1〜C4 全 OK) |
| prefix 版 (`ott_function_*` 658 名, 無接頭 export 0) vs 無接頭 | 0/128,000 cell 差 |

### 4.3 RetDec chain の「再配置前との差 2 cell」の切り分け
| 構成 (500 blk×128f×2ch = 128,000 cell) | 再配置前との差分 cell |
|---|---|
| E0 恒等再配置 (base 0x30000000, 旧レイアウト) | 0 (パイプラインが忠実) |
| E1 image=0x10000 のみ低位 (arena/heap/stack 旧) | 0 |
| E3 image=0x10000 + arena=0x320000 (heap/stack 旧) | 0 (e2e [3b] で毎回検査) |
| **lowbase 全体 (+ GLOBAL_BASE=0x440000)** | **2** (block0 の L[2],L[3]: 旧 `0x0831a2e4`/`0x887258d0` ⇔ 新 `0x64`/`0x80000088`, |v|≤7.3e-34) |
→ 再配置リテラルの誤りではなく、RetDec chain が **未初期化メモリを読む junk** (tools/ott REPORT D1〜D6) の値が stack/heap の絶対位置に依存するため。|v|max 8.5e37 の junk-high を含む 128,000 cell 中 127,998 cell は新旧一致。x64c は同じ試験で address 非依存 (bit-exact) なので、正解側 lift を使う限りこの現象は無い。

### 4.4 副作用の確認 (task 4)
- **GetProcAddress/序数判定**: shimx は値 <0x10000 を整数扱い。lowbase は `LB_BASE≥0x10000`・arena・GLOBAL_BASE がすべて ≥0x320000 のため、guest の有効ポインタは全て ≥0x10000 (lb_layout が assert)。
- **関数ポインタ値/vtable**: DIR64 13,000 件を補正、matrix で vtable 経由の仮想呼出 (x64c は dispatch switch) を含む 89 scenario が一致。IAT 375 スロットは VA を保持せず影響なし。
- **hostbridge の合成 VA**: `THUNK_BASE=0x7ff700000000` / `HMODULE_BASE=0x7ff6a0000000` は 4 GiB 外のため guest の低位 VA と衝突しない。AEffect ポインタは guest 側 u32 を 8B に拡張した値のまま (PoC T2h/T2i 通過)。
- **4 GiB 超仮定**: lowbase は全 guest アドレス < 64 MiB。wasm64 ビルド CI 雛形は作らず `tools/runtime/bench/build_ott_variants.sh` (ott32/ott64) を参照するのみ。lowbase の小 base はそのまま wasm64 へも持ち込める (Memory64 では initial/max 縮小が commit 削減に効く)。

## 5. 未解決・ブロッカー
1. RetDec chain の surrogate 依存 (`plugin_ott_entry.c`) は H2 の対象 (本チケット範囲外)。lowbase は `-DLB_ARENA_ADDR` で追従可。x64c 版は hostbridge 用の VSTPluginMain 入口が未作成 (H2 で作る時に `ott_run` を `hb_icall` へ接続すればよい)。
2. 同居方式 (§0 最終項) は CPU 状態 `R/X` を共有する逐次実行 (単スレッド) 前提。複数 AudioWorklet/Worker で同一 Memory を並行実行するには shared memory + 状態分離が要る (未着手)。
3. Chrome の RSS は他 chrome プロセス混在で信頼できず非掲載。Memory 個数上限 (計 123) は CAB-124 の領分で本チケットでは緩和できない (同居方式が回避経路)。
4. m11 (FLEngine) への適用は未実施: LVA=RVA で <0x10000 の reloc 先が 55,929 件ある (§2)。audit_va.py の IAT 判定は FLEngine で 738 slot が image 範囲値を持つと出たが、原因は hint/name RVA の誤判定と確定 (IAT に VA は無い。`../../m11/REPORT_N403.md` §1)。
5. `lb_reloc.py` は「0x30000000 系に shift 済みの成果」を後段で動かす近道。liftlib 統合時は最初から `newbase` 引数で作る方が堅い (integration.md)。

## 6. ユーザ依頼事項
特に無し。

## 7. 次タスク提案
- **H2 (CAB: OTT closure を VSTPluginMain まで)** は x64c 版 + lowbase を土台にする (JS `ott_run` → `hb_icall` 接続, SDK glue 部分は x64c で lift)。
- **liftlib 統合**: `newbase`=LB_BASE と `lb_layout` を `liftlib` の recipe 共通設定へ、`dataimage.py` の `0x400000 <= nt` フィルタ除去 (integration.md §A)。
- **m11 に LB_BASE=0x10000 適用検討**: audit_va.py を FLEngine に実行済みの数値を起点に、LVA=RVA+0x10000 化の影響範囲 (m11_image_gen/m11_data_gen) を評価。
- **CAB-124 連携**: 「DLL 1 本 = 1 Memory」で足りない数のプラグイン (Kilohearts 47 stub 等) に対し、同居方式 (prefix + base 割当表 + CPU 状態分離) の設計。

## 8. 再現
```sh
bash tools/hostbridge/lowbase/lowbase_e2e.sh            # 約 65 秒 (--no-chrome / --quick あり)
# 個別
LB_BASE=0x10000 bash tools/hostbridge/lowbase/x64c/build_x64c.sh
LB_BASE=0x10000 bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh
python3 tools/hostbridge/lowbase/audit_va.py <dll> 0x10000
```
前提: `tools/m10/work/ott_m10.ll`, `tools/hostbridge/work/ott_hb.cjs` (「再配置前」基準; `hostbridge.sh` の産物), `tools/plugins/work/balance/k.final.ll`, `tools/ott/work/libottnative.so`, python (capstone/pefile), emsdk, Chrome。tools/m6〜m10, ott, plugins, shim, hostbridge の既存ファイルは読取のみ (生成物は `lowbase/work`, gitignore 済み)。

## 9. HB-H24 (#974): ブラウザ実機検証の受入条件の対応 (2026-10-14 再測定)

- 測定 commit: `85e27fe2` (コードを変えた最後の commit。`lowbase_e2e.sh` の変更)。`git diff 85e27fe2 HEAD -- tools/hostbridge/lowbase ':!tools/hostbridge/lowbase/REPORT.md'` の出力は下記。測定後の差分は `lowbase_e2e.sh` のヘッダ 6 行目 (`#` のコメント行) の 1 行だけで、`#` 以外の行は `85e27fe2` と同一 (下の比較の出力は空)。

```diff
-#   所要: ビルド/試験すべて合わせて約 1〜2 分 (キャッシュ不要; 全ビルドは数秒)。tools/m6..m10, ott, plugins, shim, hostbridge の既存ファイルは読取のみ (生成物は lowbase/work).
+#   所要: ビルド/試験すべて合わせて約 1〜2 分 (キャッシュ不要; 全ビルドは数秒)。tools/m6..m10, ott, plugins, shim, hostbridge の既存ファイルは読取のみ (生成物は lowbase/work。ただし ott/work/libottnative.so は build.sh で毎回作り直す).
```

```sh
diff <(git show 85e27fe2:tools/hostbridge/lowbase/lowbase_e2e.sh | grep -v '^[[:space:]]*#') <(grep -v '^[[:space:]]*#' tools/hostbridge/lowbase/lowbase_e2e.sh)
```

- 再測定: 未実施 (この fix run の `$ARTIFACTS_DIR` は `fl-win64` のみで、`plugins-ott`・`work-m6-ott` が無く `lowbase_e2e.sh` を実行できない)。上の実測値は `85e27fe2` のもの。PR 本文に `oc_artifacts` 行を足したので、次の review run で素材付きの独立再実行を行う。
- 検証: `bash tools/hostbridge/lowbase/lowbase_e2e.sh` = **ALL PASS** (PASS 29 / FAIL 0)、所要 **92.7 秒** (全ビルド・Chrome 155 込み)。load average 0.70 (開始時)。
- 素材: `fl-win64` → `[WIN64]`、`plugins-ott` → `[ANALYSIS-PLUGINS]`、`analysis-ott-binaries`・`work-m6-ott`・`work-liftlib` (展開先は `docs/REFERENCES.md` 参照)。前提の `ott_hb.cjs` は `hostbridge.sh` (ALL PASS)、`k.final.ll` は `t0_e2e.sh` (357/357 × seed 3 種) で当 run に生成。

| # | 受入条件 (#974) | 実測 (Chrome/155・`work/chrome_result.json`・`work/ring/ring_result.json`) | 判定 |
|---|---|---|---|
| 1 | OTT lowbase を headless Chrome dedicated Worker で同期 `WebAssembly.Instance` 化し C1〜C4 PASS | C1 (OTT×4 + Balance が同一 host/bridge に LoadLibrary) OK / C3 (Balance block0 sha256 = node) OK / C4 (追加 100 instance 生成) OK 662 ms・linear 計 2,400 MiB | 達成 |
| 2 | OTT 出力 sha256 が node と一致 | C2: `4262907b2a26cd5d` = node (500blk×128f) | 達成 |
| 3 | OTT 出力を SAB ring 経由で AudioWorklet に流し消費量と総和が一致 | step [5] A3a/A3b: 消費 126,976 float (= 期待値)、総和 uint32 `1952270321` = node。実装は #1419 (§10) | 達成 (#1419) |
| 4 | Worker を SAB + `Atomics.wait` RPC で呼び出し、`VSTPluginMain` 経由の処理が往復 | step [5] A4/A4b: RPC 区間 24.8 ms、先頭 4 ブロックのビットが node と一致。実装は #1419 (§10) | 達成 (#1419) |
| 5 | 128 frame の 1 処理の実時間を実測 | C5: median **0.685 ms** / p99 0.880 ms / min 0.635 ms (n=1000, 50 回ウォームアップ後, OTT 単独 `effs[0]`) / 予算 2.902 ms (128/44100)。headless Worker 計測 (AudioWorklet 上の値ではない) | 達成 |

- 修正 (本 PR): `lowbase_e2e.sh` が `tools/ott/work/libottnative.so` を毎回 `build.sh` で作る。素材 `work-m6-ott` 同梱の版は `ott_enc_slots` を欠き、x64c matrix が 89/89 で `undefined symbol` により失敗していた。stale 版を戻して再現し、修正後の `85e27fe2` で ALL PASS。
- 旧記録 (PR 作成 run 38452251025・ログ未保存・Chrome 154・C5 median 0.820 ms) は本測定で置き換えた。前段として `9286a6bb` でも、素材 `.so` を手で作り直した状態で ALL PASS・C5 median 0.695 ms を得ている。
- §3 の wasm 名前空間検査の修正: `wasm-objdump` (runner に無い) の代わりに node の `WebAssembly.Module.exports` で数える。`ott_function_*` 211 件 / 無接頭 `function_*` 0 件。
- 経緯 (受入 3・4 は子 issue #1174 へ分割): AudioWorklet 側の SAB ring 消費と `Atomics.wait` RPC の新規実装が要った。RT-4 (#123) の「AudioWorklet は ring 消費専用 (`Atomics.wait` 不可)」制約を前提に設計し、#1419 で実装・close 済み。§10 参照。

## 10. HB-H27 (#1174): SAB ring → AudioWorklet と Atomics.wait RPC の往復 (2026-10-14 実測)

- 測定 commit: `bc871968` (HEAD)。`git diff bc871968 HEAD -- tools/hostbridge/lowbase` は空 (測定後のコード差分 0)。
- 検証: `bash tools/hostbridge/lowbase/lowbase_e2e.sh` = **ALL PASS**、所要 **103.0 秒** (全ビルド込み・Chrome 154 込み)。load average 0.04 (開始時)。素材: `fl-win64`・`plugins-ott`・`analysis-ott-binaries`・`work-m6-ott`・`work-liftlib`・`toolchain-*` を展開して実行。`ott_hb.cjs` と `k.final.ll` は `hostbridge.sh` と `t0_e2e.sh` で当 run に再生成 (357/357 PASS・seed 3 種)。

| # | 受入条件 (#1174) | 実測 (`work/ring/ring_result.json`) | 判定 |
|---|---|---|---|
| 1 | OTT の出力を SAB ring 経由で AudioWorklet に流し、消費量と総和が node と一致 | 消費 **126,976 float** (= 期待 126,976, 500 blk − NRPC 4 blk × 2ch × 128f)、総和 uint32 checksum **1952270321** = node 参照 | 達成 |
| 2 | Worker を SAB + `Atomics.wait` RPC で呼び出し、`VSTPluginMain` 経由の処理が往復 | LOAD/CONFIG/BLOCK×4/SHUTDOWN の 7 往復。RPC 区間 **25.8 ms**。先頭 4 ブロック L[0] ビット `[0, 1705319804, 3920893779, 4162865819]` = node 参照 | 達成 |

- 方式:
  - Worker (`ring_rpc_worker.mjs`) が OTT lowbase module を保持し、`Atomics.wait(REQ)` で page からの要求を待つ。処理は `host_load_plugin` → guest `VSTPluginMain` (hb_bridge.mjs:67) → `host_process`。
  - 残りの 496 ブロックは Worker が SAB ring (Float32, L,R interleave, capacity 4096) へ書く。AudioWorklet (`ring_worklet.js`) は `Atomics.load` で消費し `Atomics.store` で消費量を返す。`Atomics.wait` は AudioWorklet では使わない (RT-4 #123)。
  - 比較は float 総和ではなく **uint32 bit 和** (`accum`)。OTT 出力は 1e27 級まで育つため float 総和が溢れて判定不能になるので使わない。
- 限界 (未検証の範囲):
  - ring は実時間ではなく**全量を先に流す**形で検証した。128 frame の quantum を実時間で回す (AudioContext の時計と同期する) 検証は含まない。
  - 同じ Memory を複数 AudioWorklet/Worker が並行に叩く構成は未検証 (§5-2 の通り)。
  - AudioWorklet 側の `process` は headless Chrome の offline 描画ではなく live `AudioContext` で回した。描画のタイミング依存の揺れは観測していない。
