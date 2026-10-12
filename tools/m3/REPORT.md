# tools/m3 — REPORT.md (M3: 中規模 lift → wasm)

作成: 2026-10-09 (M3 成果物の独立検証セッション ses_* 検証者による記録更新)
対象コミット: 3f71131 以前の work ツリー上の untracked 成果物

## 判定サマリ

| M3 検証条件 (`docs/REFERENCES.md` `[STRATEGY]`) | 状態 | 実測 |
|---|---|---|
| 1. 対象 wasm bit-exact ユニット一致 | **部分達成** | 純計算 4 関数 (EasyFLAC slice) は bit-exact 50/50 PASS (`m3.sh`)。ただし「中規模 dylib 丸ごと wasm 動作」(FastMM/Delphi closure 677 関数) は llvm コンパイル未通過 |
| 2. 性能比の記録 (>10x なら route 再評価) | **達成 (本検証で新規測定)** | 同一 lifted IR の native(-O2) vs wasm/node: crc8 1.44x, crc16 1.33x, silog2+mulbits 約 36x* — *i64 FFI の BigInt ボックス化込みでオーバーヘッド主導。データ主導の crc 系はどちらも **10x 未満 → route 再評価不要** (§1.5 条件適用なし) |
| 3. lift-down IR pass 1 本以上 + 定量化 | **未達** | ir_patch.py の pass 数は stage 計上として出力するが、性能影の定量化なし。flags.sh に比較用の O0 入口フラグ (M3_EMCC_O0) を用意したのみ |

総合: **M3 は未完了** (純計算 subset の実証までは進んだ)。

## 検証で実行した E2E (1 回の再実行)

```sh
bash tools/m3/m3.sh     # exit=0
```

- 事前ステップ: `ir_patch.py` が `tools/m2/work/easyflac.drc.ll` 由来の正規形
  `work/ef_norm0.ll` (= easyflac_norm.ll 1025 define と datalayout 差分のみ実測) から
  純計算 4 関数の call-graph 閉包を選別 (`_FLAC__crc8`, `_FLAC__crc16`,
  `_FLAC__bitmath_silog2`, `_FLAC__bitmath_extra_mulbits_unsigned`, 外部参照 0)
- [1] M3 セッション実測の再現: `work/t1_h.mjs` → **crc8 bit-exact 6/6 OK (exit=0)**
- [2] 4 関数 bit-exact: `work/m3_e2e.mjs` → **PASS 50 / FAIL 0**
  (`_FLAC__crc8` 7/7, `_FLAC__crc16` 4/4, `_FLAC__bitmath_silog2` 19/19,
  `_FLAC__bitmath_extra_mulbits_unsigned` 20/20)
  - 参照実装は FLAC upstream 公開定義に基づく独立実装
    (silog2 / extra_mulbits は bitmath.c の定義写し、crc8/crc16 は poly 0x07 / 0x8005
    init=0 MSB-first の標準定義 + EasyFLAC slice 内の表データと bit 一致確認)
  - crc16 の 8 バイト高速パスが参照する slice-by-8 サブテーブル群
    (VA 0x30b40〜 約 4KB) を EasyFLAC slice から写す必要があった
    (`m3_e2e.mjs` コメント参照)
- [3] 性能比: `work/m3_perf_native.c` (同一 IR を x86_64 host clang -O2 で
  ネイティブ再コンパイル, テーブル領域は mmap MAP_FIXED で VA 通りに敷設)
  vs wasm/node。JIT による純関数ループ消去/定数畳み込みを防ぐため、
  hrtime ベースの非恒等化入力 + sink 蓄積で測定 (誤測定 2 型を検知・排除済)。

| 実装 | silog2+mulbits (200k 回) | crc8 (200k 回, 変動長 32..2079B) | crc16 (同) |
|---|---|---|---|
| native x86_64 -O2 (同一 IR) | 0.61 ms | 235.2 ms | 78.0 ms |
| wasm/node (BigInt FFI 込み) | 22.0 ms | 338.3 ms | 104.1 ms |
| 比 (wasm/native) | 約 36x | **1.44x** | **1.33x** |

> silog2+mulbits の 36x は i64 引数の BigInt 変換 (FFI) オーバーヘッドが支配的で、
> wasm 計算本体を表さない。データ主導の crc 系が 1.3〜1.5x 程度であることを
> 本命の指標とする。

## poc_crc8_results.json (M3 セッション実測) の独立再計算照合

6/6 すべて録値 == 再計算値 (python による CRC-8 poly 0x07 独立実装)。
`117, 233, 254, 219, 201, 74` はいずれも一致 → bit-exact 録は信頼可。

## M3 セッション成果物の修正 (独立検証で見つかった破損)

1. **ir_patch.py が動作不能だった** (最終編集 19:59 で破損):
   - `main()` が未完成の [A9] 関数 (`ce_lift_all`) を呼ぶ RuntimeError/TypeError
   - `collect_declare_lists` が ce_after 関数内の dead code に埋もれ未定義
   - 修復: [A9] を「残存 constexpr の検出・計上 (count-only)」として確定
     (命令化 lift は未実装 — 中規模 IR の現ブロッカー, 下記)、
     [B1] 修正結果の blocks 書き戻し漏れ (subn 結果が捨てられていた) を修正、
     `collect_declare_lists` をモジュールレベルへ復旧。
   - mm closure (`work/fftest_mm.ll`, 677 define) に再適用し `work/ft7.ll` と diff:
     差分は [B1] 修正が初めて実効適用された 280 件 (未初期化 alloca load → 値 0)
     のみ (他は byte 等価)。
2. `m3.sh` を新規作成 (E2E 再現エントリ。既定手順の全工程を 1 コマンド化)。
3. `work/m3_e2e.mjs` / `work/m3_perf_native.c` を新規追加 (上記)。

*このセッションの検証前状態では ir_patch.py を土台にした再実行が不可能だったため、
「M3 セッションの実測 (crc8 t1.* 経路) の再現」+「閉包 4 関数での 4 関数 bit-exact」の
双方を満たす形で E2E を再実行した。*

## 中規模 lifting (FastMM/Delphi closure 677 関数) の現ブロッカー (未解決)

- M3 セッションは `closure_lift.py` (declare 閉包固定点反復) で
  FastMM/Delphi closure (seed `0x412d60`) を固定点まで伸ばし
  `work/fftest_mm.closure.json` / `work/fftest_mm.ll` を生成したが、
  wasm コンパイルには届かない。
- 本検証による再現: `emcc work/ft7.ll ...` → `exit=1`,
  `ft7.ll:4281:13: error: constant expression type mismatch: got type 'i64' but expected 'i32'`
  (`store i32 ptrtoint (ptr @global_var_15eac48 to i64)` 形成)。
  ir_patch [A9] 計上では ft7 相当に `add 5 / ptrtoint 119 / inttoptr 20 / bitcast 43`
  の残存 constexpr。
- 未解決事項 (M3 継続 or M5 入りの問題点として継承):
  1. [A9] 残存 constexpr の命令化 lift (型幅付替えを含む) 未実装
  2. VMT 間接呼が selective decode-only lift で IR から欠落する事象 (M2 既知 (d) 同型)
     の動作確認は本検証でも未実施 (`work/probe_vmt.*`, `work/vmt_call_hits.txt` は調査材料)
  3. Delphi try-finally 実測 (0x40ace0 + closure での例外無し経路 bit-exact 計画のみ)
     は M3 セッション・本検証とも未達 (E2E 記録なし)
  4. lift-down pass の性能影定量化は未達 (flags.sh の O0 比較用意のみ)

## 成果物一覧 (コミット対象, work/ を除く)

- `closure_lift.py` — RetDec selective lift の declare 閉包固定点反復 (fftest 実績 r0..r9)
- `ir_patch.py` —RetDec .ll → wasm 再コンパイル可能形の機械変換 ([A1..A9]/[B1][B2]/[C1])
- `flags.sh` — 定型フラグ集 (emcc 6.0.12 / RetDec 5.0 pin, GLOBAL_BASE=512MB)
- `m3.sh` — E2E 再現エントリ (本検証で追加)
- `REPORT.md` — 本ファイル
