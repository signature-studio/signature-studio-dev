// SR-85 #5034: SR-83 と同じ閉包 (FN_ADDRS_TSV の 8 関数から直接 call・thunk 転送で到達する関数) を辿り、
// 閉包内の間接 call (computed call) を 1 件ずつ出す。各サイトの命令文字列と、参照先 (import 名・データ先) を含む。
// 入力: 環境変数 FN_ADDRS_TSV。出力: 標準出力の SITE 行と SUMMARY 行。
// usage: analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_indirect.java
// @category Serum2
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;
import java.io.BufferedReader;
import java.io.FileReader;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.Map;

public class ghidra_xferonoff_indirect extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String tsv = System.getenv("FN_ADDRS_TSV");
        ArrayDeque<Function> queue = new ArrayDeque<>();
        Map<Address, Function> seen = new LinkedHashMap<>();
        try (BufferedReader br = new BufferedReader(new FileReader(tsv))) {
            String line;
            while ((line = br.readLine()) != null) {
                if (!line.startsWith("0x")) continue;
                long rva = Long.parseLong(line.split("\t")[0].substring(2), 16);
                Function f = getFunctionContaining(toAddr(getCurrentProgram().getImageBase().getOffset() + rva));
                if (f == null || seen.containsKey(f.getEntryPoint())) continue;
                seen.put(f.getEntryPoint(), f);
                queue.add(f);
            }
        }
        int sites = 0;
        int funcs = 0;
        while (!queue.isEmpty()) {
            Function f = queue.poll();
            funcs++;
            if (f.isThunk() && f.getThunkedFunction(true) != null) {
                Function t = f.getThunkedFunction(true);
                if (!seen.containsKey(t.getEntryPoint())) {
                    seen.put(t.getEntryPoint(), t);
                    queue.add(t);
                }
            }
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                if (ins.getFlowType().isCall() && ins.getFlowType().isComputed()) {
                    sites++;
                    StringBuilder refs = new StringBuilder();
                    for (Reference r : ins.getReferencesFrom()) {
                        Address to = r.getToAddress();
                        String sym = getSymbolAt(to) == null ? "" : getSymbolAt(to).getName(true);
                        refs.append(" ref=").append(to).append(":").append(sym);
                    }
                    println("SITE in=" + f.getEntryPoint() + " at=" + ins.getAddress() + " insn=" + ins.toString() + refs);
                }
                for (Function g : f.getCalledFunctions(monitor)) {
                    if (!seen.containsKey(g.getEntryPoint())) {
                        seen.put(g.getEntryPoint(), g);
                        queue.add(g);
                    }
                }
            }
        }
        println("SUMMARY funcs=" + funcs + " computed_call_sites=" + sites);
    }
}
