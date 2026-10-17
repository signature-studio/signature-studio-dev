# #6212 (PY-5419): Q を this とする間接 call の呼出し先の確定

親: #3817 (PY-258) の受入 1 の子。`REPORT_PY72_APPENDIX_3212.md` §8 の未確定 2 箇所 (`0x4100d1`・`0x415ca8`) と、this = Q の未確認 3 関数 (`0x410090`・`0x410340`・`0x4103c0`) を扱う。

- 測定 commit: `69f71ed78` (`pe_q_icall_6212.py` 追加。コードを変えた最後の commit)。
- 素材: `fl-win64.tar.zst` の `extracted/block00031_PE.bin` (22,227,016 B) を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` で展開。
- 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_q_icall_6212.py`。

## 判定 (PE 上の値のみ)

| 間接 call | 命令 | 判定 | 根拠 |
|---|---|---|---|
| `0x4100d1` | `call [rbp+0x20]` (`0x40ff70` の戻り値) | **Q では到達しない** | `0x40ff70` は `[vptr-0x90]` (message map) を親 VMT 鎖 (`[vptr-0x78]` → 親 VMT) で辿る。Q の VMT `0x9764d8` と親 `0x401a38` の全段で message map ポインタが 0。`0x40ff70` は 0 を返し、`0x4100d6` 側 (`0x4100df`) に進む |
| `0x4100df` | `call [rbx-0x38]` (rbx = obj の vptr) | `0x410060` (確定) | Q の VMT `[0x9764a0]` = `0x410060` (DefaultHandler。`0x410060` は ret 1 命令) |
| `0x4100ed` | `call [rbx-0x38]` (`0x4100e4` 側) | `0x410060` (確定) | 同上 |
| `0x415ca8` | `call [rbx+0x11]` (rbx = `[rbp+0x30]` = 入力構造体の entry) | **未確定** | 関数ポインタは entry の実行時データ。`cmp qword [rax+0x11], 0` で非 0 を見るだけで、PE の定数からは決まらない。呼出元 `0x415c30` は本 PR では追わない |

## 残り

- `0x415ca8` の 1 箇所のみ未確定。`0x4100d1` は「Q では到達しない」で閉じる (呼出し先の値は問わない)。残件の追跡先は本 issue #6212 (open)。`0x415c30` 側の解析は #4848 (PY-397, CLOSED) で扱われた範囲で、本 PR の受入には含めない。
- `0x410090`・`0x410340`・`0x4103c0` の this = Q の確認 (ブロック跨ぎを含む) は本 PR の範囲外。こちらも追跡先は #6212。

## 測定

- `pe_q_icall_6212.py` の出力: `0x4100d1 (handler call) reachable from Q VMT chain: False`・`0x4100df`・`0x4100ed` = `call qword ptr [rbx - 0x38]`・`Q VMT[-0x38] = 0x410060`・`0x415ca8` = `call qword ptr [rbx + 0x11]`。
