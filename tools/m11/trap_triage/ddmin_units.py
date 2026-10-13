# unit 集合の delta debugging (#418): python3 trap_triage/ddmin_units.py 0,1,...,114  (tools/m11 で実行; 8 s 超を「ハング」とみなす)
import subprocess,os,sys
def hangs(units):
    env=dict(os.environ,SV_ONLY=','.join(map(str,units)))
    try:
        p=subprocess.run(['node','trap_triage/survey_units.mjs','/dev/null'],env=env,capture_output=True,timeout=8)
        return False
    except subprocess.TimeoutExpired: return True
cur=[int(x) for x in sys.argv[1].split(",")]
assert hangs(cur)
n=2
while len(cur)>=2:
    sz=len(cur)//n; chunks=[cur[i:i+sz] for i in range(0,len(cur),sz)] if sz else [[x] for x in cur]
    done=False
    for i in range(len(chunks)):
        comp=[x for j,c in enumerate(chunks) if j!=i for x in c]
        if comp and hangs(comp): cur=comp; n=max(n-1,2); done=True; break
    if not done:
        if n>=len(cur): break
        n=min(len(cur),n*2)
    print(len(cur),cur,flush=True)
print('MIN',cur)
