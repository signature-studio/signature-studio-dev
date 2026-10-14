# PY-115 (#2951): mixer.setTrackColor の格納先と mixer.getTrackColor の取得式を逆アセンブルで確定し C/mock を合わせる

親: #2943 (PY-113 の子)。前段: `tools/python/REPORT_PY113.md` (playlist 側の格納式。`ce1aae29` は `2943-playlist-settrackcolor-byteorder` にあり main 未 merge)・`tools/python/REPORT_PY61.md` (playlist の取得式)。既知類型との関係: 該当なし (lift 作業ではない。C provider の格納式の不一致)。

## 結論

- **格納 (mixer)**: `setTrackColor(i, v)` は v の R と B を入替え、alpha を `0xff` に固定した `swap_rb(v) | 0xff000000` を、track 要素 (`base + i*0x1478`) の **+0x4 (dword)** へ格納し、**+0x0 (byte) のフラグを 1** にする。`0xffffff` での切り捨ては無い (issue の「alpha 保持」の仮説は外れ、alpha は入力によらず `0xff`)。
- **取得 (mixer)**: フラグが立っていれば `swap_rb(+0x4) | 0xff000000` を返す。往復は `setTrackColor(1, 0x123456)` → `getTrackColor(1)` = `0xff123456` (playlist 側と同じ期待値)。
- **未確定 (フラグが立っていない track)**: 戻り値は既定色 (グローバル参照先の実行時値) に依存し、静的には確定できない。C と mock は仮置き `0x5A6B7C` (旧 mock の初期値)。→ 未解決の表 (§7)。
- **修正**: C の `FL_H(mixer, setTrackColor)` を格納式に合わせ、`FL_H(mixer, getTrackColor)` を追加した。mock も同じ式にした (`provider/fl_engine.c`・`host/fl_mock.mjs`)。

## 1. 測定

- 素材: `mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64`。real 6.078 s (user 3.958 s / sys 7.781 s)。`toolchain-emsdk` は `$RUNNER_TEMP/opt` に展開 real 3.917 s。
- 解析: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/mixer_settrackcolor_facts.py`。real 0.120 s (user 0.086 s / sys 0.030 s)、n=1。実行直前の load average `0.28 0.41 0.22`。
- build (emsdk): `EMSDK_ENV=$RUNNER_TEMP/opt/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`。rc 0。`fl_table.c: 435 関数, ハンドラ 80`。real 0.906 s (sysroot のライブラリはキャッシュ済み。初回は real 14.555 s で、そのうち約 13 s は sysroot の生成)。load `0.36 0.44 0.23`。
- mixer 差分: `node tests/mixer_diff.mjs` → `{"calls":56,"diffs":0,"PASS":true}`、real 0.058 s。
- channels 差分 (playlist 側の回帰なし): `node tests/channels_diff.mjs` → `{"calls":122,"diffs":0,"PASS":true}`、real 0.053 s。
- provider 集合検査: `node tests/provider_check.mjs` の §1〜§2b (実装集合 80 / 未実装 355、エラー code) は PASS、real 0.089 s。§3 以降は `dist/flpy.js` と `work/midi.py` (CPython wasm 側の生成物) が無いため**未実行** (§7)。
- 測定 commit (コードを最後に変えた commit): `2893e78b` (`fix(python): store mixer track color in FL byte order and add getTrackColor (PY-115)`)。

## 2. 逆アセンブルの事実 (mixer)

| 対象 | VA | 根拠 (逆アセンブル) |
|---|---|---|
| PyMethodDef 配列 (mixer) | ファイル offset `0x1116ea8` (72 行) | `setTrackColor` の fn = `0xd5edd0`、`getTrackColor` の fn = `0xd5ec60` |
| setter wrapper | `0xd5edd0` | index を `[rbp+0x9c]`、value を `[rbp+0x98]` で受け、dispatch `0xd843d0` の前に `lea r8,[rip-0x11f]` で core `0xd5ed20` を渡す |
| setter コア | `0xd5ed20` | `0xd5ed76`〜`0xd5eda8`: value の R/B 入替え (`and ecx,0xff00ff`・`shl r8d,0x10`・`shr ecx,0x10`) の後に `or eax,0xff000000` |
| 要素の算出 | `0xd5ed6e`〜`0xd5ed90` | `index*0x28f*8` (= 要素 stride `0x1478`)。配列の先頭は `[0x15e06a0]` (pointer)、件数は `[0x15e2198]` (dword) |
| 格納 | `0x12c17a0` | `cmp byte [rcx],0`・`cmp edx,[rcx+4]`・sentinel `0x716c63` → `mov [rcx],al` (**+0 フラグ**)・`mov [rcx+4],edx` (**+4 値**)。その後 `call 0x12c1920` (edx=2) |
| getter | `0xd5ec60` | index は `0 <= i <= [0x15e2198]-1` (外は RANGE 側)。`imul rcx,rcx,0x28f` → `call 0x12c18f0`。戻り値を R/B 入替え (`and ecx,0xff00ff`・`and esi,0xff00ff00`) して `or esi,0xff000000` |
| 取得の核 | `0x12c18f0` | `cmp byte [rcx],0`。フラグ立ち: `mov eax,[rcx+4]` を返す。フラグ無し: `[0x15e3858]` の pointer 先の dword を R/B 入替えて返す (既定色) |

- 格納式: `stored = swap_rb(v) | 0xff000000`、`swap_rb(v) = ((v&0xff)<<16) | (v&0xff00) | ((v>>16)&0xff)`。
- 取得式 (フラグ立ち): `get(u) = swap_rb(u) | 0xff000000`。フラグ無し: `get = swap_rb(swap_rb(G)) | 0xff000000 = G | 0xff000000` (G = 既定色、§4)。
- sentinel `0x716c63`: 値が sentinel なら フラグを 0 に戻す経路がある。格納値は必ず `0xff` の alpha を持つため、この経路は到達しない。

## 3. 格納式と取得式の検算

| 入力 v | 格納値 (`+0x4`) | 取得 (`get`) | 判定 |
|---|---|---|---|
| 0x123456 | 0xff563412 | 0xff123456 | PASS (`set→get` の期待値) |
| 0xABCDEF | 0xffefcdab | 0xffabcdef | PASS |

- `analysis/flapi/mixer_settrackcolor_facts.py`: PASS 6 件 (PyMethodDef の VA、コアの R/B 入替え・要素算出・`call 0x12c17a0`、格納の +0/+4、取得の `call 0x12c18f0`・R/B 入替え、`0x12c18f0` のフラグ経路) と、検算 2 件の `assert`。
- playlist (`REPORT_PY113.md` §2) と同じ R/B 入替えだが、mixer は alpha 固定とフラグ付きの格納である点が違う。

## 4. 既定経路 (フラグ無し) の未確定

- `0x12c18fa` の `mov rax,[rip+0x321f57]` は VA `0x15e3858` (.data) の pointer を読む。その file 値は `0x15f6774` で、これは `.bss` (file 内に実体無し)。つまり既定色の実体は FL の実行時に決まり、静的には確定できない。
- C と mock の仮置き `MIX_DEFAULT_COLOR = 0x5A6B7C` (旧 mock の初期値を流用)。未設定 track の `getTrackColor` は `0xff5a6b7c` を返す。実機の既定値とは一致する保証が無い。

## 5. 変更と検証

- `provider/fl_engine.c`: `Mix` に `color_set` を追加。`setTrackColor` を格納式に、`getTrackColor` を追加。初期化の `color = 0x5A6B7C` を外し (既定経路は `MIX_DEFAULT_COLOR`)。
- `host/fl_mock.mjs`: `swapRb` と同じ式で `setTrackColor`・`getTrackColor` を実装。mixer の初期 `color` を 0・`colorSet: false` に。
- `tests/mixer_diff.mjs`: `getTrackColor` を 7 件 (往復 3 組・既定・範囲外 2 件) 追加。`setTrackColor(1,0x123456)` → `getTrackColor(1) === 0xff123456` を mock と wasm の両方で assert。ヘッダの関数数を 19 件・未定義 56 件に更新。
- `tests/provider_check.mjs`: 実装集合に `pe115` (`mixer.getTrackColor`) を追加。実装 79→80、未実装 356→355。
- playlist 側 (`ce1aae29`・`#2943` ブランチ) には触れていない。本 PR は main 基準で、mixer の行だけを変更する (playlist の setter 行とは重ならない)。

## 6. 差分の確認

- `git diff 2893e78b HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis`: 本 REPORT を commit した後も、コードの範囲の差分は 0 (下の確認は PR 作成時に実行)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| フラグ無し track の既定色 G (`0x15e3858` → `.bss`) の実行時の値 | 未設定 track の `getTrackColor` は仮置き `0xff5a6b7c`。実機と食い違う可能性 | #2975 (PY-118)。`親: #2951` |
| `provider_check.mjs` の §3 以降 (flpy 経由の戻り型・例外写像) | Python 経由の `mixer.getTrackColor` の型は未検査 (`dist/flpy.js`・`work/midi.py` が無い) | 起票しない (再測定のみ)。全体 e2e (`tools/python/run_all.sh`) で確認 |
| playlist 側の setter の検証 (`ce1aae29` の main 未 merge) | 本 PR と独立 (依存しない)。playlist 側の `tests/playlist_diff.mjs` は #2885 の未 merge | #2949 (PY-114) |
