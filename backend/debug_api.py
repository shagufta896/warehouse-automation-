import requests

url = "http://127.0.0.1:8000/auth/me"
headers = {"Authorization": "Bearer some_invalid_token"} # Just to trigger middleware

try:
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Body: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
