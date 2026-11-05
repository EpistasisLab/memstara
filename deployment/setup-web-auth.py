"""Create private browser credentials; run interactively to rotate the password."""
import getpass
import json
import os
from pathlib import Path
import subprocess
import tempfile


def configure(username, password, root=None):
    if not username or any(c in username for c in ":\r\n"):
        raise ValueError("Invalid username")
    if not password or any(c in password for c in "\r\n"):
        raise ValueError("A nonempty single-line password is required")
    directory = Path(root or Path(__file__).resolve().parents[1] / ".memstara" / "web-auth")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    hashed = subprocess.run(
        ["openssl", "passwd", "-apr1", "-stdin"], input=password + "\n",
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    # Nginx workers read only the password hash. The private readiness client
    # credentials are mounted separately into the control service, never web.
    for name, content, mode in (
        ("htpasswd", username + ":" + hashed + "\n", 0o644),
        ("client.json", json.dumps({"username": username, "password": password}) + "\n", 0o600),
    ):
        fd, temporary = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(content)
                os.fchmod(stream.fileno(), mode)
            os.replace(temporary, directory / name)
        finally:
            Path(temporary).unlink(missing_ok=True)
    print("Private web authentication configured. No credentials were printed.")


if __name__ == "__main__":
    configure(input("Username [memstara]: ").strip() or "memstara", getpass.getpass("Password: "))
