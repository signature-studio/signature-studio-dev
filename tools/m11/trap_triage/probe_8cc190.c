/* #483 probe (negctl_483.sh の probe_head 構成が #481 HEAD の m11_ov.c の後ろに連結する): function_8cc190 (TDictionary.Add) の転記 + 観測.
 * [probe] 行 = Add 1 回ごとの self / key / FComparer / その先頭 qword (正常なら vtable 番地, 壊れていると .text の機械語), hash, Find の戻り idx (>= 0 = 重複判定) */
u64 function_8cc190(u64 self, u64 key, u64 val) {
    u32 h; long long idx;
    fprintf(stderr, "[probe] 8cc190 self=%llx key=%llx cnt=%lld cap=%lld cmp=%llx vt=%llx\n", self, key, (long long)Q(self + 0x10), (long long)Q(self + 0x20), Q(self + 0x18), Q(self + 0x18) ? Q(Q(self + 0x18)) : 0);
    if ((long long)Q(self + 0x10) >= (long long)Q(self + 0x20)) function_8cbcb0(self);
    h = (u32)function_8cbda0(self);
    idx = (long long)function_8cbce0(self, key, h);
    fprintf(stderr, "[probe]   hash=%x idx=%lld%s\n", h, idx, idx >= 0 ? " DUP" : "");
    if (idx >= 0) function_411e80(function_448ee0(Q(R(0x2f078)), 1, Q(R(0x11e00e0))));
    return function_8cbe40(self, h, ~(u64)idx, key, val);
}
