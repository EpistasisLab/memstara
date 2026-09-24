import asyncio
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'viewer/api'))
import flat_history


def test_completed_history_reused_but_live_calls_and_completion_changes_refresh():
    first,second=uuid.uuid4(),uuid.uuid4()
    class Connection:
        def __init__(self):
            self.scope=[];self.flat=[];self.reads=[]
            self.completed={first:'done-at-1',second:None}
            self.tasks={first:1,second:2}
        async def execute(self,sql):
            if sql=='TRUNCATE selected_run_ids':self.scope=[]
            elif sql.startswith('DROP TABLE IF EXISTS flat'):
                self.flat=[]
                if ' AS ' in sql:
                    self.reads.extend(self.scope)
                    self.flat=[dict(zip(flat_history._COLUMNS,(i,i,None,'memstara-board','claim_task','{}',json.dumps({'task_id':self.tasks[i],'huge_unused_payload':'not cached'})))) for i in self.scope]
        async def executemany(self,sql,values):
            if 'selected_run_ids' in sql:self.scope.extend(v[0] for v in values)
            else:self.flat.extend(dict(zip(flat_history._COLUMNS,v)) for v in values)
        async def fetch(self,sql,*args):
            if sql.startswith('SELECT id, completed_at'):return [{'id':i,'completed_at':self.completed[i]} for i in args[0]]
            return self.flat
    async def check():
        flat_history._cache.clear();c=Connection()
        await flat_history.build_flat(c,[first,second])
        assert c.scope==[first,second] and len(c.flat)==2
        assert all('huge_unused_payload' not in r['result'] for r in c.flat)
        c.reads=[];c.tasks[second]=3
        await flat_history.build_flat(c,[first,second])
        assert c.reads==[second]
        assert {json.loads(r['result'])['task_id'] for r in c.flat}=={1,3}
        c.completed[first]='corrected-at-2';c.tasks[first]=4;c.reads=[]
        await flat_history.build_flat(c,[first,second])
        assert set(c.reads)=={first,second}
        assert {json.loads(r['result'])['task_id'] for r in c.flat}=={4,3}
        flat_history._cache.clear()
    asyncio.run(check())


def test_compaction_preserves_error_presence_and_required_identifiers():
    row=dict(zip(flat_history._COLUMNS,(uuid.uuid4(),uuid.uuid4(),None,'board','claim_task','{}',json.dumps({'task_id':4,'run_tag':'run','error':None,'large':'discard'}))))
    assert json.loads(flat_history.compact(row)[-1])=={'task_id':4,'run_tag':'run','error':None}
