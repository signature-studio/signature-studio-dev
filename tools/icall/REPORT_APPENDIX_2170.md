# 付録: icall #2170 (ICALL-61) — fatal RIP の採取と encoded slot 表の参照範囲

> 親: #2148 (ICALL-60)。前付録: `REPORT_APPENDIX_2148.md`。本 run は受入条件の一部 (fatal RIP を採れるハーネス化と、
> 読出し元 table の静的参照範囲の確認) まで。表の終点・entry 数、47 件の原因切り分け、OTT api-set 表との比較は子 issue へ移管 (§4)。

## 1. 結論

- 受入条件 1 (表の開始 VA・終了 VA・entry 数の確定): **未達**。table の起点 2 本 (`0x181307100`・`0x1813071a0`) は静的参照から確認したが、終点と entry 数は未確定。
- 受入条件 2 (既知 12 slot が表に含まれるか): **未達**。既知 12 の読出しは 3 件のまま。
- 受入条件 3 (残り 46 件の fatal RIP の切り分け): **部分達成**。fatal RIP を採取できるようにし、RIP を群ごとに数えた。原因の確定は未達。
- 受入条件 4 (OTT api-set 表 `0x18026c9f0` との形式比較): **未達**。
- #2148 の前提の訂正は再確認した: `0x1810806a0` で落ちたのは rc=95 の 53 件中 7 件だけ。

## 2. 実測

### 2.1 ハーネス修正

`slot_trace.sh` は子プロセスの stderr を `/dev/null` に捨てていたため、fatal 行 (`[slot_trace] fatal sig= rip= addr=`) が採れなかった。
stderr を `work/slot_trace_err.txt` に、fatal 行を `work/slot_trace_fatal.txt` (先頭に関数 VA が付く) に保存するよう変えた。
集計 (`slot_trace_enc.txt`) の形式は変えていない。

- 測定 commit: `fe6f0acc` (変更は `tools/icall/diff/slot_trace.sh` のみ)。
- 再現条件: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (closure 131 関数・1 関数 1 プロセス)。
- 所要 12.1 s (real) / user 10.8 s / sys 1.2 s。load average 0.54 (開始時, 09:49)。
- 結果: funcs 131 / exit rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 / zero-fill VA 7 個 / 既知 12 中 hit 3・miss 9。
  #2148 のベースライン (rc=95: 53, VA 7, 3/12) と一致した。

### 2.2 読出し元 table の静的参照

`SlateCore.core_64` の section (pefile): `.data` = VA `0x18125c000`・VirtualSize `0xae000`・raw `0x33400`。
zero-fill は raw 末尾 `0x18128f400` から始まる。`.pdata` は `0x18130a000` から。

ディスパッチャ `0x18105de80` (`objdump -d -M intel` で確認) の参照は次の 2 本。

| table | 起点 VA | 参照形 | 備考 |
|---|---|---|---|
| T1 | `0x181307100` | `[r14+rsi*8+0x1307100]` (index は `[rbp]`) | 静的参照 3 箇所 |
| T2 | `0x1813071a0` | `[r14+r15*8+0x13071a0]` (index は `ecx`) | 静的参照 3 箇所 |

- 終点は静的参照からは決まらない (参照が起点から離れた範囲に散らばる)。entry 数は未確定。
- 測定で読まれた zero-fill VA 7 個 (ベースライン): `0x1813062d0`・`0x1813068f8`・`0x181306ce0`・`0x1813070f8`・`0x1813073f0`・`0x181307418`・`0x181307420`。
  このうち T1 の起点 `0x181307100` より後にあるのは `0x1813073f0`・`0x181307418`・`0x181307420` の 3 件。
  `0x1813062d0`・`0x1813068f8`・`0x181306ce0`・`0x1813070f8` は起点より前で、T1/T2 の範囲外にある。
- 既知 12 slot のうち読出しが確認できたのは `0x1813068f8`・`0x1813073f0`・`0x181307418` の 3 件。
  残り 9 件 (`0x1813068d0`・`0x181306900`・`0x181306908`・`0x181306910`・`0x1813072b0`・`0x1813073f8`・`0x181307400`・`0x181307408`・`0x181307410`) は未読出し。
  `0x181307420` は既知 12 に含まれない。

### 2.3 fatal RIP の内訳 (ベースライン rc=95 の 53 件)

`fatal_base.txt` の RIP を数えた。

| RIP | 件数 | 所見 |
|---|--:|---|
| `0x1810806a0` | 7 | `int3` 埋め領域 (`0x1810806a9` 以降が `cc`)。#2148 の stub 対象 |
| `0x180c8b9c0` | 3 | 逆アセンブル済み: `mov rax,[rcx+0x18]`。引数 `rcx` の不正が疑われる (未確定) |
| `0x18106a3b4`・`0x18105bd74`・`0x18100ca79`・`0x180da6e99`・`0x180da6d0b` | 2 each | 逆アセンブル未確認 (命令境界か未検証) |
| `0x55..`・`0x56..` で終わる host 側 RIP | 9 | host 実行ファイル側。下位 12 bit は `0x95f` で揃う (ASLR で基底のみ変化)。`0x95f` の命令は未確認 |
| その他 1 件ずつ | 残り | 一覧は `fatal_base.txt` |

### 2.4 stub 有効 (`SLOT_STUB_VA=1810806a0`) の比較

測定: rc=0: 73, rc=95: 47, rc=97: 2, rc=98: 8, rc=124: 1。zero-fill VA は 9 個 (`0x1813071c8`・`0x1813071d0` が増えた)。既知 12 の判定は 3/12 のまま。
stub 後の fatal RIP (`fatal_stub.txt`, 47 行): `0x18103d494` 4・`0x180c8b9c0` 3・`0x18106a3b4` 2・`0x18100ca79` 2・`0x180da6e99` 2 ほか。
`0x18103d494` はベースラインには出ず、stub 後に 4 件現れた。stub で `0x1810806a0` が消えた分の fault の行き先と見られるが、因果は未確認。

## 3. 再現

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh                          # ベースライン
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_base.txt     # 退避 (手作業)
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh   # stub 有効
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_stub.txt     # 退避 (手作業)
```

- 結果ファイル: `tools/icall/work/slot_trace_enc.txt` (集計)・`tools/icall/work/slot_trace_fatal.txt` (fatal 行。gitignore)。
- `slot_trace.sh` は毎 run `slot_trace_fatal.txt` を上書きする。§2.3 の `fatal_base.txt`・§2.4 の `fatal_stub.txt` は、上の `cp` で各 run の直後に退避した名前であり、スクリプトが生成するファイルではない。
- 素材: `work-icall` (`tools/icall/work/`)・`plugins-freshair` (`fetch.sh` で `tools/targets/freshair/work/`)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T1 (`0x181307100`)・T2 (`0x1813071a0`) の終点と entry 数の確定。OTT api-set 表 `0x18026c9f0` との形式比較 | 受入条件 1・2・4 | #2197 (ICALL-62) |
| fatal RIP 群 (`0x18103d494`・`0x180c8b9c0`・命令境界外の RIP・host 側 `0x..95f`) の原因切り分け | 受入条件 3 | #2198 (ICALL-63) |
| closure 外 indirect target `0x1810806a0` の本解決 (7 件の fault のみ) | 本 PR は迂回のみ | #2079 (ICALL-56) |
