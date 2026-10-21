"""python run_growth_v21.py INPUT.json OUTPUT.json — opt-in, no legacy mutation."""
import argparse,json
from pathlib import Path
from prospect_os.growth_engine_v21 import audit_run
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');a=p.parse_args()
 src=Path(a.input).resolve();dst=Path(a.output).resolve()
 if src==dst:raise SystemExit('Refusing to overwrite input evidence')
 if dst.exists():raise SystemExit('Choose a new output path; existing run is immutable')
 data=json.loads(src.read_text());result=audit_run(data)
 dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({'run_id':data['run_id'],'inventory':result['inventory'],'gaps':result['release']['gaps']}))
