"""Check the public example using only extracted sdist code and resources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = Path('examples/research-inputs')


def verify(sdist):
    tracked = subprocess.check_output(
        ['git', 'ls-files', '-z', str(EXAMPLE)], cwd=ROOT).decode().split('\0')
    expected = {name: (ROOT / name).read_bytes() for name in tracked if name}
    assert expected, 'Public example inventory is empty'
    with tempfile.TemporaryDirectory(prefix='memstara-source-smoke-') as temporary:
        work = Path(temporary)
        with tarfile.open(sdist) as archive:
            archive.extractall(work, filter='data')
        roots = list(work.iterdir())
        assert len(roots) == 1 and roots[0].is_dir(), 'Expected one sdist root'
        source = roots[0]
        assert not (source / '.git').exists(), 'Acceptance must not use Git metadata'
        original = {}
        for name, content in expected.items():
            packaged = (source / name).read_bytes()
            # Git text checkout can normalize CSV CRLF to LF across build hosts.
            assert packaged.replace(b'\r\n', b'\n') == content.replace(b'\r\n', b'\n'), (
                f'Missing or changed example: {name}')
            original[name] = packaged
        # No inherited deployment settings, credentials or checkout PYTHONPATH.
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT') if key in os.environ}
        env['MEMSTARA_CONFIG_MODE'] = 'environment'
        registry = work / 'registry'
        env['MEMSTARA_RESEARCH_INPUTS_DIR'] = str(registry)
        code = """import runpy, sys
sys.path.insert(0, sys.argv.pop(1))
runpy.run_module('memstara.research_inputs', run_name='__main__')
"""
        base = json.loads((source / EXAMPLE / 'research.json').read_text())
        modes = []
        for knowledge in ('okf', 'llm_only'):
            for data in ('dataset', 'proposal'):
                config = {**base, 'knowledge_mode': knowledge, 'data_mode': data}
                path = source / 'mode.json'
                path.write_text(json.dumps(config))
                for action in ('inspect', 'register'):
                    result = json.loads(subprocess.check_output(
                        [sys.executable, '-I', '-c', code, str(source / 'src'), action, str(path)],
                        cwd=source, env=env, text=True))
                    assert result['input_checks_passed'], result['issues']
                    assert result['execution_ready'] is False
                    assert result['configuration']['knowledge_mode'] == knowledge
                    assert result['configuration']['data_mode'] == data
                    assert result['dataset']['rows'] == (120 if data == 'dataset' else 0)
                    if data == 'dataset':
                        assert result['dataset']['eligible_predictor_count'] == 4
                    if action == 'register':
                        assert json.loads((registry / (result['id'] + '.json')).read_text()) == result
                modes.append(f'{knowledge}-{data}')
        for name, content in original.items():
            assert (source / name).read_bytes() == content, f'Example modified: {name}'
    return {'sdist': sdist.name, 'sha256': hashlib.sha256(sdist.read_bytes()).hexdigest(),
            'example_files': len(expected), 'inspected_and_registered_modes': modes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    archives = list(args.dist_dir.resolve().glob('*.tar.gz'))
    if len(archives) != 1:
        raise SystemExit('Expected exactly one source distribution')
    print(json.dumps(verify(archives[0]), indent=2))
    print('Source example acceptance passed; no model, embedding or database calls were made.')


if __name__ == '__main__':
    main()
