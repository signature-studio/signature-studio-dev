# LIFTLIB #898 (HB-H22) — iargs 未対応 3 site の bind (付録)

親: [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17 (#898 の節)。
REPORT_APPENDIX.md が 250 行上限を超えているため、#898 の節はこのファイルに分けて置く (`REPORT_APPENDIX_883.md` と同じ運用)。

## 状態

部分達成。`site_unbound` は 3 → 2 (受入条件 #1 の `site_unbound` 0 は未達)。
残り 2 site (`1801c162b`・`1801c1752`) はスタック渡し引数の bind であり、[HB-H25] #1124 で扱う。
0 を渡した場合の機能上の影響は未確認。

### 3 site の bind (検証コード HEAD 220c4703)

| site | 原因 | 対応 |
|---|---|---|
| `1801a3117` | rdx = `movzx edx, dl` (呼出元の入口 dl の 0 拡張) | **解決**。`_resolve` の movzx 分岐 (`sw` = 元レジスタ幅で切る → 呼出側の型へ `zext`)。emit 行は `iargs.py` の `nm_` 規則 (`%ia_<C>_<k>`) から導いた次の 3 行 (実行ログからの貼付ではない。入口値の token は未確認): `%ia_1801a3117_1mt = trunc <入口 rdx の型> <入口値> to i8` → `%ia_1801a3117_1mz = zext i8 %ia_1801a3117_1mt to i32` → `%ia_1801a3117_1z = zext i32 %ia_1801a3117_1mz to i64`。call の引数は `i64 %ia_1801a3117_1z` |
| `1801c162b` / `1801c1752` | r8 = `mov r8d,[rbp+0x5f]`。`[rbp+0x5f]` は呼出元の入口 rsp+0x28 (**5 番目の引数 = スタック渡し**)。`iargs.py` 冒頭の「スタック渡し (5 引数目〜) は扱わない」の範囲外 | **未解決**。0 を渡す (T16 で `site_unbound=2` を固定)。0 が無害かは未確認 (callee `1801c4d00`/`1801c5038` は r8 を `test r8b` 等で読む)。子 issue **[HB-H25] #1124** で扱う |

### 実測 (検証コード HEAD 220c4703・main 取り込み前)

- `iargs.run` (OTT `ott.drc.ll`): `site_unbound` 3 → 2。
- `leafspec targets/ott_iargs.json --n 200`: match=200 mismatch=0 wasm_trap=0 (rate 1.000 → PASS)。所要 22.8 秒 (rc=0)。
- 測定の出所: PR 作成時の単一測定。実行 ID・出力全文は保存していない。同じ HEAD の再測定値は別に存在しない。

### 再実行できなかった検証 (レビュー指摘 5)

- 本 fix run (HEAD 39a70381 系) では `$ARTIFACTS_DIR` に `fl-win64.tar.zst` のみがあり、OTT 素材 (`tools/m6/work/ott.drc.ll`・`OTT_vst2_win64.dll`) が無い。T16 と leafspec は再実行できず、本節の数値は再検証していない。
- 再実行に必要な素材: `fl-win64 work-m6-ott analysis-ott-binaries work-liftlib` (`docs/WORKFLOW.md` §11)。素材が揃った run の Actions run ID と出力全文を、ここに追記すること。
