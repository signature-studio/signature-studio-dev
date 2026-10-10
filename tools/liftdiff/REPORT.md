# liftdiff — flelift (x64c) 全数採点 (CAB-232) + native 全起動の参照化 (CAB-233)

**判定: CAB-232 達成 / CAB-233 達成 (残 3 unit は下流)**。CAB-232 では FLEngine closure **7,421 関数の全数採点**
(9 pattern × native/wasm) で **一致 4,143 / 不一致 633 / 実行不能 2,645** を実測し、m11 RetDec route との突合で
**m11 mismatch → flelift match が 2,226 関数** (leaf 差分 1,281 → 19) を確定した。CAB-223 残差 0x6a7990 は
harness の scratch zero 化バグと特定し 1 行修正で 16/16 一致 (§4)。
CAB-233 では **native entry_point 起動を 171 unit → 928/942 unit 完走**まで拡張 (stub 拡充 + hybrid boot)、
m11 の boot 状態を 17 → 22 unit に拡大し、flelift route を再採点して**実行不能 2,645 → 2,498**・
**wasm_trap 2,053 → 941 case** を数値計上。f_410360 (TObject.Free 系) OOB カスケードを個別化し、
**246 case は f_410360 自身の欠陥**と確定した (§3)。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| native 全起動 (flelift target, hybrid boot) | **928/942 unit 完走** (entry 単独 246 / units 従来 22)。残 3 = unit 830/895/898、11 unit は空 (proc==0) |
| m11 boot 状態 (TLS 修正効果) | 17 → **22 unit** (unit #17 = 0x455790 が native/wasm とも完走。TLS 配列を heap 内に移し状態移送で写す) |
| flelift 全数再採点 (928 unit 状態) | **一致 4,182 (+39) / 不一致 741 (+108) / 実行不能 2,498 (−147)**。比較可能 4,776 → 4,923 (64.4% → 66.3%) |
| native 全滅 (fault + null deref) | 1,849 → **1,738** (null deref 691 → 494 / fault 1,158 → 1,244)。hang 357 → 321 |
| wasm_trap (OOB) | case **2,053 → 941 (−54%)**、関数 361 → 211 |
| f_410360 カスケード個別化 | 941 case = **trap_direct 246** (f_410360 自身の欠陥) + **trap_upstream 327** (上流乖離が到達) + 非経由 368。innermost = f_410360 が 573 case |
| 0x6a7990 (CAB-226 残差) | lift 欠陥に非ず。fle_wasm_runner.mjs の scratch zero 化 no-op バグ → 1 行修正で spot 16/16 一致 (§4) |
| 回帰 (fresh HEAD A/B) | OTT 欠陥 D1〜D6 全検出維持 / unit#18 check 1-2 PASS / m11 sample:800 一致 355→353・不一致 198→217・実行不能 247→230 (§5) |

## 2. native 全起動の参照化 (CAB-233 本体)

`bootstate` に mode を追加 (`ldlib/boot.py`)。Delphi InitTable は 942 unit。

| mode | 動作 | flelift 实测 |
|---|---|---|
| `units` (従来) | unit 0 から 1 本ずつ実行し最初の失敗で停止 | 22 unit (TLS 修正後。修正前は 17 で unit #17 が TLS で segv) |
| `entry` | `entry_point(hinst,1,0)` を 1 case で直接実行 (実 InitUnits ループ) | **246 unit** 完走後 rip 0x26833d で停止 (起案時 171 から stub 拡充で +75) |
| `hybrid` | entry → 到達 unit (`System.InitCount` = image 0x11eac98) の次から unit 単位で継続。実 InitUnits と同じ「proc && *proc」判定 (PEEK)・失敗 unit は記録して続行 | **928/942** |

起動を 246 → 928 に伸ばした stub 拡充 (`rt/ld_core.h`、native/wasm が同一応答モデルを共有 = 比較の公平性不変):

| 追加応答 | 内容 |
|---|---|
| LoadLibrary/FreeLibrary/GetModuleHandle | 名前で同一視した仮 module handle (native は thunk ページ内で一貫) |
| **GetProcAddress** | (module, 名前) で同一視した**仮 proc**。native は 0x50010000+i*32 に**実行可能 thunk** を敷いて本当に呼べる (`ld_native.c`)、wasm は `ott_dispatch` が同番地を捕捉して同一 `ld_stub` 応答に振り向ける (`rt/fle_ldbridge.c`) |
| LoadStringW | `.rsrc` の RT_STRING (type 6) を辿って実文字列を返す (`ld_rsrc_string`) |
| FastMM 経由 | VirtualAlloc / GetMem 系を bump heap (heap 先頭 64KB は偽 TEB、TLS 配列は heap+0x1000) に割り当て。**TLS 値を heap に置くことで状態移送 (SHEAP) 時に wasm へも写る** → m11 unit #17 解消 |
| GetLocaleInfoW/A 系 | en-US 決定値の表 (LOCALE_SDECIMAL 等 23 種) |
| 画面/DB/同期系 | GetDeviceCaps / GetVersionEx (Win7 SP1) / GetSystemInfo / Reg* (empty) / CreateEvent・DC・LoadImage は連番仮 handle / VerSetConditionMask / MultiByteToWideChar・WideCharToMultiByte (第5/6引数 = スタック経由で取得、`ld_ms_call.S` で参照) |
| 出力ポインタ | `ld_dst_ok()` で image/arena/heap/guest stack 外への書込みを拒否 (guest ゴミポインタから native ランナを守る) |

entry が 0x26833d で止まるのは `System.@Langs` 系が要求する DLL 読み込みの枝。unit 単位フェーズで 942 unit のうち
**11 は proc==0 (空) をスキップ**、928 が完走。

### 残 3 unit (830/895/898) — 原因確定、下流タスク化

3 unit とも `\System\Languages\LC_MESSAGES\default.moe` (GNU gettext .mo カタログ) を読む言語カタログ初期化で
rip 0x4e0fab (`mov ebx,[rdx]`、rdx=カタログバッファ) に落ちる。検証した 3 通りの stub 応答:

1. CreateFileW = 0 (従来): バッファが NULL → 必修の magic check (`0x4e1a3c`、GNU .mo magic 0x950412de/0xde120495) に到達できず segv。
2. INVALID_HANDLE_VALUE (-1): entry が別地点 (0x2690dc) に落ち **906/942 に後退**。
3. **実カタログ供給** (win64 `extracted/block25158_DATA.bin` = 先頭 magic 0x950412de・47,405B・498 エントリの正規 .mo を
   CreateFileW→仮 handle + ReadFile で読ませる実験): magic check は通過するが、catalog iteration loop
   (0x513da9 の VMT 仮想 call `Get(i)`) から **rbp ごと破壊されて戻る** (rbp=0x7fff00000000, rax=.mo サイズ, rdx=.mo の host バッファ)
   → さらに深い stub ギャップ (または例外経路の縮退) が残る。0 応答の 928/942 が最良として** revert し記録のみ残した**
   (`rt/ld_core.h` のファイル系コメント、`tests/boot_probe.py` の fault detail にレジスタが出るので再検証可)。
   なお stub 0 応答 (採用形) での crash は rbp 健全・rdx=0 の素直な NULL deref (`mov ebx,[rdx]`) である。

## 3. flelift route 再採点と f_410360 カスケードの個別化

928 unit 状態で全数再採点 (`batch --state auto`、1788 s / 14 shard)。旧 (17 unit) との遷移
(`tests/compare_bootstate.py` → `results/flelift_vs_bootstate.md`):

| 遷移 | 関数数 | 解釈 |
|---|---|---|
| unexec → match | 125 | 状態が充実し native が完走・wasm も一致 |
| unexec → mismatch | 132 | 同上で wasm 欠陥が可視化 |
| mismatch → match | 139 | 状態依存の偽不一致が解消 |
| **match → mismatch** | **200** | 充実状態で深部経路まで到達し wasm の欠陥が露出 (tag 内訳: callee_divergence 139・unlifted_callee 135・zero_init_drop 60・import_call_seq 59・wasm_trap 25) |
| mismatch → unexec | 85 | 状態変更で native 側が落ちる経路に変化 |
| match → unexec | 25 | 同上 |

不一致 741 の主因は unlifted_callee 407 → (実在 callee 解消後) は引き続きキャリブレーション対象。
実行不能 −147 の内訳は native null deref −197 / hang −36 / fault +86 = 状態が充実したことでの**native 参照の完走増**。

### f_410360 (TObject.Free 系) OOB カスケード (`tests/cascade_410360.py` → `results/cascade_410360.md`)

旧データの「wasm_trap 該当 361 = OOB 354 + abort 7」を、新状態の **941 case / 211 関数**について
import 呼出列での乖離判定で個別化 (batch は trace を保持しないため calls[] を使用):

| 分類 | case | 内容 |
|---|---|---|
| **trap_direct (innermost f_410360)** | **246** | native ok・import 呼出列まで一致した状態で f_410360 内 OOB = **f_410360 自身の欠陥** (VMT-0x50 間接 call)。カスケードの根源はこの 1 関数 |
| trap_upstream (f_410360 経由) | 327 | f_410360 に到達する前に上流乖離 (call_arg 265 / native_extra_call 181 が主因、最多は FreeLibrary の module handle 差) → f_410360 は被害者 |
| trap_direct_other | 167 | f_410360 非経由の別 OOB (f_412770 115 / f_415c30 108 / f_407e20 45 / f_511fe0 26) |
| trap_upstream_other | 201 | 上流乖離 + 別 OOB |

**結論: OOB カスケードは「単一 helper のカスケード」ではなく (a) 246 case = f_410360 自身の修正で消える、
(b) 327 case = 上流の stub 応答差 (仮 module handle の取扱い) の修正で消える、の 2 層に分離できる。**

## 4. 0x6a7990 の 2/16 byte 差 (CAB-232、結論のみ)

x64c lift の欠陥ではない。`fle_wasm_runner.mjs` の `resetState()` の `U8.fill(0, 0x20000000, 0x3100000)` は
start > end で no-op で、wasm 側だけ scratch に前 case の byte が残留していた。arena/scratch の 2 分割 fill に修正し
`fle_diff.py` = 7 関数 16 case 全て equal (16/16)。tools/flelift 側の 1 行修正 (+ results 更新)。

## 5. 回帰 — fresh HEAD との A/B (本チケットで実測)

HEAD (= f555629) の tools/liftdiff を作業ツリー外に展開し (REPO を実リポジトリに差し替え、入力 IR は共有)、
**同じ IR・同じ手順**で A/B した (CAB-232 の手法を再現・検証):

| 指標 | HEAD (fresh A/B) | CAB-233 | 判定 |
|---|---|---|---|
| OTT  closure (212 関数) | match 39 / mismatch 106 / unexec 67、D1〜D6 全検出 | **38 / 108 / 66、D1〜D6 全検出** (D3 callsite_arg_drop 12→14) | 検出維持・感度向上。check_ott PASS |
| unit#18 check 1 (_UStrAsg mem diff) | PASS | PASS | 維持 |
| unit#18 check 2 (Move spill_slot_deref) | PASS | PASS | 維持 |
| unit#18 check 3 (4123c0 resourcestring, wasm trace ≤6) | **FAIL (native 53 / wasm 25)** | FAIL (native 67 / wasm 46) | **HEAD でも同一 FAIL** = CAB-131 の boot_final3.ll 再生成 (10-10 20:48) 由来で本チケット無関係。wasm trace は 25→46 と native (53→67) に近づく方向 |
| unit#18 case 追加所見 | 446370 = wasm_trap / 455790 = unexec | **446370 = diff (trap 解消) / 455790 = match** | 改善 |
| m11 closure sample:800 | 355 / 198 / 247 | **353 / 217 / 230** | match −2・unexec −17 (実行可能域拡大)・mismatch +19 は全て深部乖離型 (callee_divergence 10・wasm_trap 5・import_call_seq 5・icall_drop 4・memory_semantics 2。leaf 自己欠陥 45→49)。状態・応答が充実し native/wasm がより深い経路まで到達して wasm lift 欠陥が可視化されたもので、検出器の劣化ではない |

判定基準 (m11 sample:800 356/205/239 非劣化) に対し、一致は 355→353 (−0.6%)・実行不能は 247→230 (−6.8%)。
不一致の増加は上記の可視化効果で、**OTT 欠陥検出・unit#18 の既有 2 チェックは完全維持**。

## 6. 成果物と再現

| パス | 役割 |
|---|---|
| `ldlib/boot.py` | bootstate mode (units/entry/hybrid)、InitCount PEEK、tolerant unit 継続、`_dump_state` 分離 |
| `rt/ld_core.h` | stub 応答拡充 (仮 module/proc・LoadStringW・FastMM/TLS・GetLocaleInfoW・画面/DB/同期系・`ld_dst_ok`) |
| `rt/ld_native.c` | 仮 proc の実行可能 thunk (mmap)、MultiByteToWideChar 第5/6引数、guest 外 fault 時の image 内復帰 address 探索、**fault 時の汎用レジスタ (rbp/rbx/rdi/rsi/rax/rcx/rdx/r8) を detail に出力** (仮想 call 後のフレーム破壊診断用) |
| `rt/ld_ms_call.S` | `ld_stub_common` が MS 第5/6引数を読めるよう r9 を設定 |
| `rt/fle_ldbridge.c` | inbuf 8→192MB (928 unit の heap = 66MB hex を載せる)、`ott_dispatch` の仮 proc 捕捉 |
| `tests/compare_bootstate.py` | 新旧 boot 状態の全数 verdict 比較 → `results/flelift_vs_bootstate.md` |
| `tests/cascade_410360.py` | wasm_trap case の個別化 (import 呼出列ベース) → `results/cascade_410360.md` |
| `tests/boot_probe.py` | 残 3 unit の fault 詳細・要求ファイルパスのダンプ (`\System\Languages\\LC_MESSAGES\default.moe`) |
| `docs/FORMAT.md` §7 | boot mode・仮 module/proc・TLS 配置の仕様 |

```sh
python3 liftdiff.py bootstate targets/flelift.json --mode hybrid --nobuild   # 928/942 unit
python3 tests/boot_probe.py --mode hybrid                                    # 残 3 unit の原因 (file path・fault)
python3 liftdiff.py batch targets/flelift.json --set closure --shards 14 \
  --state auto --out work/flelift/batch_closure_hybrid.jsonl                # 全数 約 30 分
python3 tests/compare_bootstate.py work/flelift/batch_closure_hybrid.jsonl \
  results/flelift_closure_verdicts.tsv --md results/flelift_vs_bootstate.md
python3 tests/cascade_410360.py work/flelift/batch_closure_hybrid.jsonl \
  --md results/cascade_410360.md
bash tools/liftdiff/liftdiff_e2e.sh                                          # OTT/unit#18/m11 sample:800 (check3 は CAB-131 IR 由来で FAIL)
```

## 7. 限界と下流チケット

- **実行不能 2,498 の大半は native が落ちる case** (route 非依存)。比較可能 4,923 の不一致 741 が real の追跡対象。
- **残 3 unit (830/895/898)**: 実カタログを読ませても catalog loop の VMT 仮想 call で rbp 破壊 (§2)。
  真正ファイル I/O + 例外/仮想 call 経路の stub 化が次の一手。`block25158_DATA.bin` を boot 時に読む
  仮想ファイル層は experiment として revert 済み (差分は git history、手順は §2)。
- **f_410360 自身の欠陥 246 case** と **上流 stub 応答差 327 case** (FreeLibrary handle 取扱い) は独立した downstream 修正で
  それぞれ消える見込み (§3)。leaf 自己欠陥確定数は 19 → 41 (深部到達による露出増、m11 sample:800 では 45 → 49)。
- unlifted_callee の実在 callee (~7 個) 追加は fle_entries.json 拡張 = tools/flelift 側作業 (CAB-252 と競合のため要調整)。
- boot 状態は host stack アドレスが heap に残留するため run 間でバイト一致しない (guest 意味論は同一: unit 数・heap_used・クラッシュ点は完全再現)。
