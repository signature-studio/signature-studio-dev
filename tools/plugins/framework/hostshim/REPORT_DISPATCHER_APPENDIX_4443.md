# PLG-P0b-48 (#4443) — 間接 call 3 件の受け手と再現手順の記録

親 #4130。受入 1・2 の結論は `REPORT_DISPATCHER_APPENDIX_4130.md` §2・§4 が正本。
Phase A 回帰 (`dispatch=38 ff=0`) は子 #5185 で PASS 済み。本ファイルは受入 3 (再現コマンド・素材・測定 commit) の記録。

## 1. 受入 1・2 の結論 (前 run の確定事項・再掲しない内容は §4 の参照のみ)

- 0x1320e21・0x13213ee・0x132296f の 3 件の受け手は、PE 内に初期化元が無い (ヒープ域・`0x141d6b8 → 0` の null 連鎖)。呼出先 VA は**未確定**。
- 応答表 (`hostshim.c`) への反映は行わない。根拠は 4130 §4 と同じ (3 件は呼出先が未確定、8 件の即値は gate の連鎖が閉じている)。
- Phase A 回帰 `dispatch=38 ff=0` は子 #5185 で実測 PASS (同 issue の結果コメント参照)。

## 2. 測定条件 (受入 3)

- 測定 commit: `7ffd8bd40` (origin/main・本ブランチの起点。測定はこの commit のコードで行った)。`hs_disp_emu.py` の最後の変更は `6d46d9bcd`、`hs_store_supplier.py` は `9f225f5e0`。`4130` の測定 commit `9f225f5e0` 以後も、`hs_disp_emu.py` と `hs_store_supplier.py` は変わっている (§5)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` 1 件のみ。`tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" --wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl4443` に展開。`work-fw-stage1` は本測定では使わない (受入 1・3 は PE 静的解析のみ)。
- Python: venv に `unicorn==2.1.4`・`pefile`・`capstone==5.0.7`。
- load: 測定開始時 0.65〜0.94 (1 分平均)。実行は n=1。

## 3. 再現コマンドと実測値

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl4443 PYTHONPATH=$RUNNER_TEMP/venv4443/lib/python3.14/site-packages
cd tools/plugins/framework/hostshim
HS_DISP_PATH=1 HS_DISP_OUT=$RUNNER_TEMP/hs4443/base.json python3 hs_disp_emu.py   # 基準 run
python3 hs_store_cov.py $RUNNER_TEMP/hs4443/base.json                              # 被覆
python3 hs_store_supplier.py                                                       # 11 件の供給元
```

| 手順 | 結果 (実測) | 4130 の値 |
|---|---|---|
| `hs_disp_emu.py` (基準・256 ID・既定 callee 戻り値 0) | exit 0・real 1 分 12.9 秒 (`time` real 72.8 秒) | 1 分 12.8 秒 |
| 基準 distinct (rax, path) | 109 / IDs 256 | 109 |
| unmapped | 61 ID・5,340 件・200 組・197 ページ | 同じ |
| `hs_store_cov.py` | 静的 69・基準被覆 30・未実行 39・no-case-store 202 | 同じ |
| `hs_store_supplier.py` | exit 0・11 件の `====` 見出し・331 行 | 11 件 |

- 基準 JSON は `$RUNNER_TEMP` に置いた (リポジトリには入れない)。
- 3 件の間接 call の供給元 (0x1320e23・0x13213f3・0x1322971) は、今回の出力でも `call` 戻り値の格納として出ることを確認した。受け手の値は出力に無い (未確定のまま)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 3 件の受け手 VA の確定 (実行時の受け手オブジェクトの値が要る) | 応答表への反映の可否 | 本 issue #4443 の範囲外。実行時トレースの計画は PM 判断 |
| 8 件の即値格納の gate 入力 | 8 件を実行させる条件 | #4444 (PLG-P0b-49)・`REPORT_DISPATCHER_APPENDIX_4444.md` |

## 5. コードの差分 (測定 commit から HEAD まで)

```
git diff 7ffd8bd40 HEAD -- tools/plugins/framework/hostshim ':!*.md'
```

出力 (本 PR の commit 直前に実行): 空 (差分 0 行)。本 PR は REPORT の追加のみで、測定に使ったコードは変えていない。
main 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。
