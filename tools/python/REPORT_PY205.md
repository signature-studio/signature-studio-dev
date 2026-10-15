# tools/python REPORT: PY-205 mixer getTrackCount・getEqBandCount の PE 確定 (#3493)

> 正本の関係: PE の読み方は `REPORT_PY87.md`、変換スロット `0x15e4280` の同定は `REPORT_PY152.md` §42 (本 REPORT はその流用と再確認)。
> 残り mixer 関数は子 #3553 (PY-212)。

## 結論

- mixer の 2 関数を PE で確定し、C provider (`provider/fl_engine.c`) と mock (`host/fl_mock.mjs`) に実装した。
- `getEqBandCount` = 3 (VA `0xd63870`)。`ecx=3` を変換スロットに渡すだけ。
- `getTrackCount` = (ポインタ大域 `0x15e2198` の指す先の dword) − 2 (VA `0xd641d0`)。`trackCount` (`0xd5e8b0`) と同じ読み方。
- **絶対値は未確定**。大域の実行時値は静的に確定できない。C/mock の 125 は既存の `trackCount` の 127 (`NMIX`) を前提にしている。
- wasm 版の `mixer_diff.mjs`・`provider_check.mjs` は本 run では未実行 (emsdk 無し)。ネイティブ照合で代替した (下の測定)。

## 手段

- 素材: `fl-win64.tar.zst` から `extracted/block00031_PE.bin` (22,227,016 B) のみ展開 (1.6 秒)。`toolchain-emsdk` は `$ARTIFACTS_DIR` に無く、runner に emsdk も無い。
- 逆アセンブル: `tools/python/analysis/flapi/pe_mixer_wrappers.py` (本 PR で修正。後述の訂正 1)。
- 再現コマンド:

```
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_mixer_wrappers.py trackCount getTrackCount getEqBandCount
```

## 機械語 (PE、関数先頭から最初の ret まで)

| 関数 | VA | 命令 (抜粋) | 読み |
|---|---|---|---|
| getTrackCount | 0xd641d0 | `mov rax,[rip+0x87dfbd]` (0xd641d4 → 大域 0x15e2198) → `mov eax,[rax]` → `sub eax,2` → `mov ecx,eax` → `call [0x15e4280]` | ポインタ大域の指す先の dword − 2 を 1 引数で変換 |
| getEqBandCount | 0xd63870 | `mov ecx,3` → `mov rax,[0x15e4280]` → `call [rax]` | 定数 3 を変換 |
| trackCount | 0xd5e8b0 | `mov rax,[0x15e2198]` → `mov ecx,[rax]` → `call [0x15e4280]` | 同じ大域の dword をそのまま変換 |

- 大域 `0x15e2198` は **qword のポインタ** (int の大域ではない)。静的初期値は `0x14188a8` (`.data`)。その先の dword の静的初期値は 502 (`0x1f6`)。これが実行時の mixer の track 数かは未確認 (下の未解決)。
- 間接 call の呼出し先 `[0x15e4280]`: `.data` の初期値は cell `0x16b8298` (`.bss`・実行時に埋まる)。cell への書込みは `0xc396c5` (`mov [0x16b8298],rax`)。直前 `0xc396b9` で `lea rdx,[0xc3a292]` (UTF-16 の `PyLong_FromLong`) を渡し、`call 0x4235f0` の結果を書く。
- 名前の根拠は REPORT_PY152 §42 の同定 (初期化文字列経由) の流用。本 PR で再確認したのは「cell の書込み元の直前に、この UTF-16 文字列を渡す呼出しがある」まで。`0x4235f0` の内部は未読 (名前解決関数と推定)。
- `trackCount` も同じスロットを 1 引数 (`ecx`) で呼ぶ (`0xd5e8c4`)。

## 解析補助の訂正 (pe_mixer_wrappers.py)

修正前は (a) `ret` で止まらず、関数末尾の後ろを読んでいた (`trackCount` の `calls` が ret `0xd5e8ca` の後の `0xd5e935` 等)、(b) `call qword ptr [rax]` を拾わず `getTrackCount`・`getEqBandCount` が `calls=[]` だった。修正後は最初の ret で打切り、間接 call は呼出し先スロットの VA と .data の raw 値を出す。出力 (3 関数):

```
trackCount                       fn=0xd5e8b0 flags=0x4 calls=['ind rax->[0x15e4280]=0x16b8298'] str=[]
getEqBandCount                   fn=0xd63870 flags=0x4 calls=['ind rax->[0x15e4280]=0x16b8298'] str=[]
getTrackCount                    fn=0xd641d0 flags=0x4 calls=['ind rax->[0x15e4280]=0x16b8298'] str=[]
```

72 行すべて出力できることを確認 (`grep -c fn=` = 72)。複数 ret の関数は最初の ret までしか読まない (既知の制限・本 PR の 3 関数は ret が 1 つ)。

## 測定 (ネイティブ、測定 commit `699a5fd93`)

- 測定 commit: `699a5fd93` (コードを変えた最後の commit)。以後の REPORT 追加 commit はコード範囲の外。
- ハンドラ数: `python3 tools/python/provider/gen_provider.py --check-handlers tools/python/provider/fl_engine.c` → `ハンドラ 151`、rc 0。
- ネイティブ C: `gcc -O2 -w -Iprovider provider/fl_dispatch.c provider/fl_engine.c provider/gen/fl_table.c drv.c` (driver は下)。fn_id は `analysis/flapi/flapi_ids.json` の列挙順 (trackCount 169・getTrackCount 123・getEqBandCount 106)。
- mock: `node --input-type=module -e 'import {createMockEngine} from "./host/fl_mock.mjs"; ...'`。

| 呼出し | native (C) | mock | 差分 |
|---|---|---|---|
| mixer.trackCount | 127 | 127 | 0 |
| mixer.getTrackCount | 125 | 125 | 0 |
| mixer.getEqBandCount | 3 | 3 | 0 |

- ネガティブコントロール: 一時コピー (リポジトリ外) で `fl_ret_i(c, NMIX - 2)` を `NMIX - 3` に変えると、native `getTrackCount` = **124** で mock (125) と不一致 → `mixer_diff.mjs` なら diff 1 件で FAIL する。
- driver (`drv.c`): `#include "fl_api.h"` の `main` で `fl_slot ret; memset(&ret,0,sizeof ret); fl_api_call(atoi(argv[1]), NULL, 0, &ret);` を呼び `rc/tag/code/i` を表示。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 版 `mixer_diff.mjs`・`provider_check.mjs`・`all_tools.mjs` の実行 (emsdk 無し) | 2 関数の wasm 照合は未実施。ネイティブ照合のみ | #3553 |
| `*(0x15e2198)` の実行時値 (静的初期値 502 の扱い) | getTrackCount の絶対値 125 は 127 前提 | #3553 |
| `0x4235f0` の内部 (名前解決) | 呼出し先の名前は PY-152 同定の流用 (本 PR で未読) | #3553 (未解決の再確認) |
| mixer 件数の表記 (#941・#3493 の旧本文「57」) | flapi 表 75 − C 実装 21 = 54 (旧 19 時点は 56) | #3553 本文を 54 に訂正 |
