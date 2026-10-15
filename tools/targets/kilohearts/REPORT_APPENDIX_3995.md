# REPORT APPENDIX 3995 — KH-82 (#3995): Phase Plant (phaseplant) の process slot と x64c 閉包

> 本付録は #3995 (親 #61 の分割 f) の測定値の正本。process slot は**未確定** (§1)。lift・build・wasm は未実施 (子 #3994 [KH-81] の範囲)。
> 導線は `REPORT_APPENDIX_61.md` (Snap Heap / Multipass の同形式の付録)・`REPORT_APPENDIX_849.md` (間接 call の規則)。

## 0. 結論 (先出し)

- **Snap Heap / Multipass の「slot 14 = process」規則は Phase Plant に当てはまらない**。`PhasePlantDsp` の vtable は **12 slot** (slot 0〜11) で、slot 12 は null、slot 14 は存在しない。`SnapinDsp<...>` 基底も持たない。
- 候補を全 slot で測った。最大は **slot 8** (`0x1806652c0`、7,178 B の最大関数)。closure は **287 関数 / 26,477 命令 / unsup 70 site**。全 slot を root にした closure は 336 関数 / 30,547 命令 / unsup 70 site。
- slot 8 が process であることは**未確定**。根拠は「最大サイズ・最大の closure」だけで、ホスト側の呼出元で (this, ctx, AudioBuffer*) の形を確認していない (§3 の未解決)。
- unsup の内訳 (slot 8 closure): rcpps 30・rsqrtps 25 (計 55 site = 79%。近似命令) / vcomiss 4・vcvtdq2ps 2・vpsrld 2・vpslld 1・vandps 1・vandnpd 2・vpcmpeqq 2・haddps 1 (計 15 site)。

## 1. 数え方の定義と process slot の判定

| 項目 | 定義 |
|---|---|
| vtable | `.?AVPhasePlantDsp@phaseplant@@` の COL 付き vtable。`rtti_walk.py` で出し、slot 12 が null であることを生バイトで確認 (vtable RVA `0x181e7b498`・file off `0x1e7a298`) |
| 候補 slot | 12 slot 全部 (slot 9 `0x180020e60`・slot 10 `0x180003370` は他クラスと共有される slot で、関数 1 本 / 2 命令の共通 stub) |
| closure | `x64c.py --closure 1000`。根から直接 call/jmp を辿る。間接 call は辿らない |
| 判定の材料 | (a) slot 14 規則が効かないこと (§0)、(b) 関数サイズ、(c) closure の規模 |

判定の結論: slot 14 規則は使えない。slot 8 が最有力候補だが確定ではない。

## 2. 測定 (再現: `KH_CORE=<HeartCore.core_64> OUT=<repo 外> bash scripts/phaseplant_x64c_closure.sh`)

- 入力: `HeartCore.core_64` 76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe` (`REPORT_APPENDIX_61.md` と同一。素材 `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`。repo 外 `$RUNNER_TEMP/kh3995` で展開)。
- 測定 commit: `81e1e6c18` (`scripts/phaseplant_x64c_closure.sh` を追加した commit)。同 commit の HEAD で全 slot を再実行し、初回実行 (未 commit) と全項目一致。
- 所要: スクリプト全体 2 分 32 秒 (測定 commit で 1 回)。load average は実行後 0.95 (nproc=4)。

| root | VA | 関数サイズ | functions | insns | unsup sites | imports | traps |
|---|---|--:|--:|--:|--:|--:|--:|
| slot 0 | `0x1806673e0` | 103 | 32 | 962 | 0 | 8 | 0 |
| slot 1 | `0x180664250` | 197 | 181 | 13,274 | 10 | 26 | 0 |
| slot 2 | `0x180664500` | 192 | 174 | 10,427 | 10 | 26 | 0 |
| slot 3 | `0x1806648a0` | 762 | 115 | 5,678 | 0 | 26 | 0 |
| slot 4 | `0x180664ba0` | 549 | 110 | 5,545 | 0 | 26 | 0 |
| slot 5 | `0x180664dd0` | 34 | 108 | 5,266 | 0 | 26 | 0 |
| slot 6 | `0x180664e00` | 674 | 120 | 4,950 | 10 | 25 | 0 |
| slot 7 | `0x1806650b0` | 525 | 90 | 5,376 | 0 | 17 | 0 |
| **slot 8** | `0x1806652c0` | **7,178** | **287** | **26,477** | **70** | **30** | 0 |
| slot 9 (共有 stub) | `0x180020e60` | — | 1 | 2 | 0 | 0 | 0 |
| slot 10 (共有 stub) | `0x180003370` | — | 1 | 2 | 0 | 0 | 0 |
| slot 11 | `0x18007a830` | 216 | 1 | 35 | 0 | 0 | 0 |
| 全 slot を root | 12 本 | — | 336 | 30,547 | 70 | 30 | 0 |

- slot 8 の unsup 内訳: rcpps 30・rsqrtps 25・vcomiss 4・vcvtdq2ps 2・vpsrld 2・vandnpd 2・vpcmpeqq 2・vpslld 1・vandps 1・haddps 1 (計 70 site・10 種)。
- slot 1 / 2 / 6 の unsup は同じ 5 種 10 site (vandps 1・vcomiss 4・vcvtdq2ps 2・vpslld 1・vpsrld 2)。slot 1・2 は VEX 語彙だけで、近似命令を含まない。
- 全 slot の unsup 種は 10 種 70 site。Snap Heap / Multipass (8 種 65 site) より 2 種多い (`vpcmpeqq`・`vandnpd`)。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| process slot の確定 (slot 8 が (this, ctx, AudioBuffer*) の process か) | slot 8 の closure を lift 対象にしてよいか未確定。誤れば閉包の規模が変わる | #4395 [KH-96] |
| closure が直接 call の辺だけの下界であること | 間接 call 先 (vtable 経由) は根に入れた slot だけ。slot 8 から先の vtable 呼出は未追跡 | #3994 [KH-81] の範囲 |
| unsup 70 site (近似 55 + 語彙 15) の解消 | lift・build が通らない | #3994 [KH-81] |
| lift・build・wasm・native 比較 | 受入の本体 | #3994 [KH-81] |
