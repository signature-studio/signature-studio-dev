# #2008 REPORT — 0x710030/0x710040 の値確定と Phase B の plug != 0 実測 (未達・調査記録)

- 担当 issue: #2008 `[PLG-P0b-11]` (親 #1935 系列)。受入 1 (0x710030/0x710040 の値確定) と 受入 2 (Phase B の plug != 0) は **未達**。受入 3 (Phase A 回帰 `dispatch=38 ff=0` の毎回確認) は **達成**。
- 起点: `origin/main` c171b9dc。worktree `ws-2008`・branch `2008-plg-p0b-11`。
- 測定 commit: `c171b9dc` (コード変更なし。本 REPORT の追加のみ)。
- 既知類型との関係: 該当なし (lift 欠陥ではなく、FL 本体の外部状態 (export table) 不在による soft-miss)。

## 1. 実測

素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`・`FL_WIN64_DIR` に設定)、`work-fw-stage1` / `work-liftlib` は repo ルートに展開。`toolchain-*` は既存の `/opt/emsdk` `/opt/retdec` を使用。

| 手順 | 結果 | 所要時間 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 8 分 45 秒 (08:25:53 → 08:34:38) | 1.70 → 2.82 |
| `hs_e2e.sh --fresh` (初回) | exit 1。Phase A PASS (`dispatch=38 ff=0`)。Phase B 例外 `memory access out of bounds`・`plug=0x0`・`rec=8` | 1 分 25 秒 (08:34:46 → 08:36:11) | 2.39 → 1.37 |
| `hs_e2e.sh` (2 回目・3 回目) | 出力は初回と同一 (Phase A PASS・Phase B 同一失敗) | **未計測** (`time` の記録が `0 秒` となり信頼できない) | — |
| `hs_e2e.sh` (4 回目・日付差分計測) | rc=1・Phase A PASS (1 件)・`Phase B: status=0xffffffff plug=0x0` | **0.204 秒** (`date` 差分) | 0.03 → 0.03 |

- n=4 だが、所要時間は 1 回目 (85.5 秒) と 4 回目 (0.2 秒) で桁が違い、同一条件の時間として扱えない。このため所要時間のレンジは **未取得**。Phase A・Phase B の結果 (成否・`dispatch=38 ff=0`・`plug=0x0`) は 4 回とも同一。
- 測定の不整合は未解決 (§4)。

## 2. 0x710030 / 0x710040 の調査結果

| 項目 | 結果 | 根拠 |
|---|---|---|
| PE 上の位置 | `0x710000`〜 は PE の `.bss` (raw サイズ 0・仮想 0x10578)。ファイルに初期値なし | `fw_icall.dll` の section table |
| IR 上の書き込み (0x710030) | `function_417ee0` が `store i64 4213760` (= `0x404c00`) | `fw_flat4_canon3.ll` 72135・72157 行付近 |
| IR 上の書き込み (0x710038) | 同じ関数が `0x710038` (= 7405624) に `0x404c10` (= 4213776) を書く | 同上 (135〜136 行付近) |
| IR 上の書き込み (0x710040) | 定数 `7405632` への直接 store は **見つからない**。読み出しは `function_40d6e0` (33490 行) のみ | `grep 7405632` |
| 呼出元 | `call ... @function_417ee0(` は IR 内に **0 件**。`function_417ee0` の名前は `%ce…` 変数名にも現れるため、単純な名前一致では呼出の有無を判定できない | `grep -c 'call .*@function_417ee0'` = 0 |
| PE の参照 | `0x710040` は PE `.data` (file offset 0x30e1b8) に値 `0x710040` として 1 件あるのみ。`0x710030`・`0x710038` の直接出現は 0 件 | バイナリ検索 |
| `fw_map.json` | `0x417ee0 → 0x7d7fd0` のみ (呼出側情報無し) | `fw_map.json` |

- `function_40d6e0` は `[0x710040] == 0` のとき必ず `dec_label_pc_7b812a` に進む (前 REPORT §3 と同じ構造)。`[0x710040]` の値は、lift 済み IR のどこでも決まっていない。
- `0x710030` の初期化は `function_417ee0` が担うが、この関数は IR 内から呼ばれていない (エントリ・未到達)。FL 本体の起動シーケンスからの呼出は、headless では再現されていない可能性が高い。

## 3. Phase B の状態 (未達)

- `plug=0x0`・`status=0xffffffff`・`slotsCalled=0x0`・`rec=8`。
- 失敗の位置は前回 (#1935) と同じ。`CreatePlugInstance → ctor` の Dispatcher ID prefix は `0x47,0x56,0xd,0x2e,0x10000738,0x47,0x1d` で期待 (`0x47,0x56,0xd,0x2e,0x47,0x1d`) と 1 件ずれる。
- soft-miss は `0x0`・`0xf003f`・`0x657243205d73685b` (文字列由来) など多数。`0x40d807`・`0x4e5fa6` の site で `target=0x0` が繰り返される。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x710040` の書き込み元 (IR・PE のどちらにも無い) | `function_40d6e0` の経路を塞げず、`plug=0` のまま (受入 1・2) | #2008 (本 PR で `Refs #2008`) |
| `function_417ee0` が IR 内から呼ばれない (起動シーケンス未再現) | `0x710030` の値は書かれるが、呼出経路を再現できていない | #2008 |
| Phase B `memory access out of bounds` と ID `0x10000738` の呼出 | ctor 連鎖が途中で落ちる (受入 2) | #2008 |
| 所要時間の測定不整合 (初回 85.5 秒 / 4 回目 0.2 秒) | 時間のレンジが取れない (受入 3 の n≥3 レンジ未達) | #2008 |
| GitHub API のレート上限 (installation 170170783) | 子 issue の重複確認・起票ができなかった | 次 run (#2008 の再起動) |

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst    # repo ルートで展開
tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst      # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh --fresh       # exit 0・SMOKE PASS (8 分 45 秒)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh # Phase A PASS・Phase B 例外 (1 分 25 秒)
```

## 6. コード差分 (測定 commit 以降)

測定 commit `c171b9dc` 以降、コード変更は無し。`git diff c171b9dc HEAD -- tools/plugins/framework` は本 REPORT の追加のみ。
