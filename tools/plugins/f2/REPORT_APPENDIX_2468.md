# tools/plugins/f2 REPORT_APPENDIX_2468 — PLG-F3-28 (#2468): 0x5da070 の間接 call 先と停止点の対応 (部分、測定 commit ccb6af73、block19148)

- 測定 commit: **ccb6af73** (`unicorn_trace.py` の変更の最終 commit)。以降の commit は本ファイルと REPORT_1305.md の文言のみ。
- 既知類型との関係: (DEFECTS.md) 該当なし。NULL this 参照は、合成 host (`-H`) の未初期化グローバルに由来する harness 側の欠落で、lift の miscompile ではない。waiver (`icall_gate_waivers.json`) は変更しない。
- 担当 dir: `tools/plugins/f2/` のみ。入力は `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`)。依存は `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 範囲: unicorn による実行と静的走査のみ。実 FL の host 値は得られないため、host は合成 (`-H`)。

## 0. 結論 (先出し)

1. **受入 1 達成**: `0x5da070` の `call [rax+0x28]` は、this (`rcx`) = 0、vtable (`rax`) = `[0]` = 0 (page 0 の読み)、呼出し先 = `[0x28]` = **0x501319d0** (プール上の文字列データ、非コード)。この `0x28` は NULL this への格納で書かれた値である (§2)。
2. **停止の直接原因を確定**: `0x5da04b` で `[rbp+0x20]` (= 関数 `0x5d9f50` の引数 this) が 0 のまま、`lea rcx,[rax+0x28]` (= 0x28) で `0x4125c0` (文字列代入) を呼び、`0x412613` の `mov [rbx],rsi` が `[0x28]` に書く。page 0 が RW のため黙って通り、後段の vtable 参照が 0 を読んで非コードを呼ぶ。`-z` (page 0 読取専用) で最初の違反は `UC_ERR_WRITE_PROT rip=0x412613` になる (§2・§3)。
3. **根の this = NULL は `[0x8cd068]` (.bss のグローバル) が 0 のため**。`0x83cbac` が読む。PE 内の格納元は `0x5e0483` (関数 `0x5e0340` の中) の 1 件のみ。ただし `0x5e0340` を含む関数表 (`0x852d70`〜`0x852e88`) の参照元は CreatePlugInstance 経路にも DllMain 経路にも現れず、初期化経路は未特定 (§4)。
4. **受入 3 未達**: `0x83efb0 -H -V -p 0x409090` は `0x411a80` に届かず、`0x5da070` で止まる。DllMain (`0x8525f0`) を前処理に置くと `0x41c740` → `0x411a80` に入るが、これは CreatePlugInstance 経路ではない。`rdx=1` (DLL_PROCESS_ATTACH) を与えたときだけ `0x411bb8`・`0x411940` まで進む (§5)。
5. **受入 4 部分**: DllMain 経路で `0x411bb8` 呼出し時 `[0x8c3c80]`=`0x300ffcb8`、`[[rcx]+0x28]`=0、`[0x8c3ca8]` は呼出し前 `0x41bf30` (`0x4113f2`)、呼出し中の `0x41196b` で 0 に上書きされ、最終値 0 (§5)。CreatePlugInstance 経路では未到達。
6. **受入 2 部分**: 0x50138cf0 の obj 配置 (`0x40cffa` の 0 埋め、`0x40ed36` の vtable 格納 `0x5baca8`) は書込み元 rip で確定。ただし `0x501319d0` から `0x50138cf0` への中間経路は未追跡 (`-z` では到達しない)。

## 1. 測定 (測定 commit ccb6af73、逐次、load 0.16–0.31)

| 実行 | 結果 | wall |
|---|---|--:|
| A 既定 `-H -V -p 0x409090` | `UC_ERR_INSN_INVALID rip=0x50138d06` (§16 と一致) | 1.45 s |
| B 同 `-z` | `UC_ERR_WRITE_PROT rip=0x412613` | 1.39 s |
| C `-q 0x8cd068` | 前後とも `0x0` | — |
| D `-p 0x8525f0:rdx=1` を追加 | `0x411a80` `0x411bb8` `0x411940` に到達。`0x8c3ca8` 最終 0 | 1.43 s |
| E 関数表 36 エントリ (`0x852d70`〜`0x852e88`) の `-t` | 両経路で **0 hits** | — |

A の `-t` 出力 (抜粋、`-t 0x5da05f -t 0x5da06d -t 0x5da070 -t 0x501319d0`):

```
trace 0x5da06d #1 rcx=0x0 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x501319d0 [[rcx]+0x28]=0x501319d0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x501319d0
trace 0x5da070 #1 rcx=0x0 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x501319d0 [[rcx]+0x28]=0x501319d0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x501319d0
trace 0x501319d0 #1 ... (非コードの実行開始)
status: UcError Invalid instruction (UC_ERR_INSN_INVALID) rip=0x50138d06 rax=0x0
```

B の `-t` 出力 (`-t 0x4125c0 -t 0x412613`):

```
trace 0x4125c0 #2 rcx=0x28 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x0 ... rbp=0x300ffcc0
trace 0x412613 #2 rcx=0x2 rdx=0x501319d0 ...
status: UcError Write to write-protected memory (UC_ERR_WRITE_PROT) rip=0x412613 rax=0x0
```

## 2. 受入 1: 0x5da070 の呼出しと this・vtable の対応 (実測)

逆アセンブル (capstone) の該当部分:

```
0x5da04b: mov rax,[rbp+0x20]        ; this (関数 0x5d9f50 の引数。0x5d9f5b で [rbp+0x20] に保存)
0x5da04f: lea rcx,[rax+0x28]        ; rcx = 0x28 (this=NULL のとき)
0x5da053: mov rdx,[rbp+0xa0]        ; 文字列バッファ (0x501319d0)
0x5da05a: call 0x4125c0             ; 文字列代入。0x412613 で [rbx]=[0x28] に rsi を書く
0x5da05f: mov rax,[rbp+0x20]
0x5da063: mov rax,[rax+0x358]       ; this = [[rbp+0x20]+0x358] = [0+0x358] = 0
0x5da06a: mov rcx,rax
0x5da06d: mov rax,[rax]             ; vtable = [0] = 0 (page 0 は TLS 用に RW マップ済み)
0x5da070: call [rax+0x28]           ; 呼出し先 = [0x28] = 0x501319d0 (非コード)
```

| 項目 | 値 | 根拠 |
|---|---|---|
| `[rbp+0x20]` (this of 0x5d9f50) | 0 | `-t 0x5da05f` の rax (= 0) |
| this (`rcx` at 0x5da06d) | 0 | `-t 0x5da06d` |
| vtable (`rax` = `[this]`) | 0 | `-t 0x5da070` の rax |
| 呼出し先 (`[vtable+0x28]` = `[0x28]`) | 0x501319d0 | `-t 0x5da070` の `[rax+0x28]` |
| 0x28 への書込み元 | `0x412613` (`mov [rbx],rsi`、rbx=0x28) | `watch` (`write 0x28 val=0x501319d0 rip=0x412613`) |

`-z` (B) では NULL への書込みが `0x412613` で止まるため、呼出し先 0x501319d0 は実行されない。実プロセスでも同じ箇所で access violation になると判断できる (page 0 は通常プロセスでは未マップ)。

## 3. 受入 2: 0x50138cf0 への到達 (部分)

- 既定 (A) で `0x501319d0` の実行後、制御は `0x50138cf0` を経て `0x50138d06` で停止 (`last executed` の末尾 12 命令)。`-t 0x50138cf0` の `trace #1` は `0x501319d0` 実行後に出る。中間経路 (プール上の非コードの実行中の分岐) は未追跡。
- `0x50138cf0` の内容の書込み元 (A の watch): `write 0x50138cf0 val=0x0 rip=0x40cffa` (領域の 0 埋め)、`write 0x50138cf0 val=0x5baca8 rip=0x40ed36` (vtable 相当のポインタ格納)。つまり 0x50138cf0 は pool 上で確保・初期化された obj で、その先頭 qword は `0x5baca8`。
- 解釈: 0x50138cf0 への飛び込みは、NULL this 由来の非コード呼出しの連鎖の結果。obj の vtable 書換えが原因ではない (書換え元は obj 自身の初期化 `0x40ed36`)。`-z` で元の書込みが止まるため、これ以上の追跡は優先度が低い。

## 4. this = NULL の根: [0x8cd068] (受入 2 の前段、部分)

- 呼出し: `0x83cbac: mov rax,[rip+0x80c45]` (= `0x8cd068` の address) → `0x83cbb3: mov rcx,[rax]` → `0x83cbbe: call 0x5d9f50`。実測 `-t 0x83cbbe`: `rcx=0`、`rax=0x8cd068`、`[0x8cd068]=0` (`-q`)。
- PE 内の `0x8cd068` への直接アクセス (`slot_write_scan.py`、rip/abs 直接、lea を除く、測定 commit ccb6af73): 20 件。書込みは **2 件**のみ: `0x5e01f4 W mov qword ptr [rip+0x2ece69], 0` (0 埋め) と `0x5e0483 W mov qword ptr [rip+0x2ecbde], rax` (`rax` は `call 0x5d7df0` の戻り値)。`relocs overlapping: 0`。
- `0x5e0483` は pdata 関数 `0x5e0340` の中 (`0x5e0340` は静的ローカルの初期化 guard `sub dword [..],1; cmp dword [..],-1` を持つ)。`0x5e0340` の VA は `0x852e30` に格納されている (`fn_refs.py`)。
- `-p 0x409090 -p 0x5e0340` は `UC_ERR_FETCH_PROT rip=0` で止まる。`0x5e044d` が `[0x8cd098]` (別の NULL グローバル) を読み、`0x5e0457` の `call [vtable+0x78]` が 0 を呼ぶため。`0x5e0340` の初期化には `0x8cd098` のオブジェクトも要る。
- `0x852d70`〜`0x852e88` (36 エントリ、`0x5e0340` を含む表) は `.text` 内にあり、rip 相対・絶対 disp・即値のいずれでも参照する箇所が `.text` 全体で 0 件 (走査を実施)。表の走査元は未特定。
- E: 36 エントリのいずれも、CreatePlugInstance 経路・DllMain 経路のどちらでも実行されない (0 hits)。よって、この表の走査は両経路に含まれない。

## 5. 受入 3・4: 0x411a80 到達 (DllMain 経路) と 0x411bb8 の記録

- DllMain (`0x8525f0`) は PE のエントリポイント (`AddressOfEntryPoint = 0x8525f0`)。reason (`edx`) は `[rbp+0x3c]` を経て `0x41c740` の `r9d` に渡る。
- 既定 (`rdx=host`) の DllMain 前処理: `0x411930` → `0x41c740` → `0x411a80` に入る (`-t` 実測。`0x411a80` は `rcx=0` で入り、戻り値 `rax=1`)。`0x411bb8` は本測定では未確認。
- `-p 0x8525f0:rdx=1` (DLL_PROCESS_ATTACH) の場合: `0x411a80` は `rcx=0xe2`・`rdx=0x298` で入り、戻り値 `rax=0`。このときだけ下記の `0x411bb8`・`0x411940` まで進む。
- 実行 (D): `trace 0x411a80 #1` → `trace 0x411bb8 #1 rcx=0x8c3c80 [rcx]=0x300ffcb8 [rcx+0x28]=0x41bf30 [[rcx]+0x28]=0x0` → `trace 0x411940 #1` (同じ引数)。
- `0x8c3ca8` の書込み (`-w 0x8c3ca8:0x8c3cb0`): `0x4113f2` で `0x41bf30` (`0x411330` の格納。§9 の `[0x86b188]`)、`0x41196b` で `0` (`0x411940` の `rep movsq` が `[[rcx]+0x28]` = `[0x300ffce0]` = 0 をコピー)。最終 `[0x8c3ca8]=0`。
- `[0x300ffce0]` の書込み順 (`-w 0x300ffcb8:0x300ffd00`): `0x411378` で 0 (初期化)、以後 `0x532f0d` で `0x5baca8`、`0x532f28` で `0x50138cf0`。0x411940 のコピー (`0x41196b`) は `0x532f*` より前なので、`0x8c3ca8` の最終値は 0。
- 注意: これは DllMain 経路の結果で、受入 3 が指定する `0x83efb0` 経路 (CreatePlugInstance) ではない。`0x83efb0` は DllMain 前処理を入れても `0x5da070` で止まる (A と同じ)。

## 6. 検証 (測定 commit ccb6af73 の鮮度)

- `git diff ccb6af73 HEAD -- tools/plugins/f2/*.py` = 出力なし (本 appendix 追加の commit は `.md` のみ)。
- 再現 (ccb6af73、`PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin`、`T=$RUNNER_TEMP/f2venv/bin/python`):
  - A: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x5da05f -t 0x5da06d -t 0x5da070 -t 0x501319d0 -m 2000000`
  - B: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -z -t 0x5da05f -t 0x4125c0 -t 0x412613 -m 2000000`
  - C: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x83cbbe -t 0x5d9f50 -q 0x8cd068 -m 2000000`
  - D: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x8525f0:rdx=1 -t 0x411a80 -t 0x411bb8 -t 0x411940 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000`
  - F: `$T tools/plugins/f2/slot_write_scan.py $PE 0x8cd068 0x8cd070`
  - 静的確認: `$T tools/plugins/f2/fn_refs.py $PE 0x5e0340 0x852e30` (`0x5e0340` は `0x852e30` に格納)。
- ネガティブコントロール: `-z` を外す (A) と `UC_ERR_INSN_INVALID` に戻る (`-z` の効果を示す)。`0x8cd068` の書込みは 2 件 (rip 直接参照の走査で 0 件ではない = 検出器は動いている)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[0x8cd068]` (CreatePlugInstance の this) を埋める初期化経路。`0x5e0340` の呼出し元 (`0x852d70`〜`0x852e88` の表の走査元) が未特定 (.text 内の rip/abs 参照 0 件、36 エントリは両経路で未実行) | `0x83efb0` 経路が `0x5da070` で止まり、受入 3・4 (`0x411a80`・`0x411bb8` の CreatePlugInstance 側) が未達 | #2468 (本 issue。次 run で継続) |
| `0x5e0340` は `[0x8cd098]` (vtable+0x78) の別 NULL グローバルも要る | 上の経路を見つけても、その直後に止まる可能性 | #2468 |
| `0x501319d0` → `0x50138cf0` の中間経路 (非コード実行中の分岐) | `-z` で到達しないため優先度は低い。既定の挙動の説明にのみ必要 | #2468 (受入 2 の残り) |
| DllMain (rdx=1) 経路の `0x8c3ca8` 最終値 0 が、実 host の CreatePlugInstance 経路と同じかは未確認 | 受入 4 の値 (0) の一般性 | #2468 |
| waiver (`icall_gate_waivers.json`) は変更しない | — | #529 |
