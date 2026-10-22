#!/usr/bin/env python3
import sys, xml.etree.ElementTree as ET
from pathlib import Path
out=Path(sys.argv[1]); suite=ET.Element('testsuite',{'name':'pytest'})
for raw in sys.argv[2:]:
    path=Path(raw)
    if not path.is_file(): continue
    root=ET.parse(path).getroot()
    for node in root.iter('testcase'):
        suite.append(node)
suite.set('tests',str(len(list(suite))))
suite.set('failures',str(sum(1 for n in suite if n.find('failure') is not None)))
suite.set('errors',str(sum(1 for n in suite if n.find('error') is not None)))
suite.set('skipped',str(sum(1 for n in suite if n.find('skipped') is not None)))
root=ET.Element('testsuites'); root.append(suite)
ET.ElementTree(root).write(out,encoding='utf-8',xml_declaration=True)
