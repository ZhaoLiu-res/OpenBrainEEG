"""Run a real local EDF job against an already started server; no login."""
import json
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
session = requests.Session()
session.trust_env = False
session.headers['X-Brainifly-Local'] = '1'
base = 'http://127.0.0.1:8765'
assert session.get(base+'/api/health',timeout=5).json()['edition']=='local'
assert session.get(base,timeout=5).status_code==200
source = ROOT/'backend/test_data/physionet/S001R01.edf'
with source.open('rb') as stream:
    response = session.post(base+'/api/jobs',files={'file':(source.name,stream)},data={'config_json':json.dumps({'report_language':'en','report_formats':['html']})},timeout=30)
response.raise_for_status()
job_id = response.json()['id']
print('Submitted without authentication:',job_id,flush=True)
deadline = time.monotonic()+300
while time.monotonic()<deadline:
    response = session.get(base+'/api/jobs/'+job_id,timeout=10); response.raise_for_status(); job=response.json()
    if job['status'] in ['completed','failed']: break
    time.sleep(2)
assert job['status']=='completed',job
result={'job_id':job_id,'status':job['status'],'warnings':job['warnings'],'downloads':{}}
for kind in ['fif','edf','csv','html','parameters']:
    response=session.get(base+f'/api/jobs/{job_id}/files/{kind}',timeout=30); response.raise_for_status()
    assert response.content
    result['downloads'][kind]=len(response.content)
    if kind=='html':
        assert '<script src="https://cdn.plot.ly/' not in response.text
        assert 'plotly.js' in response.text.lower()
preview = session.get(base+f'/api/jobs/{job_id}/report',timeout=30)
assert preview.status_code == 200
assert 'text/html' in preview.headers['content-type']
assert 'attachment' not in preview.headers.get('content-disposition','')
assert 'local-report-layout' in preview.text
assert 'plotly.js' in preview.text.lower()
result['inline_report_bytes'] = len(preview.content)
assert session.get(base+'/api/ai/settings',timeout=5).json()['provider']=='disabled'
(ROOT/'.local-data/smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
