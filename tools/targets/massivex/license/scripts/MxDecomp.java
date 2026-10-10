// Ghidra postScript: decompile GetPluginFactory cluster of Massive X.vst3 (CAB-46/MX-1)
// runs headless with -noanalysis; creates functions at known addresses then decompiles.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.util.task.ConsoleTaskMonitor;

public class MxDecomp extends GhidraScript {
    long[] addrs = {
        0x18000a870L, // GetPluginFactory
        0x180115cd0L, // called helper (entry+0x3b used)
        0x1801270e1L, 0x18011ca74L, 0x18011cc51L,
        0x180014615L, 0x180016375L, 0x180016519L
    };
    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        StringBuilder sb = new StringBuilder();
        for (long a : addrs) {
            Address ad = toAddr(a);
            Function f = getFunctionAt(ad);
            if (f == null) {
                disassemble(ad);
                f = createFunction(ad, null);
            }
            if (f == null) { sb.append("// no function at " + a + "\n"); continue; }
            DecompileResults res = di.decompileFunction(f, 60, new ConsoleTaskMonitor());
            sb.append("// ===== " + a + " " + f.getName() + "\n");
            if (res != null && res.getDecompiledFunction() != null) {
                sb.append(res.getDecompiledFunction().getC());
            } else {
                sb.append("// decompile failed\n");
            }
            sb.append("\n\n");
        }
        java.io.PrintWriter pw = new java.io.PrintWriter(
            new java.io.FileWriter(getScriptArgs().length > 0 ? getScriptArgs()[0] : "mx_gpf.c"));
        pw.print(sb.toString());
        pw.close();
        println("MxDecomp done");
    }
}
