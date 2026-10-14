# PY-113 (#2943): playlist.setTrackColor の格納 byte 順を逆アセンブルで確定し、getTrackColor との食い違いを解消する

親: #2809。前段: `tools/python/REPORT_PY61.md` (getTrackColor の取得式は確定済み)・#2885 (PY-62、未 merge)。既知類型との関係: 該当なし (lift 作業ではない。C provider の格納式の不一致)。

## 結論

- **格納式 (playlist)**: `setTrackColor(i, v)` は v の R と B を入替え、`0xffffff` で切って `track+0x2c` へ格納する。`0x123456` は `0x00563412` として格納される (根拠 VA は §2)。
- **取得式 (playlist)**: `getTrackColor(i)` は `+0x2c` の値の R と B を入替え、`0xff000000` を立てて返す (PY-61 §2-1 の確定と一致)。
- **食い違いの原因**: C provider の `FL_H(playlist, setTrackColor)` が値を素通し (`p->color = A_INT(1,0)`) で格納していた。FL の格納式と違うため、取得式 (R/B 入替え) を通すと `setTrackColor(3, 0x123456)` の後に `0xff563412` が返った (§4)。
- **修正**: C 側の setter を FL の格納式に合わせた。mock の setter も同じ式にした (`provider/fl_engine.c`・`host/fl_mock.mjs`)。取得式は変えていない (main には C の `getTrackColor` が無く、#2885 のブランチにある実装は FL と一致する)。
- **未達 (分割)**: 受入条件 3 (`tests/playlist_diff.mjs` の暫定期待値の置換と C/mock の diff 0 の実測) は、#2885 (未 merge) のブランチにしか無いため、子 **#2949 (PY-114)** に移した。mixer 側は格納先が未確定のため、子 **#2951 (PY-115)** に移した。

## 1. 測定

- 素材: `fl-win64`。`mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64`。実測 real 5.661 s (user 4.582 s / sys 5.698 s)。
- 解析: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/settrackcolor_facts.py`。実測 real 0.114 s (user 0.101 s / sys 0.015 s)、n=1。実行直後の `uptime` の load average は `0.12 0.16 0.09` (並列 1)。出力は 4 項目 PASS・末尾 2 件の算法一致 (§5)。
- 対象: `extracted/block00031_PE.bin`。逆アセンブルは `analysis/flapi/pe_disasm.py` と同じ capstone 方式。
- PyMethodDef の配列の位置: `pymethoddef_scan.py` が出す `start` は**ファイル offset** (VA ではない)。playlist 配列は offset `0x1114ac8` (42 行)、mixer 配列は `0x1116ea8` (72 行)。
- 測定 commit (コードを最後に変えた commit): `ce1aae29` (`fix(python): store playlist track color in FL byte order (PY-113)`)。この REPORT を含む後続の commit は、コードの範囲 (`provider`・`host`) に差分が無いことを §6 で示す。

## 2. 逆アセンブルの事実 (playlist)

| 対象 | VA | 根拠 (逆アセンブル) |
|---|---|---|
| setTrackColor の wrapper | 0xd56040 | PyMethodDef 配列の行 4 (fn)。引数 index を `[rbp+0x9c]`、value を `[rbp+0x98]` に受ける |
| wrapper → コア | 0xd560a8〜0xd560f3 | `lea r8,[rip-0x17f]` = 0xd55f30。`call 0xd843d0` (dispatch) へ、index を `[rsp+0x20]`、value を `[rsp+0x28]` で渡す |
| コア (setter 本体) | 0xd55f30 | 0xd55f6d で guard (`[rax+0x98]` の vtable 呼出し)。0xd55f8f で `1 <= index <= 0x1f4` (範囲外は 0xd55ff5 で -4) |
| R/B 入替え | 0xd55fba〜0xd55fe0 | `and edx,0xff00ff`・`and eax,0xff00ff00`・`shl r10d,0x10`・`shr edx,0x10`・`add`・`or eax,0xff000000` |
| 格納 (経由) | 0xd55fee → 0x12e60b0 → 0x12e5d80 | `call 0x12e60b0` (rcx=track 配列, edx=index, r8=elem, r9d=色) → 0x12e60f9 `call 0x12e5d80` |
| 格納先 | 0x12e5d80 (0x12e5d8c・0x12e5d9b) | `and eax,0xffffff` の後 `mov dword ptr [rbx+rcx*4+0x2c],eax` (rcx = index×0x45 = 要素 0x114 B) |
| getTrackColor | 0xd55ea0 | 0xd55ee6 `mov eax,[rax+rcx*4+0x2c]` → R/B 入替え (0xd55eec〜0xd55efe) → 0xd55f03 `or eax,0xff000000` |

- 格納式: `stored = swap_RB(v) & 0xffffff`、`swap_RB(v) = ((v&0xff)<<16) | (v&0xff00) | ((v>>16)&0xff)`。alpha は格納されない。
- 取得式: `get(u) = swap_RB(u) | 0xff000000`。
- 往復: `get(set(v)) = 0xff000000 | v` (v が `0xRRGGBB` の範囲)。

## 3. 格納式の検算 (別算法)

| 入力 v | ビット算法 (`settrackcolor_facts.py` の `store_fl`) | バイト列の並べ替え (`store_bytes`) | 取得式 (`get`) |
|---|---|---|---|
| 0x123456 | 0x563412 | 0x563412 | 0xff123456 |
| 0xABCDEF | 0xefcdab | 0xefcdab | 0xffabcdef |

- `FL_WIN64_DIR=... python3 tools/python/analysis/flapi/settrackcolor_facts.py`: `PASS` 4 件 (wrapper VA の一致・コアの R/B 入替え・格納先の `and eax,0xffffff` と `[+0x2c]`・取得式の `[+0x2c]` と `or eax,0xff000000`)。末尾の 2 算法の一致は `assert`。

## 4. 食い違いの原因

- 修正前 (`p->color = A_INT(1,0)`) では、`setTrackColor(3, 0x123456)` で `+0x2c` に `0x00123456` が入る。取得式 (FL と同じ R/B 入替え) を通すと `0xff563412` になる。
- 再現 (負例・修正前の格納式を取得式に通す): `node -e` で `g(0x123456) = 0xff563412`。issue の観測値と一致する。
- 修正後: 格納は `0x00563412`。取得式を通すと `0xff123456` (期待どおり)。

## 5. 変更と検証

- 変更: `provider/fl_engine.c` の `FL_H(playlist, setTrackColor)` を格納式に合わせた (`ce1aae29`)。`host/fl_mock.mjs` の `playlist.setTrackColor` も同じ式にした。取得式・mixer 側は変えていない。
- 検証 1 (C の文法): `gcc -fsyntax-only -Wall -Wextra -I provider -I provider/gen provider/fl_engine.c` → rc 0。
- 検証 2 (mock の格納値を state から読む、`node`): `0x123456` → stored `0x563412` (getter `0xff123456`) PASS、`0xABCDEF` → `0xefcdab` PASS、`0xFF0000FF` → `0xff0000` (getter `0xff0000ff`) PASS。
- 検証 3 (逆アセ): §3 の `settrackcolor_facts.py` が 4 PASS・算法一致。
- **未実測**: `provider/build.sh` (emcc) と `node tests/channels_diff.mjs` (C と mock の差分 0)。このランナーに emsdk (`provider/build.sh` の `EMSDK_ENV` の既定先) が無く、`toolchain-emsdk` は本 run の `oc_artifacts` に無いため、wasm を作れなかった。`channels_diff.mjs` の playlist 部分は戻り値だけを比べ、setTrackColor は戻り値 `None` のため、格納式の変更で差分は出ない見込み (推定。実測していない)。→ 子 #2949。

## 6. 差分の確認

- `git diff ce1aae29 HEAD -- tools/python/provider tools/python/host` (この REPORT の commit 時点): 空 (コードの範囲に差分 0)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `tests/playlist_diff.mjs` (#2885 のブランチ) の暫定期待値 `0xff563412` の置換と、C/mock の diff 0 の実測 (emsdk) | 受入条件 3。#2885 の期待値が誤ったまま | #2949 (PY-114)。#2885 の merge 後に着手 |
| `mixer.setTrackColor` の格納先 (`0x12c17a0` の書込み先・mask) と `mixer.getTrackColor` (0xd5ec60) の取得式。C の mixer setter は素通しのまま | mixer 側の往復が C で食い違う可能性 (未実測) | #2951 (PY-115) |
