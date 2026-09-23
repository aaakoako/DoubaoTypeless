"""Validate the handoff graph and references, not production implementation."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1]
tasks=json.loads((R/'fixtures/tasks.json').read_text())
cases=json.loads((R/'fixtures/acceptance.json').read_text())
byid={t['id']:t for t in tasks};caseids={c['id'] for c in cases}
assert len(tasks)==len(byid)==24
assert len(cases)==len(caseids)==96
assert all(c['status']=='NOT_RUN' and not c['evidence'] for c in cases)
assert all(t['status']=='NOT_STARTED' for t in tasks)
assert {x for t in tasks for x in t['cases']}==caseids
visited=set();visiting=set()
def visit(key):
    assert key in byid
    assert key not in visiting, f'cycle at {key}'
    if key in visited:return
    visiting.add(key)
    for dep in byid[key]['depends_on']:visit(dep)
    visiting.remove(key);visited.add(key)
for t in tasks:
    visit(t['id'])
    assert (R/'tasks'/f"{t['id']}.md").exists()
    assert (R/'spec'/t['spec']).exists()
report={'status':'PASS','task_count':24,'product_case_count':96,'product_cases_not_run':96,'acyclic_dependencies':True,'missing_task_files':0,'missing_spec_files':0}
(R/'evidence/handoff-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Handoff graph and untouched acceptance status: PASS')
