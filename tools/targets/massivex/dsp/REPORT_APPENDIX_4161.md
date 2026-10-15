# Massive X DSP REPORT 付録 (#4161 MX-45 受入 1・4)

MX-45 (#4161) の受入 1 (FH3 FuncInfo の funclet walk の C 移植) の実測と、その契約。
受入 2 (SjLj 形の呼出し)・受入 3 (二重 lift 確認) は子 #4928 (MX-49) が扱う。

## 1. 結論 (先出し)

1. `shimx_fh3_funclets` の C 移植は、実 PE の全 FH3 FuncInfo (13,356 件) で Python 正本と集合一致 (13,002 件・不一致 0)。
2. 戻り値の契約を直した (commit `d896246c4`)。`out_cap` 超過時の件数は「真の件数の上界」であり、正確な件数は保証しない。
   `test_fh3.c` に out_cap 超過の期待値を追加した。
3. 検証素材 `plugins-massivex` は reviewer の環境に無く、parity の再実行は未達。数値は implementer の測定 (commit `e1c5152ac`) を引き継ぐ。

## 2. 契約 (out_cap 超過)

- `out` には先頭 `out_cap` 件まで書く。
- 戻り値 `n` は、`n <= out_cap` なら重複を除いた件数 (正確)。
- `n > out_cap` なら `out` は先頭 `out_cap` 件のみ有効。`n` は真の件数の上界で、重複を含みうる。呼出し側は cap を増やして再呼出しする。
- 理由: 件数専用の重複判定を持つと、動的な集合が要る。検証 (`mx45_fh3_parity.py`) は cap=4096 固定で `min(n, 4096)` を取り、上限に当たらないため、この契約で足りる。

再現 (修正前 `e1e11d8ad`・修正後 `d896246c4` で同じ入力): nTry=2・各 try の nCatch=2・handler RVA {0x500, 0x600} (try 間で共有)。

| 入力 | 修正前 | 修正後 (契約) |
|---|--:|--:|
| `out_cap=16` | 2 | 2 (正確) |
| `out_cap=1` | 3 | 3 (上界。真の件数 2 より大きい) |

修正後の `test_fh3.c` は `out_cap=16` で 2、`out_cap=1` で `>= 2` と `out[0] == 0x500` を確かめる。

## 3. 測定

### 3.1 実 PE との全数一致 (`mx45_fh3_parity.py`)

- 測定 commit = **e1c5152ac** (`tools/shimx` の最後のコード変更)。検証スクリプトは `e1e11d8ad` で追加。
- 素材: `plugins-massivex` → `Massive X.vst3` (95,356,824 B、md5 `622993e7…`)。
- 実測 (e1c5152ac 時点): exit 0・**3.2 s**・FH3 FuncInfo **13,356**。C と Python が一致 **13,002**、不一致 **0**。両方が棄却 (上限・magic) **354**。C 側の棄却のみ 0。
- 再実行 (reviewer 環境): 不可。`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみで `plugins-massivex` が無い。

### 3.2 コード差分 (測定 commit から HEAD まで)

`git diff e1c5152ac HEAD -- tools/shimx` の出力 (commit `d896246c4` の差分):

- `seh_fh3.c`: `fh3_rd32` の上にコメント 1 行 (実行コードは不変)。
- `shimx.h`: 宣言コメントを out_cap 超過の契約に直す (宣言は不変)。
- `test/test_fh3.c`: out_cap 超過の期待値を追加 (テストのみ)。

オブジェクト差分: `clang -O1` で `seh_fh3.c` の旧版 (`e1e11d8ad`) と新版をビルドし、`.text` を比べた。`.text` は 965 バイトで完全一致。

### 3.3 単体テスト

- `bash tools/shimx/test.sh --quick` は emcc (EMSDK の環境) が runner に無く、この run では実行できなかった。
- 代わりに `test_fh3.c` の `t_walk` を、ホストの clang と最小ヘッダで単独に実行した: PASS (修正後)。修正前の `t_walk` も PASS (期待値は 2 件のみを見ていた)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SjLj 形の funclet 呼出し・二重 lift 確認 (受入 2・3) | funclet は lift されるが呼べない | #4928 [MX-49] |
| parity の再実行 (`plugins-massivex` 素材) | 数値は implementer 測定の引継ぎ | 次回の素材付き run で確認 (#4928 の `oc_artifacts` 行に追加) |
| 棄却 354 (FuncInfo 単位) と REPORT_APPENDIX_3776 §9.2 の 355 (pdata 行単位) の差 | 説明済み (§5)。残るのは 339 件の読取不能の中身 | #4928 [MX-49] (本文に追記) |

## 5. 354 と 355 の差

`REPORT_APPENDIX_4192.md` §2.2 のとおり、355 は pdata 行単位、354 は FuncInfo 単位の数である。差は 1 件で、本測定の結果と矛盾しない。
棄却の内訳 (FuncInfo 単位) は読取不能 339・magic 不正 6・nCatch 上限 9 (`REPORT_APPENDIX_4192.md` §2.2)。
未確認なのは、読取不能 339 件に本物の funclet が含まれるかどうか (母数 36,533 は下界) だけで、これは #4928 に追記する。
