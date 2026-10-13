# Serum 2 SR-3c: muParser 窓外 6 関数の帰属 (#867 / #71 残件)

親: `REPORT.md` §11.5 (muParser 窓の組込み関数登録側)。再現: `python3 scripts/sr3c_muparser_attr.py` (`sr3_run.sh` 実行後・`work/` 要)。

## 1. 窓外 6 関数の実体

窓 = muParser cut 窓 0x18091ace0–0x18099a6d0 (cut 204 関数)。6 関数はいずれもこの外。

6 関数はすべて `.pdata` 関数である (`out/sr3_verify.txt` の OUT 行は `.pdata` の index から出た size で、`out/sr4_funcs.tsv` でも 4 件が `pdata`)。`out/sr3_gap_blocks.tsv` に先頭を持つ行は無い。

| 関数 VA | size (`.pdata`) | 参照する数学名 (`.rdata`) | 直接 call/jmp の呼び出し元 | 呼び出し元の所属 |
|---|---:|---|---|---|
| 0x1809e3240 | 275 | `acos` (0x180fdc5dc) | 0x1809e3231 | gap ブロック 0x1809e3220 (22 B) |
| 0x1809eb7b0 | 293 | `log2` (0x180fdc880) | 0x1800bbb06・0x18088fb25 (旧表・未再確認) | 未再確認 |
| 0x1809ef030 | 306 | `sinh` (0x180fdc69c) | 0x1809ef021 | gap ブロック 0x1809ef010 (22 B) |
| 0x1809ef7b0 | 184 | `sqrt` (0x180fdc5b0) | 十数箇所 (旧表・未再確認) | 未再確認 |
| 0x180a0a3e0 | 253 | `acos` (0x180fdc5dc) ほか | 直接 call/jmp なし (旧表) | 間接 or 登録テーブル経由と推定 |
| 0x180a0f3f0 | 32 | `log10` (0x180fdc890) | 0x1809eb0a1 ほか (旧表・未再確認) | 未再確認 |

- 「未再確認」の列は、前回 run の記録 (旧表) で、本 run では `work/` が無く再実行できていない。
- 6 関数の size は `out/sr3_verify.txt` (コミット済み) と一致する。
- 呼び出し元の所属のうち gap ブロック内の 2 件は、コミット済みの `out/sr3_gap_blocks.tsv` で確認した (0x1809e3231 ∈ 0x1809e3220 22 B、0x1809ef021 ∈ 0x1809ef010 22 B)。
- 呼び出し元は cut 表 (muParser / 他ライブラリ) のどれにも属さない。muParser 窓の拡張 (呼出閉包) だけでは帰属しない。

## 2. 数学名表 (名前ポインタ表)

- 旧 run の記述: `.rdata` 0x180fae600 付近に `(ID, 名前ポインタ)` の 16 バイト組の表がある。
- 数学名表の走査と、表を指す lea/mov 参照元の列挙は `scripts/sr3c_muparser_attr.py` に入れた (`name table:` と `lea/mov refs into name table:` の行)。本 run では `work/` が無く未実行のため、出力は未取得。
- 旧 run の「lea 参照元 5 関数」「12 参照」等の個数は、committed スクリプトの出力では再現できないため本 REPORT から外した。再取得後に出力を貼る。
- 6 関数のアドレスを 8 バイト絶対ポインタとして `.rdata` で探したが 0 件。

## 3. 結論

- **帰属は未確定**。数学名表の ID から関数を引く dispatch 側は、静的走査 (直接 call/jmp・RIP 相対 lea・絶対ポインタ) では特定できなかった。
- 6 関数が muParser の組込み関数か、Serum 側の別の数学関数かは、この結果だけでは判定できない。
- 次の手段: 動的トレース (Serum2 を実行し、数学名表の参照時点で実行中の関数を記録)。Linux runner では実行環境が未整備のため、#71 に継続。

## 4. 実測

- 本 run の検証 (コミット済みデータのみ): `out/sr3_verify.txt`・`out/sr4_funcs.tsv`・`out/sr3_gap_blocks.tsv` で §1 の所在を確認。`scripts/sr3c_muparser_attr.py` は `py_compile` 成功のみ (実行は未実施)。
- 素材: `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe`) は本 run の `$ARTIFACTS_DIR` に無く、`work/` も無いため、`sr3_run.sh` の再実行と `sr3c_muparser_attr.py` の実行はできていない。
- 前回 run の記録 (再現未確認): `sr3_run.sh` 43.8 秒 (4 core, user 26.0 s)。cut 1,510 関数 / 1,464,181 B (§11.6 の基準 `699addb` と一致)。入力 sha256 `501e7bb3…5283` (§11 と同一)。
- 未了: `plugins-serum2` を `oc_artifacts` で取得し、`sr3_run.sh` → `sr3c_muparser_attr.py` を実行して §1 の「未再確認」列と §2 の出力を埋める。
