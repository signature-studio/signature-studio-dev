# #1620: unit 477 の `0x10a9f910` 下位 4B 上書きの書込み元 (IR 外か) の切り分け (結論は部分)

親: #1288 (経緯は `REPORT_1046.md` §10〜§19)。測定 commit: `2ba1bce8` (`trap_w1620.py` を追加した commit。計測に使ったコードはこれ)。検証 HEAD: `f4fa48f9` (origin/main) に上記 1 ファイルを足したもの。

> **注 (§10 で訂正)**: 本ファイルの結論 (§6 まで) は HEAD `7d15ceab` 系の計装に基づく。§10 で、その前提 (現 HEAD で `0x10a9f910` に `0x100000003` を書く store) は HEAD (`d6176933`) で再現しないと分かった。§2・§3 の埋め実験は埋め範囲が W を含み、検証できていない (§10.3)。

**結論 (本 run): 受入 1 (書込み元 store の IR site) は未達。ただし、unit 477 で `0x10a9f910` の下位 4B を `0x1029e5d8` から `2` に変えた書込みは、IR の `store` 経路ではないことを、挙動を変えない計装 (C 呼出しなし) で確かめた。** D17 (IR の 8B→4B 縮退) の仮説は、この書込みには当てはまらない見込み。

## 1. 基準

- 素材: `fl-win64` は `extracted/block00031_PE.bin` だけを `tar --zstd --wildcards` で展開 (2.9 s)。`work-m11`・`work-liftdiff` は worktree に展開 (4.8 s)。toolchain は `[EMSDK]`・`[RETDEC]` (既存のインストール先)。
- `m11_gen_ir2.sh` rc 0 (51.5 s、490,735 行) → `m11_build.sh` rc 0 (26.1 s) → `survey_units.mjs` rc 0 (13.3 s): `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (§2 と一致)。

## 2. スタック埋めへの感度 (`SV_STK_FILL`: 各 unit の直前に SP 直下 8 KiB を埋める)

> **訂正 (#1620 次 run、§10.3)**: 本節の埋め範囲 `[sp−8 KiB, sp)` は W (`0x10a9f910`) を含む。埋めで W を上書きしていたため、本節の埋め値依存 (埋め値ごとの kind の変化・§3 の unit 134 の trace) は、W の書込みの影響を含み、検証できていない。REPORT_1046 §19 の FILL 結論と同じ扱い。

| 埋め値 | ok | oob | abort |
|---|--:|--:|--:|
| なし | 870 | 16 | 0 |
| 00 | 872 | 12 | 2 |
| aa | 866 | 18 | 2 |

- kind が変わる unit は 8 件: 134 (なし ok → aa oob)・144 (なし oob → 00 ok)・149・153・158・265・304 (oob → abort)・555 (oob → abort)。最初の分岐は unit 134 (埋め aa)。
- 結果が埋め値に依存する。推定: lift 側が書かれていない stack 領域を読んでいる (命令レベルでは未確認)。REPORT_1046 §19 の結論を survey で再確認した。

## 3. unit 134 (埋め aa) の trap 位置

> 注: 本節の trace は W を含む埋め (`SV_STK_FILL`) で取った。§2 の訂正を参照。

- frames: `function_413870 ← function_639920 ← function_63a330 ← function_63a5e0`。最上位は wasm-function[2080]:0x14dec3 の `i32.load8_u offset=0`。
- 直前の列: `local0+48` の qword を読み (`i64.load offset=48`)、`local0+72` へ複製し、その値を `i32.wrap_i64` して読み取りアドレスに使う。値が 0 なら分岐で飛ばされる。
- 推定 (未実測): `local0+48` は未初期化の stack 残骸。埋め 00 では 0 になり分岐が飛んで ok、埋め aa では OOB、と整合する。
- 注意: IR の `define i64 @function_413870()` は引数なしだが、呼出し側 `function_639920` は 3 引数で呼ぶ。wasm 側の型との対応は未確認。

## 4. 計装の副作用 (C 呼出しを含む計装は挙動を変える)

| 版 | 0..477 の survey | 基準との差分 unit |
|---|---|---|
| 基準 (計装なし) | ok 422 / oob 6 | — |
| 対照: 計装なし・同じ経路 (`emcc -c boot_final3.ll -o work/obj/boot.o` + `M11_KEEP_BOOT_O=1`) | ok 422 / oob 6 | 0 |
| `watch_store_682.py --fns function_903d20,function_904190,function_abfd60` (store 7 件に `m11_sw` 呼出し) | ok 423 / oob 5 | unit 304 (oob → ok) |

- unit 304 は §2 で埋め値に依存する unit。`m11_sw` の呼出しが stack 残骸の並びを変えたと読める。以後、C 呼出しを使う計装 (`watch_store_682.py` 系) は、基準との差分を必ず確認すること。 (`trap_w1620.py` の注釈の「REPORT_1046 §20」は存在しない節を指す。この表が根拠。)

## 5. unit 477 の UStrAsg (`SV_TRACE_AT=477`、0..477 の実行)

- unit 477 の trace の `[m11][UStrAsg]` は 1 件のみ: `dest=0x10bd5a08 src=0x6befcc old=0x0`。`dest=0x10a9f910` は無い。よって UStrAsg (`m11_ov.c` の C helper) は unit 477 の書込み元ではない。
- 同じ trace の icall は `0x6bfd60`・`0xf960`。OOB 直前は `function_903d20 ← function_904190 ← function_abfd60`。

## 6. C 呼出しなしの計装 (`tools/m11/trap_triage/trap_w1620.py`)

- 方式: IR の全 store 54,041 件 (store 行の全数と一致、未マッチ 0) の直前に、「`0x10a9f910` の下位 4B が OLD と等しく、store 範囲がその 4B と重なる」を判定する。真なら、site 固有の OOB アドレス (`0xE0000000 + site`) への volatile load に `select` で差し替える。C 呼出し・新規 global は無い。trap の wasm 位置から site を引く処理は未実装 (`sites_trap.json` は site → fn・line・store のみ。wasm 位置は持たない)。
- 陰性対照 (OLD = `0x1029e5d8`、unit 477 直前の値): 0..477 の全 unit で kind と frames が対照と一致 (差 0)。site trap の発火は見られなかった。
  - 判定基準: 対照 (計装なし・同じ経路) と、各 unit の kind と frames (wasm 関数名の列) が一致すること。wasm offset は計装でコードサイズが変わるため比べない。判定は関数単位なので、同一関数内の先行発火は区別できない。
  - unit 477 の trap は従来どおりの自然 OOB と推定 (`function_903d20` wasm[5371]:0x5c949c、命令は `i64.load offset=0` と推定 = `*(arg-8)` の参照カウント読み。命令種は未確認)。
- 陽性対照 (OLD = 0): unit 1 で `ok → oob` (`memory access out of bounds`) で発火 (W への初回書込みを検出)。検出機構は IR store に対して動く。OLD = 0 では 0..477 の 69 unit の kind が変わる (oob 75 件。`SURVEY_UNITS` の `oob: 75` と同じ run)。全 942 unit では 115 unit (ok→oob 106、halt0→oob 7、miss→oob 1、other→oob 1)。kind が変わるのは、発火した unit が trap で止まるため。942 unit の数は差し戻し (round 1) のレビュー run が同じ計装で再現した値 (本 PR での再測定ではない)。
- 解釈: 0..477 の実行で、`0x10a9f910` の下位 4B が `0x1029e5d8` の間に、W と重なる IR store は実行されていない。よって unit 477 の `0x1029e5d8 → 2` (下位 4B) の書込みは、IR の store 経路ではなく、C 側 (`m11_simd.c`・`m11_rt.c`・`m11_win.c`・`m11_fnstubs.c`・shim の C、またはそれらの生成元) の書込みと推定する。根拠: IR の store は全数計装済み、`llvm.memcpy`/`llvm.memset` の呼出しは IR に 0 件。「C 側」は推定。IR に store として無い書込みの候補は、ほかに 2 つ残る (棄却していない): 機械語 store の lift 脱落、closure 外の関数。

## 7. 含意

- D17 (IR の qword store が 4B に縮退) の仮説は、unit 477 の下位 4B 書込みには当てはまらない (その書込みは IR store ではない)。
- 残る構図 (推定): 上位 4B の `1` は 477 より前の 8B 書込み (`0x1_1029e5d8`、REPORT_1046 §14) の残り。下位 4B だけを後から C 側が書き、上位が残る。「上位が残る」は埋め値依存 (§2・REPORT_1046 §19) と整合する。
- 次の手順 (子 issue に分割): (a) C 側の書込み主体を特定する。C 呼出しを増やさない方式 (C 側で「W と重なる & 下位 4B == OLD」のとき不正アドレスへ書いて trap) で、対応する C 関数を絞る。(b) 陽性対照を先に取る。(c) 0..477 の kind と frames が計装なしの基準と一致することを実測で確認する。(d) IR に store として無いことを判定する: 機械語 store の lift 脱落・closure 外の関数を候補に含め、棄却または特定する (#2672)。

## 8. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | 書込み元 store の IR site | 未達。IR store 経路ではない見込み (§6)。書込み主体は未特定 (子 #2672) |
| 2 | D17 か別類型か | 未達。unit 477 の書込みは IR 縮退 (D17) に当たらない見込み (§7) |
| 3 | 修復後の回帰 | 未達 (修復未実施) |

## 9. 差分 0 の証跡 / 再現

- 測定 commit `2ba1bce8`: 追加は `tools/m11/trap_triage/trap_w1620.py` のみ。`git diff --stat f4fa48f9 HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_rt.c tools/m11/m11_win.c tools/m11/trap_triage/survey_units.mjs tools/m11/ldfix` の出力は空 (既存コードの差分 0)。
- 修正 commit `debd55d0` (表示と docstring のみ。計装ロジックは不変)。`git diff 2ba1bce8 HEAD -- tools/m11/trap_triage/trap_w1620.py` の出力 (`debd55d0` 時点で確認。以後この範囲は変えていない):

```diff
diff --git a/tools/m11/trap_triage/trap_w1620.py b/tools/m11/trap_triage/trap_w1620.py
index 799cc5cd..c171bab2 100644
--- a/tools/m11/trap_triage/trap_w1620.py
+++ b/tools/m11/trap_triage/trap_w1620.py
@@ -2,7 +2,7 @@
 """trap_w1620.py (#1620): 監視番地 W への「上書き元」を、C 関数呼出しを使わずに捕まえる IR 計装。
   W の下位 4B が OLD (既定 0x1029e5d8, unit 477 直前の値) で、store 範囲が W と重なるとき、その store を
   site 固有の OOB アドレス (0xE0000000 + site) への volatile load に差し替える。
-  → survey の trap frame (wasm offset) から site を引ける。計装は select と load だけで C 呼出しを含まない
+  → trap の wasm 位置から site を引く処理は未実装 (sites_trap.json に wasm 位置は無い)。計装は select と load だけで C 呼出しを含まない
      (watch_store_682.py の m11_sw 呼出しは unit 304 の結果を変えた: REPORT_1046 §20)。
   usage: trap_w1620.py [--src work/boot_final3.ll] [--out work/probe1620] [--w 0x10a9f910] [--old 0x1029e5d8]
   出力: <out>/boot_trap.ll と <out>/sites_trap.json (site -> {fn, line, store})。"""
@@ -19,15 +19,17 @@ OLD = int(opt('--old', '0x1029e5d8'), 0)
 os.makedirs(out, exist_ok=True)
 
 STORE = re.compile(r'^(\s*)store (.*), ptr (nonnull )?(%[-a-zA-Z$._0-9]+|@[-a-zA-Z$._0-9"]+|inttoptr \(i64 (-?\d+) to ptr\)|null)(, align \d+)?\s*$')
+STORE_ANY = re.compile(r'^\s*store ')
 DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
 WIDTH = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'ptr': 4, 'float': 4, 'double': 8}
 
 lines = open(src_path).read().split('\n')
-outl = []; fn = '?'; site = 0; sites = {}; skipped = 0
+outl = []; fn = '?'; site = 0; sites = {}; unmatched = 0
 for ln, line in enumerate(lines, 1):
     m = DEF.match(line)
     if m: fn = m.group(1)
     s = STORE.match(line)
+    if not s and STORE_ANY.match(line): unmatched += 1
     if not s or fn == '?':
         outl.append(line); continue
     ind, vs, ptr = s.group(1), s.group(2), s.group(4)
@@ -49,4 +51,4 @@ for ln, line in enumerate(lines, 1):
     ]
 open(os.path.join(out, 'boot_trap.ll'), 'w').write('\n'.join(outl))
 json.dump(sites, open(os.path.join(out, 'sites_trap.json'), 'w'), indent=1)
-print(f'trap sites: {site} (skipped 0)')
+print(f'trap sites: {site} (unmatched store lines: {unmatched}; 計装されない store)')
```

- 出力一致: 同じ入力 (main 側の作業ツリーにある `tools/m11/work/boot_final3.ll`、21 MiB) で旧版と新版を走らせ、`boot_trap.ll` の sha256 は両方 `517da10a…`、`sites_trap.json` は両方 `45ab0c1e…` (一致)。表示は `unmatched store lines: 0`。旧版の `(skipped 0)` は常に 0 の固定値で、未マッチ件数ではなかった。合成入力 (`!tbaa` 付きの store を 1 件含む) では `unmatched store lines: 1` を出すことを確認。
- 確認: `grep -cE '^\s*store ' work/boot_final3.ll` = 54,041 = `sites_trap.json` の件数 (未マッチ 0 の判定は、この 2 数の一致で行う)。
- 計装 build は `work/` にだけ置き、各回の後に `m11_build.sh` で基準へ戻した (restore rc 0 を 4 回確認)。`git status` に `work/` 以外の差分なし。
- 再現 (`CF` は `store_watch_2270.sh` と同じ `-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=0 -DM11_OV_CLASSCREATE=0 -I.`):
  1. `python3 trap_triage/trap_w1620.py --out work/probe1620 --old 0x1029e5d8`
  2. `rm -f work/obj/boot.o work/obj/ov.o; emcc -c work/probe1620/boot_trap.ll -o work/obj/boot.o $CF`
  3. `M11_KEEP_BOOT_O=1 bash m11_build.sh`
  4. `SV_RAW=1 SV_ONLY=0,1,...,477 node trap_triage/survey_units.mjs work/probe1620/trap.json`
  5. 復元: `rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh`

## 10. #1620 run (HEAD `d6176933` = origin/main): 前提が現 HEAD で再現しない・REPORT_1046 §19 の埋め実験は W を上書きしていた

測定 commit: `b1d4c328` (`probe_1620_fill.mjs` の修正。以後の変更は注釈 1 行のみ・§10.6 参照)。素材 (`fl-win64`・`work-m11`・`work-liftdiff`) は `oc_artifacts` の取得物を展開。toolchain は `[EMSDK]`・`[RETDEC]`。

初期 SP (sp0) の定義: `probe_1620_fill.mjs` で `_m11_boot_enter` を呼んだ後 (例外時は boot 前の SP に戻した後) の `_emscripten_stack_get_current()` の値。以下の「初期 SP」はこの値。

### 10.1 現 HEAD の基準は REPORT_1620 §2 と一致しない

- 測定: `m11_gen_ir2.sh` rc 0 (35.5 s、490,735 行) → `m11_build.sh` rc 0 (20.6 s) → `survey_units.mjs` rc 0 (6.9 s): **`ok 872 / oob 14 / halt0 7 / miss 47 / other 1 / noproc 1`**。REPORT_1620 §2 の `870 / 16` とは違う。
- 同じ runner で 7d15ceab (本 issue の前提の測定 commit) を別 worktree で再構築すると `ok 870 / oob 16` (REPORT_1620 §2 と一致)。差は runner 側ではなく、7d15ceab 以降のコード変更による。
- HEAD の unit 477・484・492 は、なお `oob` (`memory access out of bounds`)。ただし 492 の trap 位置は `function_4133f0` ← `function_4473f0` ← `function_446400` ← `function_446ad0` ← `function_ad5700` (`survey_units.mjs` の frames)。§2 の unit 492 の入力 (`0x100000003` の書込み) とは別の経路。

### 10.2 `0x10a9f910` への書込みは build の静的データ配置 (初期 SP の位置) で消える

`probe_1620_fill.mjs` (埋めなし、`FILL=-1`) で、各 build の初期 SP と W の関係、W への書込みを測った。W は初期 SP より下に位置する (W − SP の値を表に示す)。

| build | 内容 | 初期 SP | W − SP | W への書込み (unit 477・484・492) | survey |
|---|---|---|---|---|---|
| A | 7d15ceab (IR・C とも旧) | `0x10a9fa10` | −256 | あり (`1_2` → `1_3` → `0`) | 870 / 16 |
| B | 新 IR + 旧 C | `0x10a9fa10` | −256 | あり (A と同じ) | 870 / 16 |
| C | 新 IR + 新 `m11_ov.c` + 旧 `m11_rt.c` | `0x10a9fa40` | −304 | なし (unit 496 の 1 件のみ変化) | 872 / 14 |
| D | 新 IR + 新 C (= HEAD) | `0x10aa1260` | −6480 | なし | 872 / 14 |
| E | B + `static unsigned char g_pad_1620[6176]` (C 側の静的データを増やしただけ) | `0x10aa1230` | −6432 | なし | 872 / 14 |

- A と B は IR が違う (7d15ceab と新 IR。差は `boot_final.ll` の 6 行、`fix_ld108` の IR 差分) が、結果は同じ。IR の差は、この現象の原因ではない。
- B と E は IR が同じで、差は C 側の静的データ量だけ (pad)。pad で初期 SP が 0x10a9fa10 → 0x10aa1230 に動くと、W への書込みが消える。
- 5 つの build (A〜E) のうち、W への書込みが観測されたのは初期 SP が 0x10a9fa10 の A と B だけ。SP の一致が書込みの十分条件かは未確認だが、配置が結果を変えることは E の対照で示された。
- 含意: #1620 の前提「特定の IR store が `0x10a9f910` に `0x100000003` を書く」は、HEAD (D) では成立しない。ただし、書込みの site は固定である。REPORT_2672 は、W に書いた主体を C 版 `function_4133f0` の局所 `u32 len` (`m11_ov.c:345`) と同定した。W への到達先はフレーム配置で変わる。W は初期 SP から −256 の位置にあり、SP を動かした E では外れる。
- 推定: 「配置で消える」は 5 build の観測からの推定である (A〜E の 5 件のみ。配置を変える他の要因は未切り分け)。HEAD で同じ site が別の番地を書くかは未測定。
- #2672 の同定との対応 (未検証): REPORT_2672 の基底 `0x10a9f8e0` + 48 = W。基底が初期 SP − 0x130 なら、W = 初期 SP − 0x100 と整合する (`0x10a9fa10 − 0x130 + 0x30 = 0x10a9f910`)。ただし REPORT_2672 は初期 SP を記録しておらず、その build (origin/main `208b4ef9` の IR・C) は A (7d15ceab) と C 版が異なる (7d15ceab → 208b4ef9 の変更行数 `git diff --stat`: `m11_ov.c` 108・`m11_rt.c` 25)。よって、REPORT_2672 の build が A/B のどちらに当たるか、基底が A/B の配置で成立するかは、本 run では検証していない。検証は #2706 (同一 build で初期 SP と基底を同時に測る)。

### 10.3 REPORT_1046 §19・本ファイル §2・§3 の埋め実験の訂正

- 旧 `probe_1620_fill.mjs` の埋め範囲 `[sp−64 KiB, sp)` は W を含む (sp − W は 256 (A) / 6480 (D))。埋めは各 unit の前に行われるため、W は埋め値で上書きされていた。REPORT_1046 §19 の「上位 dword が埋め値のまま残る」は、埋めた値が W に残った結果であり、W の値が未初期化 stack 読みに由来するという証拠ではない。REPORT_1046 §19 の「W の値が埋め値に依存する」は取り消す。ただし、埋めた範囲の残りが unit の挙動を変えること (下記、unit 492) は、修正後も残る。
- `survey_units.mjs` の `SV_STK_FILL` (`[sp−8 KiB, sp)`) も W を含む。本ファイル §2・§3 の埋め値依存 (unit 134 を含む) は、同じ理由で検証できていない。本 PR では `SV_STK_FILL` を変えない (未検証と扱う)。
- 修正 (commit `b1d4c328`): 埋めの前に W の 8 B を退避し、埋めの後に戻す。修正後の実測 (D = HEAD):
  - 埋め −1 (なし)・0・0xAA・0xCC の 4 回で、W の遷移は 0 件 (end `0x0`)。埋め値に依存しない。
  - 修正後の A (旧 build) の埋め −1: unit 477 `0x1_1029e5d8 → 0x1_2`、unit 484 `→ 0x1_3`、unit 492 `→ 0x0` (REPORT_1046 §14 と一致)。埋め 0xAA: unit 477・484 の遷移は同じだが、unit 492 の `0x1_3 → 0` は出ず、unit 496 の値も変わる (`0x10bd5b30`、埋め −1 は `0x10bd5d70`)。W の上書きは除いてあるので、この差は埋めた範囲の残りが unit の実行を変えたことを示す。未初期化 stack 読みの候補は未特定 (REPORT_1046 §19 の次の手順 (a))。
- 訂正の反映: 本ファイル §2・§3 と REPORT_1046 §19 に訂正注記を付けた。

### 10.4 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | 書込み元 store の IR site (fn・行) の特定 | 未達。HEAD (D) では W への書込みが起きない。旧 build (A・B) の書込みは IR site に紐づかない (REPORT_2672 の同定は C 版 `function_4133f0`・`m11_ov.c:345`。A/B との同一性は未検証、#2706)。配置で消えるのは推定 (§10.2) |
| 2 | D17 か別類型かの判定 | 未達。前提の store が現 HEAD に無いため判定の対象が無い |
| 3 | 修復後の回帰 (ok→非 ok 0 件) | 条件不成立 (D17 判定なし・未実施)。元 issue の受入 3 は D17 と判定された場合のみ |

### 10.5 次の手順 (PM 判断)

- #1620 の前提 (HEAD で `0x10a9f910` に `0x100000003` を書く store) は現 HEAD に存在しない。受入 1〜3 はこのままでは達成できない。範囲の再定義 (例: HEAD の unit 492 OOB `function_4133f0` の入力出自へ置換) か、前提の終結かを PM が判断する。
- 本 run は子 issue を起票していない (残りは再測定と追跡だけになるため)。
- 未解決表の #1620 行: PM agent の判断待ち: 範囲を再定義するか終結するか・既定案: 範囲を再定義 (受入 1〜3 を HEAD の unit 492 OOB の入力出自へ置換)。
- #2672 の同定 (A/B 配置での成立) の検証は #2706 に追加する (既存 issue へのコメント。新規起票はしない)。
- 埋め実験 (`SV_STK_FILL`・`probe_1620_fill.mjs`) の結果は、埋め範囲が観測対象を含まないことを確かめてから使うこと (`probe_1620_fill.mjs` は修正済み)。

### 10.6 差分の証跡 (WORKFLOW §6)

- 測定 commit: `b1d4c328` (`probe_1620_fill.mjs` の実行される行は以後変えていない)。`git diff --stat b1d4c328 -- tools/m11` の対象は REPORT 2 件と probe 1 件のみ (build・survey・IR 生成のコードの差分 0)。
- probe の差分は注釈 1 行だけ (`git diff b1d4c328 -- tools/m11/trap_triage/probe_1620_fill.mjs` の出力を下に示す)。注釈を除いた行の一致: `diff <(git show b1d4c328:… | grep -v '^//') <(grep -v '^//' …)` の出力は空。`node --check` 通過。注釈は実行に影響しないため、再測定は行わない。

```diff
diff --git a/tools/m11/trap_triage/probe_1620_fill.mjs b/tools/m11/trap_triage/probe_1620_fill.mjs
index 8f4cbc38..d986a405 100644
--- a/tools/m11/trap_triage/probe_1620_fill.mjs
+++ b/tools/m11/trap_triage/probe_1620_fill.mjs
@@ -1,6 +1,6 @@
 // #1620 診断 (読取り + stack 埋め。IR 不変): 各 unit の前に、現在 SP より下の stack 領域を FILL で埋める。
 // 0x10a9f910 の遷移と unit ごとの戻り値が、埋め値に依存するかを見る。usage: node fill_probe.mjs <fillByte> <from> <to>
-// 注: W は埋め範囲 [sp-64KiB, sp) に入りうる (#1620 の実測では sp - W = 0x1950)。埋めで W を上書きすると遷移が埋め値に見えるため、埋めの前後で W の 8B を保存・復元する。
+// 注: W は埋め範囲 [sp-64KiB, sp) に入りうる。埋めで W を上書きすると遷移が埋め値に見えるため、埋めの前後で W の 8B を保存・復元する。
 import fs from 'fs';
 const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
 const W = 0x10a9f910;
```
