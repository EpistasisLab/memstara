"""Install locked runtime dependencies and a wheel in an isolated environment."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    'memstara.blackboard', 'memstara.experiment_registry', 'memstara.research_inputs',
    'memstara.pipeline.board', 'memstara.pipeline.llm', 'memstara.control.service',
    'memstara.mcp_servers.data', 'memstara.mcp_servers.ml',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    wheels = list(args.dist_dir.resolve().glob('*.whl'))
    if len(wheels) != 1:
        raise SystemExit('Expected exactly one wheel')
    uv = shutil.which('uv')
    if not uv:
        raise SystemExit('uv is required for locked runtime installation')
    with tempfile.TemporaryDirectory(prefix='memstara-runtime-install-') as temporary:
        root = Path(temporary)
        requirements = root / 'runtime.txt'
        subprocess.run([uv, 'export', '--frozen', '--no-dev', '--extra', 'runtime',
                        '--no-emit-project', '--format', 'requirements-txt',
                        '--output-file', str(requirements)], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL)
        environment = root / 'environment'
        subprocess.run([uv, 'venv', '--python', sys.executable, str(environment)], check=True)
        python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        # requirements export retains +cpu pins but not the explicit torch index.
        backend = ['--torch-backend', 'cpu'] if sys.platform == 'linux' else []
        subprocess.run([uv, 'pip', 'sync', '--python', str(python), *backend,
                        str(requirements)], check=True)
        subprocess.run([uv, 'pip', 'install', '--python', str(python), '--no-deps',
                        str(wheels[0])], check=True)
        subprocess.run([uv, 'pip', 'check', '--python', str(python)], check=True)
        code = '''import importlib, json, sys
from pathlib import Path
from importlib.metadata import version
import memstara
assert Path(memstara.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert memstara.__version__ == version('memstara')
assert version('motoro') == '0.13.0'
modules = json.loads(sys.argv[1])
for name in modules:
    importlib.import_module(name)
print(json.dumps({'version': memstara.__version__, 'motoro': version('motoro'),
                  'imported_modules': modules, 'runtime_dependencies': 'compatible'}))
'''
        subprocess.run([str(python), '-I', '-c', code, json.dumps(MODULES)],
                       cwd=root, check=True,
                       env={**{k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'HOME') if k in os.environ},
                            'MEMSTARA_CONFIG_MODE': 'environment'})
    print('Runtime wheel installation/import smoke passed; no provider or database calls were made.')


if __name__ == '__main__':
    main()
