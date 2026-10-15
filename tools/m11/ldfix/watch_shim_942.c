/* watch_shim_942.c: watch_ir_942.py が IR に差し込む観測フック (診断専用・#942)。shim_*.o として link し genstubs の対象から外す。
 * stdio・malloc を使わず、固定アドレス 0x11FFF000 のリングに (id, 指定アドレスの 8B 値) を記録する (配置を変えないため)。 */
void m11_wh(unsigned long long id, unsigned long long addr) {
    volatile unsigned int* cnt = (volatile unsigned int*)0x11FFF000u;
    unsigned n = *cnt;
    if (n < 2000u) {
        volatile unsigned long long* e = (volatile unsigned long long*)(0x11FFF010u + 16u * n);
        e[0] = id;
        e[1] = *(volatile unsigned long long*)(unsigned long)addr;
    }
    *cnt = n + 1u;
}
