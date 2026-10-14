# KH-19d (#850): 対照 Gain の before 160 閉包を x64c で lift し、build の最初の失敗点を記録する

- 対象: 対照 Gain (`gain`) の before 160 閉包。root 27 件は `gain_before_160.tsv` の root 行 (機械生成・`verified` 列は全行 `auto`)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
  ImageBase `0x180000000`・SizeOfImage `0x625c000`・AMD64。Windows 側だけを手で展開 (`extract_installer.sh` は macOS 側で停止するため)。展開先は repo 外。
- 測定 commit (コードを変えた最後の commit): `196f37ef`。以降の変更は本ファイルと `docs/DOC_MAP.md` のみ。

## 0. 結論

- 受入 1 の「KH-19b で確定した closure」はまだ確定していない (手検証 160 との差分判定は #2176 待ち)。本節が lift したのは**未確定の before 160** (直接 call 閉包の下界・機械生成)。確定 closure の lift は未実施 (子 issue KH-36)。
- x64c で **148 関数**を lift した。before 160 との差 12 件の内訳は §3 (tail jmp 9・IAT thunk 2・取りこぼし 1)。
- 最初の build 失敗点: **`fle_data_gen.py` に直書きされた FLEngine 固有の VA `0x42f670` の窓**。Kilohearts の像の外で負の番地になり、emcc が字句エラーで止まる (§4 の B)。範囲内に限る 1 行で解消。
- 既定 ImageBase (`0x180000000`) のままでは wasm32 の番地に収まらない。像を `0x2000000` 起点へ shift すると、compile・link・smoke が通る (§4 の C)。ただし正しさは未検証 (bit 突合は範囲外)。

## 1. 再現手順

```
# 素材 (ARTIFACTS_DIR は実在を ls で確認してから使う)
tar --zstd -xf ${ARTIFACTS_DIR}/plugins-kilohearts.tar.zst --wildcards '*Offline Installer.zip'
unzip -q -o "Kilohearts Offline Installer.zip" payload.dat -d win
unzip -q -o win/payload.dat index.json 'windows.zip/*' -d blobs
unzip -q -o blobs/windows.zip/1ccb1df8c8f10745 -d winpkg        # → winpkg/HeartCore.core_64

# lift → data 敷設 → emcc compile・link → smoke (出力は repo 外)
KH_CORE=<winpkg/HeartCore.core_64> OUT=<repo 外の出力先> EMSDK=<emsdk のルート [EMSDK]> \
  bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh
```

`scripts/lift_closure_x64c.sh` は `gain_before_160.tsv` の root 行から `entries.json` を作り、`tools/flelift/x64c.py` (`--closure 60`・shift 付き)、`tools/flelift/fle_data_gen.py` (shift 付き)、`emcc` (`fle_lift.sh` と同じフラグ)、node の smoke の順に実行する。

## 2. 実測 (測定 commit `196f37ef`・4 vCPU・各 1 回・load average 0.28 → 0.72)

| 段 | 結果 | 時間 |
|---|---|--:|
| x64c (roots 27・closure 60・`--img 0x180000000 --shift 0x17E000000`) | functions 148・insns 9,502・unsup 285 site (48 mnemonic 種)・unlifted callees 0・imports used 25 (IAT 404 slot) | 13.7 s |
| fle_data_gen (`shift 0x17E000000`) | sections `.rdata` 21.8 MB・`.data` 1.8 MB・`.reloc` 0.8 MB、windows 8、total 24,441,216 B | — |
| emcc compile (`fle_lifted.c`、`-w` なし) | warnings 0・errors 0 | — |
| emcc link (`fle_lift.sh` と同じフラグ) | exit 0・`kh.wasm` 25,295,206 B | 21.0 s |
| smoke (node): `_fle_init` / `_fle_data_install` / `_fle_run(Gain process, 引数 0)` | 3 段とも trap なし。`fle_run` の戻り値 RAX = 303376204 | — |
| スクリプト全体 | exit 0 | 54.5 s |

- smoke は**正しさの検証ではない**。入力 spec を与えていないため戻り値の値は意味を持たない。bit 突合は issue の範囲外。
- unsup 285 site: 実行到達時は `ott_unsup` で停止する。多い順は `vmovntdq` 30・`vmovsd` 32・`vmovd` 29・`vmulsd` 25・`vaddsd` 23・`vmovq` 17・`vfmadd213sd` 16 (VEX / FMA 系)。

## 3. 閉包の差分 (x64c 148 vs TSV 160)

- 集合の包含: x64c の 148 関数はすべて TSV の 160 行に含まれる。逆方向の差は 0。
- 差 12 件の内訳 (一時確認スクリプト。repo 外・未コミット):
  - **tail `jmp` 9 件** (`0x6500`・`0x4d400`・`0xf87d40`・`0xfd099c`・`0xfd66a0`・`0xfd8d08`・`0xfd8d24`・`0xfe3488`・`0x1327348`): 親の descend で到達し、親の C 本体に取り込まれている。x64c は他関数への `jmp` を `calls` に入れないため、関数としては数えられない (コードは lift 済み)。
  - **IAT thunk 2 件** (`0xfd81e4`・`0xfd81ec`): `jmp qword ptr [rip+..]` で IAT の `FlsGetValue`・`FlsSetValue` へ飛ぶ thunk。x64c は import 経路 (`imp_*`) として扱い、関数にしない。
  - **取りこぼし 1 件** (`0xfc7468`、size 42): 親 `0xfd08d0` の call 位置 `0xfd0995` を x64c の descend が辿らない。原因は未調査 (子 issue KH-37)。
- `unlifted_callees` が 0 件のため、x64c が見た直接 call 先はすべて lift 済みか thunk。

## 4. build の失敗点の記録 (同じ入力・手順の 3 試行)

| 試行 | 構成 | 結果 |
|---|---|---|
| A | 既定の VA のまま (`--img 0x180000000 --shift 0`) | compile 警告 0・link exit 0。ただし `_fle_data_install` が `RuntimeError: memory access out of bounds` で停止。VA の 64 bit 定数は 32 bit 番地へ切り詰められる |
| B | shift `0x17E000000` (像を `0x2000000` 起点)・`fle_data_gen.py` は FLEngine 版のまま | **link 失敗** (最初の失敗点)。`fle_data.c:1018374:18: error: invalid suffix 'x' on integer constant` `memcpy((void*)0x-17dbd0990u, w_0, 48u);`。`-0x17dbd0990` = `0x42f670 - 0x180000000`。`fle_data_gen.py` の `(0x42f670, 0x30)` (FLEngine の vtable 窓・#1936/#2005) が Kilohearts の像の外で負の番地になった |
| C | B + 窓を像の範囲内に限る (本 PR) | **成功**。§2 の実測 |

- 試行 B の原因箇所: `tools/flelift/fle_data_gen.py` の `for a, n in [(0x42f670, 0x30)]`。本 PR で `IMG <= a < IMG + SizeOfImage` の判定を足した。FLEngine (像内) では従来どおり追加される。
- 試行 A の補足 (未確認): 直書き窓は VA 版では `IMG + rva` が打ち消し合い `0x42f670` へ書き込む。emcc の静的領域と重なるかは確認していない。

## 5. FLEngine 側の回帰確認

- `fle_data_gen.py` の変更 (敷設先 = `IMG + RVA - SHIFT`、既定 `SHIFT = 0`、窓の範囲判定) は、FLEngine の PE (`block00031_PE.bin`、素材 `fl-win64` から展開) で旧版と出力が一致 (`cmp` 一致・14,820,487 B)。
- 注意: 確認に使った `lift_meta.json` は空の合成値 (jt / textrefs / IAT なし)。FLEngine の全 lift (`fle_lift.sh`) は再実行していない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 確定 closure (手検証 160 との差分 0) の lift と build | 受入 1 の「確定 closure」は未確定。本節は未確定の before 160 | KH-36 (子・前提 #2176) |
| x64c の閉包の取りこぼし 1 件 (`0xfc7468`)・tail jmp と thunk の数え方 | 関数数 148 ≠ 160 | KH-37 (子) |
| unsup 285 site (VEX / FMA 系 48 mnemonic 種) | 実行到達時に `ott_unsup` で停止 | KH-38 (子) |
| bit 突合 (native 対照) | 範囲外 (issue 本文) | 起票なし |
