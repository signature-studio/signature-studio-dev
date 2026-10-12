// Ghidra headless postScript: VA:SIZE ペアを明示 disassemble してから decompile する。
// 使い方: analyzeHeadless <proj> <name> -import <PE> -noanalysis -scriptPath <dir> \
//           -postScript DecompAt2.java <out.txt> 0x1802ed7f0:3291 [0x...:size ...]
//@category Analysis

import java.io.BufferedWriter;
import java.io.FileWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;

public class DecompAt2 extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(outPath))) {
            bw.write("// image base " + currentProgram.getImageBase() + "\n");
            for (int i = 1; i < args.length; i++) {
                String[] ps = args[i].split(":");
                long va = Long.decode(ps[0]);
                long size = ps.length > 1 ? Long.decode(ps[1]) : 0x1000;
                Address a = toAddr(va);
                AddressSet set = new AddressSet(a, toAddr(va + size));
                DisassembleCommand cmd = new DisassembleCommand(a, set, true);
                cmd.applyTo(currentProgram, monitor);
                Function f = getFunctionAt(a);
                if (f == null) f = createFunction(a, null);
                if (f == null) { bw.write("// FAIL createFunction " + a + "\n"); continue; }
                DecompileResults r = di.decompileFunction(f, 300, monitor);
                bw.write("// ==== " + f.getName() + " @ " + a + " body=" + f.getBody().getNumAddresses() + " ====\n");
                if (r.decompileCompleted()) bw.write(r.getDecompiledFunction().getC() + "\n");
                else bw.write("// decompile failed: " + r.getErrorMessage() + "\n");
            }
        }
    }
}
