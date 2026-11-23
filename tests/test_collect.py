import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect import validate_config, normalize, merge, collect, utc
ROOT=Path(__file__).resolve().parents[1]
NOW='2026-11-23T11:00:00Z'
def raw(ident='mobibikes',station='a'):
 return {'network':{'id':ident,'name':'Test','location':{'city':'Vancouver','country':'CA'},'stations':[{'id':station,'name':'Station '+station,'latitude':49,'longitude':-123,'timestamp':'2026-11-23T10:50:00+00:00Z','free_bikes':0,'empty_slots':None,'extra':{'renting':True,'returning':False}}]}}
class CollectorTests(unittest.TestCase):
 def setUp(self):self.config={'defaultNetwork':'mobibikes','trackedNetworks':[{'id':'mobibikes','label':'Vancouver','timezone':'America/Vancouver'}],'maxTrackedNetworks':12,'historyDays':28,'maxCapturesPerNetwork':672,'maxStationsPerNetwork':15000,'requestTimeoutSeconds':35,'staleMinutes':60,'minimumSamplesPerCell':3,'liveCooldownSeconds':30}
 def test_extra_configured_network_not_fixed_size(self):
  self.config['trackedNetworks'].append({'id':'bixi-toronto','label':'Toronto','timezone':'America/Toronto'})
  self.assertEqual(len(validate_config(self.config)['trackedNetworks']),2)
 def test_zero_missing_and_service_pause_preserved(self):
  a=normalize(raw(),self.config['trackedNetworks'][0],NOW)
  self.assertEqual(a['captures'][0]['rows'][0][1:3],[0,None]);self.assertFalse(a['captures'][0]['rows'][0][5])
 def test_timezone_validated(self):
  self.config['trackedNetworks'][0]['timezone']='Planet/Vancouver'
  with self.assertRaises(Exception):validate_config(self.config)
 def test_retention_keeps_old_station_when_coverage_changes(self):
  a=normalize(raw(),self.config['trackedNetworks'][0],NOW)
  b=normalize(raw(station='b'),self.config['trackedNetworks'][0],'2026-11-23T12:00:00Z')
  c=merge(a,b,self.config);self.assertEqual(len(c['captures']),2);self.assertEqual(set(c['stations']),{'a','b'})
  self.config['maxCapturesPerNetwork']=1
  c=merge(a,b,self.config);self.assertEqual(len(c['captures']),1);self.assertEqual(set(c['stations']),{'b'})
 def test_rejects_empty_wrong_id_or_duplicate_station(self):
  a=raw();a['network']['stations']=[]
  with self.assertRaises(ValueError):normalize(a,self.config['trackedNetworks'][0],NOW)
  with self.assertRaises(ValueError):normalize(raw('other'),self.config['trackedNetworks'][0],NOW)
  a=raw();a['network']['stations']*=2
  with self.assertRaises(ValueError):normalize(a,self.config['trackedNetworks'][0],NOW)
 def test_failure_leaves_saved_files_unchanged(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'web/data').mkdir(parents=True);(root/'web/config.json').write_text(json.dumps(self.config));saved=root/'web/data/index.json';saved.write_text('previous good record')
   with patch('collect.fetch',side_effect=[{'networks':[{'id':'mobibikes'}]},RuntimeError('source unavailable')]):
    with self.assertRaises(RuntimeError):collect(root)
   self.assertEqual(saved.read_text(),'previous good record')
 def test_source_timestamp_variants(self):
  self.assertEqual(utc('2026-11-23T10:50:00+00:00Z'),'2026-11-23T10:50:00Z')
  self.assertEqual(utc('2026-11-23T10:50:00'),'2026-11-23T10:50:00Z')
 def test_bundled_real_capture_valid(self):
  index=json.loads((ROOT/'web/data/index.json').read_text())
  for item in index['networks']:
   data=json.loads((ROOT/'web/data'/item['file']).read_text());self.assertEqual(data['schema'],'coolcode.dockdiary.v1');self.assertGreater(len(data['captures'][0]['rows']),0)
