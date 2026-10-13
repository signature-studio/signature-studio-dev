# #494: survey に間接 call の入口計測 (hit 数) を常設し、D15 復元を検収可能にする

**判定: 受入条件 3 件すべて達成。** `survey_units.mjs` の per-unit JSON に `icall` 欄 (site = 元バイナリの `call` 命令 VA 別 / target = 解決先 VA 別の
`[ok, miss]`) を足した。#482 の復元は **JSON の hit 数だけで** `site 0x5c0437 = 4/0` と `target 0x5c0e70 = 4/0` として検収できる (unit 114 の 4 呼出し)。
復元を外すと同じ 2 項目が 0/0 に戻る。survey の分類・既存欄は計測の有無で不変 (§3)。

検証起点 = 本 PR の `m11_ov.c` / `survey_units.mjs` = `5688a39` (base = `cda69f5` = #493 HEAD)。以降のコミットは `icall_sites_check.py` / docs のみ。
先行: #481 → #493 → 本 PR (stacked)。

既知類型との関係 (`docs/DEFECTS.md`): **D15 (DEFECTS.md) の検出信号の追加** (類型の新規発見ではない)。D15 は復元後も survey が判定力を持たない (#482 REPORT §4・§6) ため、
復元した call の実行回数を常設の信号にした。新規類型なし。

## 1. 出力形式 (定義)

`node trap_triage/survey_units.mjs <out>.json` が次を出す。**既定で常に ON** (計測は `m11_icall` 内のカウンタ加算のみ。§3 で所要への影響なしを実測)。

**(a) per-unit 欄 `icall`** (`<out>.json` の各 unit 記録。その unit の実行**前後の差分**。変化が無い unit では欄ごと省略):

```json
{ "unit": 114, "kind": "oob", "icall": {
    "sites":   { "0x5c0437": [4, 0], "0x5c037e": [4, 0], "0x41032e": [27, 0] },
    "targets": { "0x5c0e70": [4, 0], "0x5c04a0": [4, 0], "0x40f960": [26, 0], "0x41c160": [1, 0] } } }
```

| 欄 | 意味 |
|---|---|
| `sites` のキー | 間接 call 命令の **元バイナリ VA** (`m11_ov.c` の `ICALL_AT(<VA>, …)` が渡す。`M11_LB_BASE` 非依存)。`"ext"` = `ICALL_AT` を使わない外部 TU (shimx の callback 等) からの `m11_icall` |
| `targets` のキー | 解決先の VA。`m11_icall` の第 1 引数を LVA とみなして `+0x400000-M11_LB_BASE` した値 (既存 `disp_find` の第 1 引き)。LVA で解決できず VA として解決した場合 (`g_icall_viaVA`) は引数そのまま。miss は第 1 引きの値 (`g_miss` が生値を持つのと表記が違う点に注意) |
| 値 `[ok, miss]` | `ok` = call 先が解決でき実行された回数 / `miss` = closure 外で解決できず skip (ret 0) した回数 |
| 数えない呼出し | survey ドライバ (`m11_call_unit` が unit の Init を呼ぶ 1 回/unit) は `M11_SITE_NONE` で除外 (含めると target に 942 unit の proc VA が並ぶ) |

**(b) 側ファイル `<out>.icall.json`** (`<out>` が `/dev/*` でない時のみ): `{ "boot": {sites, targets}, "total": {sites, targets}, "drop": n }`。
per-unit 配列には **boot 段階 (unit 実行前の `m11_boot_enter`) の hit が入らない**ため別に出す (`boot`)。`total` = boot + 全 unit の累計、`drop` = 表 (site 256 / target 2048 種) 溢れで数えなかった回数 (今回 0)。

**(c) 集計・検収 `trap_triage/icall_hits.py <survey.json> [--expect KIND:KEY=OK[/MISS] …] [--sidecar] [--units]`**: unit を足し合わせた hit を表示し、
`--expect` と合わなければ exit 1。`survey_diff.py` は `icall` 欄を従来の比較から外し、両方に欄がある時だけ site / target ごとの総数差を別行で出す (旧形式の JSON とも比較できる)。
`icall_sites_check.py` は `ICALL_AT(<VA>, …)` の VA が `work/m11_image.bin` 上で**間接 call 命令**を指すかを capstone で検査する (VA 誤記の防止。§5)。

### 計測している site (`m11_ov.c` の `m11_icall` 全 9 箇所 + ドライバ 1)

| site VA | 関数 | 命令 (`icall_sites_check.py`) | 現行 survey の hit [ok, miss] |
|---|---|---|---|
| `0x5c0437` | `function_5c03d0` (**#482 の復元**) | `call qword ptr [rbx + 0x18]` | **4, 0** (unit 114) |
| `0x5c037e` | `function_5c0270` (#474) | `call qword ptr [rbx]` | 4, 0 (unit 114) |
| `0x41032e` | `function_410320` `_ClassCreate` (#418) | `call qword ptr [rax - 0x30]` | 18405, 0 (105 unit) |
| `0x5c0e91` | `function_5c0e70` (所有者の Changed) | `call qword ptr [rbx + 0x18]` | 0 (所有者 null) |
| `0x5c0826` | `function_5c0810` (DoChange) | `call qword ptr [rbx + 8]` | 0 (OnChange null) |
| `0x41223e` / `0x412258` / `0x41226d` | `m11_InitLib` (reason 1,2 / DllProc / reason 3) | `call [rbx+rsi*8]` / `call [rbp+0x160]` / `call [rbx+rsi*8]` | boot 段階に `0x41223e` が 1 回 (側ファイル `boot`)、他 0 |
| `0x412126` | `function_4120c0` InitUnits | `call qword ptr [rbp + 0x38]` | 0 (survey モードは InitUnits をドライバで置換) |

## 2. 実装

- `m11_ov.c`: `m11_icall` が site / target 別カウンタ (開番地ハッシュ、site 256 / target 2048 エントリ) を加算。site は `ICALL_AT(va, m11_icall の引数…)` マクロが
  file-static の `g_icall_site` に置いて `m11_icall` を従来どおり呼ぶ。**`m11_icall` の署名・呼出し経路は不変** (`shimx_link` が `-Wl,--wrap=m11_icall` するため別関数にしていない)。
  読出し用に `m11_icall_cnt_{n,key,ok,miss,drop}` を export (`m11_build.sh` の EXPORTS)。
- `survey_units.mjs`: unit の前後で表を読み差分を `icall` 欄に出す。boot 段階と累計を側ファイルへ。
- `negctl_482.sh`: 各構成の survey JSON から `icall_hits.py --expect` を呼び、PASS / FAIL を `json:` 行に追加 (既存の trace 計測列は独立の検算として残した)。

## 3. 検証 (コミット済み `5688a39` を `bash m11_build.sh` で再ビルド → survey。wasm-ld signature mismatch 0 / undefined symbol 0)

| 構成 | ok | oob | halt0 | miss | noproc | trap | 所要 (n=3) | load average (1 分) | per-unit JSON md5 (n=3 全回同一) | JSON サイズ |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|
| base `cda69f5` | 839 | 24 | 32 | 46 | 1 | **56** | 7.59–7.73 s | 0.51–0.69 (各回の直後) | `4a7f66a4…` | 102109 B |
| `5688a39` (本 PR) | 839 | 24 | 32 | 46 | 1 | **56** | 7.48–7.49 s | 0.72–0.78 (各回の直前) | `258d8cf9…` (側ファイル `509c6250…`) | 116878 B |

- 分母 = 942 unit。`trap` = oob + halt0 + abort。所要は `/usr/bin/time` の wall、直列 1 本 (#482 REPORT の 4.3 s と差があるのは runner の違い、と**推定**。比較は同一 runner の base との上表)。
  計測の追加による所要の悪化は観測されない (本 PR の範囲は base の範囲を下回る)。`icall` 欄を持つ unit は 105 / 942 (site 延べ 107 / target 延べ 112)。
- `survey_diff.py` base → 本 PR: **遷移はすべて同一 kind、ok→非 ok 0 unit**。kind 以外の差分 unit は 9 (`err` の `Runtime error 0 at 00000000102510A0` → `…C0` が 8 unit、
  unit 368 の `va_mb` 734.7 → 737.1 が 1 unit)。これは計測コードの有無ではなく **static 領域のレイアウト差**による: 計測を持たず、同じ大きさ・同じ section 構成の
  ダミー static (`.data` 32 B + `.bss` 36872 B) だけを足した対照ビルド (`work/ov_pad.c` = base の `m11_ov.c` + ダミー。一時ファイルで commit しない)
  と本 PR の差は **kind 以外も含め 0 unit** (`icall` 欄を除く)。対照と base の差は同じ 9 unit。→ カウンタは動作を変えない。
  (ダミーを `.bss` だけにした初版対照は本 PR との差が 8 unit 残った。差はすべて上記アドレスの +0x20 で、`.data` に入る初期化済みポインタ (表 2 本 = 32 B) の分と**推定**し、`.data` 32 B を足して 0 unit になった)。

## 4. 受入条件ごとの結果

| 条件 | 結果 |
|---|---|
| 復元した間接 call (override した関数内の `call [mem]` を含む) の hit 数を survey JSON に出す。出力形式を REPORT に定義 | **達成**: §1 に定義。`m11_ov.c` 内の `m11_icall` 呼出し 9 箇所すべてが site VA 付き (`icall_sites_check.py` が 9 件全部で機械語が間接 call と一致を確認)。override 内の `5c03d0` / `5c0270` / `410320` は survey JSON に出る |
| #482 の復元 (5c0e70 への通知 4 回) を JSON の hit 数だけで検収できる | **達成**: `python3 trap_triage/icall_hits.py work/after.json --expect site:0x5c0437=4/0 target:0x5c0e70=4/0` が PASS (exit 0)。両方 unit 114 のみ。通知先 `0x5c0e70` に解決できた (miss 0) ことまで JSON で分かる |
| ネガコン (復元を外すと hit 数が 0 に戻る) | **達成**: `negctl_482.sh` 5 構成 (下表) |

ネガコン (`bash trap_triage/negctl_482.sh`, 構成を 1 つずつ差し替えて再ビルド → 全 survey。`json:` 行 = JSON の `icall` 欄だけで判定、`trace` 列 = 最小集合を trace 付きで別実行して `[m11][icall] 0x1c0e70` を数える**独立の別方式**):

| 構成 | JSON `site 0x5c0437` [ok, miss] | JSON `target 0x5c0e70` [ok, miss] | trace 列 `0x5c0e70` ok / miss | 期待との一致 |
|---|---|---|---|---|
| `full` (現行) | **4, 0** | **4, 0** | 4 / 0 | PASS |
| `no5c03d0` (5c03d0 の転記を外す) | **0, 0** | **0, 0** | 0 / 0 | PASS (4 → 0) |
| `no5c0e70` (通知先の転記を外す) | 0, **4** | 0, **4** | 0 / 4 | PASS (call は起きるが先が miss) |
| `probe` (full + stderr 記録) | 4, 0 | 4, 0 | 4 / 0 | PASS (stderr の 5c03d0 呼出し 4 回 / 5c0e70 入口 4 回とも一致) |
| `probe_no5c03d0` | 0, 0 | 0, 0 | 0 / 0 | PASS (5c0e70 入口 0 回) |

- 5 構成とも survey の分類は ok 839 / oob 24 / halt0 32 / miss 46 / noproc 1 で不変。JSON の hit は stderr 記録 (`probe` の `[probe5c03d0]` 4 行 / `[probe5c0e70]` 4 行) と trace 計測の両方と一致した。
- `icall_hits.py` 自体のネガコン: 期待を `site:0x5c0437=5/0` にすると `FAIL … got ok=4 miss=0, want ok=5 miss=0`、exit 1。`icall_sites_check.py`: `ICALL_AT(0x5c0437,` を `0x5c0438` (命令の途中) に書き換えると `NG 0x5c0438: push rbx`、exit 1 (書き戻し済み、`git status` クリーン)。

## 5. 検証範囲 / 範囲外

- 範囲: `survey_units.mjs` (942 unit 各 1 回) の `icall` 欄と側ファイル、`negctl_482.sh` 5 構成、site VA の機械語照合。逆アセンブルは work の `m11_image.bin` (`M11_LB_BASE=0`) を `capstone` で読んだ (fl-win64 は未取得)。
- 範囲外: `m11_e2e.sh` (PE 要)、`M11_LB_BASE != 0` のビルド (site は VA なので影響しないはずだが未実行)、`m11_survey.mjs` / `m11_run.mjs` / `ldfix/*` (計測を出していない。`ldfix/stage4.sh` は別 EXPORTS で別ビルド)、
  `shimx_link` の `--wrap=m11_icall` 構成 (経路を変えない設計だが未ビルド)、#447 併用時。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **IR 側 (RetDec 出力) に残る間接 call は計測対象外**。計測するのは C 転記が `ICALL_AT` で呼ぶ 9 箇所だけで、**未復元の脱落 (D15 の検出漏れ)** は数えられない。`5c04b0` のような closure 外の同形 call も同様 | hit 数は「復元した call が動いた」ことの確認であって、脱落の網羅検出ではない | #474 REPORT §6 の「D15 / ldfix 検出漏れ全数」子チケットに併記 (`m11_icall_audit.py` の 4,175 件との突合が必要) |
| 新しい `m11_icall` 呼出しを足す時に `ICALL_AT` を付け忘れると `ext` に混ざる (強制する仕組み無し) | 将来の復元が site 別に出ない | 慣習として `icall_sites_check.py` を `m11_build.sh` 後に走らせる運用 (CI 化は #130 の判断) |
| `5c0e70` の OnChange / 所有者 (非 null) 経路 (`site 0x5c0826` / `0x5c0e91`) は survey で 0 回 (JSON でも 0 と確認できた) | 実機 UI 経路で効く可能性 | #130 (#482 REPORT §6 と同じ) |
| `m11_run.mjs` (full boot) の結果 JSON に icall 欄が無い (InitUnits の `0x412126` はそちらで 942 回のはず — **推定**、未計測) | boot 経路の復元 call は survey では見えない | #130 にコメント (必要なら子チケット) |
| trap 56 (#130 の完了条件 < 20 は未達) | #130 の完了条件 | #130 |

DEFECTS.md 行案 (D15 の「検出信号」に追記、編集は PM 判断): 「復元した間接 call は `survey_units.mjs` の per-unit `icall.sites["0x<call 命令 VA>"]` の hit 数で検出する (`trap_triage/icall_hits.py --expect`)。
復元が外れると hit が 0 に戻る。IR に残る未復元の脱落は計測できない (別途 `m11_icall_audit.py`)」。

## 7. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。emsdk (/opt/emsdk) が要る。icall_sites_check.py は capstone (pip) が要る
bash m11_build.sh && node trap_triage/survey_units.mjs work/after.json                 # ok 839 / trap 56。work/after.icall.json も出る
python3 trap_triage/icall_hits.py work/after.json --expect site:0x5c0437=4/0 target:0x5c0e70=4/0   # 受入条件 2 (PASS / exit 0)
python3 trap_triage/icall_hits.py work/after.json --sidecar --units                      # 全 site / target の hit と unit 番号 + boot / 累計
python3 trap_triage/survey_diff.py <base の survey.json> work/after.json                 # 分類不変 + icall 総数差 (両方に欄がある時)
python3 trap_triage/icall_sites_check.py                                                 # site VA が間接 call 命令か (9 件 OK)
bash trap_triage/negctl_482.sh                                                           # ネガコン 5 構成 (json: 行が hit 数による判定。終了時 ov.o を再生成)
```
