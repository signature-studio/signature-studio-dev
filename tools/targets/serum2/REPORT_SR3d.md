# Serum 2 SR-3d: 窓外 muParser 6 関数の参照走査 (#867 受入 2 / #71 残件)

親: `REPORT_SR3c.md` (§1〜§3)。再現手順は §5。

## 0. 測定の範囲

- 入力: `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B)。REPORT §11 と一致。
- 測定 commit: `530ac84b` (旧 script による実測。`scripts/sr3d_fnptr_scan.py` の追加 `3a15db93` と CWD 非依存化の修正)。
- **線形走査の被覆率は未測定**。`capstone` は無効バイトに当たると出力を止めるため、旧 script は `.text` の後半を読み飛ばしうる。本 round で script に「無効バイトから 1 バイト進めて再開」と「セクションごとの被覆率 (`(c0)` 行)」を追加したが、この run では入力 `plugins-serum2` が無く、修正版は実バイナリで未実行。
- したがって §1・§2 の数値 (0 件・7 件・69 件) は**旧走査 (再開なし) の値**で、偽陰性を排除できていない。被覆率の実測後に書き直す (§5)。
- 測定 commit から HEAD までのコード差分: §5。

## 1. 結論

| 項目 | 結論 | 区分 |
|---|---|---|
| 6 関数は関数ポインタとして取得されていない | abs8 0 件 (ファイル全体のバイト走査)。RVA4 は `.pdata` と `.rdata` の unwind 3 つ組のみ。RIP 相対 lea 0 件 (旧走査) | abs8・RVA4 は実測 (被覆率に依らない)。RIP lea は**被覆率未確定** |
| 数学名の参照元は 6 関数の内部だけ | `acos` `log2` `sinh` `sqrt` `log10` の RIP lea は旧走査で計 7 件、すべて 6 関数の内部 (関数の範囲は `.pdata`) | 実測 (旧走査)・被覆率未確定 |
| 6 関数の直接 call/jmp 呼出元は cut 表の区分の外 | 直接 call/jmp 68 件 (下表) はすべて cut 表の区分の外。条件分岐 (jcc) 1 件 (`je 0x1809e322b`) は別列 | 実測 (旧走査)・被覆率未確定 |
| 数学名表 (ID, 名前ポインタ) は muParser 窓の外 | 名前表 `.rdata` 0x180fae640 (24 件) と、表を参照する dispatch `0x180a0ea50` はいずれも窓 0x18091ace0–0x18099a6d0 の外 | 実測 |
| 6 関数は muParser の組込み登録ではない | 推定 (弱)。根拠は、名前の参照が 6 関数の内部に限られること (旧走査) と、名前表・dispatch が窓の外にあること。呼出元の所属は根拠にしない (cut 表は 0x18099a6d0 までで、それより上の呼出元は定義上いつも cut 外になる) | 推定 (弱) |
| 6 関数の**帰属の確定** | 未確定。静的走査の範囲では確定できない | 未達 (#71 へ) |

## 2. 形式別の実測 (測定 commit `530ac84b`・旧走査。被覆率未確定)

対象は 6 関数 (`0x1809e3240` `0x1809eb7b0` `0x1809ef030` `0x1809ef7b0` `0x180a0a3e0` `0x180a0f3f0`) と、名前の lea 先 5 件。`.text` の RIP 相対オペランドは旧走査で 95,268 件。

| 対象 | (a) abs8 (LE) | (b) RVA4 (LE) | (c) RIP 相対 lea/mov | 直接 call/jmp 呼出元 | jcc 呼出元 |
|---|---:|---|---:|---|---|
| 0x1809e3240 (acos) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809e3231) | 0 |
| 0x1809eb7b0 (log2) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 2 (0x1800bbb06 / 0x18088fb25) | 0 |
| 0x1809ef030 (sinh) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809ef021) | 0 |
| 0x1809ef7b0 (sqrt) | 0 | `.pdata` 1 | 0 | 59 | 0 |
| 0x180a0a3e0 (acos 別) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 0 | 1 (je 0x1809e322b) |
| 0x180a0f3f0 (log10) | 0 | `.pdata` 2 | 0 | 5 | 0 |

数学名の参照 (名前 VA ごと):

| 名前 (VA) | abs8 (名前表の名前ポインタ) | RIP lea (参照元 = 6 関数の内部) |
|---|---|---|
| `acos` (0x180fdc5dc) | 1 (`.rdata` 0xfae6c8 = 表 index 8) | 2 (0x1809e330e・0x180a0a49d) |
| `log2` (0x180fdc880) | 0 (表に無い) | 2 (0x1809eb80e・0x1809eb87a) |
| `sinh` (0x180fdc69c) | 1 (0xfae688 = index 4) | 1 (0x1809ef0f1) |
| `sqrt` (0x180fdc5b0) | 1 (0xfae6f8 = index 11) | 1 (0x1809ef800) |
| `log10` (0x180fdc890) | 1 (0xfae678 = index 3) | 1 (0x180a0f3f4) |

- 名前表 `.rdata` 0x180fae640 は `(ID, 名前ポインタ)` の 16 B 組 24 件 (`exp pow log log10 sinh cosh tanh asin acos atan atan2 sqrt sin cos tan ceil floor fabs modf ldexp _cabs _hypot fmod frexp`、SR-3c §2 と一致)。名前ポインタ 4 件 (index 3・4・8・11) は abs8 で格納されるため、表の名前参照は abs8 走査で見える。
- 表を参照する RIP lea は 1 件 (0x180a0ea64 → dispatch `0x180a0ea50`、SR-3c §2 と一致)。
- `log2` は表に無い。

## 3. 呼出元の所属 (cut 表照合)

`out/sr3_cut_table.tsv` (1,510 関数) と直接呼出元の VA を照合した。直接 call/jmp と条件分岐 (jcc) は別に数えた。

| 6 関数 | 直接 call/jmp | jcc | 所属 (cut 表) |
|---|---:|---:|---|
| 0x1809e3240 | 1 | 0 | cut 外 |
| 0x1809eb7b0 | 2 | 0 | cut 外 |
| 0x1809ef030 | 1 | 0 | cut 外 |
| 0x1809ef7b0 | 59 | 0 | cut 外 |
| 0x180a0a3e0 | 0 | 1 | cut 外 (jcc のみ) |
| 0x180a0f3f0 | 5 | 0 | cut 外 |
| **計** | **68** | **1** | |

- **SR-3c との差 (68 → 69)**: SR-3c §1 は直接 call/jmp のみを数え、`0x180a0a3e0` は 0 件。SR-3d の 69 件は jcc `je 0x1809e322b` 1 件を加えた数で、差はこの 1 件だけ。call/jmp の内訳 (68 件) は SR-3c と一致する。
- `je 0x1809e322b` が線形走査の誤り (命令境界のずれ) かは、被覆率を測定してから確認する (未確認)。
- 呼出元 68 件は、旧走査の範囲で cut 表の区分に属さない。ただし cut 表は 0x18099a6d0 までしか無いため、この事実は muParser でないことの根拠にはしない (§1 の推定 (弱))。
- `sqrt` の wrapper 0x1809ef7b0 は 59 箇所から直接呼ばれる。muParser の組込み関数が parser の評価経路 (関数ポインタ経由) でしか呼ばれないなら、この形とは整合しない。推定 (弱) の根拠の一つ。
- 帰属の確定は #71 (動的トレース) に移す。

## 4. 訂正

- `REPORT_SR3b.md` §3 の「名前を参照する RIP lea 0 件」と「8 バイト絶対ポインタ 0 件」は誤りだった。旧走査で、名前 5 件への RIP lea は計 7 件 (すべて 6 関数の内部)、8 バイト絶対ポインタで名前を参照する箇所は 4 件 (名前表 `.rdata` 0x180fae640 の index 3・4・8・11)。SR-3b の「0 件」の原因は特定できない (旧 run のスクリプトは未コミット)。SR-3b §3 は原文を残し、訂正注記を付した。
- `0x180a0a3e0` の呼出元数は SR-3c (0 件・call/jmp) と SR-3d (1 件・jcc) で数え方が違った。§3 で統一して差を示した。

## 5. 検証記録 (WORKFLOW §6)

- 旧走査の実測: 測定 commit `530ac84b` の `python3 tools/targets/serum2/scripts/sr3d_fnptr_scan.py tools/targets/serum2/work/Serum2_win64.vst3` (入力 sha256 `501e7bb3…5283`)。所要 19.6 s (real) / 17.9 s (user)、4 core、load average 0.72。出力は未コミットのため、前回出力との `cmp` 一致は**確認できない** (前版の記載は取り消す)。
- 修正 (本 round): script に線形走査の再開 (`sweep`) と被覆率の出力 (`(c0)` 行) と、直接 call/jmp と jcc の分離を追加。合成バイト列で検証した。`90 06 90 90` は命令 3 件 (0x1000・0x1002・0x1003 の nop)、被覆 3/4 B、再開 1 回。`06 e8 00 00 00 00` は call 1 件 (0x2001、5 B)、被覆 5/6 B。
- **再測定 (未実施・残件)**: 入力 `plugins-serum2` が無いため、この run では実バイナリを走査できない。再現手順は次のとおり。
  1. `bash scripts/sr3_run.sh` (入力 `work/Serum2_win64.vst3` を `$ARTIFACTS_DIR` の `Install_Xfer_Serum2_2.1.5.exe` から 7z で展開する)
  2. `python3 scripts/sr3d_fnptr_scan.py work/Serum2_win64.vst3 > out/sr3d_scan.txt`
  3. `(c0)` の被覆率を §0 に転記し、§1・§2・§3 の数値を走査結果に合わせて書き直す。被覆率が 100% に達しない場合、§1 の「0 件」は「走査範囲 X% で 0 件」と書く。
- 測定 commit から HEAD までのコード差分: `git diff 530ac84b HEAD -- tools/targets/serum2` (script の差分を含むため、再測定が必要)。
- 20 MiB 超のファイル: 追加なし。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正版 script の実バイナリでの再測定 (被覆率・§1〜§3 の数値) | 「0 件」「7 件」「68 件 + jcc 1 件」の偽陰性を判定できない | 本 PR の未解決 (素材 `plugins-serum2` 付きの run で §5 の手順により実施) |
| 6 関数の帰属 (呼出元 68 件が Serum 本体側か muParser 側か) の確定 | muParser 組込みか Serum 側かを静的に決められない | #71 (動的トレース) |
| 間接ジャンプテーブル (4 バイト相対オフセット型) の網羅検査は未実施 | 6 関数がこの型で参照される可能性を排除できない (abs8 / RIP lea / RVA4 の 0 件は、この型を除いた結論) | #71 |
| 名前表の 24 件のうち dispatch 0x180a0ea50 の全分岐の検査は未実施 (SR-3c §2 の 2 分岐のみ) | 名前→実装の対応が未確定 | #71 |
