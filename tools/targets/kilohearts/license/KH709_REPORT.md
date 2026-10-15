# KH-14 (#709) — ymm (VEX.256) 命令の gen_simd 対応と module F の 2 関数 (0x180f89cf0 / 0x180fb6124)

- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。ただし §3 の xmm/ymm 別グローバルは **silent miscompile の類型候補** (KH-51 #3306 で扱う)。
- 親 #656 (KH-13) の閉包展開で、この 2 関数が `KeyError: 'i256'` (`license/lift/gen_simd.py` の i256 経路なし) により停止していた (`KH656_REPORT.md`)。
- 素材: `fl-win64` (HeartCore.core_64 は `ui_eval/extract_core.sh` で sha256 一致の展開を確認)・`toolchain-retdec` (`[RETDEC]`)・`toolchain-emsdk` (`[EMSDK]`)。`plugins-kilohearts` は HeartCore の展開にのみ使用。
- 測定 commit: 本 PR のコード commit (下の `§5`)。

## 1. 結論

| 受入条件 (#709 元の本文) | 結果 |
|---|---|
| (1) i256 を gen_simd.py が扱えるようにする (または liftlib の ymm helper へ) | **達成**。`license/lift/gen_simd.py` に ymm 整数語彙 (`vpcmpeqb/w/d`・`vpmovmskb`・`vinsertf128`) を追加し、`.i256.ll` を emit。liftlib 経路は採らなかった (vpmovmskb ymm が未実装、§18.7 of liftlib appendix) |
| (2) 2 関数が lift され emcc を通る・ネガコン | **部分**。試行ビルド (2 関数を lift 対象に追加) は emcc 通過。ただし 2 関数の ymm/xmm 別グローバル問題と SSE 語彙不足が残るため、**product 設定 (`lic_config.json`) には入れていない**。ネガコン (i256 経路を外す → KeyError) は実測 |
| (3) 既存 KH snap-in 14 種の bit-exact 維持 | **未実施**。本 PR は既存 module F の出力不変 (wasm sha 一致, §4-a)。snap-in 14 種の 200/200 × 12 系は走らせていない → KH-52 へ移管 |

完了範囲に縮めたため、issue #709 は `Closes`。未達は子 issue #3306 (KH-51) と #3307 (KH-52) に移した。

## 2. 変更

- `license/lift/gen_simd.py`: `gen256` (i256 語彙の IR 定義)・`stub256` (未対応 i256 は abort スタブ)・`main` の i256 分岐 (`<dst>.i256.ll` を出力)・`vzeroupper` を no-op。
- `license/lift/kh_lower.py`: 使われた `@ymmN` を `global i256 0` として定義 (ymm を使わない module の出力は不変)。
- `license/lic_build.py`: `simd.c.i256.ll` を emcc の入力に追加 (snapins の `build.py` と同じ扱い)。
- `license/lic_config.json`: `modules.F.excluded_i256` に `0x180f89cf0`・`0x180fb6124` を記録。`kh656_closure.py` の i256 除外を product 設定に固定する (`lic_build.py` は当該キーを読まないため wasm は不変)。
- `license/scripts/kh709_ymm_check.py`: 語彙の bit-exact 検証 (host AVX2 の intrinsics と突合・ネガコン付き)。

## 3. 2 関数が使う命令と、未解決の 2 点

2 関数 (`kh_180f89cf0`・`kh_180fb6124`) の ymm 命令: `vpcmpeqd` / `vpcmpeqw`・`vpmovmskb`・`vinsertf128`・`vzeroupper` と、i128 の `vmovd`・`vpshufd`・`vpxor`・`tzcnt` (SSE 系は license 版に無い)。

- **(a) xmm/ymm 別グローバル (silent miscompile の懸念)**: VEX-128 命令は `@xmmN` (i128) だけを書き、`@ymmN` の下位 128bit は更新されない。`kh_180f89cf0` では `store i128 @xmm2` の直後に `load i256 @ymm2` を読むため、実機 (同一レジスタ) と異なる値が vinsertf128 に入る。→ **KH-51 (#3306)**。
- **(b) SSE 語彙不足**: 試行ビルドで `i128 __asm_pcmpeqd`・`__asm_pcmpeqw`・`__asm_pmovmskb`・`__asm_pshufd`・`__asm_vpxor`・`__asm_tzcnt` が abort スタブになった (到達すると abort する loud 失敗)。→ **KH-52 (#3307)**。
- **(c) vzeroupper の挙動変更 (loud → silent)**: 基底 `8303a813` の gen_simd は `vzeroupper` に処理が無く (未知 mnemonic)、呼ばれると停止する abort スタブだった (loud)。本 PR で no-op にしたため、呼ばれても停止せず、上位 ymm は後続の `@ymmN` undef 書込みに任される (silent)。product 設定 (module F) は 2 関数を含まないので現行出力は変わらない (sha 不変) が、2 関数を lift すると (a) と合わせて黙って誤る。→ **KH-51 (#3306)**。
  - DEFECTS 行案 (`docs/WORKFLOW.md` §5。ID は PM 採番。`docs/DEFECTS.md` は本 PR では編集しない):
    - 症状: 未対応の VEX.256 上位初期化命令が abort せず無言で通り、後続の ymm 読みが実機と異なる上位値を見る (silent)。
    - 根本原因: `vzeroupper` を no-op 化し、上位 128bit を後続の `@ymmN` undef 書込みで表す設計。VEX-128 の書込みが `@ymmN` の下位に反映されないため、この前提が成り立たない。
    - 観測: 未測定 (2 関数は product 設定に入れていないため、現行出力では発火しない)。
    - 検出信号: `vzeroupper` の後に同じ `@ymmN` を `load i256` する IR の有無 (静的)。
    - 修復 (案・未実装): KH-51 で `vzeroupper` を `@ymmN` の上位 128bit のゼロ化として IR 化し、xmm/ymm を同期する。

## 4. 検証 (実測)

host: nproc=4, Linux, host の clang 18.1.3, emcc は `[EMSDK]` の 6.0.12。

**(a) 回帰: module F (lift 8 件・shim 4 件、本 PR の product 設定) は不変**

| 項目 | 変更前 (HEAD `8303a813`) | 変更後 (本 PR) |
|---|---|---|
| `lic_build.py --module F` | emcc OK, wasm 54394 bytes, sha256 `7ba79e65…8c7707` (実測 real 14.2 秒) | emcc OK, wasm 54394 bytes, sha256 同一 (測定 commit `88144ea56`: real 13.45 秒、うち retdec 11.0 秒。stage-0 キャッシュを退避して全工程を実行) |

**(b) 変更前の再現: 2 関数を lift 対象に加えた build**

- HEAD の gen_simd: `KeyError: 'i256'` (`gen_simd.py` の `CT[ret]`)。
- 本 PR の gen_simd (試行): emcc OK, wasm 64661 bytes。`simd` report は helpers 12・undefined(abort stub) 7 (SSE 系 6 件 + `__asm_int3`)。undefined の内訳は §3 (b)。試行後は config を戻した。

**(c) ymm 語彙の bit-exact (`scripts/kh709_ymm_check.py 20000 1`)**

| 検査 | 結果 | 所要 |
|---|---|---|
| positive: vpcmpeqb/w/d・vpmovmskb・vinsertf128 (imm 0/1) | cases 100000, **mismatch 0** | 3.7 秒 (real, 検証スクリプト全体) |
| ネガコン: vpcmpeqd の icmp eq→ne | mismatch 20000 (rc=1) → **FAIL を検出** | 同上 |
| RESULT | **PASS** (positive=True, negctrl_detected=True) | — |

**(d) 閉包の除外ガード (`scripts/kh656_closure.py --rounds 1`、測定 commit `88144ea56`)**

| 項目 | 結果 |
|---|---|
| `excluded_i256` (記録) | `[180f89cf0, 180fb6124]` |
| `new_lift` | 34 件。両件とも含まれない |
| round 1 の build | wasm 54394 bytes, undefined imports 0 |
| 終了コード | rc=1 (`--rounds 1` の上限で閉包に達しないための既定の終了) |

修正前 (`ddf4773d`) は `new_lift` に両件が入ることをレビューが実測している。実行後は `lic_config.json` を修正版へ戻した (作業ツリーに差分なし)。

## 5. 測定 commit と差分

- 測定 commit (コードを変えた最後の commit): `88144ea56` (`lic_config.json` の `excluded_i256` 追加)。
- コード差分 (測定 commit → HEAD): `git diff 88144ea56 HEAD -- tools/targets/kilohearts/license ':!*.md'` = **0 行** (以降は REPORT の追記のみ)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| xmm/ymm 別グローバル (VEX-128 の上位ゼロ化・下位同期) | 2 関数を lift すると silent に誤る恐れ | #3306 (KH-51) |
| SSE 語彙 (pcmpeqd/w・pmovmskb・pshufd・vpxor・tzcnt) の license 版欠落 | 2 関数は abort スタブ経由で loud に失敗 | #3307 (KH-52) |
| 2 関数の lift・bit-exact 突合・既存 snap-in 14 種の 200/200 × 12 系 | 受入 (2) (3) | #3307 (KH-52) |
| `vzeroupper` の no-op 化 (基底の loud abort → silent)・§3 (c) の DEFECTS 行案 | 2 関数を lift すると上位 ymm の誤りが無言で通る | #3306 (KH-51) |
