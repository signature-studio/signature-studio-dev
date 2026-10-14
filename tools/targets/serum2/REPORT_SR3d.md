# Serum 2 SR-3d: 窓外 muParser 6 関数の参照走査 (#867 受入 2 / #71 残件)

親: `REPORT_SR3c.md` (§1〜§3)。再現手順は §5。

## 0. 測定の範囲

- 入力: `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B)。素材 `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` (1,313,084,056 B) から 7z で取り出した。REPORT §11 と一致。
- 測定 commit: `b28b08df` (script の最終変更 commit。出力は `out/sr3d_scan.txt`)。
- **線形走査の被覆率: `.text` 10,593,790 / 10,593,792 B = 100.00%** (未デコード 2 B・再開 2 回)。未デコードの位置は `0x180a0fcac` と `0x180a16cdc`。両方とも 6 関数の範囲の外で、`.pdata` 照合では `0x180a0fcac` は関数 `0x180a0fb60`〜`0x180a0fcd0` (size 368)、`0x180a16cdc` は関数 `0x180a16930`〜`0x180a16ce8` (size 952) の内部。
- 再開なしの旧走査 (測定 commit `530ac84b`) は、RIP 相対オペランド 95,268 件・数学名への RIP lea 計 7 件だった。修正版 (被覆率 100.00%) は 95,679 件・計 8 件。差は RIP オペランド 411 件と lea 1 件 (`0x180a10864`) で、旧走査が無効バイト (`0x180a0fcac` 付近) で止まって以降を読まなかったためと推定する (旧出力は未保存のため未確認)。
- 測定時間: `python3 scripts/sr3d_fnptr_scan.py` は real 1 分 54 秒・user 1 分 24 秒・sys 8 秒。測定後の `/proc/loadavg` は 0.37 / 0.82 / 0.57 (測定中の load は未取得)。
- 測定 commit から HEAD までのコード差分: §5。

## 1. 結論

| 項目 | 結論 | 区分 |
|---|---|---|
| 6 関数は関数ポインタとして取得されていない | abs8 0 件 (ファイル全体のバイト走査)。6 関数への RIP 相対 lea・mov は 0 件。RVA4 は `.pdata` 1〜2 件と `.rdata` 0〜2 件 (件数のみ実測。内容は未検査) | 実測 (被覆率 100.00%) |
| 数学名の参照元 | `acos` `log2` `sinh` `sqrt` `log10` への RIP lea は計 8 件。うち 7 件は 6 関数の内部、1 件 (`sinh` の `0x180a10864`) は関数 `0x180a107b0` (size 289) の内部で 6 関数の外。数学名の abs8 は名前表の 4 件 (index 3・4・8・11) | 実測 (被覆率 100.00%) |
| 6 関数の直接 call/jmp 呼出元は cut 表の区分の外 | 直接 call/jmp 68 件 (§3) はすべて cut 表の区分の外。条件分岐 (jcc) 1 件 (`0x1809e322b` の `je`) は別列 | 実測 (被覆率 100.00%)。cut 表の範囲は §3 |
| 数学名表 (ID, 名前ポインタ) は muParser 窓の外 | 名前表 `.rdata` 0x180fae640 (24 件) と、表を参照する dispatch `0x180a0ea50` はいずれも窓 0x18091ace0–0x18099a6d0 の外 | 実測 |
| 6 関数は muParser の組込み登録ではない | 推定 (弱)。名前の参照は 6 関数の外にも 1 件あるため、「名前の参照が 6 関数の内部に限られる」は成立しない。根拠は、6 関数への abs8・RIP 参照が 0 件であること、名前表・dispatch が窓の外にあること、`sqrt` の wrapper が 59 箇所から直接呼ばれること | 推定 (弱) |
| 6 関数の**帰属の確定** | 未確定。静的走査の範囲では確定できない | 未達 (#71 へ) |

## 2. 形式別の実測 (測定 commit `b28b08df`・被覆率 100.00%)

対象は 6 関数 (`0x1809e3240` `0x1809eb7b0` `0x1809ef030` `0x1809ef7b0` `0x180a0a3e0` `0x180a0f3f0`) と、名前の lea 先 5 件。`.text` の RIP 相対オペランドは 95,679 件。

| 対象 | (a) abs8 (LE) | (b) RVA4 (LE) | (c) RIP 相対 lea/mov | 直接 call/jmp 呼出元 | jcc 呼出元 |
|---|---:|---|---:|---|---|
| 0x1809e3240 (acos) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809e3231) | 0 |
| 0x1809eb7b0 (log2) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 2 (0x1800bbb06 / 0x18088fb25) | 0 |
| 0x1809ef030 (sinh) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809ef021) | 0 |
| 0x1809ef7b0 (sqrt) | 0 | `.pdata` 1 | 0 | 59 | 0 |
| 0x180a0a3e0 (acos 別) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 0 | 1 (je 0x1809e322b) |
| 0x180a0f3f0 (log10) | 0 | `.pdata` 2 | 0 | 5 | 0 |

数学名の参照 (名前 VA ごと):

| 名前 (VA) | abs8 (名前表の名前ポインタ) | RIP lea (参照元 → 所属する関数) |
|---|---|---|
| `acos` (0x180fdc5dc) | 1 (`.rdata` 0xfae6c8 = 表 index 8) | 2 (0x1809e330e → 0x1809e3240 (6 関数の内部)、0x180a0a49d → 0x180a0a3e0 (6 関数の内部)) |
| `log2` (0x180fdc880) | 0 (表に無い) | 2 (0x1809eb80e・0x1809eb87a → 0x1809eb7b0 (6 関数の内部)) |
| `sinh` (0x180fdc69c) | 1 (0xfae688 = index 4) | 2 (0x1809ef0f1 → 0x1809ef030 (6 関数の内部)、**0x180a10864 → 0x180a107b0 (6 関数の外)**) |
| `sqrt` (0x180fdc5b0) | 1 (0xfae6f8 = index 11) | 1 (0x1809ef800 → 0x1809ef7b0 (6 関数の内部)) |
| `log10` (0x180fdc890) | 1 (0xfae678 = index 3) | 1 (0x180a0f3f4 → 0x180a0f3f0 (6 関数の内部)) |

- 名前表 `.rdata` 0x180fae640 は `(ID, 名前ポインタ)` の 16 B 組 24 件 (`exp pow log log10 sinh cosh tanh asin acos atan atan2 sqrt sin cos tan ceil floor fabs modf ldexp _cabs _hypot fmod frexp`、SR-3c §2 と一致)。名前ポインタ 4 件 (index 3・4・8・11) は abs8 で格納されるため、表の名前参照は abs8 走査で見える。
- 表を参照する RIP lea は 1 件 (0x180a0ea64 → dispatch `0x180a0ea50`、SR-3c §2 と一致)。
- `log2` は表に無い。

## 3. 呼出元の所属 (cut 表照合)

`out/sr3_cut_table.tsv` (1,510 関数) と直接呼出元の VA を照合した。直接 call/jmp と条件分岐 (jcc) は別に数えた (`out/sr3d_scan.txt` の (d) 行)。

| 6 関数 | 直接 call/jmp | jcc | 所属 (cut 表) |
|---|---:|---:|---|
| 0x1809e3240 | 1 | 0 | cut 外 |
| 0x1809eb7b0 | 2 | 0 | cut 外 |
| 0x1809ef030 | 1 | 0 | cut 外 |
| 0x1809ef7b0 | 59 | 0 | cut 外 |
| 0x180a0a3e0 | 0 | 1 | (call/jmp なし。jcc は下記) |
| 0x180a0f3f0 | 5 | 0 | cut 外 |
| **計** | **68** | **1** | |

- **SR-3c との差 (68 → 69)**: SR-3c §1 は直接 call/jmp のみを数え、`0x180a0a3e0` は 0 件。SR-3d の 69 件は jcc `je 0x1809e322b` 1 件を加えた数で、差はこの 1 件だけ。call/jmp の内訳 (68 件) は SR-3c と一致する。
- `je 0x1809e322b` の所属: script は jcc の所属を照合していない。事実として、`0x1809e322b` は cut 表の範囲 (〜`0x18099a6d0`) より上にあり、cut 表の区分の外。加えて `.pdata` のどの関数範囲にも入らない (関数境界の外)。線形走査の誤り (命令境界のずれ) かは未確認 (#71)。
- 呼出元 68 件は、cut 表の範囲より上にあるため区分の外に出る。この事実は muParser でないことの根拠にはしない (§1 の推定 (弱))。
- `sqrt` の wrapper 0x1809ef7b0 は 59 箇所から直接呼ばれる。muParser の組込み関数が parser の評価経路 (関数ポインタ経由) でしか呼ばれないなら、この形とは整合しない。推定 (弱) の根拠の一つ。
- 帰属の確定は #71 (動的トレース) に移す。

## 4. 訂正

- `REPORT_SR3b.md` §3 の「名前を参照する RIP lea 0 件」と「8 バイト絶対ポインタ 0 件」は誤りだった。SR-3d (被覆率 100.00%) で、名前 5 件への RIP lea は計 8 件 (6 関数の内部 7 件・外 1 件)、8 バイト絶対ポインタで名前を参照する箇所は 4 件 (名前表 `.rdata` 0x180fae640 の index 3・4・8・11)。SR-3b の「0 件」の原因は特定できない (旧 run のスクリプトは未コミット)。SR-3b §3 は原文を残し、訂正注記を付した。
- `0x180a0a3e0` の呼出元数は SR-3c (0 件・call/jmp) と SR-3d (1 件・jcc) で数え方が違った。§3 で call/jmp と jcc を分けて統一し、差を示した。

## 5. 検証記録 (WORKFLOW §6)

再現手順 (素材は `[PLUGINS-SERUM2]` の `$ARTIFACTS_DIR/plugins-serum2.tar.zst`。`$RUNNER_TEMP` は作業用の展開先):

1. 素材の展開 (installer のみ): `mkdir -p $RUNNER_TEMP/serum2 && cd $RUNNER_TEMP/serum2 && tar --zstd -xf $ARTIFACTS_DIR/plugins-serum2.tar.zst Install_Xfer_Serum2_2.1.5.exe`
2. 入力の取り出し: `cd tools/targets/serum2 && bash scripts/sr3_run.sh`。`work/Serum2_win64.vst3` を 7z で取り出し、cut 表 `out/sr3_cut_table.tsv` などを生成する。取り出しは `sr3_run.sh` の先頭部分が行い、scan は行わない。
3. 線形走査: `python3 scripts/sr3d_fnptr_scan.py work/Serum2_win64.vst3 > out/sr3d_scan.txt` (`out/sr3_cut_table.tsv` を読むため、2 の後に実行する)。

- 実測 (測定 commit `b28b08df`): 手順 2 は real 34 秒 (rc 0)、入力 sha256 `501e7bb3…5283`・19,236,864 B。手順 3 は real 1 分 54 秒・user 1 分 24 秒 (rc 0)。出力は `out/sr3d_scan.txt` (70 行) にコミットした。
- 同じ入力で修正前の版 (未デコード位置の出力が無いもの) を 1 回走らせ、出力の差は (c0) 行の未デコード位置の追記だけだった (数値は同一)。
- 合成バイト列 `90 06 90 90` の検証: 命令 0x1000・0x1002・0x1003、未デコード 0x1001 (再開 1 回)。
- 未デコード位置の所属は `.pdata` (`pefile` の `DIRECTORY_ENTRY_EXCEPTION`) で照合した (§0)。
- 測定 commit から HEAD までのコード差分 (script と out/ のみ): `git diff b28b08df HEAD -- tools/targets/serum2/scripts tools/targets/serum2/out` の出力は 0 行 (REPORT のみの commit)。
- `sr3_run.sh` の実行後も `git status` に変化は無かった (tracked の `out/` は同一内容)。
- 20 MiB 超のファイル: 追加なし (`out/sr3d_scan.txt` は 3,000 B)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x180a107b0 (sinh 名の lea 元 `0x180a10864` を含む関数、size 289) の呼出元は未検査 | 6 関数の外にある名前参照の用途が未確定 | #71 |
| 未デコード 2 B (`0x180a0fcac` `0x180a16cdc`) の周辺で、再同期により命令を取りこぼした可能性 | 近傍の関数 (`0x180a0fb60`・`0x180a16930`) の参照は未確定。6 関数の範囲の外 | #71 (未確認) |
| `je 0x1809e322b` は `.pdata` の関数範囲の外にある。線形走査の誤りかは未確認 | 呼出元 (jcc) 1 件の扱い | #71 |
| 6 関数の帰属 (呼出元 68 件が Serum 本体側か muParser 側か) の確定 | muParser 組込みか Serum 側かを静的に決められない | #71 (動的トレース) |
| 間接ジャンプテーブル (4 バイト相対オフセット型) の網羅検査は未実施 | 6 関数がこの型で参照される可能性を排除できない (abs8 / RIP lea / RVA4 の結論は、この型を除いた結論) | #71 |
| 名前表の 24 件のうち dispatch 0x180a0ea50 の全分岐の検査は未実施 (SR-3c §2 の 2 分岐のみ) | 名前→実装の対応が未確定 | #71 |
