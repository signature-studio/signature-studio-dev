# Fresh Air REPORT 付録 (#4976 / FA-60): KH のみ snap-in 4 組の param offset→意味 (機械語の読み)

- 親: #4053 (FA-50)・#3740 (FA-44)。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。前段: [REPORT_APPENDIX_FA44.md](REPORT_APPENDIX_FA44.md) §4。
- 位置づけ: 写像の根拠を機械語の読みで残す。差分実行 (C5・C6) はしない。製品 KPI は動かしていない (静的・機械語の読みのみ)。

## §1. 結論

| クラス | 写像の根拠 (機械語) | 結果 |
|---|---|---|
| QuickEq | §2 | **未確定** (レビュー指摘: 検査スクリプトが §2 の表と食い違う。素材無しで再検証できず。表またはスクリプトの誤りを逆アセンブルで確定するまで写像は確定扱いにしない) |
| Delay | — | 未確定。KH 側 `this+0x3188` の読み出しを一部だけ確認。SC 側は P+0x9ee4・0x9f38・0x9f74・0x9fbc・0xa004 の 5 件 |
| Disperser | — | 未確定。KH 側の P 読み出しを自動抽出できず (§4)。SC 側は P+0x9bec・0x9dc4・0x9e0c・0x9e54 を確認 |
| Phaser | — | 未確定。KH 側 P+0xc・+0x10・+0x14 と SC 側 P+0x9dc4・0x9e18・0x9e54・0x9e9c・0x9ee4 を確認。対応づけは未了 |

**この run で全 4 組の受入条件は満たさなかった** (部分達成。PR は `Refs #4976`)。4 組とも param 写像は未確定のまま §5 に残す。QuickEq の表 (§2) は、検査スクリプトとの食い違いが解消するまで根拠として使わない。

## §2. QuickEq の写像 (確定できた範囲)

素材 `work-liftlib-targets` の `HeartCore.core_64` (KH) と `SlateCore.core_64` (SC) を capstone で逆アセンブルし (`disasm.py`)、再現スクリプト `ks_fa60_quickeq_map.sh` で行の存在を検査した。

| 側 | P の取得 | 読み出し | 渡し先 (同一の設計関数呼出の引数) |
|---|---|---|---|
| KH `0x18035fb10` | `mov rax,[rdx+0x3188]` | P+0 → `[rsp+0x20]`・P+4 → `[rsp+0x28]`・P+8 (`movd`) → `[rsp+0x30]` | `call 0x180362700` |
| KH | 同上 | P+0xc → `xmm2`・P+0x10 → `xmm3` | 同上 |
| SC `0x180ac5550` | `mov rax,[rcx+0x90]` | 0x9dc4 → `[rsp+0x20]`・0x9e0c → `[rsp+0x28]`・0x9e54 → `[rsp+0x30]` | `call 0x180ad5ce0` |
| SC | 同上 | 0x9e9c → `xmm2`・0x9ee4 → `xmm3` | 同上 |

- 対応 (表の主張・未検証): KH P+0 ⇄ SC 0x9dc4、KH P+4 ⇄ SC 0x9e0c、KH P+8 ⇄ SC 0x9e54、KH P+0xc ⇄ SC 0x9e9c、KH P+0x10 ⇄ SC 0x9ee4。
- 既知の不一致 (レビュー指摘): `ks_fa60_quickeq_map.sh` は SC 0x9dc4 の直後に `movss [rsp+0x30], xmm1` を見ており、これは「0x9dc4 → [rsp+0x30]」の読みで、上の表 (0x9dc4 → [rsp+0x20]、0x9e54 → [rsp+0x30]) と食い違う。スクリプトは 0x9e54・[rsp+0x20]・[rsp+0x28]・KH P+0・P+4 の格納を検査していない。どちらが誤りかは逆アセンブルで未確定。
- 限界: 呼出先 (`0x180362700` と `0x180ad5ce0`) が同じ関数かは未確認。引数の対応だけを確定した。P+8 と 0x9e54 は KH が整数 (`movd`)、SC が float (`movss` を経由) として読むので、型の一致は未確認。
- 意味ラベル (周波数の下端・上端、Q、フラグ) は引数の並びからの推定で、機械語だけでは確定していない。SC の 0x9dc4 は float として渡し、Phaser の読み (`mov ebp,[rcx+0x9dc4]`) では int として使うため、型は関数ごとに違う可能性がある。
- 差分実行 (C4・C5) は未実施。

## §3. 検証 (測定 commit と再現)

- 再現: `bash tools/targets/freshair/ks_fa60_quickeq_map.sh` (素材 `work-liftlib-targets` を展開したもの)。
- 測定 commit: 未確定。この fix run では素材を展開できず、スクリプトを実行していない。以前の「14.8 s・EXIT=0」の記録は、この HEAD のスクリプトでは確認できない (レビュー指摘 2)。
- 検査の既知の限界 (レビュー指摘 1): 上の `need` は 5 組の対応の一部しか検査していない。SC 0x9dc4 の slot の読みは表と食い違う。表とスクリプトの修正は、素材を展開した環境で逆アセンブルにより行い、その後に再実行して EXIT と出力を本節に貼る。
- 実行結果 (この HEAD・素材無し): `missing core (work-liftlib-targets を展開する)` を出力し EXIT=2 (実測)。写像の検査は行えていない。
- Delay・Disperser・Phaser の逆アセンブルは `work/fa60/` (gitignore) に出した。判定には使っていない。

## §4. 未確定の理由 (残り 3 組)

- **Delay**: process `0x1802ed7f0` (KH) と `0x180ba8ad0` (SC) は長い (KH 3291 B・SC 2551 B)。KH 側は P を `[rdx+0x3188]` と `[rbx+0x3198]` (`0x3198` は別の state) から読むため、P の読み出しを全部追うには時間が足りなかった。
- **Disperser**: KH 側 `0x180316480` の P 読み出しを、単純な抽出では拾えなかった (P が `[rbx+0x3188]` を経由して保持される)。手で追う必要がある。
- **Phaser**: KH 側 P+0xc・+0x10・+0x14 は読まれているが、SC 側の 0x9dc4〜0x9ee4 との呼出先の対応が未確定。

## §5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| QuickEq の意味ラベル (周波数下端・上端・Q・フラグ) と呼出先 (`0x180362700`・`0x180ad5ce0`) の同一性 | 差分の param 写像の意味が未確定 | #4976 (Refs・残件) |
| Delay の param 写像 (KH P 読み出しの全件確定) | 差分実行の前提が無い | #4976 (Refs・残件)。同一 scope の #4977 (残件 B) とも重なるため、起票はしていない |
| Disperser の param 写像 | 差分実行の前提が無い | #4976 (Refs・残件) |
| Phaser の param 写像 (KH P+0xc〜0x14 と SC 側の対応) | 差分実行の前提が無い | #4976 (Refs・残件) |

- 子 issue は起票していない: 同じ残件の issue が既にあり (#4977 `[FA-61] ... 残件 B`・#4978 `[FA-60] ... SC 側 process 特定: Resonator (#4047 残件)`)、重複を避けた。
