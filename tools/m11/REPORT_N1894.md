# M11 REPORT §18 (#1894 [M11-13]): _CopyArray (416db0) の呼出し元関数の実行時到達 (#1847 の残り)
本体 `REPORT.md` §18 の付録。前提は `REPORT_N15.md` §16 (#1847 の site 別計測)。

既知類型との関係: 該当なし (計測専用 probe。lift 欠陥の新類型は見つけていない)。

## 結論
- 呼出し元 7 関数 (site 1・4・5・6・7・8/9・10/11 の所属) のうち、**survey で実行時到達が確認できたのは `417b70` (site 5) のみ**。残りの 6 関数 (`12a3ff0`・`417110`・`418030`・`418280`・`4183d0`・`418700`) は全 942 unit で entry が 0 件 = 実行されない。
- `416750` (site 2) は 7 unit で実行 (既知の経路と一致し、probe の陽性対照として機能)。
- 未到達 6 関数の直接 call 上界 unit は、**上界の unit 自体は実行されるが、その中で呼出し元関数は実行されない** (下表)。上界は実行を示さない。

## 測定
測定 commit: `09723d9e` (origin/main 起点) + 本 PR のコード変更 (`git diff` は本節末尾)。
4 vCPU・load 0.54〜0.83 (各 build/survey の前後 `uptime`)。素材 `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`) と `work-m11` を展開。
`m11_gen_ir2.sh` 50 s・rc 0・ldfix applied。`m11_build.sh` 24 s。survey 13 s (既定) / 57 s (probe 版, 全 942 unit)。

| 構成 | ok/miss/other/halt0/oob/noproc | stderr 行 | 備考 |
|---|---|---|---|
| 既定 (`M11_ENTRY_PROBE=0`, 本 PR の survey_entry.mjs) | 870/47/1/7/16/1 | 70 (`SV_ERR_LOG`) | #1511 節 (REPORT_N15.md) の 870/47/1/7/16/1・70 行と一致 |
| entry probe 版 (ep3) | 872/47/1/7/14/1 | - | 既定との差は unit 304・555 等 (#1670 と同じ既知の probe 副作用) |
| entry probe 版 (ep4, 再現) | 872/47/1/7/14/1 | - | ep3 と unit 別 kind・到達フラグの差分 0 件 |

### entry 到達 (probe 版 ep3・ep4 で一致, unit 別)
| 関数 | site | 実行された unit 数 | kind の内訳 |
|---|---|---|---|
| `12a3ff0` | 1 | **0** | - |
| `417110` | 4 | **0** | - |
| `417b70` | 5 | 24 | ok 21・other 1・halt0 1・oob 1 |
| `418030` | 6 | **0** | - |
| `418280` | 7 | **0** | - |
| `4183d0` | 8/9 | **0** | - |
| `418700` | 10/11 | **0** | - |
| `416750` (陽性対照・site 2 の所属) | 2 | 7 (17/36/86/138/357/496/501) | ok 7 |

- 受入 1 (site 1・4〜11 の判定): 達成。上表。
- 受入 2 (未到達 site の上界 unit が実行されるか): 達成。下表。
- 受入 3 (測定 commit・load・秒・stderr 件数): 達成。上表。

### 上界 unit の実行 (直接 call 閉包 = 上界)
| 関数 | 上界 unit (閉包に入る) | 上界 unit のうち survey で実行された entry |
|---|---|---|
| `12a3ff0` | 895, 898 | 895 halt0 (入口前に停止)・898 ok (`417b70` のみ) → **呼出し元は 0** |
| `417110` | 501 | 501 ok (`416750` のみ) → **0** |
| `418280` | 895, 898 | 同上 → **0** |
| `4183d0` | 895, 898 | 同上 → **0** |
| `418700` | 17, 492 | 17 ok (`417b70`・`416750`)・492 oob (`417b70`) → **0** |
| `418030` (site 6) | 82 unit (上界・閉包に入る unit 数) | 82 件すべてで 418030 の entry は 0 件 (実測。上界 82 unit のうち実行された unit は 0) |

- 注: 上界 unit が**実行されても**呼出し元は 0 件。よって「上界 unit が実行されるから呼出し元も実行される」とは言えない。呼出し元の内部で分岐 (前段の条件) が落ちている可能性が高いが、これは未測定 (次節)。

## 測定上の注意 (読み方)
- `417b70` と `416db0` は `m11_ov.c` で strong 定義されており (`ov.o` の T)、IR 版 `function_417b70` は link で捨てられる。IR 挿入の probe では読めない (初回測定で 417b70 が 0 件だった理由)。そのため `m11_ov.c` 側に `M11_ENTRY_PROBE` 付きの同じ global store を入れて測った。
- 残り 6 関数 (`12a3ff0`・`417110`・`418030`・`418280`・`4183d0`・`418700`) は boot.o の weak 版。`416750` (weak 版) が 7 件立つことで、IR 挿入 probe が機能することを確認した (陽性対照)。
- probe は `global` への volatile store のみで、呼出しを挟まない (#1847 の注意)。ただし既定 build との kind 分布には unit 304・555 の差がある (#1670 と同じ既知の副作用。isolation の有無は差を作らない)。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 上界 unit の中で呼出し元 (`12a3ff0`・`417110`・`418030`・`418280`・`4183d0`・`418700`) の直前の分岐がどこで落ちるか | site 1・4・6〜11 が未到達の理由が未特定 | 本 PR 範囲外。#1894 の後続として起票 (子 issue) |
| 既定 build と probe 版の unit 304・555 の差 | 到達判定の透過性 | #1670 の既存未解決 (継続) |

## 再現
```
cd tools/m11
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin
bash m11_gen_ir2.sh                                       # IR (ldfix applied)
bash m11_build.sh                                         # 既定 build
SV_ERR_LOG=work/s1894/base_err.txt node trap_triage/survey_units.mjs work/s1894/base.json   # 既定 (70 行)
bash m11_entry_probe.sh work/s1894/ep3                    # probe 版 (entry 到達 8 関数)
python3 - <<'PY'                                          # 集計 (ep3/entry.json の fe[0..7] = 12a3ff0,417110,417b70,418030,418280,4183d0,418700,416750)
import json
per = json.load(open('work/s1894/ep3/entry.json'))
names = ['12a3ff0','417110','417b70','418030','418280','4183d0','418700','416750']
for i, f in enumerate(names):
    u = [r['unit'] for r in per if r['fe'][i]]
    print(f, len(u), u[:12])
PY
```

## 測定 commit と差分 (鮮度)
- 測定 commit (コード変更の最後): 本 PR の commit (`m11_build.sh`・`m11_ov.c`・`m11_entry_probe.py`・`m11_entry_probe.sh`・`m11_entry_probe_rt.c`・`trap_triage/survey_entry.mjs`)。
- 既定 build の挙動は不変: `M11_ENTRY_PROBE` 既定 0 で `ov.o` の定義は従来と同一 (`#if M11_ENTRY_PROBE` で囲んだ 3 行のみ追加)、`EXPORTED_FUNCTIONS` も 0 で従来同一。既定 kind 分布 870/47/1/7/16/1 は #1511 節 (REPORT_N15.md) と一致。
