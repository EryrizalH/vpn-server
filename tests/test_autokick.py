#!/usr/bin/env python3
"""
Self-check test suite for VPN Auto-Kick and Duplicate Session Handling.
Tests kick-on-connect script logic and python watchdog duplicate scoring without requiring live ppp interfaces.
"""

import os
import sys
import tempfile
import time
import subprocess
import shutil

# Ensure import of functions from vpn_cli
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

import vpn_cli

def test_watchdog_duplicate_scoring():
    print("[*] Testing watchdog duplicate scoring logic...")
    
    # Mock data: User 'alice' has 2 sessions:
    # ppp0: older (ts 1000), traffic delta 0 (stuck)
    # ppp1: newer (ts 1020), traffic delta 50 (healthy active)
    # User 'bob' has 1 session (single):
    # ppp2: (ts 1010), single session (should never be touched)

    mock_sessions = [
        {"username": "alice", "interface": "ppp0", "ip": "192.168.20.10", "timestamp": 1000, "pid": "99991", "protocol": "L2TP", "container": "l2tp-server"},
        {"username": "alice", "interface": "ppp1", "ip": "192.168.20.11", "timestamp": 1020, "pid": "99992", "protocol": "L2TP", "container": "l2tp-server"},
        {"username": "bob", "interface": "ppp2", "ip": "192.168.20.12", "timestamp": 1010, "pid": "99993", "protocol": "PPTP", "container": "pptp-server"}
    ]

    prev_traffic = {
        "ppp0": {"rx_packets": 100, "tx_packets": 100, "exists": True},
        "ppp1": {"rx_packets": 100, "tx_packets": 100, "exists": True},
        "ppp2": {"rx_packets": 50, "tx_packets": 50, "exists": True},
    }

    current_traffic = {
        "ppp0": {"rx_packets": 100, "tx_packets": 100, "exists": True}, # delta = 0 (stuck!)
        "ppp1": {"rx_packets": 125, "tx_packets": 125, "exists": True}, # delta = 50 (active!)
        "ppp2": {"rx_packets": 50, "tx_packets": 50, "exists": True},   # single session (ignored)
    }

    kicked_sessions = []
    
    # Monkeypatch get_active_sessions, get_interface_traffic, and kick_session
    orig_get_active = vpn_cli.get_active_sessions
    orig_get_traffic = vpn_cli.get_interface_traffic
    orig_kick_session = vpn_cli.kick_session

    vpn_cli.get_active_sessions = lambda: mock_sessions
    vpn_cli.get_interface_traffic = lambda iface: current_traffic.get(iface, {})
    vpn_cli.kick_session = lambda s, reason="": kicked_sessions.append((s, reason))

    try:
        traffic, kicked_count = vpn_cli.check_and_kick_stuck_duplicates(prev_traffic)
        
        # Assertions
        assert kicked_count == 1, f"Expected 1 kicked session, got {kicked_count}"
        assert len(kicked_sessions) == 1, f"Expected 1 kick call, got {len(kicked_sessions)}"
        
        kicked_session, reason = kicked_sessions[0]
        assert kicked_session["interface"] == "ppp0", f"Expected ppp0 to be kicked, got {kicked_session['interface']}"
        assert kicked_session["username"] == "alice"
        assert "ppp1" in reason, f"Reason should mention kept session ppp1, got: {reason}"
        assert "bob" not in [s["username"] for s, _ in kicked_sessions], "Bob's single session must NOT be kicked"
        
        print("  ✔ Watchdog duplicate scoring correctly kicks stuck ppp0 and keeps active ppp1 & single bob.")
    finally:
        vpn_cli.get_active_sessions = orig_get_active
        vpn_cli.get_interface_traffic = orig_get_traffic
        vpn_cli.kick_session = orig_kick_session

def test_kick_on_connect_bash_script():
    print("[*] Testing ip-up-active kick-on-connect bash logic...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        run_dir = os.path.join(temp_dir, "vpn")
        os.makedirs(run_dir, exist_ok=True)
        active_file = os.path.join(run_dir, "active_ppp_users.txt")
        log_file = os.path.join(run_dir, "vpn-watchdog.log")

        # Seed active file with an old session for user 'charlie' on ppp0
        old_time = int(time.time()) - 100
        with open(active_file, "w") as f:
            f.write(f"ppp0|charlie|192.168.20.50|{old_time}|99999|L2TP\n")

        # Now simulate user 'charlie' reconnecting on ppp1
        ip_up_script = os.path.join(SCRIPT_DIR, "l2tp", "ip-up-active")
        
        # We run bash with RUN_DIR set to our temp directory
        bash_cmd = f"""
        export RUN_DIR="{run_dir}"
        export PEERNAME="charlie"
        # Source/run the script simulating pppd invocation
        sed 's|/var/run/vpn|{run_dir}|g' {ip_up_script} > {temp_dir}/test_ip_up.sh
        chmod +x {temp_dir}/test_ip_up.sh
        {temp_dir}/test_ip_up.sh ppp1 /dev/pts/1 115200 192.168.20.1 192.168.20.51 charlie
        """
        res = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
        assert res.returncode == 0, f"Script failed: {res.stderr}"

        # Verify active_file contents:
        # ppp0 should be REMOVED, ppp1 should be ADDED
        with open(active_file, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        assert len(lines) == 1, f"Expected exactly 1 active session line, got {lines}"
        assert lines[0].startswith("ppp1|charlie|192.168.20.51|"), f"Unexpected active session line: {lines[0]}"
        assert "ppp0" not in lines[0], "Old session ppp0 must be removed from active_file"

        # Verify log_file has the kick event recorded
        assert os.path.exists(log_file), "Log file should have been created"
        with open(log_file, "r") as f:
            log_content = f.read()
        assert "[KICK-ON-CONNECT]" in log_content, f"Log missing kick event: {log_content}"
        assert "charlie" in log_content
        assert "ppp0" in log_content

        print("  ✔ ip-up-active kick-on-connect successfully kicks previous ppp0 and registers ppp1.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_watchdog_duplicate_scoring()
    test_kick_on_connect_bash_script()
    print("\n[✔] ALL AUTO-KICK UNIT CHECKS PASSED SUCCESSFULLY!\n")
