# PY-73 (#2547) 付録: `0x1046a30` (lo・hi・cur の共通 getter) の振り分け表 (5 回目 run)

親: #2547 (PY-73)。前段: `tools/python/REPORT_PY73.md` §9-6 (未解決 `0x1046a30` の mode 0x20・mode 2)。値源の残りは子 #2887 (PY-103) が扱う。

## 結論

- `0x1046a30(eventId = ecx, value = edx, mode = r8d)` で `mode & 0x240 == 0` の呼出し (mode 0x20 の lo・hi、mode 2 の cur を含む) は、戻り値を決める本体へ入らず、**eventId 種別の振り分け `0x1047424` へ直接飛ぶ** (0x1046e23 `test`・0x1046e28 `je 0x1047424`)。
- RetDec 出力の `return result2` (行 83-85) は、この飛び先を return と誤読したもの。`0x1047424` はエピローグではなく振り分け (compare チェーン) の先頭。
- 振り分け先は下表の 7 分岐先 (`0x104c2a6`・`0x104c4af`・`0x104c64f`・`0x104c919`・`0x1047497`・`0x104aa87`・`0x104caae`)。各ハンドラの lo・hi・cur は未読。よって lo・hi・cur は本 run でも未確定で、provider・mock は未実装のまま。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に `*block00031_PE.bin` だけ展開 (実測 2.9 秒)。
- 逆アセンブル `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py <VA> <命令数>`: `1046a30 900`・`1047424 60`・`10476f0 22`・ハンドラ先頭 `104c2a6`・`104c4af`・`104c64f`・`104c919`・`104aa87`・`104caae`・`104cc72` (各 6)。いずれも終了 0・0.1 秒未満。
- RetDec 5.0: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 RETDEC_BIN=[RETDEC] 配下の retdec-decompiler (`docs/REFERENCES.md` §4) bash tools/python/analysis/flapi/pe_retdec.sh <out.c> 0x1046a30-0x1047424` (終了 0・9.3 秒)。
- 測定 commit: `e87eb52a` (PR の base)。本 run でコードは変えていない (追加は本付録・`REPORT_PY73.md` の 1 行・DOC_MAP の 1 行)。
- 差分 0 の証跡: `git diff e87eb52a HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。

## 1. 引数の割り当て (エントリ 0x1046d65〜0x1046d71)

- `[rbp+0x5b0] = ecx` (eventId)・`[rbp+0x5b8] = edx` (value)・`[rbp+0x5c0] = r8d` (mode)。RetDec は a2 (edx) を使っていないように見せるが、`[rbp+0x5b8]` は 0x10476f9 系の経路 (下記 §3) で読まれる。

## 2. eventId 種別の振り分け (0x1047424 の compare チェーン)

eventId は符号付きで比較される (0x104742f `jg`)。下の範囲は、チェーンの各 `sub`・`cmp`・`jcc` を追って求めた。境界値は、同じ命令列を Python で写した判定でも確認した。

| eventId の範囲 | 分岐先 | 根拠 (VA) |
|---|---|---|
| `0x40000000` | `0x104c2a6` | 0x1047458 `sub 0x40000000`・0x104745d `test`・0x1047465 `jmp 0x104c2a6` |
| `0x40000001` | `0x104c4af` | 0x1047431 `cmp`・0x1047436 `je` |
| `0x40000002` | `0x104c64f` | 0x104746a `jg` 後の 0x1047471 `je` (`sub 0x40000002`) |
| `0x40000005` | `0x104c919` | 0x104746a `sub 0x40000002` (結果 3)・0x1047477 `sub 3` (結果 0)・0x104747c `je` |
| `0x00000000`〜`0x0fffffff` | `0x1047497` (H = eventId >> 16 で項目を引く。§3) | 0x1047456 `jb 0x1047497` |
| `0x70000000`〜`0xefffffff` | `0x104aa87` (下位 16 bit に 0x70000000 を足す正規化。以降は未読) | 0x1047446 `jb 0x104aa87` (`0x80000000`〜`0xefffffff`)・0x1047492 `jmp 0x104aa87` (`0x70000000`〜`0x7fffffff`) |
| 上記以外 (`0x10000000`〜`0x3fffffff`・`0x40000003`・`0x40000004`・`0x40000006`〜`0x6fffffff`・`0xf0000000`〜`0xffffffff`) | `0x104caae` | 0x104745f `jne`・0x104748c `jae` |

- `0x40000003` は `0x1047477 sub 3` の結果が 0 にならず (`eventId - 0x40000005` ≠ 0)、0x1047482 `sub 0x2ffffffb` → 0x104748c `jae` で振り分け外 (`0x104caae`) へ入る。`0x104c919` に入るのは eventId = `0x40000005` だけ。
- `0x1047497` 系では H と項目数 `[*(...) + 0x10]` を比べ、H ≥ 件数なら `0x104cc72` (0x412e40 と 0x41a770 を呼ぶ経路。文言・戻り値は未読)。

## 3. mode の効き (判明分)

- 0x1046e1d `mov eax, [rbp+0x5c0]`・0x1046e23 `test eax, 0x240`・0x1046e28 `je 0x1047424`: 0x200 と 0x40 の両方が無い mode は振り分けへ直行する。mode 0x20 と mode 2 はこの形。
- 0x1046dbe〜0x1046e00: `mode & 0x8a1 ≠ 0`・`mode & 0x20 == 0`・`mode & 0x10000 == 0` のときだけ `0xf82c20(*(*(0x15e0a00)), eventId, 0, 0, 0)` を呼ぶ。mode 0x20 では呼ばれない。
- 0x10476f9〜0x1047719 (0x1047497 系の末尾): `mode & 0x20` のとき `value := 0x10469f0(value, 0, 0x3200)` (`ecx = [rbp+0x5b8]`・`edx = 0`・`r8d = 0x3200`)。戻り値で `[rbp+0x5b8]` を置き換える。`0x10469f0` は未読。
- 同 0x104771f: `mode & 1` (値 1 の bit) のとき `[[rbp+0x4e0]+4] = value` (書込み)。mode 0x20 と mode 2 はこの bit を持たないので、この書込みは通らない。

## 4. 未解決 (子 #2887 に残す)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 振り分け先 `0x104c2a6`・`0x104c4af`・`0x104c64f`・`0x104c919` (eventId 0x40000000〜2・0x40000005) の lo・hi・cur | eventId 0x40000000〜2・0x40000005 の値源が未確定 | #2887 (PY-103) |
| `0x1047497` 系 (O 項目) の lo・hi・cur と `0x10469f0(value, 0, 0x3200)` の意味 | 通常事象の値源が未確定 | #2887 (PY-103) |
| `0x104aa87` 系 (0x70000000〜0xefffffff) の正規化と値源 | 表経路の値源が未確定 | #2887 (PY-103) |
| `0x104cc72` (H ≥ 件数の経路) と `0x104caae` (振り分け外) の戻り値 | 範囲外・対象外 eventId の挙動が未確定 | #2887 (PY-103) |

## 5. 受入条件 (#2547) への影響

縮小後の受入は 1 項目 (issue #2547 本文・PR 本文と同じ)。

- [x] incEventValue の戻り値の型・範囲外 code を PE 解析箇所つきで REPORT に残す — **満たした**。戻り値の型・範囲外 code・副作用は `REPORT_PY73.md` §7 (main に既存) で確定しており、本付録は `0x1046a30` の振り分け表 (§2) を追加した。

縮小で外した範囲: 元の受入 1 のうち midiNoteOn の副作用は #2926 (PY-110) へ、元の受入 2〜4 (`provider/fl_engine.c`・`host/fl_mock.mjs` の実装、`tests/channels_diff.mjs` への追加、`FL_ENGINE=wasm node tests/all_tools.mjs` 48/48) は #3038 (PY-142) へ移した。本付録では未実施 (コード差分 0)。
