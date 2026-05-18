import urllib.request
import urllib.error

routes = [
    "/health",
    "/auth/me",
    "/products/",
    "/products/dashboard/summary",
    "/billing/stats"
]

for route in routes:
    url = f"http://127.0.0.1:8000{route}"
    print(f"\nTesting {url}...")
    req = urllib.request.Request(url)
    # No auth header, should give 401 for most, but 200 for health
    try:
        with urllib.request.urlopen(req) as r:
            print(f"Status: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        body = e.read().decode()
        print(f"Body: {body[:100]}")
    except Exception as e:
        print(f"Error: {e}")
