# tools/plugins/f2 REPORT_APPENDIX_2468 — PLG-F3-28 (#2468): 0x5da070 の間接 call 先と停止点の対応 (受入 1 達成。残件は子 #2574 へ。測定 commit 62636cd4、block19148)

- 測定 commit: **62636cd4** (`origin/main` の取り込み merge。main 側の `unicorn_trace.py` 修正 a70461d6 を含む)。本 PR のコード変更は `unicorn_trace.py` が ccb6af73、`fn_refs.py` が a72a9109。`git diff 62636cd4 HEAD -- tools/plugins/f2/*.py` の出力は §6。以降の commit は本ファイルと REPORT_1305.md の文言のみ。
- 既知類型との関係: (DEFECTS.md) 該当なし。NULL this 参照は、合成 host (`-H`) の未初期化グローバルに由来する harness 側の欠落で、lift の miscompile ではない。waiver (`icall_gate_waivers.json`) は変更しない。
- 担当 dir: `tools/plugins/f2/` のみ。入力は `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`)。依存は `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 範囲: unicorn による実行と静的走査のみ。実 FL の host 値は得られないため、host は合成 (`-H`)。

## 0. 結論 (先出し)

1. **受入 1 達成**: `0x5da070` の `call [rax+0x28]` は、this (`rcx`) = 0、vtable (`rax`) = `[0]` = 0 (page 0 の読み)、呼出し先 = `[0x28]` = **0x501319d0** (プール上の文字列データ、非コード)。この `0x28` は NULL this への格納 (`0x412613`) で書かれた値である (§2)。
2. **停止の直接原因を確定**: `0x5da04b` で `[rbp+0x20]` (= 関数 `0x5d9f50` の引数 this) が 0 のまま、`lea rcx,[rax+0x28]` (= 0x28) で `0x4125c0` (文字列代入) を呼び、`0x412613` の `mov [rbx],rsi` が `[0x28]` に書く。page 0 が RW のため黙って通り、後段の vtable 参照が 0 を読んで非コードを呼ぶ。`-z` (page 0 読取専用) で最初の違反は `UC_ERR_WRITE_PROT rip=0x412613` になる (§1・§2)。
3. **this = NULL の根は `[0x8cd068]` (.bss のグローバル) の値 0**。`0x83cbbe` が渡す this は、`0x83cbac` の `mov rax,[rip+0x80c45]` が読む slot `0x8bd7f8` (.data。内容はアドレス `0x8cd068`) の指す先を読んだ値 (§4)。静的に見える経路の範囲で:
   - `0x8cd068` のアドレス値を持つ qword は slot `0x8bd7f8` の 1 件のみ。そこを読む命令は 4 箇所 (`0x83cbac`・`0x83cbe9`・`0x83cbfa`・`0x83cc08`)。4 箇所とも読取りで、続く命令も `[rax]` の読取りのみ (このポインタ経由の書込みは無い)。
   - `0x8cd068` を直接書く rip 相対命令は 2 件: `0x5e01f4` (関数 `0x5e01d0` 内、定数 0 の格納) と `0x5e0483` (関数 `0x5e0340` 内、`rax` の格納)。定数ではない値を格納するのは `0x5e0483` の 1 件。
   - lea・即値・絶対 disp による `0x8cd068` 参照は 0 件。
   - 限界: 動的に計算したポインタ経由の参照は対象外。よって「格納元は 1 件のみ」とは言わない。関数表 `0x852d70`〜`0x852e88` (36 エントリ) の参照元は未特定 (§4)。
4. **受入 3 未達**: `0x83efb0 -H -V -p 0x409090` は `0x411a80` に届かず、停止点は `0x50138d06` (A と同じ)。DllMain (`0x8525f0`) を前処理に置くと `0x411a80` に入るが、これは CreatePlugInstance 経路ではない。`rdx=1` (DLL_PROCESS_ATTACH) を与えたときだけ `0x411bb8`・`0x411940` まで進む (§5)。
5. **受入 4 部分**: DllMain 経路で `0x411bb8` 呼出し時 `[0x8c3c80]`=`0x300ffcb8`、`[[rcx]+0x28]`=0。`0x8c3ca8` は `0x4113f2` で `0x41bf30` (`0x411330` の格納) になり、`0x41196b` (`0x411940` の `rep movsq`) で 0 に上書きされて最終値 0。CreatePlugInstance 経路では未到達 (§5)。
6. **受入 2 部分**: `0x50138cf0` の obj 配置 (`0x40cffa` の 0 埋め、`0x40ed36` の vtable 格納 `0x5baca8`) は書込み元 rip で確定。`0x501319d0` から `0x50138cf0` への中間経路は未追跡 (`-z` では到達しない)。
7. **残件 (受入 2〜5 の原文) は子 issue #2574 (`親: #2468`) に移した**。未解決の一覧は §7。

## 1. 測定 (測定 commit 62636cd4、逐次、1 プロセスずつ)

| 実行 | 結果 | wall |
|---|---|--:|
| A 既定 `-H -V -p 0x409090` | `UC_ERR_INSN_INVALID rip=0x50138d06` | 1.30–1.37 s (n=3) |
| B 同 `-z` | `UC_ERR_WRITE_PROT rip=0x412613` | 1.31–1.39 s (n=3) |
| C A + `-q 0x8cd068` | 前後とも `0x0` | 1.19 s (n=1) |
| D A + `-p 0x8525f0:rdx=1` | `0x411a80` `0x411bb8` `0x411940` に到達。`0x8c3ca8` 最終 0 | 1.21–1.35 s (n=3) |
| E1 A + 関数表 36 エントリの `-t` | **0 hits** | 1.19 s (n=1) |
| E2 D + 関数表 36 エントリの `-t` | **0 hits** | 1.19 s (n=1) |
| J A + `-p 0x5e0340` | `prelude 0x5e0340: UC_ERR_FETCH_PROT rip=0x0` | 1.18 s (n=1) |

- 負荷: 測定前後の `/proc/loadavg` (1 分値) は 0.13 → 0.65。他の並列実行なし。
- 取り込み前 (a72a9109) の同じコマンドでも、A・B・C・D・E・J の状態・停止点・書込み元は同一だった。main の `-V` 修正は本件の経路の結果を変えない。

A の `-t` 出力 (`-t 0x5da05f -t 0x5da06d -t 0x5da070 -t 0x501319d0`、抜粋):

```
trace 0x5da06d #1 rcx=0x0 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x501319d0 [[rcx]+0x28]=0x501319d0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x501319d0
trace 0x5da070 #1 rcx=0x0 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x501319d0 [[rcx]+0x28]=0x501319d0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x501319d0
trace 0x501319d0 #1 ... (非コードの実行開始)
status: UcError Invalid instruction (UC_ERR_INSN_INVALID) rip=0x50138d06 rax=0x0
```

B の `-t` 出力 (`-z -t 0x4125c0 -t 0x412613`、抜粋):

```
trace 0x4125c0 #2 rcx=0x28 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x0 [[rcx]+0x28]=0x0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x0
trace 0x412613 #2 rcx=0x2 rdx=0x501319d0 [rcx]=0x0 [rcx+0x28]=0x0 [[rcx]+0x28]=0x0 rax=0x0 rbp=0x300ffcc0 [rax+0x28]=0x0
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
| 0x28 への書込み元 | `0x412613` (`mov [rbx],rsi`、rbx=0x28) | `-w 0x28:0x30` (`write 0x28 val=0x501319d0 rip=0x412613`) |

`-z` (B) では NULL への書込みが `0x412613` で止まるため、呼出し先 0x501319d0 は実行されない。実プロセスでも同じ箇所で access violation になると判断できる (page 0 は通常プロセスでは未マップ)。

## 3. 受入 2: 0x50138cf0 への到達 (部分)

- 既定 (A) で `0x501319d0` の実行後、制御は `0x50138cf0` を経て `0x50138d06` で停止 (`last executed` の末尾 12 命令)。`0x501319d0` 以降の中間経路 (プール上の非コードの実行中の分岐) は未追跡。
- `0x50138cf0` の内容の書込み元 (`-w 0x50138cf0:0x50138cf8`): `write 0x50138cf0 val=0x0 rip=0x40cffa` (領域の 0 埋め)、`write 0x50138cf0 val=0x5baca8 rip=0x40ed36` (vtable 相当のポインタ格納)。つまり 0x50138cf0 は pool 上で確保・初期化された obj で、その先頭 qword は `0x5baca8`。
- 解釈: 0x50138cf0 への飛び込みは、NULL this 由来の非コード呼出しの連鎖の結果。obj の vtable 書換えが原因ではない (書換え元は obj 自身の初期化 `0x40ed36`)。`-z` で元の書込みが止まるため、これ以上の追跡は優先度が低い。

## 4. this = NULL の根: [0x8cd068] (受入 2 の前段)

- 呼出し (capstone 逆アセンブル、`0x83cbac` 付近):

```
0x83cbac: mov rax, qword ptr [rip + 0x80c45]   ; slot 0x8bd7f8 を読む (内容 = アドレス 0x8cd068)
0x83cbb3: mov rcx, qword ptr [rax]              ; this = [0x8cd068]
0x83cbbe: call 0x5d9f50
0x83cbe9: mov rax, qword ptr [rip + 0x80c08]   ; slot 0x8bd7f8
0x83cbf0: mov rcx, qword ptr [rax]
0x83cbfa: mov rax, qword ptr [rip + 0x80bf7]   ; slot 0x8bd7f8
0x83cc01: mov rax, qword ptr [rax]
0x83cc04: mov r8, qword ptr [rax + 0x30]
0x83cc08: mov rax, qword ptr [rip + 0x80be9]   ; slot 0x8bd7f8
0x83cc0f: mov rax, qword ptr [rax]
0x83cc12: mov r9, qword ptr [rax + 0x28]
```

- 実測 C: `-t 0x83cbbe` で `rcx=0`、`rax=0x8cd068`、`-q 0x8cd068` は前後とも 0。
- slot (`fn_refs.py 0x8cd068 0x8bd7f8`): `0x8cd068` を値として持つ qword は `0x8bd7f8` の 1 件 (PE 全体の検索)。`0x8bd7f8` を読む rip 相対命令は 4 箇所 (上記)。いずれも読取りで、続く命令も `[rax]` の読取りのみ。
- 直接参照 (rip 相対、lea 含む): 20 件 (`slot_write_scan.py` は lea を除いて 20 件、`fn_refs.py` は lea を含めても 20 件)。書込みは 2 件: `0x5e01f4 mov qword ptr [rip+0x2ece69], 0` (関数 `0x5e01d0` 内、0 埋め)、`0x5e0483 mov qword ptr [rip+0x2ecbde], rax` (関数 `0x5e0340` 内、`rax` は `call 0x5d7df0` の戻り値)。`relocs overlapping: 0`。
- 即値・絶対 disp による `0x8cd068` 参照: 0 件 (`fn_refs.py` の `imm-ref`・`abs-ref`)。検出器の正例: 即値 `0x56` で `imm-ref` 197 件。
- 関数表 `0x852d70`〜`0x852e88` (36 エントリ) の参照元は未特定: rip 相対・絶対 disp・即値・rel32 のいずれも 0 件 (`fn_refs.py 0x852d70`)。表の 36 エントリは E1/E2 (§1) で両経路 0 hits。`0x5e0340` の VA は `0x852e30` に格納されている (`fn_refs.py` の qword 格納)。
- `0x5e0340` は `[0x8cd098]` (vtable+0x78 の別 NULL グローバル) も要る: J で `0x5e044d` が `[0x8cd098]` を読み、`0x5e0457` の `call [vtable+0x78]` が 0 を呼ぶ。
- 範囲: 上記の走査は `.text` (線形スイープ、capstone) と PE 全体の qword 検索に限る。動的に計算したポインタ経由の参照は対象外。

## 5. 受入 3・4: 0x411a80 到達 (DllMain 経路) と 0x411bb8 の記録

- DllMain (`0x8525f0`) は PE のエントリポイント (`AddressOfEntryPoint = 0x8525f0`)。reason (`edx`) は `[rbp+0x3c]` を経て `0x41c740` の `r9d` に渡る。
- 既定 (`rdx=host`) の DllMain 前処理: `0x411930` → `0x41c740` → `0x411a80` に入る (`-t` 実測。`0x411a80` は `rcx=0` で入り、戻り値 `rax=1`)。`0x411bb8` は本測定では未確認。
- `-p 0x8525f0:rdx=1` (DLL_PROCESS_ATTACH) の場合: `0x411a80` は `rcx=0xe2`・`rdx=0x298` で入り、戻り値 `rax=0`。このときだけ下記の `0x411bb8`・`0x411940` まで進む。
- 実行 (D): `trace 0x411a80 #1` → `trace 0x411bb8 #1 rcx=0x8c3c80 [rcx]=0x300ffcb8 [rcx+0x28]=0x41bf30 [[rcx]+0x28]=0x0` → `trace 0x411940 #1` (同じ引数)。
- 注意 (m1): `[0x8c3c80]` = `0x300ffcb8` はエミュレートスタック上の値 (`STACK_TOP=0x30100000` の直下)。本節が「obj」と呼ぶ対象はスタック局所で、pool の obj ではない。`[[rcx]+0x28]` = `[0x300ffce0]` も同じスタック局所。
- `0x8c3ca8` の書込み (`-w 0x8c3ca8:0x8c3cb0`): `0x4113f2` で `0x41bf30` (`0x411330` の格納。REPORT_1305.md §9 の `[0x86b188]`)、`0x41196b` で `0` (`0x411940` の `rep movsq` が `[[rcx]+0x28]` = `[0x300ffce0]` = 0 をコピー)。最終 `[0x8c3ca8]=0`。
- `[0x300ffce0]` の書込み (`-p 0x8525f0:rdx=1 -w 0x300ffcb8:0x300ffd00`): `0x411378` で 0 (初期化)、以後 `0x532f0d` で `0x5baca8`、`0x532f28` で `0x50138cf0`。`0x41196b` のコピーは `0x532f*` より前なので、`0x8c3ca8` の最終値は 0。
- 注意: これは DllMain 経路の結果で、受入 3 が指定する `0x83efb0` 経路 (CreatePlugInstance) ではない。`0x83efb0` は DllMain 前処理を入れても停止点 `0x50138d06` で止まる (A と同じ)。

## 6. 検証 (測定 commit 62636cd4)

- 鮮度: `git diff 62636cd4 HEAD -- tools/plugins/f2/*.py` = 出力なし (HEAD は文書のみの commit)。
- 再現 (`T=$RUNNER_TEMP/f2venv/bin/python`、`PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin`、リポジトリ直下で実行):
  - A: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x5da05f -t 0x5da06d -t 0x5da070 -t 0x501319d0 -m 2000000`
  - A の書込み元 (受入 1 の `0x28`): `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -w 0x28:0x30 -m 2000000`
  - B: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -z -t 0x5da05f -t 0x4125c0 -t 0x412613 -m 2000000`
  - C: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x83cbbe -t 0x5d9f50 -q 0x8cd068 -m 2000000`
  - D: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x8525f0:rdx=1 -t 0x411a80 -t 0x411bb8 -t 0x411940 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000`
  - 受入 2 の書込み元: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -w 0x50138cf0:0x50138cf8 -m 2000000`
  - 受入 4 の `[0x300ffce0]` の書込み元: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x8525f0:rdx=1 -w 0x300ffcb8:0x300ffd00 -m 2000000`
  - 関数表 36 エントリ (E1 は既定、E2 は `-p 0x8525f0:rdx=1` を追加): `TL=$($T -c "import pefile,struct,sys;pe=pefile.PE(sys.argv[1],fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase;img=bytes(pe.get_memory_mapped_image());print(' '.join('-t 0x%x'%struct.unpack_from('<Q',img,0x852d70+8*i-base)[0] for i in range(36)))" $PE)` のあと `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 $TL -m 2000000`。出力の `trace` 行は 0
  - `-p 0x5e0340` (J): `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x5e0340 -m 2000000`
  - 静的 (F): `$T tools/plugins/f2/slot_write_scan.py $PE 0x8cd068 0x8cd070` (direct 20 件、W 2 件)
  - 静的 (N): `$T tools/plugins/f2/fn_refs.py $PE 0x8cd068 0x8bd7f8 0x5e0340 0x852d70` (qword 格納・rip-ref・abs-ref・imm-ref)
  - 検出器の正例 (即値): `$T tools/plugins/f2/fn_refs.py $PE 0x56 | grep -c imm-ref` = 197
- ネガティブコントロール: `-z` を外す (A) と `UC_ERR_INSN_INVALID rip=0x50138d06`、付ける (B) と `UC_ERR_WRITE_PROT rip=0x412613` (`-z` の効果)。`-t` の正例は A の `trace 0x5da06d` 行。
- 範囲: 合成 host (`-H`) と合成 VirtualAlloc (`-V`)。実 host 値は得られない。静的検索は `.text` の線形スイープ (capstone) と PE 内 qword 検索で、データ内のコードや動的に計算したポインタは対象外。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[0x8cd068]` を初期化する経路。関数表 `0x852d70`〜`0x852e88` の参照元が未特定 | `0x83efb0` 経路が `0x50138d06` で止まり、受入 3・4 (CreatePlugInstance 側の `0x411a80`・`0x411bb8`) が未達 | #2574 |
| `0x5e0340` は `[0x8cd098]` (vtable+0x78) の別 NULL グローバルも要る | 上の経路を見つけても、その直後に止まる可能性 | #2574 |
| `0x501319d0` → `0x50138cf0` の中間経路 (非コード実行中の分岐) | `-z` で到達しないため優先度は低い。既定の挙動の説明にのみ必要 | #2574 (受入 2 の残り) |
| 空き obj `[obj-8]` への書込み元 (受入 5) | 空きリンクの書込みが未観測 | #2574 |
| DllMain (rdx=1) 経路の `0x8c3ca8` 最終値 0 が、実 host の CreatePlugInstance 経路と同じかは未確認 | 受入 4 の値 (0) の一般性 | #2574 |
| 静的走査の対象外 (動的に計算したポインタ経由の書込み) | 格納元の一覧は静的に見える範囲に限られる | #2574 |
