# liftdiff — flelift (x64c) 全数採点と m11 RetDec route 比較 (CAB-232)

**判定: 達成**。tools/flelift (x64c, CAB-226) の lift 産物を liftdiff ハーネスに本格接続し、FLEngine closure
**7,421 関数の全数採点** (9 pattern × native/wasm, boot state あり, **584 秒** / 14 shard) を実施した。
結果は **一致 4,143 / 不一致 633 / 実行不能 2,645**。同一関数での m11 RetDec route (既存全数) との突合で
**m11 mismatch → flelift match が 2,226 関数**、逆に **flelift のみ不一致は 5 関数** (比較可能 4,776 の 0.1%)。
「その関数自身の欠陥と確定」できる leaf 差分は m11 の 1,281 → **19** に減少。
CAB-226 残差だった **0x6a7990 の 2/16 byte 差は lift 欠陥ではなく flelift harness のバグ** と特定し
1 行修正で **16/16 一致** まで解消した (§4)。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| 全数採点 (closure 7,421 / 9 pattern / boot state あり) | **一致 4,143 (55.8%) / 不一致 633 (8.5%) / 実行不能 2,645 (35.6%)**、所要 584 秒 (14 shard) |
| 比較可能 (native 完走 case あり) | 4,776 関数 (64.4%)。うち不一致 633 (13.3%) |
| leaf (callee を呼ばず差分 = 自己欠陥確定) | **19** (m11 route は 1,281) |
| m11 RetDec route との同一関数突合 | match&match 1,907 / **m11 mismatch → flelift match 2,226** / **flelift のみ不一致 5** / 両方不一致 627 |
| x64c が解消した m11 欠陥類型 (2,226 の m11 主因) | load_dropped 891 / callsite_arg_drop 226 / callee_divergence 219 / memory_semantics 200 / ret_only 161 / wasm_trap 151 / icall_drop 108 / xmm_arg_drop 66 / simd_helper 50 / import_arg_diff 44 / fp_flag_unreflected 30 / arg_drop 23 / zero_init_drop 20 / spill_slot_deref 15 / import_call_seq 11 / unresolved_callee 7 / rep_string_helper 4 |
| flelift のみ不一致 5 関数 | `409070`・`4090e0` (memory_semantics: image 0x11e6a38 への 42 block 書込み差) / `50cb00` (unlifted_callee→OOB カスケード) / `6a1c30` (xmm_arg_drop+trap) / `786c80` (callee_divergence) |
| 不一致 633 の主因 | unlifted_callee 379 / callee_divergence 119 / callsite_arg_drop 66 / ret_only 23 / memory_semantics 13 / import_arg_diff 8 / zero_init_drop 7 / arg_drop 6 / xmm_arg_drop 6 / wasm_trap 6 (wasm_trap 該当 361 = OOB 354 + abort 7) |
| 実行不能 2,645 の内訳 | native_fault 1,158 / native NULL deref 691 / **lift 集合外 (no_wasm_definition) 389** / hang 357 / 署名未対応 50 |
| 0x6a7990 (CAB-226 残差) | **lift 欠陥に非ず**。fle_wasm_runner.mjs の scratch zero 化 no-op バグ → 1 行修正で spot 16/16 一致 (§4) |
| liftdiff e2e 回帰 | OTT 欠陥検出・unit#18 の PASS 2 項目は HEAD と完全同一。unit18 の 3 項目目 FAIL は並行 CAB-131 による tools/m11/work/boot_final3.ll 再生成 (20:48) 起因で HEAD コードでも同 FAIL (worktree A/B で実証、§6) |

## 2. harness 接続の方式 (tools/liftdiff 側のみで実現、tools/flelift は読取)

x64c は **LLVM IR ではなく C 転写** (`void f_<VA>(void)` × 7,031 + CPU 状態 R[16]/X[16] + `ott_dispatch`) であるため、
`build_wasm.build()` に `clift` ブランチ (`ldlib/clift.py`) を追加し、IR をコンパイルせずに同じプロトコルへ載せた:

1. **署名は m11 RetDec IR から借用** (`ir` を署名ソースとしてのみ使用): case の引数パターン (9 種) と callee 引数比較を
   m11 route と完全同一にし、2 route の比較可能性を保つ。lift 産物 C は「f_ entry に `ld_fle_trace(0xVA)` を挿入」する
   テキスト計装のみ (7,031 関数、意味不変)。
2. **ブリッジ** `rt/fle_ldbridge.c`: `ld_core.h` (native と同一の復元/差分/応答モデル/プロトコル) を include し、
   case 実行だけを flelift 呼出し規約 (Win64 ABI → `R[RCX..]/X[0..3]`/guest stack → `ott_dispatch(va)`) に変換する。
   アドレスは**恒等写像** (`wasm_origin=0x400000`, delta=0)。heap(=TEB/gs) 0x1D00000、arena(blob) 0x20000000。
3. **import**: 全 IAT 名 (341) の強い `imp_*` を生成し `ld_core.ld_stub` (native と同一応答モデル + 呼出しログ) に統一。
   fle_cpu.c 既定 import と fle_lifted.c の weak 既定は両方上書き (`-D` リネーム + weak オーバーライド)。
   → import 呼出し列 (calls[]) の比較が m11 route と同じ精度で効く。
4. **ランナ** `rt/fle_runner.mjs` (`runner_js` target キーで差し替え): 関数呼出しを `_fle_ld_run()` (C 内で引数設置→dispatch→
   R[RAX]/X[0] 返却) に置き換え。abort/timeout 時は応答を返してからプロセス終了し、セッションの再起動に委ねる。
5. **lift 集合外の扱い**: lift 実績 (`lift_meta.json`, 7,031) を `lifted.json` に置き、非 lift 関数 (390) は
   実行せず `unexec/no_wasm_definition` に分類。dispatch が lift 集合外 VA (VMT/関数ポインタ経由) に着地した場合は
   m11 route の unresolved_callee と同一の「**ret 0 で継続**」とし、回数/最終 VA を case JSON (`unlifted`/`unlifted_va`) に記録
   → タグ `unlifted_callee` (high)。

接続過程で見つけ harness 側を修正した問題 (いずれも採点データの品質に直結):

| 問題 | 修正 |
|---|---|
| スタック引数の off-by-one (疑似 ret 未 push で第 5 引数以降が 1 slot ずれ) | fle_run と同一の fake ret push を追加 (entry rsp = STACK_TOP−8) |
| **guest stack (2MB) 枯渇で静的領域を破壊 → node がサイレント死亡、badjson 12,901 case** | guest stack を 2MB→32MB、emcc C スタックも 8MB→32MB に拡大 (深い再帰の破壊窓を遠ざける) + `ott_dispatch` ラッパで範囲外 push を wasm trap に変換 (`gstack_ovf` 計数) |
| emcc abort / vm timeout 後のモジュール状態汚染 | 応答を返してから process.exit → セッションが再起動 |
| 応答行が壊れた (badjson) 場合の連鎖 | `runners.py`: badjson でランナ再起動 + 当該 case を 1 回再試行 |

## 3. 全数採点と類型 (チケット要件 1, 2)

verdict 全行: `results/flelift_closure_verdicts.tsv` (7,421 行)。採点は boot 状態あり
(`liftdiff.py bootstate targets/flelift.json` — native で unit 0..16 実行、m11 と同一の native 参照)。
m11 route 同様、native が全 pattern で落ちる関数は比較不能 (実行不能) に計上される。

不一致 633 の主因内訳と解釈:

| 類型 | 主因 | 解釈 |
|---|---|---|
| `unlifted_callee` | 379 | lift 集合外への間接呼び (VMT/関数ポインタ, native は実行する) を ret-0 継続した結果差。実在しない callee は **0x4071d0 / 0x4781f0 / 0x478420 / 0x478c70 / 0x4781e0 / 0x406fd0 等の計 ~7 個** (m11 closure 自体に含まれない = closure 被覆ギャップ、残りは pattern 由来の null/garbage 関数ポインタ)。lift 集合に加えるだけで解消見込み (CAB-233 へ引継) |
| `callee_divergence` | 119 | 差分が callee 境界で初観測 (例: 0x11f2f20 が GetMem(0x412c20) に渡すサイズが native 7 / wasm 5 — 文字列長計算の差、§5 追跡対象) |
| `callsite_arg_drop` | 66 | call site 引数 0 詰め (native≠0 / wasm=0) |
| `ret_only` | 23 | 戻り値のみ差 |
| `memory_semantics` / `import_arg_diff` / `zero_init_drop` / `arg_drop` / `xmm_arg_drop` | 13/8/7/6/6 | 個別調査対象 |
| `wasm_trap` | 6 (主因) / 該当 361 | OOB 354 + abort 7。**f_410360 (TObject.Free 系, VMT-0x50 間接 call) が最上位フレームに頻出** — 単一 helper 経由のカスケードで、直接原因は呼出し側の ret-0 継続/値差 |

実行不能 2,645 は lift 集合外 389 を除くと 2,256 で、m11 route の実行不能 2,261 とほぼ同等
(native 参照が同一のため、native が落ちる関数集合は route 非依存)。

## 4. 0x6a7990 の 2/16 byte 差 — 原因特定と修正 (チケット要件 3)

**結論: x64c lift の欠陥ではない。fle_diff.py ハーネスの wasm 側 scratch 初期化バグ。**

- 再現: `python3 tools/flelift/fle_diff.py` → 0x6a7990 p01/p02 の dst 1-3 block byte 差 (r戻り値/xmm0/他メモリは一致)。
- 分析 (機械語 0x6a7990 = MMX RGB 乗算): src=0 なら dst は `pmulhuw(0,mm7)=0 + paddw mm6` の語の飽和のみで決まり
  mm7 に非依存。実機 native の dst は語順 [mm6.w0..w2] の繰返し = **正しい**。flelift wasm は第 2 pixel 以降に
  `+1..+3` の小さな差を生む (= src が非零の積が混入)。
- 根本原因: `fle_wasm_runner.mjs` `resetState()` の
  `U8.fill(0, 0x20000000, 0x3100000)` は **start (0x20000000=536MB) > end (0x3100000=51MB) で no-op**
  (JS TypedArray.fill 仕様)。native 側 `fle_reset()` は scratch を正しく zero 化するため、
  **wasm 側だけ前 case (`pat` prep の 6a7e40/6a7180/69a130) の pat byte (i*13+7) が scratch に残留**し、
  0x6a7990 (prep 無し, src=0x20004400) が両側で異なる src を読んでいた。
  p01 の 1 byte 差は関数出力ではなく **baseline 汚染** (byte15 が native=0 / wasm=残留値)。
- 修正: `tools/flelift/fle_wasm_runner.mjs` の resetState を
  `U8.fill(0, 0x2100000, 0x3100000)` (arena) + `U8.fill(0, 0x20000000, 0x20100000)` (scratch) に分割 (1 行修正 + コメント)。
- 検証: 修正後 `python3 tools/flelift/fle_diff.py` = **7 関数 16 case 全て equal** (CAB-226 の 14/16 → 16/16)。
  `results/verdict_flelift.jsonl` / `verdict_summary.json` を更新済み。
  liftdiff 側でも同一 case 形 (n=5/8, mm7/mm6 同値, blob あり/なし) を 4 種実行し全て match — lift 本体の無実を裏取り。

## 5. m11 RetDec route との比較表 (チケット要件 2)

`tests/compare_routes.py` (全数突合スクリプト) → `results/flelift_vs_m11_routes.md`。m11 側は
コミット済み `results/m11_closure_verdicts.tsv` (RetDec route 全数, ldfix 適用前)。

| m11 \ flelift | match | mismatch | unexec |
|---|---|---|---|
| **match** | 1,907 | **5** | 363 |
| **mismatch** | **2,226** | 627 | 32 |
| **unexec** | 10 | 1 | 2,250 |

- **flelift のみ一致 2,226** — m11 の主要欠陥類型が x64c で構造的に消えたことの実証
  (load_dropped 891 / callsite_arg_drop 226 / callee_divergence 219 / memory_semantics 200 / ret_only 161 /
  wasm_trap 151 / icall_drop 108 / xmm_arg_drop 66 / simd_helper 50 / fp_flag_unreflected 30 / spill_slot_deref 15 ほか)。
  代表: `409c80` Move (m11: spill_slot_deref) / `4133f0` _UStrAsg (m11: memory_semantics) / `4123c0` resourcestring 初期化。
- **flelift のみ不一致 5 (0.1%)** — `409070`/`4090e0` (image 0x11e6a38 への書込み集合差, wasm が 42 block 余分に書く),
  `50cb00` (unlifted ret-0 → f_410360 OOB), `6a1c30` (機械語が xmm0..3 を読むが署名 fp=0 → trap), `786c80`
  (callee 境界で乖離)。leaf 確定の自己欠陥は 19 関数 (arg_drop 3 / ret_only 12 / memory_semantics 3 / その他 1)。
- **flelift 実行不能が +384** — 内 389 は lift 集合外の no_wasm_definition。実行可能集合は route の lift 被覆に依存するため、
  x64c の被覆拡大 (390 関数) がそのままスコア向上の餘地 (CAB-233)。
- 参考: CAB-231 A/B の m11 RetDec + ldfix route は 一致 3,161 / 不一致 2,005 / 実行不能 2,261 (要再測と注記あり)。
  本採点は ldfix **非適用**の RetDec route を比較基準にした (tools/m11 は CAB-131 担当が稼働中のため未再測)。

## 6. liftdiff e2e 回帰 (チケット要件 4)

tools/liftdiff の変更は全て後方互換: `clift` target キー (未指定 = 従来動作) / `runner_js` (既定 ld_runner.mjs) /
`lifted.json` (存在時のみ) / `classify(..., route='ir')` (既定) / `simdint` 静的特徴 (追加キー) / badjson 再試行
(badjson 発生時のみ働く復旧) / **ld_core.h は 1 行も変更していない** (bit-identical、m11 のメモリレイアウトも不変)。

検証 (worktree A/B: HEAD コード vs 本ブランチコード, 同一 IR / 同一 boot state):

1. **OTT 欠陥検出 (212 関数)**: OTT_SUMMARY は両者完全同一 (match 39 / mismatch 106 / unexec 67, D1〜D6 全検出)。
2. **unit#18 分析**: `_UStrAsg` (mem diff) / `Move` (spill_slot_deref) の 2 PASS は両者同一。
   3 項目目 (4123c0 resourcestring, 旧基準 wasm trace ≤6) は**両者とも FAIL** — 並行 CAB-131 担当が
   `tools/m11/work/boot_final3.ll` を再生成 (Oct 10 20:48) したためで、HEAD コード + 新 IR でも同値
   (native 53 / wasm 25) になることを worktree で実証。**本チケットの変更とは無関係** — 判定基準の再較正は
   m11/CAB-131 側の IR 確定後に行うべき (本チケットでは触らない)。
3. **m11 closure sample:800 の定量 A/B**: HEAD 一致 354 / 不一致 207 / 実行不能 239 (badjson 27 case =
   wasm_trap 誤分類) → 本ブランチ 一致 **356** / 不一致 **205** / 実行不能 239 (badjson 2 case)。
   差異 10 case はすべて badjson 再試行による復旧分で**非劣化 (微増)**。

## 7. 成果物

| パス | 役割 |
|---|---|
| `ldlib/clift.py` | C 転写 lift (x64c) の liftdiff 接続ビルド (計装 / imps 生成 / np テーブル / emcc) |
| `rt/fle_ldbridge.c` | flelift ブリッジ (ld_core 共有 / case→Win64 ABI→dispatch / unlifted ret-0 / guest stack guard) |
| `rt/fle_runner.mjs` | flelift 用 wasm ランナ (abort/timeout 時の clean exit) |
| `targets/flelift.json` | flelift target (恒等写像 delta=0) |
| `ldlib/session.py` / `runners.py` / `classify.py` / `pe.py` / `liftdiff.py` / `build_wasm.py` | 後方互換拡張 (runner_js / lifted.json / badjson 再試行 / route 別分類 / simdint / irfeats 分岐) |
| `tests/compare_routes.py` | 2 route の全数突合 (4 象限 + 類型遷移) |
| `results/flelift_closure_verdicts.tsv` | 全数 verdict (7,421 行) |
| `results/flelift_vs_m11_routes.md` | 比較表 (4 象限 / 解消類型 / flelift のみ不一致リスト) |
| `docs/FORMAT.md` §6 | clift ルートの仕様 (target キー / unlifted フィールド / タグ差分) |
| tools/flelift (最小修正) | `fle_wasm_runner.mjs` scratch zero 化修正 + `results/verdict_flelift.jsonl` 更新 (16/16) |

再現:

```sh
# 前提: bash tools/flelift/fle_lift.sh (CAB-226 産物 work/lift/{fle_lifted.c,fle_data.c,lift_meta.json})
python3 tools/liftdiff/liftdiff.py build targets/flelift.json
python3 tools/liftdiff/liftdiff.py bootstate targets/flelift.json        # native unit 0..16 (約 1 分)
python3 tools/liftdiff/liftdiff.py batch targets/flelift.json --set closure --shards 14 \
  --state auto --out tools/liftdiff/work/flelift/batch_closure.jsonl     # 全数 約 10 分
python3 tools/liftdiff/tests/compare_routes.py work/flelift/batch_closure.jsonl \
  results/m11_closure_verdicts.tsv results/flelift_vs_m11_routes.md      # 比較表
python3 tools/flelift/fle_diff.py                                        # 0x6a7990 修正の再現 (16/16)
```

## 8. 限界 (正直な注意)

- 一致 = 与えた状態・引数で一致 (必要条件)。実行不能 2,645 の大半は native が落ちる case (route 非依存)。
- `unlifted_callee` 379 は ret-0 継続の結果差を含む (m11 の unresolved_callee と同一セマンティクス)。
  実在 callee ~7 個を lift 集合に加えれば大半が消える見込み (実測は未実施 = CAB-233)。
- wasm_trap 該当 361 はカスケードを含む。真の個別欠陥確定は leaf 19 (§1)。
- 0x11f2f20 (GetMem サイズ 7 vs 5) 等の値差は文字列長計算まで追えず未同定 — leaf/類型データで個別追跡可。
- badjson が 200 case / 121 関数 残存 (再試行後も壊れる = ランナ再起動でも同 case が壊れる経路)。
  該当関数は verdict が保守側 (不一致) に倒れる。原因の深掘りは未了 (深い再帰での C スタック破壊の疑い)。
- boot state は unit 0..16 止まり (unit #17 から native が TLS で落ちる = m11 と同一の環境限界)。
- flelift native 参照は single-thread 前提 (lock 系非 atomic)、SEH/例外経路は fail-fast (CAB-227 の範囲)。

## 9. 下流チケット (CAB-233 への引継ぎ)

1. **lift 集合の被覆拡大**: 非 lift 390 関数 + unlifted callee 実在分 (~7 個: 0x4071d0 / 0x4781f0 / 0x478420 /
   0x478c70 / 0x4781e0 / 0x406fd0 等を fle_entries.json に追加して fle_lift.sh 再実行) → unlifted_callee 379 と
   no_wasm_definition 389 が主ターゲット。回帰判定は本チケットの `batch` + `compare_routes.py`。
2. **wasm_trap カスケードの個別化**: f_410360 (TObject.Free 系) 経由の OOB 354 case を、unlifted 解消後に再測し
   真の欠陥関数を分離 (leaf 判定は `liftdiff.py summary` の「自己欠陥確定」)。
3. **native 全起動拡張** (元案 3): boot unit #17 (0x455790) の TLS 環境 (gs:[0x58] TlsIndex) を ld_native 側で
   完走させれば実行不能 2,645 → 大幅減の見込み (m11 REPORT §6 と同一の対策)。
4. **ott_unsup の残存 site 特定**: abort 系 detail は 160 字切捨てで site VA が消える — `fle_lifted_tr.c` の
   `ott_unsup(0xADDR)` 呼出し site を静的抽出し、lift 未対応命令の実行時顕在化リストを CAB-227 (D12) へ
   (本採点での abort 系は少数: wasm_trap 該当 361 のうち abort 7)。
5. **xmm 引数を持つ関数の署名精緻化** (flelift のみ不一致 `6a1c30` 等): m11 IR 署名が fp 引数を欠く関数群 — 署名ソースの
   精緻化 (機械語 arity からの補正) で比較可能化。
6. **badjson 残留 200 case の完全復旧** (121 関数): 深い再帰経路での C スタック破壊の疑い。再現は
   `work/flelift/batch_closure.jsonl` の badjson 関数を単独実行 (tools/liftdiff 内)。
