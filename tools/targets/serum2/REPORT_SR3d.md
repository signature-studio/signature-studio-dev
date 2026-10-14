# Serum 2 SR-3d: 窓外 muParser 6 関数の参照走査 (#867 受入 2 / #71 残件)

親: `REPORT_SR3c.md` (§1〜§3)。再現: `python3 scripts/sr3d_fnptr_scan.py work/Serum2_win64.vst3` (素材 `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` から `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` を 7z で抽出した `work/` 配下のファイル)。

## 0. 測定の範囲

- 入力: `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B)。REPORT §11 と一致。
- 測定 commit: `530ac84b` (コードを変えた最後の commit。`scripts/sr3d_fnptr_scan.py` の追加 `3a15db93` と CWD 非依存化の修正)。
- 測定 commit から HEAD までのコード差分: §5 の証跡を参照。

## 1. 結論

| 項目 | 結論 | 区分 |
|---|---|---|
| 6 関数は関数ポインタとして取得されていない | abs8 0 件・RIP 相対 lea 0 件 (全 6 件)。RVA4 は `.pdata` と `.rdata` の unwind 3 つ組のみ | **実測** |
| 数学名の参照元は 6 関数の内部だけ | `acos` `log2` `sinh` `sqrt` `log10` の RIP lea は全体で 7 件、すべて 6 関数の内部 | **実測** |
| 6 関数の直接呼出元は cut 表の区分済み関数 (muParser 窓を含む) に 0 件 | 呼出元 69 件 (下表) はすべて cut 外 | **実測** |
| 数学名表 (ID, 名前ポインタ) は muParser 窓の外 | 名前表 `.rdata` 0x180fae640 (24 件) と、表を参照する dispatch `0x180a0ea50` はいずれも窓 0x18091ace0–0x18099a6d0 の外 | **実測** |
| 6 関数は muParser の組込み登録ではない | 上の 3 点から推定 (下記 §3) | 推定 (強) |
| 6 関数の**帰属の確定** | 未確定。静的走査の範囲では確定できない | 未達 (#71 へ) |

## 2. 形式別の実測 (測定 commit `530ac84b`)

対象は 6 関数 (`0x1809e3240` `0x1809eb7b0` `0x1809ef030` `0x1809ef7b0` `0x180a0a3e0` `0x180a0f3f0`) と、名前の lea 先 5 件。`.text` の RIP 相対オペランドは 95,268 件を線形走査 (`capstone`)。

| 対象 | (a) abs8 (LE) | (b) RVA4 (LE) | (c) RIP 相対 lea/mov | 直接 call/jmp 呼出元 |
|---|---:|---|---:|---|
| 0x1809e3240 (acos) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809e3231) |
| 0x1809eb7b0 (log2) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 2 (0x1800bbb06 / 0x18088fb25) |
| 0x1809ef030 (sinh) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (jmp 0x1809ef021) |
| 0x1809ef7b0 (sqrt) | 0 | `.pdata` 1 | 0 | 59 |
| 0x180a0a3e0 (acos 別) | 0 | `.rdata` 2 + `.pdata` 1 | 0 | 1 (je 0x1809e322b。線形走査由来の疑い・未検証) |
| 0x180a0f3f0 (log10) | 0 | `.pdata` 2 | 0 | 5 |

数学名の参照 (名前 VA ごと):

| 名前 (VA) | abs8 (名前表の名前ポインタ) | RIP lea (参照元 = 6 関数の内部) |
|---|---|---|
| `acos` (0x180fdc5dc) | 1 (`.rdata` 0xfae6c8 = 表 index 8) | 2 (0x1809e330e・0x180a0a49d) |
| `log2` (0x180fdc880) | 0 (表に無い) | 2 (0x1809eb80e・0x1809eb87a) |
| `sinh` (0x180fdc69c) | 1 (0xfae688 = index 4) | 1 (0x1809ef0f1) |
| `sqrt` (0x180fdc5b0) | 1 (0xfae6f8 = index 11) | 1 (0x1809ef800) |
| `log10` (0x180fdc890) | 1 (0xfae678 = index 3) | 1 (0x180a0f3f4) |

- 名前表 `.rdata` 0x180fae640 は `(ID, 名前ポインタ)` の 16 B 組 24 件 (`exp pow log log10 sinh cosh tanh asin acos atan atan2 sqrt sin cos tan ceil floor fabs modf ldexp _cabs _hypot fmod frexp`、SR-3c §2 と一致)。名前ポインタ (確認した 4 件) は abs8 で格納されるため、表の名前参照は abs8 走査で見える。
- 表を参照する RIP lea は 1 件 (0x180a0ea64 → dispatch `0x180a0ea50`、SR-3c §2 と一致)。
- `log2` は表に無い。

## 3. 呼出元の所属 (cut 表照合)

`out/sr3_cut_table.tsv` (1,510 関数) と直接呼出元の VA を照合した。

| 6 関数 | 呼出元 | cut 表の区分 |
|---|---:|---|
| 0x1809e3240 | 1 | cut 外 |
| 0x1809eb7b0 | 2 | cut 外 |
| 0x1809ef030 | 1 | cut 外 |
| 0x1809ef7b0 | 59 | cut 外 |
| 0x180a0a3e0 | 1 | cut 外 |
| 0x180a0f3f0 | 5 | cut 外 |

- 呼出元 69 件は muParser 窓 (cut 204 関数) を含む OSS 区分のどれにも属さない。`sqrt` の wrapper 0x1809ef7b0 は 59 箇所から直接呼ばれ、muParser の組込み関数が parser の評価経路 (関数ポインタ経由) でしか呼ばれないこととは整合しない。
- 推定 (§1): 6 関数は muParser の組込み登録側ではなく、Serum 本体の数学ヘルパ (定義域チェックの後に名前付きエラー経路を持つ) と推定する。
- upstream muParser v2.3.2 `src/muParser.cpp` の `InitFun` は `DefineFun(_T("acos"), MathImpl<value_type>::ACos)` 等で名前リテラルを参照する (119〜142 行)。この形の登録列が残っていれば名前リテラルへの lea が残るが、このバイナリでは 6 関数以外に無い。版は 2.2.x の可能性があり、2.2.x の `InitFun` は未突合。**推定**。

## 4. 訂正

- `REPORT_SR3b.md` §3 の「名前 (`acos` `sinh` `sqrt` `log10` `ceil` 等 21 種) を参照する RIP lea は 0 件 (95,268 件を走査)」は**誤り**。本 run の同じ走査 (95,268 件) で、名前 5 件への RIP lea は計 7 件 (§2) と再現した。旧 run のスクリプトは未コミットで、差の原因は特定できない。SR-3b §3 に訂正注記を付した (原文は残す)。

## 5. 検証記録 (WORKFLOW §6)

- 検証: `python3 tools/targets/serum2/scripts/sr3d_fnptr_scan.py tools/targets/serum2/work/Serum2_win64.vst3` (測定 commit `530ac84b`、worktree `ws-867`、入力 sha256 `501e7bb3…5283`)。
- 所要: 19.6 s (real) / 17.9 s (user)、4 core、load average 0.72。
- 出力は前回 (CWD 修正前の全件実行) の出力と全行一致 (`cmp`)。
- 測定 commit から HEAD までのコード差分: 本節の REPORT 更新のみ (`git diff 530ac84b HEAD -- tools/targets/serum2` の出力は PR 本文に添付)。
- 20 MiB 超のファイル: 追加なし。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 6 関数の帰属 (呼出元 69 件は Serum 本体側と推定) の確定 | muParser 組込みか Serum 側かを静的に決められない | #71 (動的トレース) |
| 間接ジャンプテーブル (4 バイト相対オフセット型) の網羅検査は未実施 | 6 関数がこの型で参照される可能性を排除できない (abs8 / RIP lea / RVA4 の 0 件は、この型を除いた結論) | #71 |
| 名前表の 24 件のうち dispatch 0x180a0ea50 の全分岐の検査は未実施 (SR-3c §2 の 2 分岐のみ) | 名前→実装の対応が未確定 | #71 |
