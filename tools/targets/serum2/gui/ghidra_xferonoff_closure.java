// SR-83 #5005: XferOnOffButton の 8 関数 (FN_ADDRS_TSV の entry) を decompile し、
// thunk を解決して静的 call の閉包 (到達する関数の数と本体合計バイト) を出す。
// 入力: 環境変数 FN_ADDRS_TSV (vtable_fn_addrs.py の出力)・OUT_DIR (出力先)。
// 出力: OUT_DIR/decomp_<entry>.c・OUT_DIR/closure.tsv・標準出力の SUMMARY 行。
// usage: analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -postScript ghidra_xferonoff_closure.java
// @category Serum2
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.Map;

public class ghidra_xferonoff_closure extends GhidraScript {
    private static final int CAP = 5000;

    @Override
    protected void run() throws Exception {
        String tsv = System.getenv("FN_ADDRS_TSV");
        String outDir = System.getenv("OUT_DIR");
        new java.io.File(outDir).mkdirs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);

        ArrayDeque<Function> queue = new ArrayDeque<>();
        Map<Address, Function> seen = new LinkedHashMap<>();
        try (BufferedReader br = new BufferedReader(new FileReader(tsv))) {
            String line;
            while ((line = br.readLine()) != null) {
                if (!line.startsWith("0x")) continue;
                String rvaStr = line.split("\t")[0];
                long rva = Long.parseLong(rvaStr.substring(2), 16);
                Address a = toAddr(getCurrentProgram().getImageBase().getOffset() + rva);
                Function f = getFunctionContaining(a);
                if (f == null) continue;
                if (seen.containsKey(f.getEntryPoint())) continue;
                seen.put(f.getEntryPoint(), f);
                queue.add(f);
                String hex = f.getEntryPoint().toString();
                try (PrintWriter pw = new PrintWriter(new FileWriter(outDir + "/decomp_" + hex + ".c"))) {
                    DecompileResults r = di.decompileFunction(f, 120, monitor);
                    pw.println(r.getDecompiledFunction() == null ? "// decompile failed" : r.getDecompiledFunction().getC());
                }
            }
        }

        int indirect = 0;
        long total = 0;
        int count = 0;
        try (PrintWriter pw = new PrintWriter(new FileWriter(outDir + "/closure.tsv"))) {
            pw.println("entry\tname\tbytes\tindirect_call_sites\tkind");
            while (!queue.isEmpty() && count < CAP) {
                Function f = queue.poll();
                if (f.isThunk() && f.getThunkedFunction(true) != null) {
                    Function t = f.getThunkedFunction(true);
                    if (!seen.containsKey(t.getEntryPoint())) {
                        seen.put(t.getEntryPoint(), t);
                        queue.add(t);
                    }
                }
                long n = f.getBody().getNumAddresses();
                int ind = 0;
                InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    if (ins.getFlowType().isCall() && ins.getFlowType().isComputed()) ind++;
                }
                indirect += ind;
                total += n;
                count++;
                pw.println(f.getEntryPoint() + "\t" + f.getName() + "\t" + n + "\t" + ind + "\t" + (f.isThunk() ? "thunk" : "func"));
                for (Function g : f.getCalledFunctions(monitor)) {
                    if (!seen.containsKey(g.getEntryPoint())) {
                        seen.put(g.getEntryPoint(), g);
                        queue.add(g);
                    }
                }
            }
        }
        println("SUMMARY closure_functions=" + count + " cap_hit=" + (!queue.isEmpty()) + " closure_body_bytes=" + total + " indirect_call_sites=" + indirect);
    }
}
