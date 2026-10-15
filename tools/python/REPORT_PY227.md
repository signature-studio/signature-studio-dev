# PY-227 (#3655): device.midiOutMsg の arg4 (word の bit 24–31) と -7・-6 の経路 (PE 0xd747f0 準拠)

親: #2950 (PY-115)。兄弟: #3671 (PY-231・forwardMIDICC の -7・-6)。既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型には当たらない。provider の表の既定値・引数 index の読み違い)。

## 結論

- **受入 1 (arg4 を word へ)**: C・mock は `channel ≥ 0` のとき `(channel & 0xf | message) + data1<<8 + data2<<16 + arg4<<24` を送る。`channel ≤ -1` は message だけを送る。旧 C は arg4 (index 4) を読まず、data1・data2 の既定値を -1 としていた (PE の既定は 0)。両方直した。
- **受入 2 (word 列)**: 送った word を C 側は `fl_engine_midi_word(i)`、mock は `st.midiOut[].word` で出す。`tests/device_diff.mjs` で両者の列が一致し、手計算の期待値 8 件とも一致する。
- **受入 3 (-7・-6)**: device 無し → -7、送出先無し → -6 を、channel によらず送出の前に判定する (PE の順)。両側で code 7・6 を返し、送出件数と word は増えない。
- **受入 4**: `node tests/device_diff.mjs` が差分 0 で PASS (main 取り込み後の HEAD `812614b19` で 3 回実測)。
- 範囲外: forwardMIDICC の -7・-6 (#3671)、`device.isAssigned` の PE 意味論 (#2950)、flpy (CPython wasm) 依存の 3 検査は本 run では未実行 (§4)。

## 1. PE の逆アセンブル (midiOutMsg ハンドラ 0xd747f0)

対象: REFERENCES 正本の `$FL_WIN64_DIR/extracted/block00031_PE.bin` (fl-win64 26.1.7.5653)。`pefile` で ImageBase から RVA を file offset に変換し、`capstone` (x86-64) で逆アセンブルした (script は §5)。

| VA | 命令 (抜粋) | 意味 |
|---|---|---|
| 0xd747f0〜0xd747fa | push・sub rsp,0x60・mov rbx,rdx | 関数の入口。rbx = 引数 |
| 0xd747fd〜0xd74802 | call 0xd77da0・mov rsi,[rax] | self の device 所有 obj を rsi へ |
| 0xd74805〜0xd7481a | [rbp+0x58]=-1・[rbp+0x54]=0・[rbp+0x50]=0・[rbp+0x4c]=0 | 既定値: channel=-1・data1=0・data2=0・arg4=0 |
| 0xd74824〜0xd74855 | 出力先 r8=message・r9=channel・stack=data1/data2/arg4 → call [rax] | PyArg 解析 (書式は issue 記載の `i\|iiii`。書式文字列の読出しは未実施) |
| 0xd7485d | jle 0xd748bc | 解析失敗は戻り値をそのまま返す |
| 0xd7485f〜0xd74866 | rax=[rsi+0x50] (device)・je 0xd748b5 | device が 0 なら **-7** (`mov rax,0xfffffffffffffff9`) |
| 0xd74868〜0xd7486d | cmp [rax+0x7c],0・je 0xd748ac | 送出先 (device+0x7c) が 0 なら **-6** (`0xfffffffffffffffa`) |
| 0xd74873〜0xd74877 | cmp [rbp+0x58],-1・jle 0xd7489d | channel ≤ -1 は word の組立てを飛ばし、message をそのまま送る |
| 0xd74879〜0xd7489a | ecx=((channel&0xf)\|message)+(data1<<8)+(data2<<16)+(arg4<<24) | channel ≥ 0 の word。結果を [rbp+0x5c] へ |
| 0xd7489d〜0xd748a3 | rcx=送出先・edx=[rbp+0x5c]・call 0xfdc8e0 | 送出 (word 1 個) |
| 0xd748a8 | xor eax,eax | 成功 (None) |

読み取り: 判定順は **-7 → -6** で、channel の値によらず送出より前に行う。word の式は issue 記載の式と一致する。-6・-7 の文字列 (`Linked device not assigned`・`Device not assigned`) は `REPORT_PY61.md` の文言一覧 (0xd82c20 の分岐先) と、`fl_api.h` の `FL_E_LINKED_DEVICE = 6`・`FL_E_DEVICE = 7` と一致する。

## 2. 実装

- `provider/fl_engine.c`: `midiOutMsg` を PE の順に書いた。既定 channel=-1・data1/data2/arg4=0。送った word を `midi_words[NMIDI=256]` に記録する (256 件を超えた word は記録せず、件数も増えない)。読出し口 `fl_engine_midi_word_count` / `fl_engine_midi_word(i)` (範囲外 -1) と、検査用の設定口 `fl_engine_set_device_link(dev, link)` (0 で -7 / -6) を足した。`fl_engine_reset` は既定 (両方 1) に戻す。
- `host/fl_mock.mjs`: `st.devAssigned`・`st.linkAssigned` (既定 true) を足し、`device.midiOutMsg` を同じ順で判定する (`FlError` の code 7・6)。送った word を `st.midiOut` の entry の `word` に記録する。
- `host/fl_provider.mjs`: `midiWords()`・`setDeviceLink(dev, link)` を足した。`provider/build.sh` の `EXPORTED_FUNCTIONS` に 3 関数を足した。
- `tests/device_diff.mjs`: (a) 既存 11 呼出しに arg4 入り 3 件を足して戻り値・code を比較、(b) 送出 link の 6 経路 (dev/link を切替え) の code を比較、(c) 送った word の列を mock と wasm で比較し、手計算の期待値 8 件とも照合、(d) 件数比較 (既存)。

## 3. 検証

- 実装 commit: `856af3459` (PY-227 の実装)。main 取り込みの merge commit `812614b19` (コードを変えた最後の commit)。衝突は `provider/build.sh` の `EXPORTED_FUNCTIONS` 1 行だけで、PY-227 の 3 関数と main の `_fl_engine_grid_items_probe` を両方残した。REPORT の追記はこの後の docs commit。
- 差分 (コード 3 ディレクトリ): `git diff 812614b19 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (差分 0)。main 取り込み前の `856af3459` からは 5 ファイル・+115/-13 (main 側の変更 (PY-218 ほか) と衝突解消の `build.sh` 1 行)。
- 再現 (HEAD・素材 `fl-win64`・`toolchain-emsdk`):
  ```
  FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh
  EMSDK_ENV=$RUNNER_TEMP/toolchain/emsdk/emsdk_env.sh bash tools/python/provider/build.sh
  node tools/python/tests/device_diff.mjs    (cd tools/python)
  ```
- 結果 (HEAD `812614b19`・n=3): rc=0 ×3、所要 49〜51 ms (壁時計)、load average (実行前) 0.64 / 0.52 / 0.27。出力: `calls 11・link_calls 6・rejects 4・midi_out 10・link_codes ["ok",7,6,6,7,"ok"]・diffs 0・PASS true`。
- 同じ HEAD で、取り込んだ main 側の変更が通る他の検査も実行した: `channels_diff` (PASS・calls 214・grid_calls 1200・grid_true 30・grid_diffs 0)、`note_enum_diff` (PASS・calls 33264・nonempty 5869)、`step_item_diff` (PASS・calls 5929)、`midi_path_diff` (PASS・cases 30・lit_steps 160)。`midi_rpc_split` は rc=1 (`dist/flpy.js` が無く起動できない・§4)。
- 送った word 列 (hex・C と mock で一致): `00643c90, 000000b0, 097f01b2, 7f643c91, 000000b0, 9b412dff, 00643c91, 097f01b2`。期待値は式の手計算 (例: `0x90|1 + 60<<8 + 100<<16 + 127<<24 = 0x7f643c91`)。

ネガティブコントロール (1 件を壊して FAIL を確認し、戻して PASS を確認。表は `856af3459` で実施。main 取り込み後の HEAD `812614b19` では mock の arg4 shift を 24 → 16 にした 1 件だけ再実行し、rc=1 (`device 差分 1 件`)・戻して `diffs 0・PASS true`):

| 壊した箇所 | 結果 (rc) | 検出した差分 |
|---|---|---|
| mock: arg4 の shift を 24 → 16 (`host/fl_mock.mjs`) | rc=1 | 1 件 (word 列: mock ≠ wasm) |
| C: arg4 の shift を 24 → 16 (`provider/fl_engine.c`、再ビルド) | rc=1 | 2 件 (word 列: mock ≠ wasm、expect ≠ wasm) |
| mock: -6 の判定を削除 (`host/fl_mock.mjs`) | rc=1 | 4 件 (link 経路 2 件・送出件数 1 件・word 列 1 件) |

いずれも元へ戻して `git status` が空であることを確認し、PASS に戻ることを確認した。

検証範囲: 検査は C provider (wasm) と JS mock の 2 本の比較と、手計算の期待値。PE の意味論は §1 の逆アセンブルに依る (書式文字列と `isAssigned` は未読)。範囲外は §4。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| forwardMIDICC の -7・-6 と送出 (PE 0xd748e0 に同じ判定がある) | forwardMIDICC は device 無し・送出先無しでも成功を返す | #3671 (PY-231) |
| `device.isAssigned` の PE 意味論 | mock・C は常に true で、-7 の状態 (devAssigned) と独立。本体は未逆アセンブル | #2950 |
| 32bit 外の整数の扱い | C は int64 の下位 32bit、mock は ToInt32 で切る。PE の 'i' 変換の範囲外 (OverflowError 相当) は未確認 | #2950 |
| 引数名 (kwlist 無し) | 名前は message・channel・data1・data2・arg4 のまま (stub 由来) | #2952 (PY-116) |
| `provider_check.mjs`・`midi_script.mjs`・`midi_bundled_device.mjs`・`midi_rpc_split.mjs` 未実行 | `dist/flpy.js` (CPython wasm) が無く起動できない (`midi_rpc_split` は ERR_MODULE_NOT_FOUND)。本 run は flpy を build していない | #2950 (親の受入の `provider_check` を含む) |

`DEFECTS.md` の行案: 旧 C の既定値 (data1・data2 = -1) と arg4 の読み捨ては provider の表の誤りで、lift の類型ではない。行案は作らない (PM 判断)。

## 5. 逆アセンブル script (再現用・repo 外に置いた)

```python
import sys, pefile, capstone
pe_path = sys.argv[1]; start = int(sys.argv[2], 16); n = int(sys.argv[3])
pe = pefile.PE(pe_path, fast_load=True)
off = pe.get_offset_from_rva(start - pe.OPTIONAL_HEADER.ImageBase)
data = open(pe_path, "rb").read()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for ins in md.disasm(data[off:off + n], start):
    print(f"{ins.address:x}: {ins.mnemonic} {ins.op_str}")
```
実行: `python3 disasm_pe.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" d747f0 400` (`capstone`・`pefile` が要る。`~/.local/agent-py` の venv にある)。
