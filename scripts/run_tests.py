import argparse, io, json, sys, time, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import write_json, utcnow
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',type=Path,default=ROOT/'artifacts'); args=parser.parse_args()
    start=time.perf_counter(); stream=io.StringIO(); suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    output=stream.getvalue(); args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'test_output.txt').write_text(output,encoding='utf-8')
    write_json(args.output_dir/'test_results.json',{'at':utcnow(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),'elapsed_seconds':time.perf_counter()-start})
    print(output); sys.exit(0 if result.wasSuccessful() else 1)
