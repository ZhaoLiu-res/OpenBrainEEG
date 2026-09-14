import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
import local_app
from local_ai import AISettings, AIStore
from local_locale import LocaleResolver
import requests


class ProtocolServer(BaseHTTPRequestHandler):
    received = []
    received_headers = []
    def log_message(self, *args):
        pass
    def do_GET(self):
        data = json.dumps({'models':[{'name':'local-test'}]} if self.path == '/api/tags' else {'data':[{'id':'chat-test'}]}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.received.append((self.path, body))
        self.received_headers.append(dict(self.headers))
        result = {"message": {"content": "Ollama test reply"}} if self.path == "/api/chat" else {"choices": [{"message": {"content": "Compatible test reply"}}]}
        if self.path == '/v1/messages': result = {'content':[{'type':'text','text':'Anthropic test reply'}]}
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.patcher = patch.object(local_app, 'DATA', self.directory)
        self.patcher.start()
        self.client = TestClient(local_app.app, base_url="http://127.0.0.1:8765")
        self.client.__enter__()
        self.headers = {'X-Brainifly-Local': '1'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patcher.stop()
        self.temp.cleanup()

    def test_no_login_and_exact_available_samples(self):
        self.assertFalse(self.client.get('/api/health').json()['login_required'])
        paths = self.client.get('/openapi.json').json()['paths']
        self.assertFalse(any(word in path for path in paths for word in ['auth', 'payment', 'quota', 'admin']))
        samples = self.client.get('/api/demos').json()
        self.assertEqual({d['filename'] for d in samples}, {'S001R01.edf', 'S001R04.edf', 'A01T.gdf'})
        self.assertTrue(next(d for d in samples if d['id']=='edf_baseline')['available'])

    def test_cross_site_writes_and_host_rejected(self):
        self.assertEqual(self.client.put('/api/ai/settings', json={}).status_code, 403)
        self.assertEqual(self.client.put('/api/ai/settings', json={}, headers={**self.headers,'Origin':'https://untrusted.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={'Host':'untrusted.example'}).status_code, 400)

    def test_api_key_redaction_preservation_and_new_host(self):
        settings = {'provider':'ollama','base_url':'http://localhost:11434','model':'fixture','api_key':'test-secret-only'}
        result = self.client.put('/api/ai/settings', json=settings, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('test-secret-only', result.text)
        self.assertNotIn('api_key', result.json())
        settings['api_key'] = None
        self.client.put('/api/ai/settings', json=settings, headers=self.headers)
        self.assertTrue(self.client.get('/api/ai/settings').json()['has_api_key'])
        settings['base_url'] = 'http://127.0.0.1:1234'
        self.client.put('/api/ai/settings', json=settings, headers=self.headers)
        self.assertFalse(self.client.get('/api/ai/settings').json()['has_api_key'])

    def test_disabled_ai_does_not_make_requests(self):
        with patch('requests.Session.post') as post:
            result = self.client.post('/api/ai/ask', json={'question':'hello'}, headers=self.headers)
        self.assertEqual(result.status_code, 400)
        post.assert_not_called()

    def test_locale_country_mapping_cache_and_no_private_payload(self):
        with patch('requests.Session.get', return_value=Mock(status_code=200, json=Mock(return_value={'success':True,'country_code':'CN'}))) as get:
            first = self.client.get('/api/locale').json()
            second = self.client.get('/api/locale').json()
        self.assertEqual(first, {'language':'zh','country':'CN','source':'ip'})
        self.assertEqual(first, second)
        get.assert_called_once_with('https://ipwho.is/?fields=success,country_code', timeout=(2, 3), allow_redirects=False)
        with patch('requests.Session.get', return_value=Mock(status_code=200, json=Mock(return_value={'success':True,'country_code':'US'}))):
            self.assertEqual(LocaleResolver().resolve()['language'], 'en')

    def test_locale_failure_uses_browser_without_blocking_cleaning(self):
        for response in [Mock(status_code=429, text='limit'), Mock(status_code=200, json=Mock(return_value={'success':False}))]:
            with patch('requests.Session.get', return_value=response):
                self.assertEqual(LocaleResolver().resolve(), {'language':None,'country':None,'source':'browser'})
        with patch('requests.Session.get', side_effect=requests.Timeout):
            self.assertEqual(self.client.get('/api/locale').json()['source'], 'browser')
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_connection_test_is_explicit_and_disabled_without_network(self):
        with patch('requests.Session.post') as post:
            self.assertEqual(self.client.post('/api/ai/test', json={}).status_code,403)
            self.assertEqual(self.client.post('/api/ai/test', json={}, headers=self.headers).status_code,400)
        post.assert_not_called()

    def test_system_settings_persist_and_enforce_upload_limit(self):
        self.assertEqual(self.client.get('/api/settings').json()['max_upload_mb'],512)
        settings = {'max_upload_mb':1,'max_active_jobs':2,'report_language':'en','default_pdf':False,'auto_open_report':False}
        self.assertEqual(self.client.put('/api/settings',json=settings).status_code,403)
        self.assertEqual(self.client.put('/api/settings',json=settings,headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/settings').json(),settings)
        self.assertTrue((self.directory/'system-settings.json').is_file())
        self.assertEqual(self.client.post('/api/jobs',files={'file':('too-large.edf',b'x'*(1024*1024+1))},headers=self.headers).status_code,413)
        self.assertEqual(self.client.put('/api/settings',json={'max_upload_mb':0},headers=self.headers).status_code,422)

    def test_disabled_connection_can_be_enabled_without_losing_key(self):
        self.client.put('/api/ai/settings',json={'provider':'disabled','base_url':'https://api.deepseek.com','model':'fixture','api_key':'fixture-secret'},headers=self.headers)
        self.client.put('/api/ai/settings',json={'provider':'openai_compatible','base_url':'https://api.deepseek.com','model':'fixture','api_key':None},headers=self.headers)
        self.assertEqual(self.client.app.state.ai.read().api_key,'fixture-secret')
        self.assertNotIn('fixture-secret',self.client.get('/api/ai/settings').text)

    def test_provider_catalog_and_error_diagnostics(self):
        providers=self.client.get('/api/ai/providers').json()
        self.assertTrue({'deepseek','kimi','ollama','lmstudio','claude','gemini','qwen'} <= {p['id'] for p in providers})
        store=self.client.app.state.ai
        store.save(AISettings(provider='openai_compatible',base_url='https://example.test/v1',model='fixture',api_key='never-echo'))
        for code in [401,402,404,429,503]:
            with patch('requests.Session.post',return_value=Mock(status_code=code)):
                response=self.client.post('/api/ai/test',headers=self.headers)
                self.assertEqual(response.status_code,400)
                self.assertIn(str(code),response.text)
                self.assertNotIn('never-echo',response.text)

    def test_model_discovery_anthropic_and_conversation_history(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),ProtocolServer)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            for provider,url,expected in [('ollama',base,'local-test'),('openai_compatible',base+'/v1','chat-test'),('anthropic',base+'/v1','chat-test')]:
                settings={'provider':provider,'base_url':url,'model':'fixture','api_key':'test-key'}
                response=self.client.post('/api/ai/models',json=settings,headers=self.headers)
                self.assertEqual(response.json()['models'],[expected])
                self.client.put('/api/ai/settings',json=settings,headers=self.headers)
                response=self.client.post('/api/ai/test',headers=self.headers)
                self.assertEqual(response.status_code,200,response.text)
            sent=ProtocolServer.received[-1][1]
            self.assertIn('system',sent)
            self.assertNotEqual(sent['messages'][0]['role'],'system')
            self.assertEqual(ProtocolServer.received_headers[-1]['anthropic-version'],'2023-06-01')
            conv=self.client.post('/api/conversations',json={},headers=self.headers).json()
            route=f"/api/conversations/{conv['id']}/messages"
            self.assertEqual(self.client.post(route,json={'question':'First question'},headers=self.headers).status_code,200)
            response=self.client.post(route,json={'question':'Follow up'},headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(response.json()['messages']),4)
            self.assertEqual([m['role'] for m in ProtocolServer.received[-1][1]['messages']],['user','assistant','user'])
            self.assertEqual(len(self.client.get('/api/conversations').json()),1)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_conversation_summary_consent_retry_and_restart(self):
        from local_conversations import ConversationStore
        app = self.client.app
        app.state.jobs.items['report'] = {'status':'completed','filename':'private.edf','metrics':{'quality_score':75},'config':{},'warnings':[]}
        conv = self.client.post('/api/conversations',json={'job_id':'report'},headers=self.headers).json()
        route = f"/api/conversations/{conv['id']}/messages"
        for include in [False,True]:
            with patch.object(app.state.ai,'ask',return_value={'answer':'Review quality'}) as ask:
                response=self.client.post(route,json={'question':'Review','include_summary':include},headers=self.headers)
                self.assertEqual(response.status_code,200)
                summary=ask.call_args.kwargs['summary']
                self.assertEqual(summary is not None,include)
                self.assertNotIn('private.edf',json.dumps(summary))
        with patch.object(app.state.ai,'ask',side_effect=ValueError('Provider unavailable')):
            self.assertEqual(self.client.post(route,json={'question':'Retry me'},headers=self.headers).status_code,400)
        self.assertEqual(len(app.state.conversations.get(conv['id'])['messages']),4)
        lock=app.state.conversations.request_lock(conv['id']);lock.acquire()
        try:
            self.assertEqual(self.client.post(route,json={'question':'Duplicate'},headers=self.headers).status_code,409)
        finally:lock.release()
        self.assertEqual(len(ConversationStore(self.directory).get(conv['id'])['messages']),4)

    def test_invalid_upload_and_missing_outputs(self):
        self.assertEqual(self.client.post('/api/jobs', files={'file':('bad.edf',b'not an EDF')}, headers=self.headers).status_code,422)
        self.assertEqual(self.client.post('/api/jobs', files={'file':('sample.vhdr',b'header')}, headers=self.headers).status_code,422)
        self.assertEqual(self.client.get('/api/jobs/unknown/files/html').status_code,404)
        self.assertEqual(self.client.get('/api/jobs').json(),[])

    def test_report_preview_download_and_path_boundaries(self):
        jobs = local_app.app.state.jobs
        directory = jobs.root / 'report-fixture'
        directory.mkdir()
        (directory / 'report.html').write_text('<html><head></head><body><h1>Report</h1><script>var chart = 1;</script></body></html>', encoding='utf-8')
        jobs.items['report-fixture'] = {'id':'report-fixture','outputs':{'html':'report.html'}}
        preview = self.client.get('/api/jobs/report-fixture/report')
        self.assertEqual(preview.status_code, 200)
        self.assertIn('text/html', preview.headers['content-type'])
        self.assertNotIn('attachment', preview.headers.get('content-disposition', ''))
        self.assertIn('sandbox allow-scripts', preview.headers['content-security-policy'])
        self.assertIn('local-report-layout', preview.text)
        self.assertIn('<script>var chart = 1;</script>', preview.text)
        download = self.client.get('/api/jobs/report-fixture/files/html')
        self.assertIn('attachment', download.headers['content-disposition'])
        self.assertEqual(self.client.get('/api/jobs/missing/report').status_code, 404)
        outside = jobs.root / 'outside.html'
        outside.write_text('private fixture')
        jobs.items['report-fixture']['outputs']['html'] = '../outside.html'
        self.assertEqual(self.client.get('/api/jobs/report-fixture/report').status_code, 404)
        self.assertEqual(self.client.get('/api/jobs/report-fixture/files/html').status_code, 404)

    def test_history_is_sorted_after_restart(self):
        jobs = local_app.app.state.jobs
        jobs.items['new'] = {'id':'new','created_at':'2026-09-14T00:00:00Z'}
        jobs.items['old'] = {'id':'old','created_at':'2026-09-13T00:00:00Z'}
        self.assertEqual([j['id'] for j in self.client.get('/api/jobs').json()], ['new','old'])

    def test_interrupted_job_recovery(self):
        directory = self.directory/'recover/jobs'/'abc'; directory.mkdir(parents=True)
        (directory/'job.json').write_text(json.dumps({'id':'abc','status':'running'}))
        jobs = local_app.Jobs(self.directory/'recover')
        try:
            self.assertEqual(jobs.get('abc')['status'],'failed')
            self.assertIn('interrupted',jobs.get('abc')['error'])
        finally:
            jobs.pool.shutdown()

    def test_both_ai_protocols_over_real_local_http(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), ProtocolServer)
        thread = Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            store = AIStore(self.directory)
            for provider,url,expected in [('ollama',base,'/api/chat'),('openai_compatible',base+'/v1','/v1/chat/completions')]:
                store.save(AISettings(provider=provider,base_url=url,model='fixture'))
                result = store.ask('What needs review?',{'metrics':{'quality_score':76}})
                self.assertIn('test reply',result['answer'])
                self.assertEqual(ProtocolServer.received[-1][0],expected)
                self.assertFalse(ProtocolServer.received[-1][1]['stream'])
            self.client.app.state.jobs.items['fixture'] = {'status':'completed', 'filename':'private-recording.edf', 'metrics':{'quality_score':76}, 'config':{'report_language':'en'}, 'warnings':[]}
            for include in [False, True]:
                response = self.client.post('/api/ai/ask', json={'question':'Review results','job_id':'fixture','include_summary':include}, headers=self.headers)
                self.assertEqual(response.status_code,200)
                sent = json.dumps(ProtocolServer.received[-1][1])
                self.assertNotIn('private-recording.edf',sent)
                self.assertEqual('quality_score' in sent,include)
            response = self.client.post('/api/ai/test', json={}, headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json(), {'status':'ok','model':'fixture'})
            self.assertNotIn('quality_score', json.dumps(ProtocolServer.received[-1][1]))
        finally:
            server.shutdown(); server.server_close(); thread.join()



    def test_export_guards_and_idempotent_queue(self):
        jobs = self.client.app.state.jobs
        directory = jobs.root / 'export-fixture'
        directory.mkdir()
        jobs.items['export-fixture'] = {'id':'export-fixture','status':'completed','outputs':{},'exports':{}}
        url = '/api/jobs/export-fixture/exports/pdf'
        self.assertEqual(self.client.post(url).status_code,403)
        self.assertEqual(self.client.post(url.replace('/pdf','/unknown'),headers=self.headers).status_code,422)
        jobs.items['export-fixture']['status']='running'
        self.assertEqual(self.client.post(url,headers=self.headers).status_code,409)
        jobs.items['export-fixture']['status']='completed'
        with patch.object(jobs.pool,'submit') as submit:
            self.assertEqual(self.client.post(url,headers=self.headers).json()['exports']['pdf']['status'],'queued')
            self.client.post(url,headers=self.headers)
            self.assertEqual(submit.call_count,1)
        jobs.update('export-fixture',exports={'pdf':{'status':'failed','error':'fixture'}})
        with patch.object(jobs.pool,'submit') as submit:
            self.client.post(url,headers=self.headers)
            submit.assert_called_once()


    def test_export_failure_preserves_cleaning_and_rejects_traversal(self):
        from local_exports import saved_file
        jobs=self.client.app.state.jobs
        directory=jobs.root/'export-failure';directory.mkdir()
        existing=directory/'report.html';existing.write_text('original report')
        jobs.items['export-failure']={'id':'export-failure','status':'completed','outputs':{'html':'report.html'},'exports':{},'metrics':{'quality_score':76}}
        outside=self.directory/'outside.txt';outside.write_text('private')
        with self.assertRaises(ValueError):saved_file(directory,'../../outside.txt')
        with patch('local_exports.restore_result',side_effect=ValueError('Missing saved input')):
            jobs.run_export('export-failure','pdf')
        result=jobs.get('export-failure')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['outputs'],{'html':'report.html'})
        self.assertEqual(result['exports']['pdf']['status'],'failed')
        self.assertEqual(existing.read_text(),'original report')

    def test_interrupted_export_recovers_without_failing_cleaning(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            task=root/'jobs'/'recover';task.mkdir(parents=True)
            (task/'job.json').write_text(json.dumps({'id':'recover','status':'completed','outputs':{'html':'report.html'},'exports':{'pdf':{'status':'running'}}}))
            jobs=local_app.Jobs(root)
            try:
                job=jobs.get('recover')
                self.assertEqual(job['status'],'completed')
                self.assertEqual(job['exports']['pdf']['status'],'failed')
                self.assertEqual(job['outputs']['html'],'report.html')
            finally:jobs.pool.shutdown()

    def test_portable_pdf_contains_saved_metrics_and_escaped_unicode(self):
        from types import SimpleNamespace
        from local_exports import pdf_report
        from core.quality import QualityMetrics
        from core.steps.base import StepResult
        from config import PipelineConfig
        from pypdf import PdfReader
        result=SimpleNamespace(config=PipelineConfig(report_language='zh'),
            dataset_info=SimpleNamespace(filename='测试 <recording>.edf',n_channels=4,sfreq=128,duration=20),
            metrics=QualityMetrics(quality_score=73,n_bad_channels=2),
            step_results=[StepResult(step_name='filter',description='检查 <value>',duration=1,warnings=['复核 & 保留原始数据'])],total_duration=1)
        path=self.directory/'fixture.pdf'
        with patch('local_exports.render_figures',return_value=iter([])):
            pdf_report(result,path)
        reader=PdfReader(path)
        text='\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('测试 <recording>.edf',text)
        self.assertIn('复核 & 保留原始数据',text)
        self.assertIn('73 / 100',text)
        self.assertIn('report_language',text)

if __name__ == '__main__':
    unittest.main()
