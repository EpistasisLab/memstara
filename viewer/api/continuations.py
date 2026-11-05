"""Read-only history for explicit retries; fresh executions remain independent."""
from fastapi import HTTPException
import run_artifacts as archive


def tags(tag):
    """Oldest first. Never group executions merely because their pipeline matches."""
    chain = []
    current = tag
    while current:
        if current in chain or len(chain) >= 64:
            raise HTTPException(503, 'Continuation history is cyclic or too long; totals unavailable')
        chain.append(current)
        config = archive.config_for(current) or {}
        selection = config.get('retry_selection') or {}
        parent = selection.get('source_run_tag')
        directory = archive.directory_for(current)
        if directory:
            path = directory / 'retry_lineage.json'
            if path.exists():
                lineage = archive.read_json(path)
                if not isinstance(lineage, dict) or not lineage.get('source_run_tag'):
                    raise HTTPException(503, 'Continuation history is unreadable; totals unavailable')
                if parent and parent != lineage['source_run_tag']:
                    raise HTTPException(503, 'Continuation history disagrees with the frozen configuration')
                parent = lineage['source_run_tag']
        if not parent:
            break
        source = archive.config_for(parent)
        # Both historical and current retries freeze these identity fields.
        keys = ('pipeline_id', 'dataset_sha256', 'y_column')
        if not source or any(not config.get(k) or config[k] != source.get(k) for k in keys):
            raise HTTPException(503, 'Continuation source is missing or belongs to a different study')
        current = parent
    return list(reversed(chain))


def expand(selected):
    return list(dict.fromkeys(t for tag in selected for t in tags(tag)))


def reports(selected, current):
    """Keep narratives verbatim and attach their original execution identities."""
    report = dict((current or {}).get('report') or {})
    outputs = {}
    for tag in selected:
        item = current if tag == selected[-1] else archive.lookup(tag)
        if not item:
            raise HTTPException(503, 'Continuation report archive is unavailable')
        for output in item['report'].get('explanation_outputs', []):
            outputs[(tag, output['loop'], output['result_id'])] = {**output, 'run_tag': tag}
    report['explanation_outputs'] = list(outputs.values())
    report['run_tags'] = selected
    return report
