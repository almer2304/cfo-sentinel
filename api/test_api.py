"""
Quick test for CFO Sentinel API endpoints.
Run: python api/test_api.py (while uvicorn is running on :8000)
"""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"

def api(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

print("=" * 50)
print("CFO Sentinel API Test")
print("=" * 50)

# Test 1: Root
code, data = api("GET", "/")
assert code == 200 and data["status"] == "running"
print(f"[PASS] GET / -> {data['service']} v{data['version']}")

# Test 2: Health
code, data = api("GET", "/health")
assert code == 200 and data["status"] == "healthy"
print(f"[PASS] GET /health -> {data['status']}")

# Test 3: Register
code, data = api("POST", "/api/v1/auth/register", {
    "business_name": "Test API Runner",
    "email": f"runner{id(sys)}@test.com",
    "password": "test1234",
    "business_type": "kuliner"
})
assert code == 200 and data["success"]
token = data["token"]
user = data["user"]
print(f"[PASS] POST /auth/register -> user: {user['business_name']}, token: {token[:15]}...")

# Test 4: Get Me
code, data = api("GET", "/api/v1/auth/me", token=token)
assert code == 200 and data["email"].endswith("@test.com")
print(f"[PASS] GET /auth/me -> {data['business_name']}")

# Test 5: History (empty)
code, data = api("GET", "/api/v1/history/list", token=token)
assert code == 200
print(f"[PASS] GET /history/list -> {len(data)} items")

# Test 6: Stats
code, data = api("GET", "/api/v1/history/stats", token=token)
assert code == 200 and data["success"]
print(f"[PASS] GET /history/stats -> total_sessions: {data['data']['total_sessions']}")

# Test 7: Unauthorized access
code, data = api("GET", "/api/v1/auth/me")
assert code == 401
print(f"[PASS] GET /auth/me (no token) -> 401 Unauthorized")

# Test 8: Logout
code, data = api("POST", "/api/v1/auth/logout", token=token)
assert code == 200 and data["success"]
print(f"[PASS] POST /auth/logout -> {data['message']}")

# Test 9: Token invalidated
code, data = api("GET", "/api/v1/auth/me", token=token)
assert code == 401
print(f"[PASS] GET /auth/me (post-logout) -> 401 (token invalidated)")

print()
print("=" * 50)
print("ALL TESTS PASSED!")
print("=" * 50)
print()
print("NOTE: Analysis and Chat endpoints require LLM API keys.")
print("      Test them via http://localhost:8000/docs (Swagger UI)")
