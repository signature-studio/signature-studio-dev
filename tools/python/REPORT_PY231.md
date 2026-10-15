# PY-231 (#3671): device.forwardMIDICC の -7 (device 無し)・-6 (送出先無し) の判定と送出の記録 (書式は PE 0xd75120 で確定・-7/-6 は仮置き)

親: #2950 (PY-115)。兄弟: #3655 (PY-227・midiOutMsg)。既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型には当たらない。provider の判定順と引数書式の読み違い)。

## 結論

- **受入 1 (PE の確定)**: 書式は `"L|i"` (0xd75254)。kwlist は `message`・`forwardTo`。第 2 引数は解析前に PE が 1 を書くので、省略時の既定は 1 (§1b)。第 1 引数は送る word (そのまま送る)、第 2 引数は送出先テーブルの添字 (forwardTo)。0xfdc8a0 は「添字の値が変わったときだけ」下流へ送る (cmp/je)。**-7・-6 の判定は 0xd75120 では未検証の仮置き** (§1b の注意。判定表 §1 は取り違えた 0xd748e0 = midiOutNewMsg の逆アセンブル。初版の `"ii"` も同じ取り違え。訂正は §1)
- **受入 2 (C・mock)**: -7 → -6 → 送出 (word を記録) の順。midiOutMsg と判定を共有する helper `midi_send` に寄せた。
- **受入 3 (差分 0)**: `node tests/device_diff.mjs` が rc=0 ×3 で PASS、差分 0 (送出 11 件・link 判定 9 通り)。ネガティブコントロール 2 件が FAIL することを確認 (§3)。
- **未解決 (子 issue に起票)**: 値の変化検出のテーブル初期値・添字範囲は未確定 → #4884 (PY-401・#3949 受入 1 の移管先)。-7・-6 の PE 上の裏付け (0xd75120 からの呼出し先) と 1 引数呼出しの送出失敗時の戻り code は未確定 → #4909 (PY-402)。下流の送出先 HMIDIOUT (`[obj+0x7c]`) と無効フラグ (`[obj+0x84]`) の由来 → #3981 (PY-287)。
- 受入 ① (#3950・PY-277・部分達成): 1 引数呼出しは解析成功・既定 1 で送出へ進む。確定した事実と未確定の範囲は §1b。0xd748e0 を forwardMIDICC とした初版の誤記は §1 で訂正済み。
- 測定 commit `aab81902f` (HEAD・コメント訂正のみ): `node tests/device_diff.mjs` n=3 で rc=0 ×3・所要 0.05・0.05・0.06 秒・load (1 分) 0.18・`PASS true` (diffs 0)。差分 `git diff 320633eb5 HEAD -- tools/python/provider tools/python/host tools/python/tests` はコメント 3 行のみ。
- 範囲外: flpy (CPython wasm) 依存の `provider_check`・`midi_bundled_device`・`midi_rpc_split` は未実行 (§3)。`provider_check` は #3804 (PY-255)、他 2 本は #3804 へ範囲追加を依頼 (§4)。

## 1. PE の逆アセンブル (forwardMIDICC ハンドラ 0xd75120 の書式・既定値は §1b で確定。下の -7・-6 判定表は 0xd748e0 = midiOutNewMsg の逆アセンブルで、forwardMIDICC の裏付けではない)

対象: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (fl-win64 26.1.7.5653)。方法は REPORT_PY227 §1 と同じ (pefile + capstone、script は §5)。

**訂正 (#3950・PY-277)**: 本節の初版は `0xd748e0` を forwardMIDICC としていたが誤り。`analysis/flapi/flapi_kwargs.json` で `0xd748e0` は `device.midiOutNewMsg` (書式 `"ii"`・kwlist なし)、`device.forwardMIDICC` は `0xd75120` (書式 `"L|i"`・kwlist `message`・`forwardTo`・required 1・max 2) である。下の表のうち 0xd748e0 の行は midiOutNewMsg の記述として残す。forwardMIDICC の確定は次の §1b。

### 1b. forwardMIDICC (0xd75120) の 1 引数呼出し (#3950・PY-277)

手順: `block00031_PE.bin` を pefile + capstone で逆アセンブル (§5 の script)。書式は 0xd75254 の生バイト `4c 7c 69 00` = `"L|i"`。

| VA | 命令 (抜粋) | 意味 |
|---|---|---|
| 0xd75158 | `mov dword ptr [rbp+0xa4], 1` | 解析の前に第 2 引数 (forwardTo) の出力変数へ **1 を書く**。省略時はこの値のまま |
| 0xd7516a〜0xd75197 | `lea r8,[0xd75254]`・`call [解析]` | `PyArg` 系の解析。第 2 引数は任意 (`"L|i"` の `|`) |
| 0xd7519f | `jle 0xd75202` | 解析失敗 (0 以下) は 0xd75202 へ |
| 0xd751a1〜0xd751f6 | `rcx=obj(rbx)`・`r8=0xd74eb0`・第 1 引数 = [rbp+0xa8]・第 2 引数 = `movsxd [rbp+0xa4]`・`call 0xd843d0` | 呼出し。0xd843d0 は `0xd74eb0` を `[obj+0x58]` にコールバックとして登録する (0xd84424〜0xd84467) |
| 0xd751fb〜0xd75204 | `mov rax,[rbp+0x88]`・`mov ecx,eax`・`call 0xd82c20` | 結果コード (`[rbp+0x88]`) を Python 値に変換する (0xd82c20) |

**1 引数呼出しの結果** (実測した範囲):

- 解析は**成功する** (第 2 引数は任意)。よって 0xd75202 の解析失敗経路には入らない。解析由来の例外は出ない。
- 第 2 引数は既定 **1** (0xd75158 で PE 自身が書く)。PE に「既定値なし」は当たらない。C・mock の既定 1 は PE と一致する。
- 送出の下流は未確定: `0xd74eb0` の `[obj+0x20]` (forwardTo) による分岐、送出失敗時の経路 (0xd750bc → `0x416230`・第 3 引数 3) の戻り値と例外の種類は、本 run では追い切れていない。戻り code の具体値は未確定。

**注意 (未検証)**: §1 の -7・-6 判定 (0xd74918 以降) と §2 の C・mock の -7・-6 は、取り違えた 0xd748e0 (midiOutNewMsg) の逆アセンブルに基づく。forwardMIDICC (0xd75120) の -7・-6 は、0xd75120 からの呼出し先 (0xd843d0・0xd74eb0 ほか) を確認するまで PE で裏付けられていない。`device_diff` の forwardMIDICC の -7・-6 期待値は、この裏付けが無いまま書いた仮置き。

**残る未確定**: 送出の下流 (0xd74eb0 以降) の全経路と、送出失敗時の Python 例外の型・code。`device_diff` が見る link 経路 (-7・-6) とは別で、#3950 の範囲では未確定のまま残す (下流の追跡は #3949 と同じく子に起票する)。

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

この表 (0xd748e0 = midiOutNewMsg) の判定順は **-7 → -6** で、送出より前。forwardMIDICC (0xd75120) の -7・-6 は、この表とは別に確認するまで仮置き (§1b の注意)。

**書式の根拠**: `lea rdx` の指す 0xd74960 の生バイトは `69 69 00` = `"ii\0"`。直後の `"id\0" "message\0" "lastMessage\0" "offset\0"` は、この呼出しでは使われない (解析は kwlist 無しの呼出し形)。解析関数のポインタ (.data の 0x15e1e58) は import 表に無く解決先は未同定だが、呼出し形 (引数・書式・出力ポインタ 2 個) は midiOutMsg と同じ。「両方必須」は PyArg 系の規則に従うという仮定。

**既定値 (訂正)**: 上の表の 0xd748e0 の行は midiOutNewMsg の記述で、forwardMIDICC ではない。forwardMIDICC の既定 1 は PE が 0xd75158 で書いており、C・mock の既定 1 と一致する (§1b)。-7・-6 の判定は 0xd75120 では未検証の仮置きで、この段落は既定値のみを確定とする。

**0xfdc8a0 が送る内容** (値の変化検出):

| VA | 命令 | 意味 |
|---|---|---|
| 0xfdc8a7〜0xfdc8ac | rbx=rcx (sink)・esi=edx (値 = 第 1 引数)・rdi=movsxd r8d (添字 = 第 2 引数) | 引数の取り込み |
| 0xfdc8af〜0xfdc8b3 | cmp esi,[rbx+rdi*4+0x5c]・je 0xfdc8cc | 同じ値なら何もしない |
| 0xfdc8b5〜0xfdc8bc | rax=[rbx+0x4c]・test・je 0xfdc8cc | 出力先が 0 なら何もしない (テーブルも書かない) |
| 0xfdc8be〜0xfdc8c3 | rcx=rax・edx=esi・call 0xba4a20 | 下流へ送出 (値は edx のまま) |
| 0xfdc8c8 | mov [rbx+rdi*4+0x5c],esi | テーブル更新 |

**#3949 (PY-276) での確定**: 0xfdc8a0 の全体を再逆アセンブルした (0xfdc8a0〜0xfdc8d3)。上表の通りで、添字に境界検査は無い。`[sink+0x5c+4*添字]` を書くのは 0xfdc8c8 のみ。`forwardMIDICC` の呼出し元は PE 内の 20 件以上 (例: 0xd74936・0xf90e6c)。`midiOutMsg` (0xd747f0) は 0xfdc8e0 を呼び、こちらは変化検出を通さず毎回送る (0xd748a3)。テーブル (sink+0x5c) の**初期値と長さは未確定**。PE 全 `.text` で `[base+rdi*4+0x5c]` 形の書込みを走査したが、sink を作る関数は同定できなかった (`ea9f20` は別表 (stride 0x45) の書込み)。

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

## 3b. 値の変化検出 (#3949 / PY-276)

- 実装: 0xfdc8a0 の cmp/je に合わせ、`forwardMIDICC` は添字ごとの最後に送った値と同じなら送らない (C `provider/fl_engine.c`・mock `host/fl_mock.mjs` とも)。未設定 (-1) から始まり、添字 0..15 (C の `FCC_N` 仮置き)。範囲外は重複検出せず送る。`midiOutMsg` は変えない (PE 0xfdc8e0 を毎回呼ぶ)。
- 割当判定の順 (review 指摘・PY-276 追補): `forwardMIDICC` は -7 → -6 を判定してから、添字の重複判定 (0xfdc8a0 相当) をする。C では `midi_check` (割当判定) を重複判定の前に呼ぶ。`midi_send` は `midi_check` + `midi_record` の合成。
- 測定 commit (コードを変えた最後の commit): **`20866f567`** (`fix(python): forwardMIDICC の割当判定を重複判定より前に (PY-276, #3949)`)。差分 `git diff 20866f567 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (main 取り込みの merge `bda387094` を含む)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh`、`EMSDK_ENV=$RUNNER_TEMP/toolchain/emsdk/emsdk_env.sh bash tools/python/provider/build.sh`、`node tools/python/tests/device_diff.mjs`。
- 結果 (`bda387094`・n=3・逐次・wall は `/usr/bin/time`): rc=0 ×3、所要 0.04・0.04・0.05 秒、load average (1 分) 0.16。出力: `calls 21・link_calls 9・rejects 13・midi_out 10・diffs 0・PASS true`。送った word 列 (C と mock で一致): `0a643c90, 000000b0, 00643c90, 000000b0, 097f01b2, 7f643c91, 000000b0, 9b412dff, 00643c91, 097f01b2`。
- 期待 word 列は、末尾の `forwardMIDICC(0x0A643C90, 2)` が直前に同じ添字・同じ値で送っているため送らない形に直した (旧 11 件 → 10 件)。
- 負例: mock の重複判定を外すと rc=1・`dedup mock words`・`dedup mock count` で FAIL を確認し、戻して PASS を確認 (`work/` の退避ファイルから複写)。C 側の負例 (review 指摘の差): 旧 C (`6bc77b3ef` の `fl_engine.c`) に戻して再ビルドすると rc=1・`AssertionError: device 差分 2 件` で FAIL (未割当での同値呼出しが C では成功扱いだった)。新 C に戻すと PASS。
- 他の差分検査 `channels_diff`・`note_enum_diff`・`step_item_diff`・`midi_path_diff`・`plugins_diff` は同じ HEAD で rc=0。
- 未実行: `midi_script`・`midi_bundled_device` は `dist/flpy.js` (CPython wasm) が無く `ERR_MODULE_NOT_FOUND` で起動前に落ちる (§3 と同じ範囲外)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| テーブルの初期値 (sink 生成時の `[sink+0x5c..]`)・添字の範囲 (C の FCC_N=16 は仮置き) | 初回の添字 (未設定) の扱いと、範囲外の添字の挙動 (C・mock は範囲外を重複検出せず送る) が PE と一致するかは未確定 | #4884 (PY-401・#3949 受入 1 の移管先) |
| forwardMIDICC (0xd75120) の -7・-6 判定の PE 上の裏付け (0xd843d0・0xd74eb0 ほかの確認) | -7・-6 の判定と期待値は未検証の仮置き | #4909 (PY-402) |
| 1 引数呼出しの送出失敗時の戻り code・例外の種類 (0xd750bc → 0x416230、0xd74eb0 以降の下流) | 解析成功 (既定 1) は確定。送出が失敗する経路の戻り code は未確定。C・mock は 1 引数を既定 1 で受ける | #4909 (PY-402) |
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
