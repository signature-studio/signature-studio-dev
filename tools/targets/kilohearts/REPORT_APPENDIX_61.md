# REPORT APPENDIX 61 — KH-6 (#61): ホスト Snap Heap (micropass) / Multipass (multipass) の process 閉包を x64c で測る

> 本付録は #61 の残 scope「ホスト 3 種の lift」の第一段。閉包と unsup の census まで。lift・build・wasm・native 比較は未実施 (子 #3994 [KH-81])。Phase Plant は対象外 (子 #3995 [KH-82])。
> 導線は `REPORT.md` §4 (難度表 43-45)・`REPORT_APPENDIX_849.md` (間接 call の CFG / vtable 規則)。

## 0. 結論 (先出し)

- **Snap Heap (`MicropassDsp`)**: process = slot 14 = `0x1807d8a60`。根 14 本の閉包 = **242 関数 / 18,402 命令**。unsup **65 site**・imports 30・traps 0。
- **Multipass (`MultipassDsp`)**: process = slot 14 = `0x1805488d0`。根 14 本の閉包 = **251 関数 / 20,764 命令**。unsup **65 site**・imports 30・traps 0。
- 両者の unsup は同じ 8 種。rcpps 29 + rsqrtps 25 = 54 site (83%) が近似命令。残り 11 site は VEX / SSE の語彙不足 (vcomiss 4・vcvtdq2ps 2・vpsrld 2・vpslld 1・haddps 1・vandps 1)。
- **ネガコン**: 根を process 1 本にすると Snap Heap 148 関数 / 11,102 命令、Multipass 160 関数 / 13,856 命令。unsup は両者とも 65 のまま。差の 94 / 91 関数は独自 slot 由来で、unsup を持たない。

## 1. 数え方の定義

| 項目 | 定義 |
|---|---|
| process VA | `<X>Dsp` の vtable の slot 14。`SnapinDsp<XDspModel>` の slot 14 は no-op (`0x1800128a0`) なので、独自 override である |
| roots | `<X>Dsp` の vtable のうち、`SnapinDsp<XDspModel>` と値が異なる slot (no-op `0x1800128a0` を除く)。Snap Heap 14 本 / Multipass 14 本 |
| 閉包 | `x64c.py --closure 1000`。根から直接 call/jmp を辿った関数集合。間接 call は辿らない (根に明示したものだけ入る) |
| functions / insns | `lift_meta.json` の `functions` 件数 / `ninsn` |
| unsup sites | `lift_meta.json` の `unsup_sites` 件数 (種別の合計は 65) |

## 2. 測定 (再現: `KH_CORE=<HeartCore.core_64> OUT=<repo 外> bash scripts/host_x64c_closure.sh`)

| ホスト | 条件 | 根 | functions | insns | unsup sites | imports | traps |
|---|---|--:|--:|--:|--:|--:|--:|
| Snap Heap (micropass) | 閉包 | 14 | **242** | **18,402** | **65** | 30 | 0 |
| Snap Heap (micropass) | ネガコン (process のみ) | 1 | 148 | 11,102 | 65 | 29 | 0 |
| Multipass (multipass) | 閉包 | 14 | **251** | **20,764** | **65** | 30 | 0 |
| Multipass (multipass) | ネガコン (process のみ) | 1 | 160 | 13,856 | 65 | 29 | 0 |

unsup の内訳 (両ホスト同一):

| 種 | site 数 | 性質 |
|---|--:|---|
| rcpps | 29 | 近似命令。既存 snap-in と同じ型 (実機表が要る。`snapins/scripts/approx_tables.b64`・`snapins/REPORT.md` §13) |
| rsqrtps | 25 | 近似命令 (同上) |
| vcomiss | 4 | 比較 (x64c の語彙に無い) |
| vcvtdq2ps | 2 | 変換 |
| vpsrld | 2 | シフト |
| vpslld | 1 | シフト |
| haddps | 1 | 水平加算 |
| vandps | 1 | 論理 |

- 入力: `HeartCore.core_64` 76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe` (素材 `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`)。素材は `tar --zstd -xf ... --occurrence=1` で zip だけ取り出し、repo 外 (`$RUNNER_TEMP/kh_host`) で展開した。`extract_installer.sh` は個人の既定ダウンロード先を前提にしているため使っていない。
- 所要: スクリプト全体 59.8 s (測定 commit の HEAD で 1 回)。load average は実行前 0.44、実行後 0.85 (nproc=4)。
- 再現: 測定 commit `9087f36d2` の HEAD で実行した値 (run2) が、スクリプト未 commit の状態で実行した値 (run1) と全項目一致。
- 注: `#849` の数字 (Snap Heap nogui 1,531 関数 / 722,713 B 等) は、vtable slot 番号一致の候補を同 ns の全 class から集めた上限寄りの閉包で、根の数え方も本付録と違う。本付録の数字とは直接比較しない。

## 3. 測定 commit と差分

- 測定 commit: `9087f36d2` (`scripts/host_x64c_closure.sh` を追加)。以後、測定に使うコードを変えていない。
- 差分確認: `git diff 9087f36d2 HEAD -- tools/targets/kilohearts/scripts tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts tools/targets/kilohearts/snapins/run_all.sh tools/targets/kilohearts/snapins/snapins.json` の出力は 0 行 (本付録と `docs/DOC_MAP.md` の登録行のみが後続 commit で増える)。

## 4. 対象外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Phase Plant (`phaseplant`) の process 閉包 | `PhasePlantDsp` は `SnapinDsp` 基底を持たず、slot 14 規則が効くか未検証。nogui 504 関数 (`#849` 規則) | #3995 [KH-82] |
| unsup 65 site (rcpps 29・rsqrtps 25 + 語彙 11) の解消 | lift・build が通らない | #3994 [KH-81] |
| lift・build・wasm・native 比較・1 bit ネガコン | 受入の本体 | #3994 [KH-81] |
| 閉包が直接 call の辺だけを辿る下界であること | vtable 経由の先は根に入れた slot だけ。CFG / vtable 候補 (`#849`) との統合は未実施 | #3994 [KH-81] |
