// SR-37 #2066: vtable_fn_addrs.py が出した .text アドレス (RVA) を含む関数の境界と本体バイト数を出す。
// 入力: 環境変数 FN_ADDRS_TSV (vtable_fn_addrs.py の出力、1 列目が 0x<rva>)。
// 出力: 1 行 1 関数 (rva, entry, 名前, body min..max, body バイト数 = 本体の連続範囲の要素数) と合計。
// 対応付けできなかった行は理由付きで出す (推定値は書かない)。
// usage: analyzeHeadless <proj> <name> -import Serum2_win64.vst3 -postScript ghidra_fn_size.java
// @category Serum2
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.BufferedReader;
import java.io.FileReader;

public class ghidra_fn_size extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String tsv = System.getenv("FN_ADDRS_TSV");
        long total = 0;
        int ok = 0, miss = 0;
        java.util.Set<String> seenEntry = new java.util.HashSet<>();
        try (BufferedReader br = new BufferedReader(new FileReader(tsv))) {
            String line;
            while ((line = br.readLine()) != null) {
                if (!line.startsWith("0x")) continue;
                String rvaStr = line.split("\t")[0];
                long rva = Long.parseLong(rvaStr.substring(2), 16);
                Address a = toAddr(getCurrentProgram().getImageBase().getOffset() + rva);
                Function f = getFunctionContaining(a);
                if (f == null) {
                    println(String.format("%s\tNO_FUNCTION\tundefined at %s (Ghidra に関数境界が無い)", rvaStr, a));
                    miss++;
                    continue;
                }
                long n = f.getBody().getNumAddresses();
                String entry = f.getEntryPoint().toString();
                boolean dup = !seenEntry.add(entry);
                println(String.format("%s\tentry=%s\tname=%s\tbody=%s..%s\tbytes=%d\tstart_eq=%s\tdup_entry=%s",
                    rvaStr, entry, f.getName(), f.getBody().getMinAddress(), f.getBody().getMaxAddress(), n,
                    f.getEntryPoint().equals(a), dup));
                if (!dup) {
                    total += n;
                    ok++;
                }
            }
        }
        println(String.format("SUMMARY distinct_entries_mapped=%d unmapped=%d total_body_bytes_distinct=%d", ok, miss, total));
    }
}
