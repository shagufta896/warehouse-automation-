import urllib.request
import urllib.error

url = "http://127.0.0.1:8000/auth/me"
req = urllib.request.Request(url)
req.add_header("Authorization", "Bearer invalid")

try:
    with urllib.request.urlopen(req) as r:
        print(f"Status: {r.status}")
        print(f"Body: {r.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(f"Body: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
