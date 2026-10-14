# 付録: icall #2083 (ICALL-58) — crash 残り 3 件の原因切り分け

> 親: #2009 (ICALL-55)。前付録: `REPORT_APPENDIX_2009.md` §4。

## 1. 結論

- 受入条件 1〜3 は満たした (3 関数とも、cookie 系以外を含めて切り分けて REPORT に記録。原因が確定しないものは切り分け結果を残す、の規定に従う)。
- `0x1803b3fc0`・`0x1803b5b60`: **原因を特定**。未実装 import `KERNEL32!RtlPcToFileHeader` (import 表の index 64) の thunk から `missing_import` に入り、その捕捉関数の `movaps` で SIGSEGV (`addr=nil`)。thunk の `call` で stack が 16 バイト境界からずれるため。捕捉関数だけ `force_align_arg_pointer` で整列させると `MISSING IMPORT RtlPcToFileHeader — fail-fast` に変わり、名前も確定した。
- `0x1803b9ff0`: **切り分け結果を記録** (原因は未確定)。image 内 (`rip=0x1803ba718`) で `rcx=0xa0001440` を書き先に使って SIGSEGV する。`rcx` は呼出側が渡した不正ポインタ。呼出元 (8 箇所) のどれが不正値を渡すかは未確認 (§5 の未解決)。

測定: 基点 `6a88bf35` (origin/main)。`tools/ott/native/` は未変更。`tools/ott/work/libottnative.so` は probe 版で一時的に差し替えて確認し、元の `.so` に戻した (`cmp` で一致確認済み)。追加したのは切り分け用スクリプト `tools/icall/diff/fa_import_names.py` のみ。

## 2. 実測 (`fa_cmp.py <VA> --n 8`、`OTT_NOASLR` 既定)

| VA | 素の `libottnative.so` | probe (`missing_import` を `force_align_arg_pointer`) | 備考 |
|---|---|---|---|
| `0x1803b3fc0` | `SIGSEGV addr=(nil) rip=0x7ffff7002918` (`missing_import` の `movaps`) | `MISSING IMPORT RtlPcToFileHeader — fail-fast` | rcx=0x40 (idx 64) |
| `0x1803b5b60` | `SIGSEGV addr=(nil) rip=0x7ffff7002918` (同上) | `MISSING IMPORT RtlPcToFileHeader — fail-fast` | rcx=0x40 (idx 64) |
| `0x1803b9ff0` | `SIGSEGV addr=0xa0001440 rip=0x1803ba718` (image 内) | 変化なし (同じ SIGSEGV) | rcx=0xa0001440 |

## 3. 解析の根拠

- `0x1803b3fc0`: 先頭で `call 0x1803b3d10` (vtable と構造体を書くだけの初期化)、続けて `call 0x18102f728` (`int3` で終端する C++ 後始末) を呼ぶ。`0x18102f728` 以降の IAT 呼び出しが thunk に入る。
- `0x1803b5b60`: 同型 (IAT call は 38 命令内に無い)。
- thunk (`ott_native.c` の `make_thunk`) は `mov ecx, idx; mov rax, missing_import; call rax` の 3 命令。`missing_import` は `movaps` (16 バイト整列を要求) を使うが、thunk の `call` で stack が整列されず落ちる。
- `g_impname[idx]` の名前は `ott_load` の import 表 (`IMPL` に無い名前を登録) から引く。idx 64 は `KERNEL32!RtlPcToFileHeader` (`tools/icall/diff/fa_import_names.py` が PE の import 表から復元。commit 済みで、§4 の期待出力を持つ)。
- 注: 最初の probe は `missing_import` から `MS` (ms_abi) を外したため引数 idx が読めず `?` と出た。`MS` を保って再実行すると上記の名前が出た。
- `0x1803b9ff0`: `rcx` と `rdx` を stack に退避して `push` 群へ進む。`rip=0x1803ba718` は `mov %eax,(%rcx)` で、`rcx=0xa0001440` が書き先。

## 4. 再現

```
bash tools/ott/native/build.sh
python3 tools/icall/diff/fa_cmp.py 1803b3fc0 --n 8   # SIGSEGV (addr=nil)
python3 tools/icall/diff/fa_cmp.py 1803b5b60 --n 8   # SIGSEGV (addr=nil)
python3 tools/icall/diff/fa_cmp.py 1803b9ff0 --n 8   # SIGSEGV (addr=0xa0001440)
python3 tools/icall/diff/fa_import_names.py          # 期待: implemented 28 missing 226 / idx 64 = KERNEL32 の RtlPcToFileHeader
```

素材: `work-icall` (`tools/icall/work/`)・`plugins-freshair` (`fetch.sh` 後の `tools/targets/freshair/work/win/`)。`fa_import_names.py` は `plugins-freshair` の `SlateCore.core_64` だけを読む (素材が無いと `FileNotFoundError` で止まる)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `missing_import` の thunk stack 整列 (`movaps` の SIGSEGV を fail-fast に変える)。`KERNEL32!RtlPcToFileHeader` の実装は別件 | `0x1803b3fc0`・`0x1803b5b60` の SIGSEGV (`addr=nil`) を fail-fast に置き換える (native 参照の不具合。wasm 側の結果ではない)。修正は `tools/ott/native/ott_native.c` (本 PR の範囲外) | 未起票 (PM 判断。ICALL 系の既存 issue があれば紐付け) |
| `0x1803b9ff0` の `rcx=0xa0001440` を渡す呼出元 (`0x1803ba64f` 等 8 箇所) の特定 | `0x1803b9ff0` の原因 | 未起票 (原因特定は本受入条件の必須ではない: 切り分け結果 = 入力と落ちる命令まで記録済み) |
