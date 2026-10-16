/* watch_shim_5533.c: watch_ir_5533.py が IR に差し込む値の観測フック (診断専用・#5533)。
 * shim_*.o として link し genstubs の対象から外す (stage4.sh の規約)。
 * 固定アドレス 0x11FFF000 のリングに (id, value) を記録する (watch_shim_942.c と同じ配置)。 */
void m11_wv(unsigned long long id, unsigned long long value) {
    volatile unsigned int* cnt = (volatile unsigned int*)0x11FFF000u;
    unsigned n = *cnt;
    if (n < 2000u) {
        volatile unsigned long long* e = (volatile unsigned long long*)(0x11FFF010u + 16u * n);
        e[0] = id;
        e[1] = value;
    }
    *cnt = n + 1u;
}
