"""Recovery of acknowledged pauses, under the original code and frozen inputs.

Only built-in, run-scoped tools are eligible. An unacknowledged in-flight tool
or an unknown external effect still requires review, never blind replay.
"""
import hashlib
import json
import re
import os
from pathlib import Path

VERSION = 'durable_paused_agents_v1'
TOOLS = frozenset({'okf_list_domains', 'okf_search', 'okf_read', 'describe_dataset',
    'match_concepts', 'match_concept', 'claim_question', 'create_task',
    'read_question_catalog', 'propose_questions', 'slice_columns', 'claim_task',
    'submit_result', 'get_ml_configuration', 'train_and_score', 'read_results'})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def enabled(root):
    try:
        return json.loads((Path(root) / 'config.json').read_text()).get('pause_recovery_policy') == VERSION
    except (OSError, ValueError):
        return False


def metadata(root, args, kwargs, phase):
    stage = kwargs.get('stage', '')
    tools = sorted({t.get('tool_name') or t.get('name') or '' for t in kwargs.get('tools', [])})
    config = json.loads((Path(root) / 'config.json').read_text())
    record = {'stage': stage, 'tools': tools, 'phase': phase,
              'config_hash': config.get('config_hash'), 'run_tag': config.get('run_tag')}
    record["safe"] = bool(
        re.fullmatch(r"(question[\d-]*|hypothesis\d*|data#?\d*|ml#?\d*|interpret(?:er)?#?\d*|report)", stage)
        and set(tools) <= TOOLS
        and record["config_hash"]
        and record["run_tag"]
    )
    record['input_hash'] = digest({**record, 'prompt': args[1] if len(args) > 1 else kwargs.get('prompt', '')})
    return record


def paused(root, key, record):
    from .checkpoint import atomic_json
    folder = Path(root) / 'paused_agents'
    folder.mkdir(exist_ok=True)
    atomic_json(folder / f'{key}.json', {'metadata': record, 'digest': digest(record)})


def unpaused(root, key):
    # Shutdown while paused must preserve the durable receipt.
    if not (Path(root) / 'pause.request').exists():
        (Path(root) / 'paused_agents' / f'{key}.json').unlink(missing_ok=True)


def fit_path(root, path):
    return Path(root) / 'paused_fits' / (digest(str(Path(path).resolve())) + '.json')


def save_fit(root, request):
    from .checkpoint import atomic_json
    if not enabled(root):
        return
    destination = fit_path(root, request['path'])
    destination.parent.mkdir(exist_ok=True)
    atomic_json(destination, {'run_tag': request['snapshot']['run_tag'],
        'config_hash': request['snapshot']['config_hash'], 'request': request, 'digest': digest(request)})


def saved_fit(path, snapshot):
    """Recover only the exact stopped fit, never ask the model to change its plan."""
    config_path = os.environ.get('MEMSTARA_RUN_CONFIG')
    if not config_path or not enabled(Path(config_path).parent):
        return None
    root = Path(config_path).parent
    location = fit_path(root, path)
    if not location.exists():
        return None
    record = json.loads(location.read_text())
    request = record['request']
    from memstara.ml_configuration import identity
    if (
        record["digest"] != digest(request)
        or record["run_tag"] != snapshot.get("run_tag")
        or record["config_hash"] != snapshot.get("config_hash")
        or Path(request["path"]).resolve() != Path(path).resolve()
        or identity(Path(path), request["snapshot"], request["evaluation"], request["proposal"]) != request["record"]
    ):
        raise ValueError('Paused ML input/configuration integrity mismatch')
    return request


def recoverable(checkpoint):
    root, state = checkpoint.path.parent, checkpoint.state
    if not enabled(root):
        return False
    config = json.loads((root / 'config.json').read_text())
    records = state.get('call_metadata', {})
    ml_records = []
    for key in state.get('calls', {}):
        meta = records.get(key, {})
        if (
            not meta.get("safe")
            or meta.get("config_hash") != config.get("config_hash")
            or meta.get("run_tag") != config.get("run_tag")
        ):
            return False
        try:
            receipt = json.loads((root / 'paused_agents' / f'{key}.json').read_text())
        except FileNotFoundError:
            completed = root / 'completed_agents' / f"{meta.get('input_hash')}.json"
            if meta.get('phase') and completed.exists():
                saved = json.loads(completed.read_text())
                if saved.get('metadata') == meta and saved.get('digest') == digest(saved.get('result')):
                    continue
                return False
            if meta.get('stage', '').startswith('ml'):
                ml_records.append(meta)
                continue
            return False
        if receipt != {'metadata': meta, 'digest': digest(meta)}:
            return False
    # There is one global training slot. Ambiguous concurrent ML owners cannot
    # be matched to a stopped fit and must not be guessed.
    if ml_records:
        receipts = [json.loads(p.read_text()) for p in (root / 'paused_fits').glob('*.json')]
        if len(ml_records) != 1 or len(receipts) != 1:
            return False
        receipt = receipts[0]
        if receipt.get('run_tag') != config.get('run_tag') or receipt.get('config_hash') != config.get('config_hash'):
            return False
        if receipt.get('digest') != digest(receipt.get('request')):
            return False
    return all(v.get('status') == 'done' or re.fullmatch(r'\d+:(questions|seed|report)|final_report', key)
               for key, v in state.get('phases', {}).items())


async def reconcile(checkpoint, run_tag, connect, dsn):
    """Called only after acquiring the run's database execution lease."""
    from .checkpoint import RecoveryBlocked, atomic_json
    if not recoverable(checkpoint):
        raise RecoveryBlocked('Paused agent receipts cannot establish safe recovery')
    root = checkpoint.path.parent
    config = json.loads((root / 'config.json').read_text())
    if config['run_tag'] != run_tag:
        raise RecoveryBlocked('Pause recovery belongs to another execution')
    conn = await connect(dsn)
    try:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT task_id,task_type,claimed_by FROM memstara_blackboard "
                "WHERE run_tag=$1 AND status='in_progress' FOR UPDATE",
                run_tag,
            )
            owners = {m['stage'] for k,m in checkpoint.state.get('call_metadata', {}).items()
                      if k in checkpoint.state.get('calls', {})}
            if any(r['task_type'] not in ('data','ml','interpret') or r['claimed_by'] not in owners for r in rows):
                raise RecoveryBlocked('Unfinished task ownership does not match paused agents')
            await conn.execute(
                "UPDATE memstara_blackboard SET status='ready',claimed_by='',claimed_at=NULL,updated_at=now() "
                "WHERE run_tag=$1 AND status='in_progress'",
                run_tag,
            )
            await conn.execute(
                "UPDATE memstara_questions SET claimed_run='',claimed_by='',claimed_at=NULL WHERE claimed_run=$1",
                run_tag,
            )
    finally:
        await conn.close()
    # Keep receipts and the interrupted checkpoint as audit evidence. Repeating
    # reconciliation after a crash between SQL commit and publication is harmless.
    folder = root / 'pause_recoveries'
    folder.mkdir(exist_ok=True)
    atomic_json(folder / f'{digest(checkpoint.state)}.json', checkpoint.state)
    checkpoint.state['calls'] = {}
    checkpoint.state['call_metadata'] = {}
    checkpoint.state['phases'] = {k:v for k,v in checkpoint.state['phases'].items() if v['status']=='done'}
    checkpoint.save()
