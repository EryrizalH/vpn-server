#!/usr/bin/env python3
"""
Self-check test suite for VPN NAT, Forwarding & UFW Configuration.
Verifies entrypoint scripts, install script, and CLI diagnostics without requiring root privileges.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def test_entrypoint_scripts():
    print("[*] Testing entrypoint.sh scripts (PPTP & L2TP)...")
    for proto in ["pptp", "l2tp"]:
        entrypoint_path = os.path.join(BASE_DIR, proto, "entrypoint.sh")
        assert os.path.isfile(entrypoint_path), f"File {entrypoint_path} does not exist"

        with open(entrypoint_path, "r") as f:
            content = f.read()

        # 1. Ensure hardcoded -o eth0 is removed from NAT rule
        assert "-o eth0 -j MASQUERADE" not in content, (
            f"Hardcoded '-o eth0' still found in {proto}/entrypoint.sh"
        )

        # 2. Ensure universal ! -o ppp+ MASQUERADE exists
        assert "! -o ppp+ -j MASQUERADE" in content, (
            f"Universal '! -o ppp+ -j MASQUERADE' missing in {proto}/entrypoint.sh"
        )

        # 3. Ensure top-of-chain insert (-I FORWARD 1) is used instead of append (-A FORWARD)
        assert "-I FORWARD 1 -i ppp+ -j ACCEPT" in content, (
            f"Top-of-chain insert for '-i ppp+' missing in {proto}/entrypoint.sh"
        )
        assert "-I FORWARD 1 -o ppp+ -j ACCEPT" in content, (
            f"Top-of-chain insert for '-o ppp+' missing in {proto}/entrypoint.sh"
        )

        # 4. Ensure conntrack stateful rule exists
        assert "conntrack --ctstate RELATED,ESTABLISHED" in content, (
            f"Conntrack stateful rule missing in {proto}/entrypoint.sh"
        )

    print("  ✔ Both PPTP and L2TP entrypoint.sh have universal NAT & top-of-chain forwarding.")


def test_install_script_ufw_config():
    print("[*] Testing install.sh UFW forward configuration...")
    install_path = os.path.join(BASE_DIR, "install.sh")
    assert os.path.isfile(install_path), "install.sh does not exist"

    with open(install_path, "r") as f:
        content = f.read()

    assert 'DEFAULT_FORWARD_POLICY="ACCEPT"' in content, (
        "DEFAULT_FORWARD_POLICY='ACCEPT' configuration missing in install.sh"
    )
    assert "ufw route allow in on ppp+" in content, (
        "ufw route allow in on ppp+ missing in install.sh"
    )
    assert "ufw route allow out on ppp+" in content, (
        "ufw route allow out on ppp+ missing in install.sh"
    )

    print("  ✔ install.sh correctly configures UFW DEFAULT_FORWARD_POLICY and route rules.")


def test_cli_diagnostics_coverage():
    print("[*] Testing vpn_cli.py diagnostics coverage...")
    cli_path = os.path.join(BASE_DIR, "vpn_cli.py")
    assert os.path.isfile(cli_path), "vpn_cli.py does not exist"

    with open(cli_path, "r") as f:
        content = f.read()

    assert "IPv4 Forwarding" in content, "IPv4 Forwarding check missing in vpn_cli.py"
    assert "IPTables NAT Masquerade" in content, "IPTables NAT Masquerade check missing in vpn_cli.py"
    assert "UFW Forward Policy" in content, "UFW Forward Policy check missing in vpn_cli.py"

    print("  ✔ vpn_cli.py includes checks for IPv4 Forwarding, NAT Masquerade, and UFW Policy.")


if __name__ == "__main__":
    test_entrypoint_scripts()
    test_install_script_ufw_config()
    test_cli_diagnostics_coverage()
    print("\n[✔] ALL ROUTING & FORWARDING UNIT CHECKS PASSED SUCCESSFULLY!\n")
