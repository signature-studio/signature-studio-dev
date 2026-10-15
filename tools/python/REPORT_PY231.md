# PY-231 (#3671): device.forwardMIDICC の -7 (device 無し)・-6 (送出先無し) の判定と送出の記録 (PE 0xd748e0)

親: #2950 (PY-115)。兄弟: #3655 (PY-227・midiOutMsg)。既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型には当たらない。provider の判定順と引数書式の読み違い)。

## 結論

- **受入 1 (PE の確定)**: 書式は `"ii"` (0xd74960。PyArg 規則上は両方必須・解析関数は未同定)。解析前に出力変数を初期化していないので、呼出し側に既定値は無い。第 1 引数は送る word (そのまま送る)、第 2 引数は送出先テーブルの添字 (forwardTo)。0xfdc8a0 は「添字の値が変わったときだけ」下流へ送る (cmp/je)。
- **受入 2 (C・mock)**: -7 → -6 → 送出 (word を記録) の順。midiOutMsg と判定を共有する helper `midi_send` に寄せた。
- **受入 3 (差分 0)**: `node tests/device_diff.mjs` が rc=0 ×3 で PASS、差分 0 (送出 11 件・link 判定 9 通り)。ネガティブコントロール 2 件が FAIL することを確認 (§3)。
- **未解決 (子 issue に起票)**: 値の変化検出 (0xfdc8a0 の cmp/je・テーブル初期値・添字範囲) は未実装 → #3949 (PY-276)。第 2 引数の既定値 1 (stub 由来) は PE と食い違う → #3950 (PY-277)。下流の送出先 HMIDIOUT (`[obj+0x7c]`) と無効フラグ (`[obj+0x84]`) の由来 → #3981 (PY-287)。
- 範囲外: flpy (CPython wasm) 依存の `provider_check`・`midi_bundled_device`・`midi_rpc_split` は未実行 (§3)。`provider_check` は #3804 (PY-255)、他 2 本は #3804 へ範囲追加を依頼 (§4)。

## 1. PE の逆アセンブル (forwardMIDICC ハンドラ 0xd748e0)

対象: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (fl-win64 26.1.7.5653)。方法は REPORT_PY227 §1 と同じ (pefile + capstone、script は §5)。

| VA | 命令 (抜粋) | 意味 |
|---|---|---|
| 0xd748e0〜0xd748ea | push・sub rsp,0x30・mov rbp,rsp・mov rbx,rdx | 入口。rbx = 引数 tuple |
| 0xd748ed〜0xd748f2 | call 0xd77da0・mov rsi,[rax] | self の device 所有 obj を rsi へ (midiOutMsg と同じ) |
| 0xd748f8〜0xd74903 | lea rdx,[rip+0x61] (= 0xd74960)・r8=&[rbp+0x28]・r9=&[rbp+0x2c] | 書式 `"ii"`。出力は 2 個 |
| 0xd7490e〜0xd74916 | call [0x15e1e58] → test・jle 0xd7494f | 解析。失敗 (0) は 0xd7494f へ |
| 0xd74918〜0xd7491f | rax=[rsi+0x50] (device)・je 0xd74948 | device が 0 なら **-7** (0xd74948: `0xfffffffffffffff9`) |
| 0xd74921〜0xd74926 | cmp [rax+0x7c],0・je 0xd7493f | 送出先 (device+0x7c) が 0 なら **-6** (0xd7493f: `…fa`) |
| 0xd74928〜0xd74936 | rcx=[device+0x7c]・edx=[rbp+0x28] (第 1 引数)・r8d=[rbp+0x2c] (第 2 引数)・call 0xfdc8a0 | 送出 |
| 0xd7493b | xor eax,eax | 成功 |
| 0xd7494f〜0xd74951 | mov ecx,eax・call 0xd82c20 | 戻り値の変換 (-7 → FL_E_DEVICE 7、-6 → FL_E_LINKED_DEVICE 6。REPORT_PY227 §1) |

判定順は **-7 → -6** で、送出より前。midiOutMsg (0xd747f0) と違い、word を組み立てずに第 1 引数をそのまま送る。

**書式の根拠**: `lea rdx` の指す 0xd74960 の生バイトは `69 69 00` = `"ii\0"`。直後の `"id\0" "message\0" "lastMessage\0" "offset\0"` は、この呼出しでは使われない (解析は kwlist 無しの呼出し形)。解析関数のポインタ (.data の 0x15e1e58) は import 表に無く解決先は未同定だが、呼出し形 (引数・書式・出力ポインタ 2 個) は midiOutMsg と同じ。「両方必須」は PyArg 系の規則に従うという仮定。

**既定値**: 解析の前に `[rbp+0x28]`・`[rbp+0x2c]` を初期化していない。PyArg 規則上 `"ii"` は両方必須 (上記の仮定) なので、呼出し側に既定値は無い。C・mock の既定 1 は stub 由来 (REPORT_PY15・REPORT_APPENDIX の kwlist 表で、stub の `mode` に対しバイナリは `forwardTo`) で、PE と食い違う (#3950)。

**0xfdc8a0 が送る内容** (値の変化検出):

| VA | 命令 | 意味 |
|---|---|---|
| 0xfdc8a7〜0xfdc8ac | rbx=rcx (sink)・esi=edx (値 = 第 1 引数)・rdi=movsxd r8d (添字 = 第 2 引数) | 引数の取り込み |
| 0xfdc8af〜0xfdc8b3 | cmp esi,[rbx+rdi*4+0x5c]・je 0xfdc8cc | 同じ値なら何もしない |
| 0xfdc8b5〜0xfdc8bc | rax=[rbx+0x4c]・test・je 0xfdc8cc | 出力先が 0 なら何もしない (テーブルも書かない) |
| 0xfdc8be〜0xfdc8c3 | rcx=rax・edx=esi・call 0xba4a20 | 下流へ送出 (値は edx のまま) |
| 0xfdc8c8 | mov [rbx+rdi*4+0x5c],esi | テーブル更新 |

**0xba4a20 → 0x663430 (送出の下流)**: 本 PR で再逆アセンブルした (§5 の script・`block00031_PE.bin`):

```
ba4a20: sub rsp,0x28
ba4a24: cmp byte ptr [rcx+0x84],0
ba4a2b: jne 0xba4a36        ; [obj+0x84] != 0 なら送出しない
ba4a2d: mov rcx,qword ptr [rcx+0x7c]
ba4a31: call 0x663430
663430: jmp qword ptr [rip+0x130e89a]   ; IAT = 0x1971cd0 = winmm!midiOutShortMsg
```

0x663430 は `midiOutShortMsg` の thunk で、根拠は `tools/m11/shimx_link/REPORT_APPENDIX_2839.md` §2 (同じ IAT VA・測定 commit `97908347`)。つまり送出は `midiOutShortMsg(hmo = [obj+0x7c], dwMsg = 値)` で、C・mock が記録する word がそのまま dwMsg になる。`[obj+0x7c]` の由来と `[obj+0x84]` の既定値は未確定 (#3981)。添字 (第 2 引数) に境界検査は無い。テーブル長と初期値は未確定 (#3949)。

## 2. 実装

- `provider/fl_engine.c`: 判定と記録を `static int midi_send(fl_call *c, uint32_t w)` に寄せた (-7 → -6 → 記録)。midiOutMsg は word を組み立てて `midi_send`。forwardMIDICC は第 1 引数を word として `midi_send` (第 2 引数は読むだけ・既定 1 は残す)。
- `host/fl_mock.mjs`: forwardMIDICC に -7 (`FlError` code 7)・-6 (code 6) を入れた。送出記録 `{api, message, mode}` は従来どおり (`midi_bundled_device.mjs` の期待値を変えない)。
- `tests/device_diff.mjs`: forwardMIDICC の link 経路 3 件 (ok・-7・-6) を足し、送った word の列を midiOutMsg と forwardMIDICC の呼出し順 (11 件) で期待値 (手計算) と照合。

## 3. 検証

- 測定 commit (コードを変えた最後の commit): **`df4692fcb`** (`feat(python): forwardMIDICC の -7・-6 判定と送出の記録 (PY-231, #3671)`)。本 REPORT の commit はコード 3 ディレクトリの外。
- 差分 (コード 3 ディレクトリ): `git diff df4692fcb HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (差分 0)。
- 素材: `fl-win64` (`extracted/block00031_PE.bin` 22227016 B)・`toolchain-emsdk` を `$RUNNER_TEMP` に展開。
- 再現 (HEAD `df4692fcb`):
  ```
  FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh
  EMSDK_ENV=$RUNNER_TEMP/toolchain/emsdk/emsdk_env.sh bash tools/python/provider/build.sh
  node tools/python/tests/device_diff.mjs    (cd tools/python)
  ```
- 結果 (n=3・逐次。`/usr/bin/time` の壁時計): rc=0 ×3、所要 0.05 / 0.05 / 0.06 秒、load average (1/5/15 分) 0.80・0.45・0.20。出力 (3 回とも同じ): `calls 11・link_calls 9・rejects 4・midi_out 11・link_codes ["ok",7,6,6,7,"ok","ok",7,6]・diffs 0・PASS true`。
- 送った word 列 (hex・C と mock で一致): `0a643c90, 000000b0, 00643c90, 000000b0, 097f01b2, 7f643c91, 000000b0, 9b412dff, 00643c91, 097f01b2, 0a643c90` (期待値は式の手計算。例: `0x90|(60<<8)|(100<<16)|(10<<24) = 0x0a643c90`)。
- 同じ HEAD で他の差分検査も実行: `channels_diff`・`note_enum_diff`・`step_item_diff`・`midi_path_diff`・`plugins_diff` は rc=0。
- **ネガティブコントロール** (1 件ずつ壊して FAIL を確認し、戻して PASS を確認。戻しは退避ファイルからの複写):

| 壊した箇所 | 結果 (rc) | 検出 |
|---|---|---|
| mock: forwardMIDICC の -6 判定を削除 (`host/fl_mock.mjs`) | rc=1 | `device 差分 3 件` |
| C: forwardMIDICC の -6 判定を削除 (`provider/fl_engine.c`・再ビルド) | rc=1 | `device 差分 5 件` (link codes・word 期待値ほか) |

- **未実行**: `provider_check.mjs`・`midi_bundled_device.mjs`・`midi_rpc_split.mjs` は `dist/flpy.js` (CPython wasm) が要り、本 run では build していない (`provider_check` は `ERR_MODULE_NOT_FOUND` で起動前に落ちる)。REPORT_PY227 §3 と同じ範囲外。
- 検証範囲: C provider (wasm) と JS mock の比較と手計算の期待値。PE の意味は §1 の逆アセンブルに依る。-7 側の単独の控えは未実施 (-6 と同じ判定順の helper を共有するため、C と mock の双方で -7 の経路は device_diff の link 3 件に含まれる)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値の変化検出 (0xfdc8a0 の cmp/je)・テーブル初期値・添字の範囲 | 同じ値・同じ添字の連続 forwardMIDICC を、C・mock は毎回送出として数える (PE は送らない) | #3949 (PY-276) |
| 第 2 引数の既定値 1 (stub 由来)・1 引数呼出し | PE の `"ii"` は両方必須。C・mock は 1 引数を既定 1 で受ける。解析失敗の観測 (例外・戻り code) は未確定 | #3950 (PY-277) |
| 送出先 HMIDIOUT (`[obj+0x7c]`)・無効フラグ (`[obj+0x84]`) の由来 (下流は winmm `midiOutShortMsg`・§1) | 送出先 port を C・mock の送出記録は持たない (どの MIDI 出力かは未確定) | #3981 (PY-287) |
| `provider_check` (flpy 未 build) | 同梱 script の forwardMIDICC 経路を flpy 経由で未確認 | #3804 (PY-255) |
| `midi_bundled_device`・`midi_rpc_split` (flpy 未 build) | #3804 の本文 (`provider_check`・`all_tools`) の範囲外。同梱 script の forwardMIDICC 経路を flpy 経由で未確認 | #3804 (範囲追加をコメントで依頼) |

`DEFECTS.md` の行案: なし (provider の判定順と既定値の読み違いで、lift の類型ではない)。

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
実行: `python3 disasm_pe.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" d748e0 420` (書式は同じ pefile で VA 0xd74960 の生バイトを読んだ)。
