# PY-269 (#3902): TUndoEvent_MovedFXTracks の VMT スロット 1 (0x1021670) の呼出し元と、[rbp+0x30] の所属

親: #3616 (PY-220)。前段: `tools/python/REPORT_PY203.md` §1・§3・§5、`tools/python/REPORT_PY198.md` §2。
前段の `REPORT_PY220.md` と `analysis/flapi/pe_py220_methods.py` は main 取り込み (c6a709ef1) で本 branch に入った (PY-220 #3616)。本 REPORT は PE の実測だけを根拠にする。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論

- **受入 2 (所属) は確定**: `[rbp+0x30]` (0x45c290 の引数) は 0x1021670 の**呼出しごとのスタック上のローカル**。ヒープのオブジェクトでも Self のフィールドでもなく、寿命は 0x1021670 の実行中だけ。
  - 型は Variant とみられる (推定)。0x45c290 は先頭 word で分岐し、0x45b480 は `test ax, 0xbfe8` (managed 判定) の VarCopy 形。
  - `[rbp+0x30]`・`[rbp+0x48]`・`[rbp+0x60]` の 3 つが連続するローカルで、3 要素の配列の先頭とみられる (推定。エピローグの `_FinalizeArray` 型の要素数 3 と整合)。
- **受入 1 (呼出し元) は一部のみ**: VMT の生成は classref 経由で、スロット 1 の仮想呼出しは PE 全体で 1639 件ある。受け手を TUndoEvent_MovedFXTracks に絞る作業は未了。子 [PY-275] #3944。
- 既存の `pe_vmt_probe.py --disp` は 10 進の disp (`[rax + 8]`) を取りこぼし、スロット 1 の呼出しを 0 件と誤判定していた。本 PR で修正 (§1)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` に展開 (2.9 秒、22,227,016 バイト)。
- 逆アセ: `pe_callgraph.load()` の線形走査 (int3 直後を関数先頭とみなす)。関数 0x1021670 の本体は 0x1021670〜0x1021a3f (`ret` の次が 0x1021a40 の別関数)。
- 測定 commit: `c6a709ef1` (main 取り込みの merge commit。probe と `pe_vmt_probe.py` の修正は `5c209c731` から変更なし)。

## 1. 受入 1: 0x1021670 の呼出し元

| 項目 | 実測 (probe の検査名) |
|---|---|
| VMT 0x1012f40 の vmtClassName | `TUndoEvent_MovedFXTracks`、VMT+8 = 0x1021670 (C1) |
| 0x1021670 への直接 E8 | 0 件 (C2) |
| RIP 相対で VMT VA 0x1012f40 を指す命令 | 0 件 (C4)。生成は classref 経由 |
| classref 0x1012e78 (VMT VA を格納する slot) の RIP 参照 | 1 件: 0x101ca74 (関数 0x101ca60) (C5) |
| `call qword ptr [X+8]` (スロット 1 の仮想呼出し) | PE 全体 1639 件 (C3)。既存 probe の 0 件は取りこぼし |
| `mov reg, [X+8]` → `call reg` の 2 段形 | 0 件 (直前 8 命令内に reg へ `[X+8]` の読込みが無い。`call reg` 1237 件のうち reg への読込みを持つのは 317 件で、いずれも `[X+8]` ではない) |

- 0x101ca60 は `[rbx+0x54]` の bit 0x400000 が立たないとき、classref を使って 0x1021560 を呼び (生成とみられる)、その後 0x1019b30 を `dl=0x16`・`r8=生成結果` で呼ぶ (推定。役割は未確定)。
- よって 0x1021670 を呼び得る呼出し元は 1639 件の `call [X+8]` の部分集合。受け手の出どころを追う作業が要る → [PY-275] #3944。

## 2. 受入 2: [rbp+0x30] の所属

検査 C6〜C10 (probe) の結果:

- **作成**: プロローグ 0x10216ef〜0x10216f9 で `[rbp+0x30]` を 24 バイトゼロ化 (`[rbp+0x48]` は 0x10216c5、`[rbp+0x60]` は 0x102169b)。
- **代入**: 0x10219c5 (`[rbp+0x158]` ≠ 0 側: src = `[rbp+0xa0]`) または 0x10219d7 (= 0 側: src = `[rbp+0xb8]`) で `0x45b480(&[rbp+0x30], &src)`。分岐は第 2 引数 dl の保存値 `[rbp+0x158]` (0x1021706 で保存、0x10219b1 で比較)。
- **src の作成**: `[rbp+0xa0]` は `0x461ff0(&, edx=[Self+0x3fc], r8=-4)` (0x102196f〜0x102198a)、`[rbp+0xb8]` は `0x461ff0(&, edx=-[Self+0x3fc], r8=-4)` (0x102198f〜0x10219ac)。Self は 0x10216ff で `[rbp+0x150]` に保存された rcx。
- **消費**: 0x10219e0 の `0x45c290(&[rbp+0x30])` の戻り値 eax が 0x10219f8 の `0x12a4450` の ecx になる (`edx=0`・`r8b=[Self+0x408]`)。
- **解放**: 0x1021a17〜0x1021a28 で `0x416230(&[rbp+0x30], typeinfo, r8d=3)`。typeinfo (0x401370) は kind 0x0c (tkVariant)・名前 "Variant" (C8)。0x1021a17 は 0x1021779 の `jg` (範囲外の早期 return) の飛び先でもあり、正常経路と早期経路の両方がここを通る。

よって `[rbp+0x30]` は**Self の内部状態を複写した一時 Variant** で、Self の所有ではなく、0x1021670 の呼出しごとに作られ・解放される。

## 3. 検証

- probe: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py269_probe.py` → 11 件 PASS (C1〜C10・C7b)、`summary: ALL PASS`、終了 0。所要 36 秒 (n=1)。1 分 load 0.47 (開始前) → 0.75 (終了時)。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_vmt_probe.py 0x1012f40 0x1021670 --disp 8` → `call [reg + 0x8] (virtual slot 1): 1638`、終了 0。C3 の 1639 件と 1 件ずれる (2 つの逆アセ走査の違い。merge 前から存在。§4)。
- コード差分: `git diff c6a709ef1 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (本 REPORT は docs のみ)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x101ca60 の生成結果 (0x1021560 の戻り値) の格納先と、0x1019b30 の役割 | 受入 1 (受け手の出どころ) | [PY-275] #3944 |
| 1639 件の `call [X+8]` のうち、TUndoEvent_MovedFXTracks のインスタンスを受け手にできる箇所 | 受入 1 (呼出し元の確定) | [PY-275] #3944 |
| `[rbp+0x30]` が 3 要素配列の先頭であること (隣接ローカルの配置) | 受入 2 の「配列の先頭」の記述 (推定) | 本 REPORT §2 の推定。確定は [PY-275] の検証に含める |
| `pe_vmt_probe.py --disp 8` の 1638 件と `pe_py269_probe.py` C3 の 1639 件の 1 件の差 (両者の逆アセ走査が違う。どちらが正しいかは未確定) | 受入 1 の件数 (1639) の再現性 | 未起票 (PM 判断) |
