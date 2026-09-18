#!/usr/bin/env python3
"""
Unit test suite for VPN REST API (CRM Integration).
Tests HTTP endpoints, Bearer authentication, query filtering, and kick actions.
"""

import os
import sys
import time
import json
import threading
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import vpn_cli


def test_rest_api():
    print("[*] Setting up test REST API server...")

    # Mock get_active_sessions for predictable test results
    mock_sessions = [
        {
            "username": "client_alpha",
            "ip": "192.168.100.10",
            "protocol": "L2TP",
            "interface": "ppp0",
            "pid": "1001",
            "timestamp": int(time.time()) - 120,
            "status": "Active"
        },
        {
            "username": "client_beta",
            "ip": "192.168.100.20",
            "protocol": "PPTP",
            "interface": "ppp1",
            "pid": "1002",
            "timestamp": int(time.time()) - 300,
            "status": "Active"
        }
    ]

    original_get_sessions = vpn_cli.get_active_sessions
    vpn_cli.get_active_sessions = lambda: list(mock_sessions)

    test_key = "test_crm_key_secure_456"
    vpn_cli.VPNAPIHandler.server_api_key = test_key

    # Bind to port 0 to let OS pick an available ephemeral port
    server = vpn_cli.ThreadedHTTPServer(("127.0.0.1", 0), vpn_cli.VPNAPIHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    try:
        # 1. Test /api/health (No Auth Required)
        print("  --> Testing GET /api/health...")
        req = urllib.request.Request(f"{base_url}/api/health")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "ok"
            assert data.get("active_users_count") == 2
        print("      ✔ GET /api/health passed")

        # 2. Test GET /api/users without Auth (Should fail with 401)
        print("  --> Testing GET /api/users without Auth (expect 401)...")
        req = urllib.request.Request(f"{base_url}/api/users")
        try:
            urllib.request.urlopen(req)
            assert False, "Request should have failed with 401 Unauthorized"
        except urllib.error.HTTPError as e:
            assert e.code == 401, f"Expected 401, got {e.code}"
        print("      ✔ Unauthorized request rejected with 401")

        # 3. Test GET /api/users with invalid Bearer Token (Should fail with 401)
        print("  --> Testing GET /api/users with invalid token (expect 401)...")
        req = urllib.request.Request(f"{base_url}/api/users", headers={"Authorization": "Bearer WRONG_KEY"})
        try:
            urllib.request.urlopen(req)
            assert False, "Request should have failed with 401 Unauthorized"
        except urllib.error.HTTPError as e:
            assert e.code == 401, f"Expected 401, got {e.code}"
        print("      ✔ Invalid token rejected with 401")

        # 4. Test GET /api/users with valid Bearer Token
        print(f"  --> Testing GET /api/users with Bearer {test_key}...")
        req = urllib.request.Request(f"{base_url}/api/users", headers={"Authorization": f"Bearer {test_key}"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("status") == "success"
            assert res.get("total") == 2
            users = res.get("data", [])
            assert len(users) == 2
            assert users[0]["username"] == "client_alpha"
            assert users[0]["ip"] == "192.168.100.10"
            assert users[0]["uptime_seconds"] >= 120
            assert "connected_at" in users[0]
        print("      ✔ GET /api/users with Bearer token passed")

        # 5. Test GET /api/users with X-API-Key header
        print("  --> Testing GET /api/users with X-API-Key header...")
        req = urllib.request.Request(f"{base_url}/api/users", headers={"X-API-Key": test_key})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("status") == "success"
            assert res.get("total") == 2
        print("      ✔ GET /api/users with X-API-Key header passed")

        # 6. Test GET /api/users with ?token= query parameter
        print("  --> Testing GET /api/users with ?token= query param...")
        req = urllib.request.Request(f"{base_url}/api/users?token={test_key}")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("status") == "success"
            assert res.get("total") == 2
        print("      ✔ GET /api/users with query token passed")

        # 7. Test Query Filters (?username= and ?ip=)
        print("  --> Testing query filtering (?username=client_beta)...")
        req = urllib.request.Request(
            f"{base_url}/api/users?username=client_beta",
            headers={"Authorization": f"Bearer {test_key}"}
        )
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("total") == 1
            assert res["data"][0]["username"] == "client_beta"
            assert res["data"][0]["protocol"] == "PPTP"
        print("      ✔ Username filter passed")

        print("  --> Testing query filtering (?ip=192.168.100.10)...")
        req = urllib.request.Request(
            f"{base_url}/api/users?ip=192.168.100.10",
            headers={"Authorization": f"Bearer {test_key}"}
        )
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("total") == 1
            assert res["data"][0]["username"] == "client_alpha"
        print("      ✔ IP filter passed")

        # 8. Test Single User Lookup GET /api/users/<username>
        print("  --> Testing GET /api/users/client_alpha...")
        req = urllib.request.Request(
            f"{base_url}/api/users/client_alpha",
            headers={"Authorization": f"Bearer {test_key}"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("status") == "success"
            assert res["data"]["username"] == "client_alpha"
        print("      ✔ Single user lookup passed")

        print("  --> Testing GET /api/users/non_existent (expect 404)...")
        req = urllib.request.Request(
            f"{base_url}/api/users/non_existent",
            headers={"Authorization": f"Bearer {test_key}"}
        )
        try:
            urllib.request.urlopen(req)
            assert False, "Expected 404 for non-existent user"
        except urllib.error.HTTPError as e:
            assert e.code == 404
        print("      ✔ Non-existent user returned 404")

        # 9. Test POST /api/users/<username>/kick
        print("  --> Testing POST /api/users/client_alpha/kick...")
        # Mock kick_session to avoid real OS/docker kill calls
        kicked_events = []
        original_kick_session = vpn_cli.kick_session
        vpn_cli.kick_session = lambda s, reason="": kicked_events.append((s, reason))

        req = urllib.request.Request(
            f"{base_url}/api/users/client_alpha/kick",
            data=b"",
            headers={"Authorization": f"Bearer {test_key}"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res.get("status") == "success"
            assert res.get("kicked") is True
            assert len(kicked_events) == 1
            assert kicked_events[0][0]["username"] == "client_alpha"
        print("      ✔ Kick endpoint passed")

        vpn_cli.kick_session = original_kick_session

        # 10. Test unconfigured API key (server_api_key = "")
        print("  --> Testing unconfigured server API key (expect 401)...")
        vpn_cli.VPNAPIHandler.server_api_key = ""
        req = urllib.request.Request(f"{base_url}/api/users", headers={"Authorization": f"Bearer {test_key}"})
        try:
            urllib.request.urlopen(req)
            assert False, "Should fail when server API key is unconfigured"
        except urllib.error.HTTPError as e:
            assert e.code == 401
        print("      ✔ Unconfigured server API key safely rejected with 401")

    finally:
        server.shutdown()
        server.server_close()
        vpn_cli.get_active_sessions = original_get_sessions
        print("  ✔ Test server shut down cleanly.")


if __name__ == "__main__":
    test_rest_api()
    print("\n[✔] ALL REST API UNIT TESTS PASSED SUCCESSFULLY!\n")
