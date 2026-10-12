# liftdiff — flelift (x64c) 全数採点 (CAB-232) + native 全起動の参照化 (CAB-233)

> 正本: `tools/liftdiff/REPORT.md`。書式仕様は `docs/FORMAT.md`。
> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

検証起点 commit: 01d5cb5 (CAB-233)。A/B は fba272c (CAB-232) 側。検収は b8e762d (HEAD) から実施。
既知類型との関係 (DEFECTS.md, 規則 44): 該当 **D15** (メモリ間接 call 脱落) — 残 3 unit の VMT 仮想 call
`call qword ptr [rdi+0x18]` (0x513da9) 診断で参照。jump table **D9 (DEFECTS.md)** は未使用。
icall REPORT §4 体系 (D1=間接 call / D9=disp_size) とは別物。

**判定: CAB-232 達成 / CAB-233 達成 (残 3 unit は下流)**。CAB-232 では FLEngine closure **7,421 関数の全数採点**
(9 pattern × native/wasm) で **一致 4,143 / 不一致 633 / 実行不能 2,645** を実測し、m11 RetDec route との突合で
**m11 mismatch → flelift match が 2,226 関数** (leaf 差分 1,281 → 19) を確定した。CAB-223 残差 0x6a7990 は
harness の scratch zero 化バグと特定し 1 行修正で 16/16 一致 (§4)。
CAB-233 では **native entry_point 起動を 171 unit → 928/942 unit 到達**まで拡張 (stub 拡充 + hybrid boot)、
m11 の boot 状態を 17 → 22 unit に拡大し、flelift route を再採点して**実行不能 2,645 → 2,498**・
**wasm_trap 2,053 → 941 case** を数値計上。f_410360 (TObject.Free 系) OOB カスケードを個別化し、
**246 case は f_410360 自身の欠陥**と確定した (§3)。

> **用語の定義 (規則 36・検収による訂正)**: `units_run` は **到達 unit 数** =
> `System.InitCount` (試行した unit 数) + unit フェーズの ok 数。**完走 unit 数** (init 関数が正常終了したもの)
> は別値で、検収の独立再計算により **890/942** と確定 (§2.1)。
> したがって「928/942 unit **完走**」は誤りで、「928/942 unit **到達**」が正しい。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| native 全起動 (flelift target, hybrid boot) | **928/942 unit 到達** / **完走 890/942** (§2.1)。entry 246 / units 22。残 3 = 830/895/898、空 47 (proc==0 1 + \*proc==0 46)、未実行 1 (#246)、entry 内未完走 1 (#245) |
| m11 boot 状態 | 17 → **22 unit** (units モードは最初の失敗で停止なので到達=完走。17→22 は TLS 変更ではなく stub 拡充側、§5.2) |
| flelift 全数再採点 (928 unit 到達状態) | **一致 4,182 (+39) / 不一致 741 (+108) / 実行不能 2,498 (−147)**。比較可能 4,776 → 4,923 (64.4% → 66.3%) ※絶対値は負荷で変動 (§6.2) |
| native 全滅 (fault + null deref) | 1,849 → **1,738** (null deref 691 → 494 / fault 1,158 → 1,244)。hang 357 → 321 |
| wasm_trap (OOB) | case **2,053 → 941 (−54%)**、関数 361 → 211 |
| f_410360 カスケード個別化 | 941 case = **trap_direct 246** (f_410360 自身の欠陥) + **trap_upstream 327** (上流乖離) + 非経路 368。innermost = f_410360 が 573 case (うち 237 は呼出列 0 件 = §3 の限定) |
| 0x6a7990 (CAB-226 残差) | lift 欠陥に非ず。fle_wasm_runner.mjs の scratch zero 化 no-op バグ → 1 行修正で spot 16/16 一致 (§4) |
| 回帰 (fresh HEAD A/B) | OTT 欠陥 D1〜D6 全検出維持 / unit#18 check 1-2 PASS / m11 sample:800 353/217/230 (§5) |

## 2. native 全起動の参照化 (CAB-233 本体)

`bootstate` に mode を追加 (`ldlib/boot.py`)。Delphi InitTable は 942 unit。

| mode | 動作 | flelift 实测 |
|---|---|---|
| `units` (従来) | unit 0 から 1 本ずつ実行し最初の失敗で停止 | 22 unit (CAB-233 前は 17。Ablation で原因は stub 拡充側と確定、§5.2) |
| `entry` | `entry_point(hinst,1,0)` を 1 case で直接実行 (実 InitUnits ループ) | **246 unit 試行後** rip 0x26833d で停止 (起案時 171 から stub 拡充で +75。InitCount=246 は試行数) |
| `hybrid` | entry → 到達 unit (`System.InitCount` = image 0x11eac98) の次から unit 単位で継続。実 InitUnits と同じ「proc && *proc」判定 (PEEK)・失敗 unit は記録して続行 | **928/942 到達** (完走 890、§2.1) |

起動を 246 → 928 に伸ばした stub 拡充 (`rt/ld_core.h`、native/wasm が同一応答モデルを共有 = 比較の公平性不変):

| 追加応答 | 内容 |
|---|---|
| LoadLibrary/FreeLibrary/GetModuleHandle | 名前で同一視した仮 module handle |
| **GetProcAddress** | (module, 名前) で同一視した**仮 proc**。native は 0x50010000+i\*32 に**実行可能 thunk** を敷いて本当に呼べる (`ld_native.c`)、wasm は `ott_dispatch` が同番地を捕捉して同一 `ld_stub` 応答に振り向ける (`fle_ldbridge.c`) |
| LoadStringW | `.rsrc` の RT_STRING (type 6) を辿って実文字列を返す |
| FastMM / TLS | VirtualAlloc・GetMem 系を bump heap (先頭 64KB は偽 TEB、TLS 配列は heap+0x1000)。**TLS 値を heap に置くことで状態移送 (SHEAP) 時に wasm へも写る** → m11 unit #17 の wasm 側完走 (native 起動延伸とは別、§5.2) |
| GetLocaleInfoW/A・画面/DB/同期系 | en-US 決定値 23 種 / GetDeviceCaps・GetVersionEx (Win7 SP1)・GetSystemInfo・Reg\* (empty)・CreateEvent・DC・LoadImage は連番仮 handle / VerSetConditionMask / MultiByteToWideChar・WideCharToMultiByte (第5/6引数は `ld_ms_call.S` でスタック経由取得) |
| 出力ポインタ | `ld_dst_ok()` で image/arena/heap/guest stack 外への書込みを拒否 |

entry が 0x26833d で止まるのは `System.@Langs` 系が要求する DLL 読み込みの枝 (末尾 import 呼出は
`FindFirstFileW`/`GetFileAttributesW`/`WideCharToMultiByte`。fp 0x26830f の `mov rbx,[rax]`、rax=[rbx+8]=0)。
unit 単位フェーズでは 942 unit のうち **1 は proc==0 (unit #941, 静的)**、**46 は \*proc==0** (実行時に PEEK で判定。
いずれも `0x13a9390` という同一の「空 init」を指す) をスキップする。到達 928・完走 890 の内訳は §2.1。

### 2.1 到達数と完走数の違い (検収で確定・`tests/recheck_boot_units.py`)

`System.@InitUnits` (image 0x4120c0) のループを逆アセンブルすると、**InitCount は unit 初期化関数を呼ぶ「前」に
インクリメント**される (0x12108 `add dword[rbp+0x48],1` → 0x1210f `mov [rip+0x11d8b83],eax` → 0x12126 `call [rbp+0x38]`)。
つまり InitCount=246 は「unit #0〜#245 を**試行**し、#245 の途中で落ちた」を意味する (完走 245 ではない)。
boot.py は `start = k + 1` とするため unit #246 は一度も実行されない (off-by-one)。

| 区分 | unit 数 | 根拠 |
|---|---|---|
| entry フェーズで完走 | **208** | 0..244 のうち `*proc != 0` のもの (246 試行 − 37 skip − #245 未完走) |
| entry フェーズで skip (\*proc==0) | 37 | PEEK で先頭 8B が 0 → InitUnits も呼ばない |
| entry フェーズで未完走 | 1 | unit #245 (InitCount は 246 にインクリメント後にクラッシュ) |
| unit フェーズで完走 | **682** | 各 unit を `CASE keep=1` で実行し status==ok |
| unit フェーズでクラッシュ | 3 | unit 830/895/898 (rip_rva=0x4e0fab) |
| unit フェーズで skip | 10 | proc==0 1 (#941) + \*proc==0 9 |
| **未実行 (off-by-one)** | **1** | unit #246 (`start = k+1`) |
| 合計 | **942** | 208+37+1+682+3+10+1 = 942 ✓ |

- 実装の `units_run` (到達) = InitCount 246 + phase_ok 682 = **928**
- **真の完走** = 208 + 682 = **890**
- 差分 38 = entry の skip 37 + #245 未完走 1 (「到達」に含まれるが完走ではない)

## 2.2 残 3 unit (830/895/898) — 原因確定、下流タスク化

3 unit とも `\System\Languages\LC_MESSAGES\default.moe` (GNU gettext .mo カタログ) を読む言語カタログ初期化で
rip 0x4e0fab (`mov ebx,[rdx]`、rdx=0 なので素直な NULL deref) に落ちる。検証した 3 通りの stub 応答:

1. CreateFileW = 0 (従来): バッファが NULL → 必修の magic check (`0x4e1a3c` で
   `cmp dword[rbp+0xac],0x950412de` / `cmp dword[rbp+0xac],0xde120495`) に到達できず segv。
2. INVALID_HANDLE_VALUE (-1): entry が別地点 (0x2690dc) に落ち **906/942 に後退**。
3. **実カタログ供給** (block25158 = 47,405B・498 エントリの正規 .mo を CreateFileW→仮 handle + ReadFile で読ませる):
   magic check は通過するが、catalog iteration loop (0x513da9 の VMT 仮想 call `call qword ptr [rdi+0x18]`)
   から **rbp ごと破壊されて戻る** (rbp=0x7fff00000000, rax=.mo サイズ, rdx=.mo の host バッファ)。
   0 応答の 928/942 (到達) が最良として **revert し記録のみ残した**。

> **検証範囲 (規則 40)**: 上記 3. の「rbp=0x7fff00000000 のフレーム破壊」は **revert された experiment の記録**で
> committed HEAD からは再現できない (ld_core.h のコメントとしてのみ残る)。検収では 0x513da9 が
> `call qword ptr [rdi+0x18]` (VMT スロット+0x18 の間接 call)・0x4e1a3c の magic check・block25158 が
> 498 エントリの正規 .mo であることを**独立に確認**した。

## 3. flelift route 再採点と f_410360 カスケードの個別化

928 unit 到達状態で全数再採点 (`batch --state auto`、1788 s / 14 shard)。旧 (17 unit) との遷移
(`tests/compare_bootstate.py` → `results/flelift_vs_bootstate.md`):

| 遷移 | 関数数 | 解釈 |
|---|---|---|
| unexec → match | 125 | 状態が充実し native が完走・wasm も一致 |
| unexec → mismatch | 132 | 同上で wasm 欠陥が可視化 |
| mismatch → match | 139 | 状態依存の偽不一致が解消 |
| **match → mismatch** | **200** | 充実状態で深部経路まで到達し wasm 欠陥が露出 (tag: callee_divergence 139・unlifted_callee 135・zero_init_drop 60・import_call_seq 59・wasm_trap 25) |
| mismatch → unexec | 85 | 状態変更で native 側が落ちる経路に変化 |
| match → unexec | 25 | 同上 |

不一致 741 の主因は unlifted_callee 407 → (実在 callee 解消後) は引き続きキャリブレーション対象。
実行不能 −147 の内訳は native null deref −197 / hang −36 / fault +86 = 状態が充実したことでの**native 参照の完走増**。

## 3.1 f_410360 (TObject.Free 系) OOB カスケード (`tests/cascade_410360.py`)

旧データの「wasm_trap 該当 361 = OOB 354 + abort 7」を、新状態の **941 case / 211 関数**について
import 呼出列での乖離判定で個別化 (batch は trace を保持しないため calls[] を使用):

| 分類 | case | 内容 |
|---|---|---|
| **trap_direct (innermost f_410360)** | **246** | native ok・乖離なしで f_410360 内 OOB = **f_410360 自身の欠陥** (VMT-0x50 間接 call)。カスケードの根源 |
| trap_upstream (f_410360 経由) | 327 | 上流乖離 (call_arg 265 / native_extra_call 181 が主因、最多は FreeLibrary の module handle 差) → f_410360 は被害者 |
| trap_direct_other | 167 | f_410360 非経由の別 OOB (f_412770 115 / f_415c30 108 / f_407e20 45 / f_511fe0 26) |
| trap_upstream_other | 201 | 上流乖離 + 別 OOB |
| (参考) self_native_fail | 0 | 941 case 全て native ok |

**結論: OOB カスケードは「単一 helper のカスケード」ではなく (a) 246 case = f_410360 自身の修正で消える、
(b) 327 case = 上流の stub 応答差 (仮 module handle の取扱い) の修正で消える、の 2 層に分離できる。**

> **限定 (規則 40)**: `trap_direct` 246 case のうち **237 case は native/wasm とも import 呼出列が 0 件**
> (import を 1 度も呼ばずに trap)。「上流で乖離していない」を確認できる呼出列ログが**ない**状態での分類で、
> 「import 呼出列まで一致した」は実質「両側空 = 比較情報なし」を意味する (検収の実測)。
> 分類自体 (246/327/368) は独立再計算で一致する (§6.1)。

## 4. 0x6a7990 の 2/16 byte 差 (CAB-232、結論のみ)

x64c lift の欠陥ではない。`fle_wasm_runner.mjs` の `resetState()` の `U8.fill(0, 0x20000000, 0x3100000)` は
start > end で no-op で、wasm 側だけ scratch に前 case の byte が残留していた。arena/scratch の 2 分割 fill に修正し
`fle_diff.py` = 7 関数 16 case 全て equal (16/16)。tools/flelift 側の 1 行修正 (+ results 更新)。

## 5. 回帰 — fresh HEAD との A/B (本チケットで実測)

HEAD (= f555629) の tools/liftdiff を作業ツリー外に展開し (REPO を実リポジトリに差し替え、入力 IR は共有)、
**同じ IR・同じ手順**で A/B した (CAB-232 の手法を再現・検証)。
検収では **b8e762d (HEAD) から `liftdiff_e2e.sh` をまるごと再実行**して同じ値を再現した
(実測 1 分 2.4 s / load average 開始 3.08・終了 2.47, 12 shard):

| 指標 | HEAD (fresh A/B) | CAB-233 | 検収再実行 (HEAD) | 判定 |
|---|---|---|---|---|
| OTT closure (212 関数) | 39 / 106 / 67、D1〜D6 全検出 | **38 / 108 / 66、D1〜D6 全検出** (D3 callsite_arg_drop 12→14) | 38 / 108 / 66、D1〜D6 全検出 | 検出維持・感度向上 |
| unit#18 check 1 / check 2 | PASS / PASS | PASS / PASS | PASS / PASS | 維持 |
| unit#18 check 3 (4123c0) | **FAIL (native 53 / wasm 25)** | FAIL (67 / 46) | FAIL (67 / 46) | **HEAD でも同一 FAIL** = CAB-131 由来 (§5.1) |
| unit#18 case 追加所見 | 446370 = wasm_trap / 455790 = unexec | **446370 = diff / 455790 = match** | 同 | 改善 |
| m11 closure sample:800 | 355 / 198 / 247 | **353 / 217 / 230** | **353 / 217 / 230** (93 s) | match −2・unexec −17・mismatch +19 は全て深部乖離型 (callee_divergence 10・wasm_trap 5・import_call_seq 5・icall_drop 4・memory_semantics 2。leaf 自己欠陥 45→49) = 充実状態で深部まで到達し wasm lift 欠陥が可視化されたもので検出器の劣化ではない |

判定基準 (m11 sample:800 356/205/239 非劣化) に対し、一致は 355→353 (−0.6%)・実行不能は 247→230 (−6.8%)。
**OTT 欠陥検出・unit#18 の既有 2 チェックは完全維持**。

## 5.1 check 3 (4123c0) の FAIL は既存 (CAB-131 由来)

`check 3` は **CAB-233 以前から FAIL**。A/B 取りした fba272c (CAB-232) 側でも同一条件で FAIL し、
HEAD (b8e762d) でも FAIL (native 67 / wasm 46)。原因は tools/m11/work/boot_final3.ll が CAB-131 の再生成
(10-10 20:48) で resourcestring 初期化ループの wasm トレースが 25 → 46 に増えたこと。
**本チケット (liftdiff) とは無関係**で fix 対象外。
`liftdiff_e2e.sh` は check 3 で exit 1 になるため、検収时は [4/4] を別途手動実行した (§6 参照)。

## 5.2 Ablation (規則 41)

主要な効果に対して、その修正だけを外した対照を 3 つ実施した (いずれも `work/abl/` にビルド、
結果は本節の実測):

| ablation | 操作 | 結果 |
|---|---|---|
| 旧 rt (fba272c) 全体 | CAB-233 の rt 変更を全部戻した ld_native で m11 bootstate | **units_run=17、unit #17 が segv** (rip_rva=0x1d15a) = CAB-233 前の挙動を再現 |
| **GetProcAddress 仮 proc 応答の除去** | `GetProcAddress` を `return 0` に差し替え (TLS/その他は温存) | flelift entry が **InitCount=246 → 17** (rip_rva=0xffffffffffc00000、rcx=-1 で proc 0 を call) → **仮 proc 応答が起動延伸の主因** |
| **TLS 配列の heap 移送だけ revert** | `TlsGetValue/TlsSetValue` を旧 `ld_tls_vals[]` 実装に戻す | m11 units_run は **22 のまま** (不変) → 17→22 は TLS 変更由来**ではない** |

→ CAB-233 の stub 拡充が native boot 延伸に効いているのは **GetProcAddress の仮 proc** (実測 +229 unit)。
TLS 配列の heap 化は native 起動には影響せず、**状態移送 (SHEAP) で wasm 側にも TLS 値が写る**効果
(m11 unit #17 が wasm 側でも完走) として働く。**

## 6. 成果物と再現

| パス | 役割 |
|---|---|
| `ldlib/boot.py` | bootstate mode (units/entry/hybrid)、InitCount PEEK、tolerant unit 継続 |
| `rt/ld_core.h` | stub 応答拡充 (仮 module/proc・LoadStringW・FastMM/TLS・GetLocaleInfoW・画面/DB/同期系・`ld_dst_ok`) |
| `rt/ld_native.c` | 仮 proc の実行可能 thunk (mmap)・MS 第5/6引数・guest 外 fault 時の image 内復帰 address 探索・fault 時レジスタ (rbp/rbx/rdi/rsi/rax/rcx/rdx/r8) を detail に出力 |
| `rt/ld_ms_call.S` | `ld_stub_common` が MS 第5/6引数を読めるよう r9 を設定 |
| `rt/fle_ldbridge.c` | inbuf 8→192MB (928 unit の heap = 66MB hex)、`ott_dispatch` の仮 proc 捕捉 |
| `tests/{compare_bootstate,cascade_410360,boot_probe}.py` | verdict 遷移比較 / trap 個別化 / 残 3 unit の fault 詳細・要求パス |
| `tests/recheck_boot_units.py` | **(検収・追加)** 到達数/完走数の独立再計算 (ldlib 非依存のネイティブ駆動 + 機械語解析) |
| `docs/FORMAT.md` §7 | boot mode・仮 module/proc・TLS 配置の仕様 |

```sh
python3 liftdiff.py bootstate targets/flelift.json --mode hybrid --nobuild   # 928/942 unit 到達
python3 tests/recheck_boot_units.py                                          # 到達 928 vs 完走 890 の独立再計算
python3 tests/boot_probe.py --mode hybrid                                    # 残 3 unit の原因 (file path・fault)
python3 liftdiff.py batch targets/flelift.json --set closure --shards 14 \
  --state auto --out work/flelift/batch_closure_hybrid.jsonl                # 全数 (検収実測 585 s)
python3 tests/compare_bootstate.py work/flelift/batch_closure_hybrid.jsonl \
  results/flelift_closure_verdicts.tsv --md results/flelift_vs_bootstate.md
python3 tests/cascade_410360.py work/flelift/batch_closure_hybrid.jsonl \
  --md results/cascade_410360.md
bash tools/liftdiff/liftdiff_e2e.sh   # OTT/unit#18 (check3 は CAB-131 IR 由来で FAIL → exit 1)
# (check3 は FAIL するので [4/4] は手動で)
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto \
  --out work/m11/batch_sample_800.jsonl
```

## 6.1 検収 (CAB-233) で実施した独立検証

| 検証 | 手法 | 結果 |
|---|---|---|
| unit 到達/完走 | `tests/recheck_boot_units.py` (自前 PE パーサ + ldlib 非依存のランナ駆動 + 0x4120c0 の逆アセンブル) | 到達 **928** (一致)。完走 **890** (§2.1) |
| f_410360 カスケード | stored batch jsonl を別アルゴリズムで再分類 | 246 / 327 / 368 / case 941 / 関数 211 — **すべて実装値と一致** |
| flelift 全数再採点 | `batch --set closure --shards 14` を HEAD から再実行 (585 s) | 一致 4,092 / 不一致 767 / 実行不能 **2,562** (§6.2) |
| m11 sample:800 A/B | e2e [4/4] を HEAD から再実行 (93 s) | **353 / 217 / 230** = CAB-233 値と完全一致 |
| 残 3 unit の原因 | `boot_probe.py` + 0x4e0fab/0x4e1a3c/0x513da9 の逆アセンブル + block25158 検証 | `default.moe`・magic check・VMT 間接 call を確認。フレーム破壊は experiment revert 済みで HEAD では未再現 |
| ⑤ limit 外の変数 | `ld_tls_next` の unbounded 性をコード/実測で確認 | TlsAlloc **1 回** (index 0)。1025 回目で slot 0 に折り返す設計だが未発火 |

## 6.2 全数採点の再現性について (負荷依存・規則 38)

同じ boot_state.json で `batch --set closure --shards 14` を再実行 (585 s) すると verdict 合計が
**4,092 / 767 / 2,562** となり、REPORT の 4,182 / 741 / 2,498 とは **一致 90・不一致 26・実行不能 64 の差**。
(bootstate 24.4 s・batch 585 s の所要自体は完全再現)。原因は **native ランナの `badjson` (88 case) /
timeout (native 248 / wasm 346) が負荷で変動**することで、同一 boot 状態・同一 wasm でも verdict がぶれるため
(小規模 sample:200 を 3 回回すと 102/22/76 で完全安定 = 規模依存の Shot noise)。

**結論: 全数採点の絶対値 (2,498 / 941 / 4,182 / 741) は 1 run の snapshot で数十オーダー変動する。**
下流の判断は (a) `compare_bootstate.py` の遷移 (旧→新) の方向性、(b) `cascade_410360.py` の
case 単位分類 (完全再現) を基準にすること。「実行不能 2,498」は target 値に使えない。

## 7. 限界・未解決 (起票先) ・環境前提

- **実行不能 2,498 の大半は native が落ちる case** (route 非依存)。比較可能 4,923 の不一致 741 が real の追跡対象 (§6.2 の再現性に注意)。
- **残 3 unit (830/895/898)**: 実カタログを読ませても catalog loop の VMT 仮想 call で rbp 破壊 (§2)。
  真正ファイル I/O + 例外/仮想 call 経路の stub 化が次の一手。仮想ファイル層は experiment として revert 済み。
- **f_410360 自身の欠陥 246 case** と **上流 stub 応答差 327 case** (FreeLibrary handle 取扱い) は独立した downstream 修正で
  それぞれ消える見込み。leaf 自己欠陥確定数は 19 → 41 (m11 sample:800 では 45 → 49)。
- unlifted_callee の実在 callee (~7 個) 追加は fle_entries.json 拡張 = tools/flelift 側作業 (CAB-252 と競合のため要調整)。
- boot 状態は host stack アドレスが heap に残留するため run 間でバイト一致しない (guest 意味論は同一: unit 数・heap_used・クラッシュ点は完全再現)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `units_run=928` が到達数で完走数でない (真の完走 890・#245 未完走・#246 未実行 = `start=k+1` off-by-one) | +38 unit の過大評価。boot 比較の基準がずれる | (c) 親 CAB-121 にコメント (reporting と off-by-one 修正タスク) |
| m11 17→22 は「TLS heap 移送」由来**ではない** (revert しても 22 のまま) | 効果の帰因が誤り。TLS heap 化は wasm 側状態移送の効果 | (c) 親 CAB-121 にコメント |
| 全数採点の絶対値が負荷でぶれる (2,498 ↔ 2,562) | 目標値として使えない | (c) 親 CAB-121 にコメント (A/B は遷移ベース) |
| `trap_direct` 246 case のうち 237 は import 呼出列が両側 0 件 | 「f_410360 自身の欠陥」の根拠が trap chain のみ | (c) 親 CAB-121 にコメント。strict 判定には trace 保持が必要 |
| `ld_tls_next` 無上限 (1025 回目の TlsAlloc で slot 0 に折り返す) | boot 中は TlsAlloc 1 回のみで未発火 | (c) 親 CAB-121 にコメント (軽微) |
| `g_inbuf[192MB]` / `ld_out` 256MB | wasm static data が非常に大きい | 既存 CAB-252 (続) に相乗り (読取のみ) |

**検証範囲 / 範囲外 (規則 40)** — 検証: 01d5cb5 の内容を HEAD から独立再計算 (unit 到達/完走・f_410360 分類・
m11 sample:800・残 3 unit の原因・`ld_tls_next` の limit 性・e2e 再現・ablation 3 件)。
範囲外: (1) native 実機 (Windows FL Studio) との比較は未実施 (参照は lift ランナ内実行)。
(2) wasm verdict (mismatch 741 の内訳) は lift 関数の品質そのものではなく liftdiff 比較器の出力。
(3) revert 済み experiment の `rbp=0x7fff00000000` は HEAD では再現不能。
(4) tools/liftlib・tools/flelift は読取のみ (CAB-252 続 の未コミット WIP の影響は評価対象外)。

**環境前提 (docs/WORKFLOW.md §5 の環境恒久化)** — `bash tools/liftdiff/env.sh`
(PATH/TMPDIR 修正。TMPDIR = `tools/liftdiff/work/tmp` 実ディスク。/tmp は tmpfs 3.7 GB)。
入力 (読取のみ): `docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin`・
`tools/m11/work/{boot_final3.ll,boot_final.ll,m11_image.bin}`・`tools/ott/work/ott.ll`・
`tools/flelift/work/lift/*` (CAB-252 続 が稼働中・未コミット差分あり)。
ビルド: `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm`
(format-truncation warning は既知・動作影響なし)。wasm は emcc (`[EMSDK]`)。
所要 (実測・負荷依存): bootstate flelift hybrid **24.4 s** (load 0.79→2.62)、e2e [1/4]-[3/4] **62.5 s**、
m11 sample:800 (12 shard) **93〜95 s**、flelift closure (14 shard) **585 s** (load 4.80→12.06)。

## 8. m11 wasm_trap 578 関数のトリアージ (LD-5 / #236)

集計 = `tests/triage_wasm_trap.py` → `results/m11_wasm_trap_triage.md` (表・内訳はそちらが正本)。
入力は既存 closure の batch jsonl (`work/m11/batch_closure.jsonl`、再走なし)。

- **unreachable 218 は署名不一致 thunk 由来ではない**: 全件が `function_4128b0__lifted` で trap し、frame 名に signature/thunk を含むものは 0、
  wasm の name section に `signature_mismatch` も無い (M11 §2.4 の thunk は sigfix 済み)。wasm 側の import 呼出列には全件 `ExitProcess` があり、
  native 側には 0 件。IR 上 `ExitProcess` 呼出の直後が `unreachable` なので、stub が戻る wasm でここに落ちる。
  実際の分岐点は `ExitProcess` へ至る手前 (`function_4096b0` / `function_412a60` 経由の終了経路に wasm だけが入る) で、native とのずれは上流にある (未特定)。
- OOB 222 は最上位 frame が 71 種に分散 (`function_414ad0` 68 件が最多)。hang 39・badjson 25・indirect_sig 3・arith/stack/other 計 4。個別原因は未確定。
- TSV 578 のうち 67 件は今の jsonl に wasm_trap case が無い (jsonl 側のみ 71 件)。TSV と jsonl は別 run のため (§6.2)。

## 9. wasm_trap の個別原因 (LD-7 / #307、#305 上に積んだ分)

集計 = `tests/trace_diverge_unreachable.py` → `results/m11_unreachable_diverge.md`、`tests/oob_414ad0.py` → `results/m11_oob_414ad0.md` (数値・表はそちらが正本)。
入力は §8 と同じ既存 batch jsonl (再走なし) と PE (`LD_M11_PE` または `--pe`)。

- **unreachable (最初の trap が unreachable の 220 関数) の分岐点**: native/wasm の `trace_head` を先頭から比べ、最初に食い違う直前の関数を数えると
  `function_410320` が最多 (83 件)。機械語は `test dl,dl; jl; call qword ptr [rax-0x30]` (VMT 間接 call) だが、lift 後 IR は `ret %arg1` のみで call が脱落している
  (D15 型、DEFECTS.md)。native は 410320 の次に 0x409410 へ進み (例 0x6ae290)、wasm は 0x40f9e0 へ進む。
  同型 (メモリ間接 call を持ち IR の call 数 ≤ 機械語の直接 call 数) は 0x40f9e0・0x1253610・0x678480 を含め合計 87/220。
  残り 133 件は別の分岐 (0x417b70 32 / 0x40a3d0 24 / 0x418be0 20 ほか)。**未特定**。
- ExitProcess へ至る連鎖 (例 0x6ae290: wasm のみ `409470 → 409730 → 4096d0 → 4096b0 → 412a40 → 4128b0`) は「alloc 失敗を示す Delphi の runerror 経路」と読めるが、
  410320 の call 脱落からその経路に入るまでの因果は trace_head (最大 12 件) に収まらず**直接確認していない** (推定)。
- **OOB function_414ad0 系 (68 件)**: 機械語は入口 rcx (var 文字列のアドレス) の 1 段 deref `mov r,[rbx]` が 4 箇所 (0x414af3/0x414b49/0x414b64/0x414b78)。
  lift 後 IR には `%arg1` を ptr とする load が 0 件で、`%arg1` を値のまま `icmp`/`add` に使っている (ldfix F3a/F3b 型の値↔アドレス取り違え)。
  実測: 単体 `run --fn 0x414ad0 --pattern q0` で callee 0x414850 arg0 が native=0x22479388 / wasm=0x5。
- **修正の検証 (限定的)**: 4 箇所に `load` を足した IR (`work/ld7/`、commit しない) で再ビルドして単体実行すると、
  callee_divergence タグが消え memory_semantics になり、z / s / p0 は wasm=trap/ok → wasm=ok (native_fault) になった。
  p1 / p01 / pall / pall2 / qall は native・wasm とも fault のまま。**68 件が全て解消するかは未確認**。
  また 414ad0 に到達しない 27 件 (wasm trace_head に現れない) は別原因 (上流の呼出元側、**未特定**)。

### 再現手順
```
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C "$RUNNER_TEMP/fl" extracted/block00031_PE.bin
export LD_M11_PE=$RUNNER_TEMP/fl/extracted/block00031_PE.bin
pip install numpy capstone pefile
cd tools/liftdiff
python3 tests/trace_diverge_unreachable.py > results/m11_unreachable_diverge.md
python3 tests/oob_414ad0.py > results/m11_oob_414ad0.md
```
単体実行は `targets/m11.json` の `pe` を書き換えた複製 (`/home/ubuntu` 固定のため) で `python3 liftdiff.py run <target.json> --fn 0x414ad0 --state auto --nobuild -v`。
