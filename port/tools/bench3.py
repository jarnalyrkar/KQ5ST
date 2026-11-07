# bench3.py TAG PRG: game cycles in three scenes (room 1 walk, town save, bakery save), in parallel
import sys, os, shutil, subprocess, re, glob
P=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); S=os.environ.get('BENCH_DIR', '/tmp/kq5bench')  # BENCH_DIR must hold hdm/, a copy of st/hd
tag, prg = sys.argv[1], sys.argv[2]
scenes=[('walk', P+'/st/tests/bench_walk.txt', None), ('town', P+'/st/tests/bench_save.txt', 0), ('bakery', P+'/st/tests/bench_save.txt', 1)]
procs=[]
for name, auto, save in scenes:
    d=f'{S}/b3_{tag}_{name}'; shutil.rmtree(d, ignore_errors=True); shutil.copytree(S+'/hdm', d)
    for f in glob.glob(d+'/SHOT*')+glob.glob(d+'/KQ5sg.*')+glob.glob(d+'/MT32'): os.remove(f)
    shutil.copy(prg, d+'/KQ5ST.PRG')
    for f in glob.glob(P+'/st/hd/*.snd')+glob.glob(P+'/st/hd/*.v32')+glob.glob(P+'/st/hd/*.p32'): shutil.copy(f, d)
    shutil.copy(auto, d+'/AUTO.TXT')
    if save is not None:
        shutil.copy(f'{P}/st/hd/KQ5sg.00{save}', d)
        open(d+'/KQ5sg.dir','wb').write(bytes([0,save])+b'Save\n\xff\xff')
    env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    log=open(d+'.log','w')
    procs.append((name, d, subprocess.Popen(['timeout','1200','hatari','--confirm-quit','no','--natfeats','yes','--machine','ste','--harddrive','.','--auto','C:\\KQ5ST.PRG','--fast-forward','yes','--sound','off','--log-level','error'], cwd=d, stdout=log, stderr=subprocess.STDOUT, env=env)))
res={}
for name, d, p in procs:
    p.wait(); m=re.search(r'(\d+) game cycles', open(d+'.log').read()); res[name]=int(m.group(1)) if m else None
print(tag, res, 'sum', sum(v for v in res.values() if v))
