# 付録: icall #2148 (ICALL-60) — SlateCore encoded slot 表の境界確定 (部分)

> 親: #2120 (ICALL-59)。前付録: `REPORT_APPENDIX_2120.md`。
> 本 run は受入条件の一部 (`0x1810806a0` を迂回した再トレースと、読出し VA の追加採取) まで。表の境界・entry 数・OTT 比較は子 issue へ移管 (§4)。

## 1. 結論

- 受入条件 1 (表の開始 VA・終了 VA・entry 数の確定): **未達**。
- 受入条件 2 (既知 12 slot が表に含まれるかの判定): **未達**。既知 12 件のうち読出し確認は 3 件のまま。
- 受入条件 3 (OTT api-set 表 `0x18026c9f0` との形式比較): **未達**。
- 追加の発見: 読出し元の逆アセンブルで、既知 12 slot とは別の 2 系統のテーブル (`0x1307100`・`0x13071a0` 起点) を読む
  ディスパッチャ `0x18105de80` を確認した。cookie は `0x18125eaa8` で、既知 12 slot と同じ encode 形式。
- 前提の訂正: #2148 本文は「53 関数が `0x1810806a0` で SIGSEGV」としていたが、fatal 行の実測では
  **そのうち 7 件だけが RIP `0x1810806a0`** だった。残る 46 件は別の RIP で落ちており、host 側 RIP (`0x55..`) も含む (§2.3)。

## 2. 実測

測定 commit: 本 PR の `tools/icall/diff/slot_trace.c` 変更 commit (下記 §3 の差分)。
測定条件はいずれも `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (closure 131 関数・1 関数 1 プロセス)。

### 2.1 ベースライン (`SLOT_STUB_VA` 未設定)

| 項目 | 値 |
|---|---|
| 所要 | 12.0 s (real) / user 10.9 s / sys 1.4 s |
| load average | 0.95 (開始時, 09:36) |
| exit 別 | rc=0: 69 / rc=95: 53 / rc=98: 8 / rc=124: 1 |
| 読出された zero-fill VA | 7 個 |
| 既知 12 slot | 読出し 3 / 未読出し 9 |

#2120 の実測 (rc 内訳・VA 7 個・3/9) と一致。2 回実行して同一。

### 2.2 `0x1810806a0` を迂回 (`SLOT_STUB_VA=1810806a0`)

`0x1810806a0` の fetch fault 時に、呼出し元へ戻り値 0 で復帰させる opt-in の stub を追加した (環境変数未設定なら従来と同じ)。

| 項目 | 値 |
|---|---|
| 所要 | 12.1 s (real) / user 10.9 s / sys 1.4 s |
| load average | 0.64 (開始時, 09:37) |
| exit 別 | rc=0: 72 / rc=95: 47 / rc=97: 3 / rc=98: 8 / rc=124: 1 (main checkout 実行) |
| exit 別 (再実行) | rc=0: 73 / rc=95: 47 / rc=97: 2 / rc=98: 8 / rc=124: 1 (測定 commit 259c474b の worktree 実行) |
| 読出された zero-fill VA | 9 個 (`0x1813071c8`・`0x1813071d0` が増加) |
| 既知 12 slot | 読出し 3 / 未読出し 9 |

rc=0 と rc=97 の境界は実行ごとに 1 件揺れる。rc=95 (47) と zero-fill VA (9) と既知 3/12 は両実行で一致。

- stub で追加された読出しは 2 件で、どちらも RIP `0x18105deaf` (ディスパッチャ `0x18105de80`) から。
- 既知 12 slot の判定は変わらなかった。`0x1810806a0` を迂回しても、既知 12 slot の読出しは増えない。

### 2.3 fatal RIP の内訳 (SIGSEGV 関数の内訳)

| 条件 | 件数 | 上位の RIP |
|---|---|---|
| ベースライン (rc=95: 53) | 53 | `0x1810806a0` 7・`0x180c8b9c0` 3・他 1〜2 件ずつ・host 側 RIP 数件 |
| stub 有効 (rc=95: 47 + rc=97: 3) | 50 | `0x18103d494` 4・`0x180c8b9c0` 3・他 1〜2 件ずつ・host 側 RIP 多数 |

- host 側 RIP (`0x55..`・`0x56..` 等) は、`ott_call` の戻りや thunk 経由で host 側へ落ちたものと見られる。原因は未確認。
- つまり #2148 が前提とした「53 関数の rc=95 は `0x1810806a0` の呼出し」は成り立たない。`0x1810806a0` は 7 件だけ。

## 3. 再現・差分

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh                   # ベースライン
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh   # stub 有効
```

- 結果ファイル: `tools/icall/work/slot_trace_enc.txt` (gitignore)。fatal 行の集計は `work/fatal_2148*.txt`。
- 変更は `tools/icall/diff/slot_trace.c` のみ。stub は `SLOT_STUB_VA` 指定時にだけ有効。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 表の開始・終了 VA・entry 数の確定。`0x1307100`・`0x13071a0` 系統を含めた境界の特定 | 受入条件 1・2 | [ICALL-61] (子 issue) |
| 47 関数の fatal RIP (`0x18103d494`・`0x180c8b9c0` ほか・host 側 RIP) の原因切り分け | 読出し判定の前提 | [ICALL-61] (子 issue) |
| OTT api-set 表 `0x18026c9f0` との形式比較 | 受入条件 3 | [ICALL-61] (子 issue) |
| closure 外 indirect target `0x1810806a0` の本解決 (7 件の fault のみ) | 本 PR は迂回のみ | #2079 (ICALL-56) |
