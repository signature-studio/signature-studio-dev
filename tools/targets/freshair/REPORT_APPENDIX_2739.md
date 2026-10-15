# Fresh Air REPORT §11 付録 (#2739 / FA-34): Gain 以外の snap-in への差分実行の判定基準と振り分け

- 本体: [REPORT.md](REPORT.md) §11-2 ①。Gain の差分実行結果は [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A3・§A3-5。親: #52。
- 位置づけ: 判定基準 (§1) を実測より先に確定する。基準を当てた振り分け (§3) を残す。基準を変えるときは理由を書いて版を上げる (事後の変更はしない)。

## §1. 判定基準 (版 1・実測前に確定)

| 項目 | 基準 |
|---|---|
| C1 対象 | `ks_identity.py` の ID 一致 37 クラス。各クラスの `process_pair` (KH slot 14 と、SC の対応 slot の組) を 1 組とする |
| C2 除外 (stub) | `min(KH バイト数, SC バイト数) < 64` の組は process 比較の代表にしない |
| C3 両側ハーネス | 差分実行の対象は、SC 側の実機機械語ハーネス (`lift2/native/native_<x>.c`・`lift/native_gain.c`) と KH 側の登録 (`tools/targets/kilohearts/snapins/snapins.json` の key) の両方がある組だけ。両側が揃うまで「差分実行可」と書かない |
| C4 同一入力 | 同じ seed の乱数で case を生成し、両側へ同じ値を入れる (`ks_semantic_gain.c` の方式)。param の写像は機械語の読みで対応させたものに限り、根拠を書く |
| C5 判定 | 同一入力 N=200 case の L・R 出力と処理後 state の bit 一致。許容差は 0 (ulp 許容なし) |
| C6 読み | 200/200 一致 → 「この入力分布で bit 一致」まで。不一致 → bit 不一致の確定のみ。「意味が違う」とは断定しない (Gain の丸め形の差は §A3-5 のとおり、意味の違いと同じとは限らない) |
| C7 未実行 | C3 を満たさない組は実行しない。欠けている側のハーネスを理由に書く |

## §2. 振り分け規則

- `stub`: C2 に該当。
- `両側`: C3 を満たす。差分実行の対象。
- `SC のみ` / `KH のみ`: 片側だけのハーネスがある。欠けている側を書く (子 issue の対象は 1 PR あたり最大 3 件まで)。
- `なし`: 両側とも無い。判定はしない (#52 の残件として扱う)。

§3 の表は `tools/targets/freshair/ks_candidate_triage.py` が `ident.json` から機械的に作る。
