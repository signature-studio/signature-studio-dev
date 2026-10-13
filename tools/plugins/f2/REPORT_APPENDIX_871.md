# PLG-F2 #871 付録: 0x6f1650 の原因切り分け (REPORT §10.1 の全文)

## 10.1 (#871 部分) 0x6f1650 の原因切り分け

- 検証 HEAD: `9c6f8c91` (`871-plg-f2-leaf-residual` 上、origin/main be9bb7c1 基点)。本付録の測定値はすべてこの commit で取得。`PLUG_XMMARG=1 PLUG_ICALL=0` の 6 block lift・`leaf_diff.sh` は一致 15 / 不一致 8 を再現 (139 秒、lift 19 秒)。
- **0x6f1650 (19059, `ret_only`) の原因: image 配置と IR 絶対 VA 定数のずれ (確定)**。機械語 `movaps/mulss/addss/divss` は定数 3 個 (0x6f166c・0x6f1670・0x6f1674) を rip 相対で読む。IR はこれを `inttoptr i64 <絶対 VA>` で持つが、`image/19059.bin` は RVA 配置で末尾が 0x3efa00 のため、絶対 VA 0x6f166c は image 外 (ゼロ埋め)。結果 `0 * m + a` の除算 `0/0` で NaN (0xffc00000) になり、native は 0x3f11c71c。引数 (xmm1=0x40200000) は wasm の trace で届いていることを確認済み。
- 同型の絶対 VA 定数は 30 関数 (317 箇所) にあり、`mk_targets.py` の image 配置 (RVA) と `inttoptr` の絶対 VA 規約が不整合。修正 (定数位置の再配置 or wasm_origin 規約の見直し) は 6 block 全体に効くため、回帰込みで #871 に残す (下記 未解決)。
- 残る 5 関数 (0x6bfec0・0x6c8fc0・0x6c9b60・0x6c8c90・0x6cc2e0 ほか) の原因は本 run では未切り分け。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 絶対 VA 定数の image 配置不整合の修正と 6 block 回帰 (0x6f1650 の値の解消) | 受入条件 1・4 | #871 ([PLG-F2-6]) |
| 残 5 関数 (no_placeholder 3 / slot_occupied 2) の原因切り分け | 受入条件 1・2 | #871 ([PLG-F2-6]) |

親: #613 (PLG-F2-5)。未解決の追跡先は上表のとおり #871 のみ。
