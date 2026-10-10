// hostbridge: 全関数の entry/size/name を CSV 出力 (tools/m2 版の copy)
//@category Analysis
import java.io.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;

public class DumpFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args.length > 0 ? args[0] : "functions.csv";
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(out))) {
            bw.write("name,entry,size\n");
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            while (it.hasNext()) {
                Function f = it.next();
                bw.write(f.getName() + "," + f.getEntryPoint().toString(true) + "," + f.getBody().getNumAddresses() + "\n");
            }
        }
    }
}
