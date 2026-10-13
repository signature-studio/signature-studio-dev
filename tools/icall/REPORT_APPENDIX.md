# tools/icall REPORT 付録 — §10.1 (#530) と §11 ICALL-6 (#361) の全文

> 正本: `tools/icall/REPORT.md` (§10.1・§11 に要約)。行数上限 (250 行, `docs/DOC_MAP.md` §1) のため全文をここに無変更で分割移動した (見出し番号は本体のまま)。

### 10.1 #530: OTT 回帰の再実行 (素材付き)

検証起点: base `d5e6f98` (#514 merge 済み main) + 本ブランチのコミット。素材: `analysis-ott-binaries plugins-ott work-m6-ott work-icall toolchain-retdec toolchain-emsdk`。
再現: `ANALYSIS_DIR=$HOME/analysis bash tools/icall/icall_e2e.sh` (`/home/ubuntu/work/analysis` 固定だったパスを `ANALYSIS_DIR` で上書き可に変更。既定値は従来通り)。

| 検査 | 結果 (実測) |
|---|---|
| `icall_e2e.sh` (GitHub Actions runner, load 0.45 開始・直列 1 本) | **PASS**, 71 秒, exit 0 (コミット済み HEAD `9410981` で再実行: PASS, 70 秒, load 0.27 開始) |
| 〃 [4/4] matrix | scenario 89, failed 0, cell 50,236 中 50,236 が native と bit 一致, max_ulp 0, state_diff_qwords 0 |
| 〃 [3/4] 監査 | OTT F 非IAT間接 call 81: 落ち 70 → 0, tail-jmp 11: 落ち 11 → 0, jump table 8 展開 |
| 〃 [+] CRT 関数単位 gate | SSE2 経路 6 関数すべて xmm0 600/600 bit 一致 → PASS |
| `python3 tools/icall/tests/test_icall.py` (pe 部含む) | RESULT PASS (0 failed), 1.9 秒。pe 部の固定値 (F271 成功 / sites 96 / errors {} / jt-chain ≥ 5 / 新 section) すべて PASS |

**e2e は連続配置を検出しない (実測)**: `next_slot()` の修正を外した版 (`return a`) で同じ `icall_e2e.sh` を流しても PASS (89 scenario 全 bit 一致)。OTT の F 280 関数では修正を外すと関数 range が連続する組が 21、修正後は 0 だが、RetDec の `define` 数は両者とも 331 (併合は起きない)。つまり OTT matrix は #514 の欠陥の回帰 gate にならない。
そのため `tests/test_icall.py` に「書換え後の関数 range + stub が連続配置でない」チェックを追加した (PE の `func_range_new` / `stub` / `comis_stub` から算出、RetDec 不要)。
ネガティブコントロール: `next_slot()` の `a + 16 if a == c else a` を `a` に戻すと `FAIL rewrite 関数 range が連続配置でない (#514) 21 組` で RESULT FAIL (exit 1)。修正を戻すと PASS (exit 0)。

**書換え PE の差**: #514 前 (`237010e^`) と現行の `icall_rewrite.py` で OTT を書換えると section サイズが 189405 B → 189741 B (+336 B) でバイト一致ではない。連続配置が 21 組あった OTT では #514 の「連続しない配置はバイト一致」は適用されず、配置が変わる (matrix は上記の通り 89/89 bit 一致のまま)。

**liftlib 統合への影響**: `passes.icall` を持つ liftlib target は `tools/liftlib/targets/ott_route.json` のみ (`grep '"icall"'` で確認)。`liftlib_e2e.sh` / `python3 -m liftlib regress` は fa_gain / kh_gain / OTT (`ott.drc.ll` 系) だけを扱い icall pass を通らないため、#514 の影響は無い。`liftlib_e2e.sh` 自体は `tools/targets/{freshair,kilohearts}/work` (素材 `work-liftlib-targets`) が無く未実行。
代わりに `pipeline.run_all('targets/ott_route.json', detect_only=True)` を実行: prelift 280 関数・96 site・errors {} → RetDec → restore (dispatch 96 / comis 119)、23.8 秒 (load 0.62)。RetDec 出力の `define` 数 331 (内訳は未分解: range 279 本に対し RetDec が補助関数も定義する。併合有無の判定は未実施)、書換え後 range の連続 0 組。

## 11. ICALL-6: CRT 経路の残 (#361)

既知類型との関係 (`docs/DEFECTS.md` / 本書 §4 とは別体系): **新規 2 件 (N3・N4)**。検証起点 commit: `d5e6f98` (main) → 実装 `0aa9b96` + 続く commit。DLL は §8 と同じ。

### 11.1 結果 (route, native = 実機械語, 600 点/関数, seed 3, xmm0 raw 64bit bit 比較)
| 項目 | 修復前 | 修復後 |
|---|--:|--:|
| FMA3 経路 `1801a9be0` | 42/600 | **600/600** |
| 他 4 関数の FMA3 経路 (`1801b4154` `1801c1240` `1801c12f4` `1801aa1a0 --kernel`) | 600/600 | 600/600 |
| `1801a9be0` 負入力混在 (`--neg`, SSE2 / FMA3) | (未測定) | 600/600 / 600/600 |
| override | 3/4 | **4/4** (`1801c8c00` `1801c8cb8` `1801a9a6c` `1801a9b38`) |

- **N3 (新規): RetDec が `vmovapd [rsp+disp], xmm` (xmm→stack の VEX store) を store にせず `call void @__asm_vmovapd(i128 <宛先の旧値>, i128 <値>)` にして落とす。** 宛先の旧値はエントリで 1 回 load した stack slot の値 (`%5 = load i128, i128* %0`) で、後続の `vmovapd xmm1, [rsp+0x40]` は `@__asm_vmovapd(i128 %5)` = 旧値になる。`1801a9be0` では `1801a9f4d` の store が落ち `1801aa0d6` の再読込 (符号復元) が未初期化値になる。
  検出信号: `call void @__asm_v?mov(aps|apd|dqa|dqu|ups|upd)*(i128 %D, i128 %S)` かつ `%D = load i128, i128* %alloca`。修復: `ir_fix_vstore.py` が `%D` 専用 alloca を新設し store + 読出し側で reload (phi に使われる `%D` と 256bit は触らず `vstore_unresolved` に数える)。OTT の実測: 修復 1 件 (`1801a9be0`)・未修復 19 件 (SSE `movups` i128 11 件 + `vmovdqa` i256 8 件。`oi.restored0.ll` に対し `ir_fix_vstore.py` を実行した件数)。
  **ただしこれだけでは 42/600 は直らなかった** (N3 のみ有効の build で FMA3 経路 42/600 のまま実測)。原因の本体は N4。
- **N4 (新規): closure 内 direct call の memory-ABI (`icall_rewrite.py` の `abi_ret_store/ret_load`) が戻り値を rax と xmm0 だけ BLK に通し、xmm1 を通さない。** FMA3 版 reduction `1801c1240` は `xmm0 = hi, xmm1 = lo` の 2 値を返し (逆アセ: `1801c12a9 vfnmadd132sd xmm1, ...` が最後の書込み)、`1801a9be0` は call 後の `1801a9f9c`〜 で xmm1 (lo) を使う。xmm1 が callee の戻りでなく呼出し側の元の値のままになる。
  実測の症状 (N4 未修復 build): 入力 xmm1 を 0 に固定すると native と 425/600 が一致・175/600 が 1ulp 差、入力 xmm1 に乱数 (`fn3_diff.py` の既定) だと 42/600 (max_ulp 9.27e18 = 暴走)。
  修復: `ret` 前に `movsd [BLK+0x98], xmm1`、direct call 後に `movsd xmm1, [BLK+0x98]` (+8 byte/store・load, `ICALL_ABI_XMM1=0` で無効)。`BLK+0x98` は既存レイアウトで未使用 (`0x90` = rax-in, `0xA0` = comis)。

### 11.2 ネガティブコントロール (gate = `diff/crt_fn_gate.sh`, build はそれぞれ作り直し)
| 操作 | 結果 |
|---|---|
| `ICALL_ABI_XMM1=0 bash tools/icall/ott_route.sh` (N4 を外す) | `1801a9be0 --fma 1` が **42/600** で gate FAIL (SSE2 経路・他 4 関数の FMA3 経路は 600/600) |
| `ICALL_FIX_VSTORE=0 bash tools/icall/ott_route.sh` (N3 を外す) | 通常入力は全 600/600 だが `1801a9be0 --neg --fma 1` が **321/600** で gate FAIL (負入力 = 符号復元経路 `[rsp+0x40]`)。通常入力の gate だけでは N3 の欠落は検出できなかったため `--neg` を gate に追加 |
| `ir_fix_vstore.py` の store 出力を `pass` に置換 | `tests/test_icall.py` が FAIL (1 件) |
| 両方有効 (既定) | gate PASS |

再現 (レビュー指摘, HEAD `b23593c`, 各 build 作り直し + `crt_fn_gate.sh`, runner 4 core): `ICALL_ABI_XMM1=0` = gate FAIL (`--fma 1` 42/600, `--neg --fma 1` 48/600; build+gate 35.4 s)。`ICALL_FIX_VSTORE=0` = gate FAIL (`--neg --fma 1` 321/600・他は 600/600; 37.5 s)。既定で再 build すると gate PASS。

### 11.3 `1801a9a6c` の rax
native の rax は **全入力で `0x7fffffffffffff00`** (測定 8 入力: 4.0, 2.0, 0.25, 100.0, 0.0, 1.5, 12345.678, 0.001)。`1801a9b02 movabs rax, 0x7fffffffffffffff` ... `setb al` の残りで、sqrt の戻り値ではない scratch。
`diff/rax_callers.py 1801a9a6c` (capstone, 各 call 元の直後 8 命令で rax/eax/ax/al の最初のアクセスを判定) の実測: 直接 call 元 46 件 (`call`; tail jmp は 0) のうち、rax を先に**書く** 39 件・8 命令内で触れない 7 件・**読む 0 件** (exit 0)。よって rax は戻り値として使われず、gate は xmm0 のみ判定でよい。
原因: route / x64c は BLK の rax、native は sqrt 本体末尾の scratch (上記) を返すため一致しない。**不要の根拠として記載・gate に rax 判定は追加しない。** (限界: 先読み 8 命令の静的判定。7 件の「触れない」は 8 命令より先の読みを見ていない。)
`1801a9be0` (FMA3 経路) の rax も native と一致しない (gate 出力: `--fma 1` rax 558/600・`--neg --fma 1` 552/600、xmm0 は共に 600/600)。`rax_callers.py 1801a9be0` の実測: 直接 call 元 1 件 (`180126706`) で、直後 8 命令内に rax アクセス無し (READ 0)。rax を返り値として使う呼出し元は無いため gate は xmm0 のみで足りる (限界は上記と同じ先読み 8 命令)。
(同じ道具で `1801c8c98` (`_handle_errorf` ラッパ) の呼出し元 5 件を見ると `1801bdcba` が直後に eax を読む。読む対象が errorf の戻りかは未確認で、override は xmm0 のみを定義 → 未解決表に記載。)

### 11.4 `_handle_errorf` (1801c8cb8)
`1801c8cb8` の呼出し元は F の外の `1801c8c98` のみ (さらにその呼出し元 `1801bdca5` 他 5 件も F 外) のため closure に入らなかった。`ott_route.sh` は `ICALL_EXTRA_ROOTS` (既定 `1801c8cb8`) を roots に足す (閉包 +1 関数)。override は `rt/icall_ovr.c` に追加 (戻り = xmm1 全体, `ott_ovr.c` の移植)。`diff/crt_fn_gate.sh` が `work/route/override.json` で 4/4 を判定。
範囲外: `_handle_errorf` 到達は native が CRT 未初期化で SIGSEGV のため override の動的突合は無し (§8.3 と同じ限界)。

### 11.5 検証・再現
```sh
bash tools/icall/icall_e2e.sh                 # 全体 (gate は FMA3 5 + 負入力 2 + override 4/4 を含む)
bash tools/icall/diff/crt_fn_gate.sh          # gate のみ
python3 tools/icall/diff/rax_callers.py 1801a9a6c 1801c8cb8 1801c8c98
```

検証 (コミット済み HEAD `b23593c` = main 取り込み merge + REPORT 分割。コード差分は `d383226` の実装 + main 取り込みのみ。runner 4 core, load average は開始→終了):
| コマンド | 結果 | 所要 | load |
|---|---|--:|---|
| `OTT_SKIP_INFO=1 bash tools/ott/ott_e2e.sh` | PASS: 89 scenario / 50,236 cell 全一致, max_ulp 0, state_diff 0 | 25.9 s | 0.63→0.76 |
| `bash tools/icall/icall_e2e.sh` | PASS: 89 scenario / 50,236 cell 全一致, max_ulp 0, state_diff 0, 監査 落ち 70→0, tail-jmp 11→0, crt_fn_gate PASS (SSE2 6 + FMA3 5 + 負入力 2 + override 4/4) | 95.4 s | 0.70→1.04 |
| `python3 tools/icall/tests/test_icall.py` | PASS (0 failed; fix_vstore 2 件を含む) | 2.5 s | — |
(初回実装時 HEAD `d383226`: ott_e2e 25.0 s / icall_e2e 99.2 s / test_icall PASS。)
(修復前ベースライン同環境: ott_e2e 25.1 s PASS / icall_e2e 88.9 s PASS。ただし配布スナップショットの route wasm は N1/N2 未適用の古い build で gate FAIL だったため、`ott_route.sh` の再ビルドが必要 (icall_e2e.sh が行う)。)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ir_fix_vstore` の未修復 19 件 (`movups` i128 11・`vmovdqa` i256 8) | OTT の matrix は 50,236 cell 一致のため当面無影響。他 plugin で同類型があり得る | #90 にコメント (plugin 閉包 route 適用時に `vstore_unresolved` を監査) |
| `1801c8cb8` override の動的突合なし | float 版エラー経路の戻りは UCRT 仕様由来 | #90 にコメント (§8.5 と同じ限界) |
| `1801bdcba` が `1801c8c98` 直後に eax を読む (errorf 経路の rax 戻りの意味が未確認) | float エラー経路到達時のみ | #361 (本 issue に残し、到達 scenario 構築時に確認) |
| `/home/ubuntu/work/analysis` ハードコード (`ott_route.sh`) | runner では symlink 回避 | #294 |

## 12. #229: FLEngine 巨大 2 関数の範囲分割 lift (before / after)

既知類型との関係 (`docs/DEFECTS.md` / icall §4 とは別体系): **該当なし** (新規類型の確定は未)。

検証起点 HEAD `183158f7` (main)、素材 `fl-win64` (`block00031_PE.bin`)、4 core。
再現: `FL_WIN64_DIR=<展開先>/extracted bash tools/icall/measure_flengine_split.sh <outdir>`。

| 条件 | RetDec 所要 | 書換え後の落ち (非 IAT 374 site 中) | 備考 |
|---|--:|--:|---|
| CHUNKS=1 (2 関数を 1 回) | 42.97 s (roundtrip 全体, 単独実行) | **366** (kept_indirect 8) | before は 373 落ち (RetDec 素通し) |
| CHUNKS=2 (`--select-ranges` を 2 分割) | 42.24 s (roundtrip 全体, 単独実行) | **366** (kept_indirect 8) | 分割しても差なし |
| 検証スクリプト一括 (`measure_flengine_split.sh`, HEAD 再現) | 134.0 s (load 0.14 → 1.38) | base 366 / c2 366 | 段特定 (`passes_stub_count.py`) を含む |

- 関数範囲: `0xc589b0-0xc5d667` (19,639 B) / `0x128f9e0-0x1294ab8` (20,696 B)。site は各 183 / 191 (うち 8 が書換え後も IR に残る)。
- RetDec は正常終了 (タイムアウト無し、約 10 s で `Running phase: cleanup`)。落ちは時間切れではない。
- decode 段 (`--print-after-all` の `Input binary to LLVM IR decoding`) では stub 呼出し **377** 本。`Selected functions optimization` 段で 61 関数 → 4 関数 (2 関数 + stub 2)。
  以後は関数ごとに 1 モジュールへ分けて最適化され、stub 呼出しは `Sparse Conditional Constant Propagation` (SCCP) の 1 段で 377 → 11 へ減る (§12.1)。
- 範囲分割で落ちは減らない (CHUNKS=2 で 366 のまま)。仮説 A (RetDec の打ち切り回避) は**棄却**。
- 補足 (DEFECTS 候補): RetDec は `0x128c320` 直前の関数を `data inside code section 0x128c281--0x128c320` と誤認し、`0x128c320` を 1 バイト関数にする。`NonRecursiveCFGBuilder` が `function_128c320` への edge を毎回捨てる警告 (5 件) が出る。本件の 366 落ちとの因果は未検証。

### 12.1 ICALL-9 (#847): stub 呼出しが減る段の特定 (HEAD `cc816715`)

検証 (本 HEAD `cc816715`, 本 run で実機再実行): `measure_flengine_split.sh` 151 s (load 0.14 → 1.57, 4 core) で base 366 / c2 366 (§12 と一致)。`sccp_stub_drop.py` 62 s で dump 709 本。素材は `fl-win64` の `block00031_PE.bin` と `toolchain-retdec` (`/opt/retdec/bin/retdec-decompiler`) を使用。表と `sccp_pairs.tsv` の数値は実 dump の値。未再計測は「stub を含む基本ブロック 114」のみ (`dumps.tsv` の集計対象外、前回測定の値)。
再現手順:
```sh
FL_WIN64_DIR=<fl-win64 展開先>/extracted bash tools/icall/measure_flengine_split.sh $OUT   # base/rw.dll・base/after.ranges を作る
RETDEC_BIN=<RetDec>/bin/retdec-decompiler python3 tools/icall/sccp_stub_drop.py $OUT/base/rw.dll $OUT/base/after.ranges $OUT/sccp_stub_drop
```
`sccp_stub_drop.py` は `--print-after-all` の全 dump (709 本) を読み、関数ごとに stub 数・IR 行数・基本ブロック (ラベル数)・`br i1 undef`・0x1dc0080 の load/store を `dumps.tsv` に出す (1 行 = 1 dump の 1 関数、`idx` は dump 番号)。`passes.tsv` は段名ごとの全 dump 合計 (例: SCCP は 8 dump 分の合計) で、下表の範囲集計とは別物。stub 数が変わった関数の直前・直後は `sccp_pairs.tsv`。`passes_stub_count.py` は段の変化点しか出さず、本節の行数・基本ブロック・`br i1 undef` は出さない。

下表の値は `dumps.tsv` の dump idx 範囲の合計。列 4=stub, 5=行数, 6=基本ブロック, 7=`br i1 undef`。1 行で再現できる:
```sh
awk -F'\t' -v a=401 -v b=404 'NR>1 && $1>=a && $1<=b {s+=$4; l+=$5; n+=$6; u+=$7} END{print s,l,n,u}' $OUT/sccp_stub_drop/dumps.tsv
```
(a/b を変える。下表 3 行は 401–404 / 405–408 / 629–632。対象の 4 関数は `function_1cc0000` / `function_1cc9b70` / `function_1cd3f30` / `function_1cd3fe0`。)

| 段 (dump 名) | dump idx | stub 呼出し (関数合計) | 関数 IR 行数 (4 関数) | 基本ブロック | `br i1 undef` |
|---|---|--:|--:|--:|--:|
| `Global Value Numbering` (SCCP の直前) | 401–404 | 377 (183 + 192 + 1 + 1) | 16,380 | 621 | 0 |
| `Sparse Conditional Constant Propagation` | 405–408 | **11** (0 + 9 + 1 + 1) | 4,256 | 621 | **322** |
| 2 回目の `Sparse Conditional Constant Propagation` (直前は 2 回目の GVN, idx 625–628) | 629–632 | 11 (0 + 9 + 1 + 1) | 1,828 | 60 | 0 |

- **減る段は SCCP の 1 段** (SCCP の前後の段で stub 数が 377 → 11 に変わるのは SCCP のみ)。377 − 11 = 366 は落ちた site 数と一致する。ただし site と stub の対応は未確認 (算術の一致のみ)。
- 関数単位 (`sccp_pairs.tsv`): `function_1cc0000` は stub 183 → 0・IR 7,943 → 1,884 行・基本ブロック 303 → 303 (ラベル数は不変)・`br i1 undef` 0 → 161。`function_1cc9b70` は stub 192 → 9・IR 8,380 → 2,315 行・`br i1 undef` 0 → 161。
- stub を含む基本ブロックは `function_1cc0000` で 114。SCCP 後は stub を含むブロックが 0 になる (ブロック総数は不変)。
- SCCP の直前段 (`Global Value Numbering`) で、両関数とも `load i64, i64* inttoptr (i64 31195264 to i64*)` (= 0x1dc0080) が 99 本ずつ。SCCP 後は 0 本になり、`store` は両関数とも 1 本 (`stack_var_-649.0` の phi) が残る。
- 0x1dc0080 の読み出しは両関数合計 198 本 (各 99)。なお旧記述の「100 箇所」は、ここでは 1 関数あたりの値として誤りだった (読み出し 99 + store 1 = 100 の数え間違い)。
- 分岐の条件は、直前段で 0x1dc0080 から読んだ値の比較と推定される。SCCP 後にこの分岐が `br i1 undef` になる (両関数で各 161 本)。条件の直接の対応 (どの load がどの分岐の条件か) は未確認。
- **観測と未確定を分ける**: SCCP で分岐が `undef` になることは観測された。なぜ SCCP がこの load を `undef` と判定するか (load は通常 overdefined) は未確定 (#1014)。BLK 上の値が未初期化扱いになる経路か、RetDec の memory 扱いかは未確認。
- 仮説 A (範囲分割で回避) は §12 のとおり棄却済み。落ちの直接の段は SCCP で、その判定条件は未確定。修正は未実施。

### 12.2 残 (ICALL-9 の受入条件のうち未達)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1dc0080 の load が SCCP で `undef` になる条件の特定 | 366 site 落ちの真因の本体 | #1014 (ICALL-15) |
| 落ちた 366 site の IR 上の形 (消失 / 別関数への移動) の関数単位 before/after 分類 | 受入条件 2 未達 | #1014 |
| 修正して 0xc589b0 / 0x128f9e0 の kept を 366 から減らす | 受入条件 3 未達 | #1014 |
| `0x128c320` の関数境界誤認 (1 バイト関数化) と NonRecursiveCFGBuilder 警告 | 隣接関数の lift 欠落の疑い | 子 issue (下記) |
| jump table cmp/je 展開 / Balance・KH・FA wasm 差分 / stack 引数動的検証 / plugin closure バッチ | 本 run 範囲外 | 子 issue (下記) |
