## SHX-T9 (#177) 実機 DllMain 経路の残

結論: DllMain closure は未完。逐次起動の停止要因は lift 側 #232 (`_UStrAsg` OOB)。測定値は `tools/shimx/REPORT_SHX-T9.md` §2・§4 が正本。

| 未解決項目 | 起票先 |
|---|---|
| GetProcAddress 名前空 miss (非 GUI) | P1/P2 追加候補 (`tools/shimx/REPORT_SHX-T9.md` §2.1) |
| GetProcAddress GUI 系 miss | tools/gui |
| GetProcAddress 序数 miss | R1 (`tools/shimx/REPORT_R1-R8.md`) |
| LoadLibrary 失敗 (Msctf / avrt / PowrProf) | R4 (`tools/shimx/REPORT_R1-R8.md`) |
| EnterCriticalSection (NULL) の shimx fail-fast | R7 (`tools/shimx/REPORT_R1-R8.md`) |
| LoadStringW fail-fast (plain 逐次起動) | tools/gui |
| DllMain closure 完走 | #232 (CLOSED・停止点のみ記録) |
| survey unit 160 以降の挙動 | #773 |
