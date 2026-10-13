// Ghidra headless postScript: 指定アドレス群を 1 関数 1 ファイルで decompile し、summary.tsv に
// (va, body bytes, decompile 秒, 出力行数, 結果) を書く。DecompAt.java と同じ -noanalysis 範囲限定方式。
// 使い方: analyzeHeadless <proj> <name> -import <PE> -noanalysis -scriptPath <dir> \
//           -postScript DecompEach.java <outdir> 0x1804b0380 [0x... ...]
//@category Analysis

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompEach extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File dir = new File(args[0]);
        dir.mkdirs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (BufferedWriter sum = new BufferedWriter(new FileWriter(new File(dir, "summary.tsv")))) {
            sum.write("va\tbody_bytes\tdecomp_sec\tlines\tstatus\n");
            for (int i = 1; i < args.length; i++) {
                long va = Long.decode(args[i]);
                Address a = toAddr(va);
                new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                Function f = getFunctionAt(a);
                if (f == null) f = createFunction(a, null);
                if (f == null) { sum.write(String.format("0x%x\t0\t0\t0\tFAIL createFunction\n", va)); continue; }
                long t0 = System.nanoTime();
                DecompileResults r = di.decompileFunction(f, 300, monitor);
                double sec = (System.nanoTime() - t0) / 1e9;
                long body = f.getBody().getNumAddresses();
                if (r.decompileCompleted()) {
                    String c = r.getDecompiledFunction().getC();
                    try (BufferedWriter bw = new BufferedWriter(new FileWriter(new File(dir, String.format("%x.c", va))))) { bw.write(c); }
                    sum.write(String.format("0x%x\t%d\t%.2f\t%d\tOK\n", va, body, sec, c.split("\n").length));
                } else {
                    sum.write(String.format("0x%x\t%d\t%.2f\t0\tFAIL %s\n", va, body, sec, r.getErrorMessage()));
                }
            }
        }
    }
}
