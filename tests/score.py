#!/usr/bin/env python3
"""Fail-closed weighted JUnit scorer used by the verifier audit."""
import argparse, json, math, xml.etree.ElementTree as ET
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--junit',required=True); ap.add_argument('--report-out',required=True); ap.add_argument('--reward-out',required=True); a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8')); root=ET.parse(a.junit).getroot()
    cases={}
    expected=set(cfg['gate_tests'])|set(cfg['tests'])
    for node in root.iter('testcase'):
        name=node.attrib.get('name','')
        matches=[item for item in expected if item.endswith('::'+name)]
        if len(matches)!=1:
            continue
        key=matches[0]
        cases[key]='pass' if node.find('failure') is None and node.find('error') is None and node.find('skipped') is None else 'fail'
    missing=sorted(expected-set(cases)); extra=sorted(set(cases)-expected)
    gate_passed=not missing and not extra and all(cases[k]=='pass' for k in cfg['gate_tests'])
    reward=math.fsum(float(v['weight']) for k,v in cfg['tests'].items() if gate_passed and cases.get(k)=='pass')
    status='COMPLETED' if not missing and not extra else 'INVALID'
    report={'status':status,'gate_passed':gate_passed,'reward':reward,'expected_tests':sorted(expected),'missing_tests':missing,'extra_tests':extra,'cases':cases}
    Path(a.report_out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); Path(a.reward_out).write_text(f'{reward:.6f}\n',encoding='utf-8')
    return 0 if status=='COMPLETED' else 2
if __name__=='__main__': raise SystemExit(main())
