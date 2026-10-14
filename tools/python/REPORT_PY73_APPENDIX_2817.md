# PY-73 付録 (#2817 / PY-93): `0x11d1430` のゲート参照鎖・T の書込み元・vptr・vtable 先

親: `tools/python/REPORT_PY73.md` §8-4 (要点)。本文の行数上限 (250 行) のため分割。
前段: `tools/python/REPORT_PY73.md` §2・§8-3。対象: midiNoteOn の状態ゲート述語 `0x11d1430` と本体 `0x10002a0`。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (`block00031_PE.bin` のみ。実測 2.3 秒)。
- 逆アセンブル: `analysis/flapi/pe_disasm.py`。参照列挙: `analysis/flapi/pe_xref.py 141d6b8,141d6c0` (hits 9・stores 3・48.3 秒)、`pe_xref.py 125b1c0,125b0f8` (hits 2・stores 0・48.3 秒。hits は全て `0x125b0f8` の load)。
- 書込み候補の列挙: `analysis/flapi/pe_slot_writers.py 15e4790 8` (命令 5,022,467・スロット読出し 2422・`[reg+8]` 書込み 3347・候補 20・49.4 秒)。
- 測定 commit: `9e3f9edc` (`pe_slot_writers.py` の走査修正。コードを変えた最後の commit)。走査修正は境界をまたぐ命令の読み飛ばしを直すもので、修正前 (`b5adbf47`) と数値は同一 (命令 5,022,467・候補 20)。上の 3 測定は HEAD `f295c8bc` で再現した値。以後の commit は REPORT と DOC_MAP のみ。差分 0 の証跡は PR 本文に添付 (`git diff 9e3f9edc HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests`)。
- 検証範囲: PE の逆アセンブルと参照列挙のみ。wasm・mock・C provider の実行は未実行 (コード差分 0)。

## 1. `0x11d1430` の参照鎖 (確定)

| 段 | 命令 (VA) | 内容 |
|---|---|---|
| 1 | `mov rax,[rip+0x413355]` (0x11d1434) | G3 = `0x15e4790` の内容 = `0x141d6b8` (ファイル上の静的値) |
| 2 | `mov rax,[rax]` (0x11d143b) | スロット S0 = `[0x141d6b8]`。ファイル上は 0。実行時に Q が入る |
| 3 | `mov rax,[rax+8]` (0x11d143e) | this T = `[Q+8]` |
| 4 | `mov rax,[rax]` (0x11d1445) | T の vptr |
| 5 | `call [rax+0x88]` (0x11d1448) | 呼出し先 = §5 で確定 (`0x1262a90`)。0x11d1460 は同形で `+0x90` |

## 2. Q (S0 の中身) の生成と破棄 (確定)

- 0x976a90: `cmp [S0],0` (0x976a95)。0 なら `call 0x976b60(rcx=[0x976410], dl=1)` の戻り (Q) を `[S0]` へ格納 (0x976aad)。続けて `[S1=0x141d6c0]` (関数ポインタ) が非 0 のとき、それを呼んで 0 に戻し、`Q+0x40` の `vtbl[0]` を呼ぶ (0x976ab4-0x976ae0)。
- 0x976b60: `dl≠0` のとき `Q = 0x410320([0x976410], 1)` で生成。`[Q+8]=0` を設定 (0x976b9c)。この関数内で `[Q+8]` は再設定されない。
- 0x976af0: 破棄。`Q+0x40` のメソッド (`vtbl[+8]`) を呼び、`[S0]=0` の後 `0x40faa0(Q)`。

## 3. T = `[Q+8]` の書込み元 (候補列挙で検出)

| 書込み (VA) | 関数 | 内容 |
|---|---|---|
| 0x1264145 | 0x1264100 | `if [Q+8]==0 { [Q+8] = 0x125da90([0x125b0f8], dl=1) }` (0x976a90・0x1264cb0 を先に呼ぶ) |
| 0x1263571 | 0x1263540 | カウンタを 1 減らした後の値が -1 のとき、`0x976a90` → `0x125da90([0x125b0f8], dl=1)` → `[Q+8]=rax` |

候補 20 件は、G3 読出し直後 0x40 バイト以内の `[reg+8]` 書込みを列挙したもので、この範囲で検出した。うち Q+8 ではない候補 (除外):
- 0xeef1c2 (`[[Q+0x8c]+8]`)・0xedffd2 (`[[Q+0x8c]+8]`。0xedff9f〜0xedffd2 で G3→S0→Q を辿り、`[Q+0x8c]` の先に書く。0xeef1c2 と同系統)
- 0x11c44e5 (`[[Q+0x20]+0x2c]`。0x11c44ae〜0x11c44e5 で `rax = [Q+0x20]+0x24` の後に `[rax+8]` へ書く)
- 0x11c7aec (`[rip+0x41bb43]` の別グローバルへの書込み)
- 0x1312884 (rbx は別経路の引数)
- dword 書込み 13 件 (0xd3baf0・0xdaa45f・0x10a0454〜0x10a09f6 の 8 件・0x11488e8・0x1195c83・0x1316f6d)。T は qword のポインタなので dword 書込みは T の代入ではないと判断した。個別の確認はしていない。

## 4. T の生成と vptr (確定)

- 0x125da90 は rcx = V = `[0x125b0f8]` = `0x125b1c0` を受ける (両呼出しで同じ)。0x125b0f8 は .text 内の 8 バイトで、参照は load 2 件のみ (store 0)。
- `dl≠0` で `O = 0x410320(V, 1)` を呼び、`[rbp+0x4220]` に保持。0x125e76e の `ret` 直前で `rax = [rbp+0x4220] = O` を返す (他の ret 経路は未確認)。
- 0x410320: `mov rax,rcx; test dl,dl; jl; mov rcx,rax; call [rax-0x30]`。`[V-0x30]` = `0x40f960` (V の表の -6 番目)。
- 0x40f960(rcx=V): `rbx=V`。`movsxd rcx,[V-0x80]` (dword) を `0x409410` に渡して確保し、`0x40fb40(V, 確保領域)` を呼ぶ。戻り rax を返す。
- 0x40fb40(rcx=V, rdx=mem): `rdi=V`、`rsi=mem`。`0x40d210` 呼出し (未読) の後、**`mov [rsi], rdi` (0x40fb66) で確保領域の先頭に V を書く**。戻り rax = rsi。
- よって **T の vptr = V = `0x125b1c0`** (確定)。V の表は .text 内にあり、0x125b1c0 を lea/mov で参照する命令は 0 件 (表は `[global]` の値として渡される)。

## 5. vtable 先 (確定)

- `[T.vptr+0x88]` = `[0x125b1c0+0x88]` = **`0x1262a90`** (表の 18 番目。ファイル上の値)。
- `[T.vptr+0x48]` = `0x1262950` (表の 10 番目)。

## 6. ゲート関数 `0x1262a90` (確定。本体 17 命令)

```
push rbx; sub rsp,0x20
mov rax,[0x15e04a8]; cmp byte [rax],0; jne ret0      ; flagA = byte[0x16baff0] (.bss)
mov rax,[0x15e0ff0]; cmp byte [rax],0; jne ret0      ; flagB = byte[0x16baff1] (.bss)
rcx=T; rbx=[T]; call [rbx+0x48]                       ; = 0x1262950: movzx eax, byte [*0x15e1890]
test al,al; je ret1                                   ; flagC = byte[0x13e7628] (.data)
ret0: xor eax,eax / ret1: mov al,1
```

- 0x1262a90 は、flagA = flagB = 0 かつ `T.vt[+0x48](T) == 0` のとき 1、それ以外は 0 を返す。
- midiNoteOn (0x11d1430 の呼出し後 `test al,al; je -2`) では、**`byte[0x16baff0] ≠ 0` または `byte[0x16baff1] ≠ 0` または `byte[0x13e7628] ≠ 0` のとき内部 code -2**。
- ファイル上の初期値: slot `0x15e04a8` = `0x16baff0`、slot `0x15e0ff0` = `0x16baff1`、slot `0x15e1890` = `0x13e7628`。`0x13e7628` の初期値は 0。`0x16baff0`・`0x16baff1` は .bss (ファイル外、初期値 0 相当)。

## 7. 未確定 (起票先 #2926)

| 未確定 | 根拠 | 影響 |
|---|---|---|
| 実行時の `byte[0x16baff0]`・`byte[0x16baff1]` (flagA・flagB) の値と書込み元 | .bss。書込みはポインタ経由の可能性があり pe_xref では見えない | -2 ゲートの値が決まらない |
| 実行時の `byte[0x13e7628]` (flagC) の値と書込み元 | ファイル上 0。書込みは未探索 | 同上 |
| 0x40f960・0x40fb40 の未読部分 (0x409410・0x40d210・0x40fac0 の本体) | 本 run は vptr の代入位置のみ確認 | T の初期状態 |
| 0x125da90 の他の ret 経路 | 0x125e76e 以外は未確認 | 別オブジェクトを返す経路の有無 |
| 0x1264100 の呼出し元 | 未確認 | T の遅延生成の時点 |
| midiNoteOn 本体 `0x10002a0` (note bit 31・velocity 符号・channel) と `0x63a730` の副作用 | 未着手 | midiNoteOn の副作用が決まらない |

## 8. 受入条件 (#2817) の判定

- [ ] `0x11d1430` の vtable 先を解決し、-2 ゲートの条件を REPORT に残す — **部分達成**。vtable 先 `0x1262a90` (§5)・ゲート条件 (§6) を確定。条件の値 (flagA・flagB・flagC の実行時値) は未確定 (§7) → #2926。
- [ ] `0x10002a0` の note-on 経路と `0x63a730` の副作用を PE 解析箇所つきで残す — **未達** (未着手) → #2926。
- [ ] 推測の状態モデルでは実装しない — **達成**。provider・mock は未実装 (0 件)。
