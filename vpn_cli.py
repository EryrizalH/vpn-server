#!/usr/bin/env python3
"""
VPN Server Management & Monitoring CLI
For Docker-based PPTP & Plain L2TP VPN Servers with FreeRADIUS Authentication.
Location: /home/eryrizal/vpn-server/vpn_cli.py
Symlink: /usr/local/bin/vpn-cli
"""

import os
import sys
import time
import subprocess
import re
import argparse
from typing import List, Dict, Any, Optional

import ipaddress

# Ensure rich is installed
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.align import Align
    from rich.live import Live
    from rich.rule import Rule
except ImportError:
    print("[*] Package 'rich' belum terinstall. Menginstall 'python3-rich'...")
    subprocess.run(["sudo", "apt-get", "install", "-y", "python3-rich"], check=False)
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.align import Align
    from rich.live import Live
    from rich.rule import Rule

console = Console()

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def load_env_file(filepath: str):
    """Simple parser to load key=value from .env file into os.environ if present."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass

load_env_file(os.path.join(SCRIPT_DIR, ".env"))

VPN_DIR = os.environ.get("VPN_DIR", SCRIPT_DIR)
RADIUS_SERVER = os.environ.get("RADIUS_SERVER", "127.0.0.1")
RADIUS_SECRET = os.environ.get("RADIUS_SECRET", "testing123")

def get_ip_sort_key(session: Dict[str, Any]):
    """Return ipaddress object for numerical IP sorting."""
    try:
        return ipaddress.ip_address(session["ip"])
    except ValueError:
        return ipaddress.ip_address("0.0.0.0")

def run_cmd(cmd: str, shell: bool = True) -> str:
    """Helper to run a shell command and return stdout string."""
    try:
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def run_docker_cmd(cmd: str) -> str:
    """Helper to run command inside docker context using sg docker if needed."""
    full_cmd = f'cd {VPN_DIR} && sg docker -c "{cmd}"'
    return run_cmd(full_cmd)

def get_active_sessions() -> List[Dict[str, Any]]:
    """Parse active PPP sessions from docker containers using active_ppp_users.txt & active interfaces."""
    sessions = []

    containers = [
        ("L2TP", "l2tp-server"),
        ("PPTP", "pptp-server")
    ]

    for proto, container_name in containers:
        active_txt = run_docker_cmd(f"docker exec {container_name} cat /var/run/active_ppp_users.txt 2>/dev/null")
        ps_out = run_docker_cmd(f"docker exec {container_name} ps aux 2>/dev/null")
        ip_out = run_docker_cmd(f"docker exec {container_name} ip addr 2>/dev/null")

        # Map current active ppp interfaces in this container
        ip_map = {} # interface -> ip
        for line in ip_out.splitlines():
            if "peer" in line:
                dev_m = re.search(r"scope global (ppp\d+)", line)
                peer_m = re.search(r"peer ([\d\.]+)", line)
                if dev_m and peer_m:
                    ip_map[dev_m.group(1)] = peer_m.group(1)

        if active_txt:
            # Parse lines format: INTERFACE|USERNAME|REMOTE_IP|TIMESTAMP
            for line in active_txt.splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    interface, username, ip = parts[0], parts[1], parts[2]
                    
                    # Verify interface is currently UP
                    if interface in ip_map:
                        actual_ip = ip_map[interface]
                        
                        pid = "-"
                        for ps_line in ps_out.splitlines():
                            if interface in ps_line:
                                ps_parts = ps_line.split()
                                if len(ps_parts) > 1:
                                    pid = ps_parts[1]
                                    break

                        sessions.append({
                            "protocol": proto,
                            "container": container_name,
                            "username": username,
                            "ip": actual_ip,
                            "interface": interface,
                            "pid": pid,
                            "status": "Active"
                        })
        else:
            # Fallback if active_ppp_users.txt is not yet populated
            log_out = run_docker_cmd(f"docker exec {container_name} cat /var/log/ppp.log 2>/dev/null")
            if log_out:
                for interface, ip in ip_map.items():
                    matches = re.findall(rf"Connect: {interface} <-->.*?\n.*?rcvd \[CHAP Response [^\]]+, name = \"([^\"]+)\"\]", log_out, re.DOTALL)
                    username = matches[-1] if matches else "Unknown"
                    
                    pid = "-"
                    for ps_line in ps_out.splitlines():
                        if interface in ps_line:
                            ps_parts = ps_line.split()
                            if len(ps_parts) > 1:
                                pid = ps_parts[1]
                                break

                    sessions.append({
                        "protocol": proto,
                        "container": container_name,
                        "username": username,
                        "ip": ip,
                        "interface": interface,
                        "pid": pid,
                        "status": "Active"
                    })

    return sessions

def print_status_dashboard():
    """Display overall VPN server health & connection status."""
    console.print(Rule("[bold cyan]VPN Server Status Dashboard[/bold cyan]"))
    
    ps_out = run_docker_cmd("docker compose ps")
    sessions = get_active_sessions()

    l2tp_count = sum(1 for s in sessions if s["protocol"] == "L2TP")
    pptp_count = sum(1 for s in sessions if s["protocol"] == "PPTP")
    total_count = len(sessions)

    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")

    stat_table = Table(title="Services & Active Connections", box=None)
    stat_table.add_column("Metrik", style="bold yellow")
    stat_table.add_column("Nilai", style="bold green")

    stat_table.add_row("Server Host", run_cmd("hostname"))
    stat_table.add_row("FreeRADIUS IP", RADIUS_SERVER)
    stat_table.add_row("Total Active VPN Users", f"[bold green]{total_count}[/bold green]")
    stat_table.add_row("  - Active L2TP Users", str(l2tp_count))
    stat_table.add_row("  - Active PPTP Users", str(pptp_count))

    console.print(Panel(stat_table, title="[bold white]Overview Status[/bold white]", border_style="cyan"))

    docker_panel = Panel(
        Text(ps_out if ps_out else "Docker containers not running", style="dim white"),
        title="[bold white]Docker Containers State[/bold white]",
        border_style="blue"
    )
    console.print(docker_panel)

def print_active_users_table(filter_keyword: str = None):
    """Display formatted table of active VPN clients sorted by IP address."""
    sessions = get_active_sessions()

    if filter_keyword:
        kw = filter_keyword.lower()
        sessions = [
            s for s in sessions 
            if kw in s["username"].lower() or kw in s["ip"] or kw in s["protocol"].lower() or kw in s["interface"]
        ]

    # Sort sessions by numerical IP address
    sessions.sort(key=get_ip_sort_key)

    table = Table(title=f"Daftar User VPN Terhubung ({len(sessions)} Active)", show_lines=True)
    table.add_column("No", justify="center", style="dim")
    table.add_column("Username", style="bold cyan")
    table.add_column("Protokol", justify="center", style="bold magenta")
    table.add_column("IP Statis (FreeRADIUS)", justify="center", style="bold green")
    table.add_column("Interface", justify="center", style="yellow")
    table.add_column("PID", justify="center", style="dim white")
    table.add_column("Status", justify="center", style="bold green")

    for idx, s in enumerate(sessions, 1):
        proto_badge = f"[bold green]{s['protocol']}[/bold green]" if s['protocol'] == "L2TP" else f"[bold blue]{s['protocol']}[/bold blue]"
        table.add_row(
            str(idx),
            s["username"],
            proto_badge,
            s["ip"],
            s["interface"],
            s["pid"],
            "🟢 Active"
        )

    console.print(table)

def kick_user(target: str):
    """Disconnect a client by username or IP."""
    sessions = get_active_sessions()
    targets = [s for s in sessions if s["username"].lower() == target.lower() or s["ip"] == target]

    if not targets:
        console.print(f"[bold red]❌ User atau IP '{target}' tidak ditemukan di sesi aktif![/bold red]")
        return

    for t in targets:
        console.print(f"Disconnecting [bold cyan]{t['username']}[/bold cyan] ({t['protocol']} - {t['ip']}) on {t['container']}...")
        if t["pid"] != "-":
            run_docker_cmd(f"docker exec {t['container']} kill -TERM {t['pid']}")
            console.print(f"[bold green]✔ Signal TERM dikirim ke PID {t['pid']}![/bold green]")
        else:
            # Fallback: kill pppd associated with interface
            run_docker_cmd(f"docker exec {t['container']} pkill -f {t['interface']}")
            console.print(f"[bold green]✔ pppd interface {t['interface']} di-pkill![/bold green]")

def manage_containers(action: str, service: str = "all"):
    """Handle docker compose start, stop, restart, rebuild."""
    svc_arg = "" if service == "all" else ("l2tp-vpn" if service == "l2tp" else "pptp-vpn")
    
    if action == "restart":
        cmd = f"docker compose restart {svc_arg}"
    elif action == "start":
        cmd = f"docker compose up -d {svc_arg}"
    elif action == "stop":
        cmd = f"docker compose stop {svc_arg}"
    elif action == "rebuild":
        cmd = f"docker compose up -d --build {svc_arg}"
    else:
        console.print("[bold red]Aksi kontainer tidak valid![/bold red]")
        return

    console.print(f"[bold yellow]Menjalankan {action} kontainer...[/bold yellow]")
    out = run_docker_cmd(cmd)
    console.print(out)
    console.print("[bold green]✔ Selesai![/bold green]")

def view_logs(service: str = "l2tp", follow: bool = True, lines: int = 40):
    """View or tail container logs."""
    container = "l2tp-server" if service == "l2tp" else "pptp-server"
    follow_flag = "-f" if follow else ""
    
    console.print(f"[bold cyan]Menampilkan log PPP {container} ({lines} baris terakhir)...[/bold cyan]")
    if follow:
        console.print("[dim]Tekan Ctrl+C untuk keluar dari log tailing.[/dim]\n")
        try:
            os.system(f'cd {VPN_DIR} && sg docker -c "docker exec -it {container} tail -f -n {lines} /var/log/ppp.log"')
        except KeyboardInterrupt:
            console.print("\n[yellow]Log tailing dihentikan.[/yellow]")
    else:
        out = run_docker_cmd(f"docker exec {container} tail -n {lines} /var/log/ppp.log")
        console.print(out)

def run_diagnostics():
    """Run diagnostic checks on RADIUS, containers, UFW firewall, and PPP devices."""
    console.print(Rule("[bold magenta]VPN System Diagnostics[/bold magenta]"))

    table = Table(title="Hasil Pengujian Diagnostic System", show_lines=True)
    table.add_column("Komponen", style="bold yellow")
    table.add_column("Hasil Pengujian", style="bold white")
    table.add_column("Status", justify="center", style="bold")

    # 1. Check Docker Daemon
    docker_status = run_cmd("systemctl is-active docker")
    table.add_row("Docker Daemon", f"Status: {docker_status}", "🟢 OK" if docker_status == "active" else "🔴 ERROR")

    # 2. Check Containers Running
    ps_out = run_docker_cmd("docker compose ps --services --filter 'status=running'")
    services_running = ps_out.splitlines() if ps_out else []
    is_containers_ok = "l2tp-vpn" in services_running and "pptp-vpn" in services_running
    table.add_row("Containers Health", f"Running: {', '.join(services_running)}", "🟢 OK" if is_containers_ok else "⚠️ WARNING")

    # 3. Check FreeRADIUS Reachability
    rad_out = run_docker_cmd(f"docker exec pptp-server radtest test_diag_user testpass {RADIUS_SERVER} 0 {RADIUS_SECRET} 2>&1")
    rad_ok = "Access-Accept" in rad_out or "Access-Reject" in rad_out # Access-Reject means RADIUS reached and answered
    table.add_row("FreeRADIUS Connection", f"Server {RADIUS_SERVER}:1812 respond", "🟢 OK" if rad_ok else "🔴 TIMEOUT")

    # 4. Check PPP Device
    ppp_dev = run_cmd("ls -la /dev/ppp 2>/dev/null")
    table.add_row("Host /dev/ppp Device", ppp_dev if ppp_dev else "Missing", "🟢 OK" if ppp_dev else "🔴 MISSING")

    # 5. Check UFW Ports
    ufw_out = run_cmd("sudo ufw status 2>/dev/null")
    is_l2tp_port = "1701/udp" in ufw_out or "ALLOW" in ufw_out
    is_pptp_port = "1723/tcp" in ufw_out or "ALLOW" in ufw_out
    table.add_row("UFW Firewall Ports", "1701/udp (L2TP) & 1723/tcp (PPTP)", "🟢 OK" if (is_l2tp_port and is_pptp_port) else "⚠️ CHECK")

    console.print(table)

def interactive_menu():
    """Interactive TUI Menu."""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]VPN SERVER MANAGEMENT & MONITORING CLI[/bold cyan]\n"
            "[dim]MikroTik & Windows Pure Plain L2TP / PPTP with FreeRADIUS[/dim]",
            border_style="cyan"
        ))

        console.print("[1] 📊 Overview Status & Dashboard")
        console.print("[2] 👥 Lihat Daftar User Active Terhubung")
        console.print("[3] 🔍 Cari User Active Berdasarkan Keyword")
        console.print("[4] ❌ Disconnect / Kick User Active")
        console.print("[5] 🔄 Restart Service VPN (L2TP / PPTP / All)")
        console.print("[6] 📜 View & Tail Log PPP (`ppp.log`)")
        console.print("[7] 🩺 Jalankan System & RADIUS Diagnostics")
        console.print("[0] 🚪 Keluar")
        console.print()

        choice = Prompt.ask("Pilih menu", choices=["1", "2", "3", "4", "5", "6", "7", "0"], default="1")

        if choice == "1":
            console.clear()
            print_status_dashboard()
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "2":
            console.clear()
            print_active_users_table()
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "3":
            kw = Prompt.ask("Masukkan username, IP, atau interface yang dicari")
            console.clear()
            print_active_users_table(filter_keyword=kw)
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "4":
            console.clear()
            print_active_users_table()
            target = Prompt.ask("Masukkan Username atau IP User yang ingin di-disconnect")
            if target:
                if Confirm.ask(f"Yakin ingin memutuskan koneksi '{target}'?"):
                    kick_user(target)
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "5":
            svc = Prompt.ask("Pilih service yang di-restart", choices=["all", "l2tp", "pptp"], default="all")
            act = Prompt.ask("Pilih aksi", choices=["restart", "rebuild", "stop", "start"], default="restart")
            if Confirm.ask(f"Jalankan {act} pada {svc}?"):
                manage_containers(act, svc)
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "6":
            svc = Prompt.ask("Pilih log service", choices=["l2tp", "pptp"], default="l2tp")
            lines = Prompt.ask("Jumlah baris log", default="40")
            view_logs(service=svc, follow=True, lines=int(lines))
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "7":
            console.clear()
            run_diagnostics()
            Prompt.ask("\nTekan Enter untuk kembali ke menu utama")

        elif choice == "0":
            console.print("[bold green]Terima kasih! Keluar dari VPN CLI.[/bold green]")
            sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="VPN Server Management & Monitoring CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Perintah CLI Subcommand")

    # Subcommand: status
    subparsers.add_parser("status", help="Tampilkan status dashboard & overview VPN server")

    # Subcommand: users
    users_p = subparsers.add_parser("users", help="Tampilkan tabel user VPN yang sedang terhubung")
    users_p.add_argument("-f", "--filter", help="Filter berdasarkan username atau IP", default=None)

    # Subcommand: kick
    kick_p = subparsers.add_parser("kick", help="Putuskan koneksi user aktif berdasarkan Username atau IP")
    kick_p.add_argument("target", help="Username atau IP target")

    # Subcommand: restart / rebuild
    manage_p = subparsers.add_parser("manage", help="Kelola kontainer (restart, start, stop, rebuild)")
    manage_p.add_argument("action", choices=["restart", "start", "stop", "rebuild"], help="Aksi kontainer")
    manage_p.add_argument("-s", "--service", choices=["all", "l2tp", "pptp"], default="all", help="Service target")

    # Subcommand: logs
    logs_p = subparsers.add_parser("logs", help="Tampilkan / tail log PPP kontainer")
    logs_p.add_argument("-s", "--service", choices=["l2tp", "pptp"], default="l2tp", help="Service log target")
    logs_p.add_argument("-n", "--lines", type=int, default=40, help="Jumlah baris log")
    logs_p.add_argument("--no-follow", action="store_true", help="Jangan tail (-f) log")

    # Subcommand: diag
    subparsers.add_parser("diag", help="Jalankan uji diagnostic RADIUS & modul system")

    args = parser.parse_args()

    if not args.command:
        # No subcommand provided -> run interactive menu
        interactive_menu()
    elif args.command == "status":
        print_status_dashboard()
    elif args.command == "users":
        print_active_users_table(filter_keyword=args.filter)
    elif args.command == "kick":
        kick_user(args.target)
    elif args.command == "manage":
        manage_containers(args.action, args.service)
    elif args.command == "logs":
        view_logs(service=args.service, follow=not args.no_follow, lines=args.lines)
    elif args.command == "diag":
        run_diagnostics()

if __name__ == "__main__":
    main()
