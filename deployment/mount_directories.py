"""List directory bind sources from resolved Compose JSON (no environment values)."""
import json
import sys

DIRECTORY_TARGETS = {
    '/app/outputs', '/app/cache', '/app/user-inputs', '/runs',
    '/root/.cache/huggingface',
}


def directories(config):
    paths = set()
    for service in config['services'].values():
        for volume in service.get('volumes', []):
            if volume.get('type') == 'bind' and volume.get('target') in DIRECTORY_TARGETS:
                source = volume['source']
                if not source.startswith('/') or any(c in source for c in '\n\r\x00'):
                    raise ValueError('Bind source must be an absolute, single-line path')
                paths.add(source)
    return sorted(paths)


if __name__ == '__main__':
    for path in directories(json.load(sys.stdin)):
        print(path)
