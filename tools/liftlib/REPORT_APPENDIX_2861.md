# liftlib #2861 (HB-H49, 部分達成) — iargs の支配しない値の代替が無い call 引数 (unbound) の埋め

親: #2181 (HB-H45) / 上位: #2161 (HB-H44)。本 PR は受入の一部 (rip 相対 `lea` の合成) のみ。残りは「未解決」表を参照。

## 0. 結論

| 受入 (#2861 本文) | 結果 (実測) |
|---|---|
| 1. unbound 176 件を分類し、埋められるものを埋める | **部分達成**。rip 相対 `lea` 28 件を合成して埋めた (176 → 148)。rsp / rbp / r11 基準の 148 件は未対応 (§3) |
| 2. 残る unbound を理由付きで列挙する | **部分達成**。基準の種類別の件数のみ列挙 (§3)。site ごとの VA 一覧と理由の確定は未了 |
| 3. leafspec の前後比較 | **達成**。基準 (HEAD) と変更後の両方で 200/200・wasm_trap 0 (§2) |

issue 本文の基準「147/53/0/0」は #2181 時点の値。現 HEAD (`9721869b7`) の再測定では **200/200/0/0** (match 200・mismatch 0・native_crash 0・wasm_trap 0) で、gate も PASS。

## 1. 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `789b8439d` (`fix(liftlib): fold rip-relative lea call args to their VA (#2861)`) |
| 基準 | HEAD `9721869b7` (変更前) |
| 素材 | `tools/icall/work/ott_F.txt` (F=281)・`tools/m6/work/ott.drc.ll`・`tools/liftlib/work` は main 側の検証スナップショットを symlink (commit 対象外)・`[ANALYSIS-PLUGINS]` 配下の OTT_vst2_win64.dll・RetDec (`[RETDEC]`) |
| 再現 | `cd tools/liftlib && OTT_DLL=<[ANALYSIS-PLUGINS] の OTT_vst2_win64.dll> ANALYSIS_DIR=<[ANALYSIS-DIR]> python3 -m liftlib leafspec targets/ott_getparam.json --n 200` |
| 単体 | `python3 tests/test_unit.py` → `ALL UNIT TESTS PASS (32)` (07:50:50〜07:56:10 の実測, 5 分 20 秒)。review 対応で `t16c` (rip `lea` の絶対 VA・32bit 切り詰め) を追加し、単体は 33 件 (下の検証 HEAD で再実行) |

## 2. 前後比較 (leafspec 実測)

| 設定 | build の stats (`iargs`) | leafspec `ott_getparam_idx` (match / mismatch / native_crash / wasm_trap) | gate |
|---|---|---|---|
| 基準 HEAD `9721869b7` (07:37:56〜07:39:25 の実測, 1 分 29 秒, load 0.22) | `site_unbound` 176 / `args_added` 462 / `sites_fixed` 376 | 200 / 0 / 0 / 0 | PASS (rate 1.000) |
| 変更後 (rip `lea` 合成, 07:46:53〜07:48:02 の実測, 1 分 09 秒) | `site_unbound` 148 / `args_added` 490 / `sites_fixed` 376 | 200 / 0 / 0 / 0 | PASS (rate 1.000) |

- 基準との差は `site_unbound` (-28) と `args_added` (+28)。一致率は両方 200/200 で変化なし。

確認コマンド (測定 commit から HEAD までのコード差分。0 なら測定値は現 HEAD で有効):

```
git diff 789b8439d HEAD -- tools/liftlib/liftlib tools/liftlib/targets tools/icall/rt | wc -l
0
```

## 3. 残る unbound 148 件 (内訳・未分類)

`pipeline_report.json` の log から集計 (変更後)。レジスタ別: rcx 66 / rdx 36 / r8 29 / r9 17。

基準 (変更前, 176 件) の到達定義の種別 (診断スクリプトの実測・一時作業で commit なし):

| 到達定義の機械語 | 件数 | 扱い |
|---|---|---|
| `lea` rsp 基準 | 41 | 呼出元フレームの局所アドレス。IR に値が無く、入口 rsp からの合成も未対応。**未解決** |
| `lea` rip 相対 | 28 | **本 PR で合成 (埋まった)** |
| `lea` rbp 基準 | 12 | rbp = 入口値由来の IR 値 (`%55` 等) が支配しない場合がある。未対応。**未解決** |
| `lea` r11 基準 | 8 | 未調査。**未解決** |
| `lea` rax 基準 / rbx 基準 | 2 | 未調査。**未解決** |
| 到達定義が複数 (multi) で定義 VA が無い | 42 | 分岐合流で定義が一意にならない。**未解決** |
| `mov` / `movsxd` / `xor` / `add` / `or` / `and` / `sar` | 13 + 12 + 12 + 2 + 2 + 1 + 1 | 未調査。**未解決** |

- 「未調査」の件数は、本 run の時間内に site ごとの原因を確定できなかったため、種別の件数のみ記録する。
- ネガコンの側 (0 を渡すと挙動が変わるか) は未測定。leafspec は 200/200 のため、この leaf の spec では 0 の影響は観測されていない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残 unbound 148 件の site ごとの原因の確定と埋め (rsp / rbp / r11 基準の `lea`、multi 定義、mov 系) | 呼出先に 0 が入る site が残る。leafspec 上の影響は未観測 | 本 issue #2861 の残件 (Refs #2861) |
| rsp 基準の局所アドレス (41 件) | 入口 rsp と無関係な呼出元フレーム値のため、IR 上の値の再構成が必要 | 本 issue #2861 の残件 |
| iargs を使う他 cfg (例 `ott_iargs_ctor.json`) への影響 | rip `lea` の合成で、支配しない値を使っていた既存出力が変わる可能性 | #4327 ([LIFTLIB-25]・親 #2861。census と他 cfg の leafspec) |
| leafspec gate 以外の回帰 (`tests/test_unit.py` 外) | 単体 32 件のみ確認 | 未測定 |
