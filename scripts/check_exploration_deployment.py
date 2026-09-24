"""Read-only deployment checks plus requests rejected before any run can start."""
import json
import re
import urllib.request
import urllib.error

base = "http://127.0.0.1:8070"

def read(path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.read().decode()

html = read("/")
asset = re.search(r'src="(/assets/index-[^"]+\.js)"', html).group(1)
bundle = read(asset)
assert "Hypothesis exploration" in bundle
assert "Agent settings" in bundle
assert "Your agent team" in bundle
assert "Keep agent" in bundle
assert "Settings are locked during exploration" in bundle
json.loads(read("/api/health"))
json.loads(read("/control/health"))
request = urllib.request.Request(base + "/control/runs", data=json.dumps({"continuous": "invalid"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(request, timeout=10)
    raise AssertionError("Invalid execution mode was accepted")
except urllib.error.HTTPError as error:
    assert error.code == 400
    assert "continuous must be a boolean" in error.read().decode()
print("PASS: deployed UI contains exploration controls; API/control respond; invalid mode rejected before launch")
