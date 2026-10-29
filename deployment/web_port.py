"""Read the resolved web binding or update only its installation setting."""
import json
from pathlib import Path
import sys


def port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise ValueError('Web port must be between 1 and 65535')
    return str(number)


def requested(config):
    bindings = [entry for entry in config['services']['web']['ports']
                if int(entry['target']) == 80 and entry.get('protocol', 'tcp') == 'tcp']
    if len(bindings) != 1 or bindings[0].get('host_ip') != '127.0.0.1':
        raise ValueError('Automatic port selection requires one loopback web binding')
    return port(bindings[0]['published'])


def save(root, selected):
    from dotenv import set_key
    path = Path(root) / '.env'
    if not path.is_file():
        raise ValueError('The project .env must exist before choosing a port')
    # dotenv rewrites only this key; credentials and comments remain private.
    set_key(path, 'MEMSTARA_WEB_PORT', port(selected), quote_mode='never')


if __name__ == '__main__':
    if sys.argv[1:] == ['requested']:
        print(requested(json.load(sys.stdin)))
    elif len(sys.argv) == 4 and sys.argv[1] == 'save':
        save(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit('Usage: web_port.py requested | save PROJECT PORT')
