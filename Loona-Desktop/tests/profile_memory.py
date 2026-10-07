"""Sample real Windows process memory without touching personal settings."""
from pathlib import Path
import argparse,ctypes as C,json,os,subprocess,time
from ctypes import wintypes as W

class Counters(C.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,C.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]

def profile(executable,option,output):
    executable=Path(executable).resolve();output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,LOONA_DATA_DIR=str(output.parent/'memory-test-user-data'))
    fn=C.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    fn.argtypes=[W.HANDLE,C.POINTER(Counters),W.DWORD];fn.restype=W.BOOL
    process=subprocess.Popen([str(executable),option],cwd=executable.parent,env=env,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    samples=[];started=time.monotonic()
    try:
        while process.poll() is None:
            counter=Counters();counter.cb=C.sizeof(counter)
            if fn(int(process._handle),C.byref(counter),counter.cb):
                samples.append((counter.WorkingSetSize,counter.PrivateUsage,counter.PeakWorkingSetSize,counter.PeakPagefileUsage))
            if time.monotonic()-started>120:raise TimeoutError('Memory test exceeded 120 seconds')
            time.sleep(.02)
        if process.returncode:raise RuntimeError(f'Executable test failed: {process.returncode}')
        if not samples:raise RuntimeError('No memory samples collected')
        report={'executable':str(executable),'option':option,'seconds':round(time.monotonic()-started,2),
                'samples':len(samples),'peak_working_set_mib':round(max(s[2] for s in samples)/2**20,2),
                'peak_private_mib':round(max(max(s[1],s[3]) for s in samples)/2**20,2)}
        output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
        return report
    finally:
        if process.poll() is None:process.kill();process.wait()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('executable');parser.add_argument('output')
    parser.add_argument('--stress',action='store_true');args=parser.parse_args()
    profile(args.executable,'--memory-test' if args.stress else '--smoke-test',args.output)
