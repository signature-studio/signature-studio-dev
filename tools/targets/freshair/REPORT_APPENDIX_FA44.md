# Fresh Air REPORT §11 付録 (#3740 / FA-44): KH のみ snap-in (Delay・Disperser・Phaser・QuickEq) の SC 側実機ハーネス

- 本体: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §3・§4・§7。親: #52 (FA-5)。判定基準は [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1) に従う。
- 位置づけ: SC 側ハーネスが実機機械語を動かせるかの確認 (smoke)。bit 一致の判定はしない。製品 KPI は動かしていない (静的・機械語ハーネスのみ)。

## §1. 結論

- SC 側の実機機械語ハーネス 4 組 (`lift2/native/native_{delay,disperser,phaser,quickeq}.c`) を新規に作った。fma 0/1 の smoke 各 20 case で **ERR 0・20 行** (実測 §3)。
- 差分実行 (C4〜C6) は **未実施**。KH 側の登録は 4 組とも `snapins.json` に key がある (§2) が、param の写像の根拠が未確定のため「差分実行可」とは書かない。
- 判定基準 C3 (両側ハーネス) は、SC 側が揃ったことで KH 側の登録と合わせて両側が揃った。C4 (同一入力の写像) が未達のため、差分の見通しは §4 に残す。

## §2. KH 側の登録 (C3)

`tools/targets/kilohearts/snapins/snapins.json` の top-level key を確認: `delay`・`disperser`・`phaser`・`quickeq` は全て存在する。

## §3. smoke の実測

- 測定 commit: `75fce79a3` (ハーネス 4 本・smoke・シナリオ生成を追加した commit)。素材: `work-liftlib-targets` (SlateCore.core_64) を展開して使用。
- 再現: `bash tools/targets/freshair/ks_fa44_native_smoke.sh 20 <outdir>`。
- 実測: 2 回目の実行 9.62 s (real)・nproc=4・load 1 分値 0.18〜0.20。EXIT=0。stderr 0 B。GUARD 0 件。

| ハーネス | fma | 行数 | ERR |
|---|---|---|---|
| Delay (`native_delay.c`) | 0 | 20 | 0 |
| Delay (`native_delay.c`) | 1 | 20 | 0 |
| Disperser (`native_disperser.c`) | 0 | 20 | 0 |
| Disperser (`native_disperser.c`) | 1 | 20 | 0 |
| Phaser (`native_phaser.c`) | 0 | 20 | 0 |
| Phaser (`native_phaser.c`) | 1 | 20 | 0 |
| QuickEq (`native_quickeq.c`) | 0 | 20 | 0 |
| QuickEq (`native_quickeq.c`) | 1 | 20 | 0 |

- 出力 md5 (fma 0): Disperser `7e8a51ef…`・Phaser `000552b1…`・QuickEq `46247ea4…` は 2 回で一致。fma 0/1 でも Disperser・Phaser・QuickEq は一致。
- **Delay の出力は実行ごとに変わる**。原因は状態ダンプに載る heap ポインタ (`calloc` の遅延線 buffer の値。ASLR で毎回変わる)。計算結果の差ではない。Delay の出力 bit 比較は、ポインタ欄を除いた上で行う必要がある (未実施)。
- mlift の report: Delay は 61 関数中 1 関数が未対応命令 (`pextrd`) で failed。ネイティブの実行には影響しない (lift 経路ではない) が、wasm 化には影響する (#3740 の範囲外)。
- 限界: 出力の値が正しいこと (wasm・KH との一致) は未確認。

## §4. 差分実行の見通し (受入 3)

| クラス | KH 登録 | SC ハーネス | param 写像 | 見通し |
|---|---|---|---|---|
| Delay | あり | smoke ERR 0 | 未確定 (S+0x158/0x160 の遅延線 buffer を最小状態として calloc・mask 0x3fff を置いた) | 未確定。遅延線の状態の意味が未読 |
| Disperser | あり | smoke ERR 0 | 未確定 | 未確定 |
| Phaser | あり | smoke ERR 0 | 未確定 (P+0x9f80 の関数表の slot 0x60 に C 関数 `host_get` を置いた。戻り値は placeholder の 0 で、機械語からは読んでいない) | 未確定。host 関数の戻り値の意味が未読 |
| QuickEq | あり | smoke ERR 0 | 未確定 | 未確定 |

- smoke のシナリオは sample rate (S+0x98) だけを書く。param の offset→意味は読んでいない。したがって C4 (同一 seed・同一 param の写像) は 4 組とも未達。
- 4 組とも、差分を始める前に param の写像を機械語の読みで確定する必要がある。これは次の作業として #52 の残件に残す (§5)。

## §5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 4 組の param 写像 (C4) の確定 | 差分実行の入力が未確定 | #4053 (子, 親 #3740) |
| Delay の出力の比較 (ポインタ欄を除く) | Delay の bit 比較が未実施 | #4053 (子, 親 #3740) |
| Delay の未対応命令 `pextrd` (wasm 化) | wasm 化の範囲外 | #4053 (子, 親 #3740) |
| 4 組の出力値の正しさ (wasm・KH との一致) | smoke は実行できたまでの確認 | #4053 (子, 親 #3740) |
