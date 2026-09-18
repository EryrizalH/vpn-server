#!/usr/bin/env bash
#
# Docker VPN Server All-in-One Installer & Manager (PPTP & Plain L2TP with FreeRADIUS)
# Supported OS: Ubuntu 20.04/22.04/24.04, Debian 11/12
#

set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

DEFAULT_INSTALL_DIR="/opt/vpn-server"
SCRIPT_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function: Display Banner
show_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "================================================================="
    echo "   DOCKER VPN SERVER ALL-IN-ONE INSTALLER & MANAGEMENT TOOL     "
    echo "   Supported Protocols: PPTP & Plain L2TP (FreeRADIUS Auth)     "
    echo "================================================================="
    echo -e "${NC}"
}

# Function: Check Root Privileges
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}[ERROR] Skrip ini harus dijalankan sebagai root (Gunakan 'sudo ./install.sh').${NC}"
        exit 1
    fi
}

# Function: Check OS Compatibility
check_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
            echo -e "${RED}[ERROR] Sistem operasi '$ID' tidak didukung secara resmi. Harap gunakan Ubuntu atau Debian.${NC}"
            exit 1
        fi
        echo -e "${GREEN}[✔] OS Terdeteksi: $PRETTY_NAME${NC}"
    else
        echo -e "${RED}[ERROR] Tidak dapat mendeteksi versi OS.${NC}"
        exit 1
    fi
}

# Function: Install Prerequisites & Docker
install_dependencies() {
    echo -e "\n${YELLOW}[1/6] Memeriksa dan menginstall dependensi sistem & Docker...${NC}"
    
    apt-get update -y
    apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        iptables \
        net-tools \
        python3 \
        python3-pip \
        python3-rich \
        ufw

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}[*] Docker tidak ditemukan. Menginstall Docker CE...${NC}"
        curl -fsSL https://get.docker.com | sh
    fi

    # Install Docker Compose Plugin if not present
    if ! docker compose version &> /dev/null; then
        echo -e "${YELLOW}[*] Plugin Docker Compose tidak ditemukan. Menginstall docker-compose-plugin...${NC}"
        apt-get install -y docker-compose-plugin || apt-get install -y docker-compose
    fi

    systemctl enable --now docker
    echo -e "${GREEN}[✔] Dependensi & Docker berhasil disiapkan.${NC}"
}

# Function: Configure System Kernel & Firewall
configure_host() {
    echo -e "\n${YELLOW}[2/6] Mengonfigurasi Sysctl, Kernel Modules & Firewall...${NC}"

    # Enable IPv4 Forwarding
    cat <<EOF > /etc/sysctl.d/99-vpn.conf
net.ipv4.ip_forward = 1
EOF
    sysctl -p /etc/sysctl.d/99-vpn.conf >/dev/null 2>&1 || true

    # Load required kernel modules
    for mod in ppp_generic ppp_mppe ip_gre ip_tables; do
        modprobe $mod 2>/dev/null || true
        if ! grep -q "^$mod" /etc/modules 2>/dev/null; then
            echo "$mod" >> /etc/modules
        fi
    done

    # Ensure /dev/ppp exists
    if [ ! -c /dev/ppp ]; then
        mknod /dev/ppp c 108 0
        chmod 600 /dev/ppp
    fi

    # Configure UFW if enabled
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        echo -e "${YELLOW}[*] UFW aktif. Membuka port VPN & mengonfigurasi forward routing...${NC}"
        ufw allow 1723/tcp comment "VPN PPTP" >/dev/null 2>&1 || true
        ufw allow 1701/udp comment "VPN L2TP" >/dev/null 2>&1 || true
        ufw allow 500/udp comment "VPN IPsec ISAKMP" >/dev/null 2>&1 || true
        ufw allow 4500/udp comment "VPN IPsec NAT-T" >/dev/null 2>&1 || true
        ufw allow 6155/tcp comment "VPN REST API" >/dev/null 2>&1 || true

        # ponytail: Allow forwarding in UFW so VPN clients have internet access (Full Tunnel)
        if [ -f /etc/default/ufw ]; then
            sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
        fi
        ufw route allow in on ppp+ 2>/dev/null || true
        ufw route allow out on ppp+ 2>/dev/null || true
        ufw reload >/dev/null 2>&1 || true
    fi

    echo -e "${GREEN}[✔] Konfigurasi Host & Kernel selesai.${NC}"
}

# Function: Deploy Configuration & Files
deploy_files() {
    local target_dir="$1"
    local radius_ip="$2"
    local radius_secret="$3"
    local api_key="${4:-}"
    local api_port="${5:-6155}"

    # If api_key not provided, preserve existing from .env or generate one
    if [ -z "$api_key" ]; then
        if [ -f "$target_dir/.env" ] && grep -q "^API_KEY=" "$target_dir/.env"; then
            api_key=$(grep "^API_KEY=" "$target_dir/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
        else
            api_key=$(head /dev/urandom | tr -dc A-Za-z0-9 2>/dev/null | head -c 24 || openssl rand -hex 12 2>/dev/null || echo "vpn_api_key_$(date +%s)")
        fi
    fi

    echo -e "\n${YELLOW}[3/6] Menyalin file proyek ke $target_dir...${NC}"
    mkdir -p "$target_dir"

    # Copy repository files if source is different from target
    if [ "$SCRIPT_SOURCE_DIR" != "$target_dir" ]; then
        cp -r "$SCRIPT_SOURCE_DIR"/* "$target_dir"/ 2>/dev/null || true
        cp "$SCRIPT_SOURCE_DIR"/.env.example "$target_dir"/.env.example 2>/dev/null || true
    fi

    echo -e "${YELLOW}[4/6] Menyusun file konfigurasi & environment...${NC}"

    # Write .env file
    cat <<EOF > "$target_dir/.env"
RADIUS_SERVER=$radius_ip
RADIUS_SECRET=$radius_secret
VPN_DIR=$target_dir
API_PORT=$api_port
API_KEY=$api_key
EOF

    # Configure radiusclient.conf in L2TP & PPTP
    cat <<EOF > "$target_dir/l2tp/radiusclient.conf"
auth_order    radius
authserver    $radius_ip:1812
acctserver    $radius_ip:1813
servers       /etc/radiusclient/servers
dictionary    /etc/radiusclient/dictionary
seqfile       /var/run/radius.seq
mapfile       /etc/radiusclient/port-id-map
bindaddr      *
radius_timeout 10
radius_retries 3
EOF

    cat <<EOF > "$target_dir/pptp/radiusclient.conf"
auth_order    radius
authserver    $radius_ip:1812
acctserver    $radius_ip:1813
servers       /etc/radiusclient/servers
dictionary    /etc/radiusclient/dictionary
seqfile       /var/run/radius.seq
mapfile       /etc/radiusclient/port-id-map
bindaddr      *
radius_timeout 10
radius_retries 3
EOF

    # Configure servers file for radiusclient
    echo "$radius_ip    $radius_secret" > "$target_dir/l2tp/servers"
    echo "$radius_ip    $radius_secret" > "$target_dir/pptp/servers"

    chmod 600 "$target_dir/l2tp/servers" "$target_dir/pptp/servers"
    chmod +x "$target_dir/vpn_cli.py"

    # Setup shared runtime directory for active sessions & auto-kick watchdog
    mkdir -p "$target_dir/run"
    touch "$target_dir/run/active_ppp_users.txt" "$target_dir/run/vpn-watchdog.log"
    chmod -R 777 "$target_dir/run"
    rm -f /var/log/vpn-watchdog.log
    ln -sf "$target_dir/run/vpn-watchdog.log" /var/log/vpn-watchdog.log

    echo -e "${GREEN}[✔] Konfigurasi RADIUS & runtime directory berhasil dibuat.${NC}"
}

# Function: Start Docker Containers
start_containers() {
    local target_dir="$1"
    echo -e "\n${YELLOW}[5/6] Membangun dan menjalankan kontainer Docker VPN...${NC}"
    
    cd "$target_dir"
    docker compose down --remove-orphans 2>/dev/null || true
    docker compose up -d --build

    echo -e "${GREEN}[✔] Kontainer Docker PPTP & L2TP berhasil berjalan.${NC}"
}

# Function: Setup CLI Symlink
setup_cli() {
    local target_dir="$1"
    echo -e "\n${YELLOW}[6/6] Menyiapkan CLI Symlink '/usr/local/bin/vpn-cli'...${NC}"

    rm -f /usr/local/bin/vpn-cli
    ln -s "$target_dir/vpn_cli.py" /usr/local/bin/vpn-cli
    chmod +x /usr/local/bin/vpn-cli

    echo -e "${GREEN}[✔] CLI 'vpn-cli' berhasil di-link ke /usr/local/bin/vpn-cli.${NC}"
}

# Function: Setup Auto-Kick Watchdog Systemd Service
setup_watchdog_service() {
    local target_dir="$1"
    echo -e "\n${YELLOW}[*] Menyiapkan Systemd Service Auto-Kick Watchdog (vpn-watchdog.service)...${NC}"

    cat <<EOF > /etc/systemd/system/vpn-watchdog.service
[Unit]
Description=VPN Duplicate & Stuck Session Auto-Kick Watchdog
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$target_dir
ExecStart=/usr/local/bin/vpn-cli watchdog --interval 10
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now vpn-watchdog.service 2>/dev/null || true
    echo -e "${GREEN}[✔] Service 'vpn-watchdog.service' berhasil diaktifkan & berjalan otomatis di background.${NC}"
}

# Function: Setup REST API CRM Systemd Service
setup_api_service() {
    local target_dir="$1"
    echo -e "\n${YELLOW}[*] Menyiapkan Systemd Service REST API Gateway (vpn-api.service)...${NC}"

    cat <<EOF > /etc/systemd/system/vpn-api.service
[Unit]
Description=VPN REST API Server for CRM Integration
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$target_dir
ExecStart=/usr/local/bin/vpn-cli api
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now vpn-api.service 2>/dev/null || true
    echo -e "${GREEN}[✔] Service 'vpn-api.service' (Port 6155) berhasil diaktifkan & berjalan otomatis di background.${NC}"
}

# Function: Interactive Installation Wizard
run_installation() {
    show_banner
    check_root
    check_os

    echo -e "${BOLD}--- INTERACTIVE INSTALLATION WIZARD ---${NC}\n"

    read -p "Masukkan IP FreeRADIUS Server [Misal: 10.0.0.1]: " RADIUS_IP
    if [ -z "$RADIUS_IP" ]; then
        echo -e "${RED}[ERROR] IP FreeRADIUS Server tidak boleh kosong.${NC}"
        exit 1
    fi

    read -p "Masukkan FreeRADIUS Shared Secret: " RADIUS_SECRET
    if [ -z "$RADIUS_SECRET" ]; then
        echo -e "${RED}[ERROR] FreeRADIUS Shared Secret tidak boleh kosong.${NC}"
        exit 1
    fi

    # Generate secure random API key as recommendation
    RANDOM_API_KEY=$(head /dev/urandom | tr -dc A-Za-z0-9 2>/dev/null | head -c 24 || openssl rand -hex 12 2>/dev/null || echo "vpn_api_key_$(date +%s)")

    read -p "Masukkan API Key REST API untuk CRM [Default: $RANDOM_API_KEY]: " INPUT_API_KEY
    API_KEY=${INPUT_API_KEY:-"$RANDOM_API_KEY"}

    read -p "Masukkan Port REST API Gateway [Default: 6155]: " INPUT_API_PORT
    API_PORT=${INPUT_API_PORT:-"6155"}

    read -p "Masukkan Direktori Instalasi [Default: $DEFAULT_INSTALL_DIR]: " INSTALL_DIR
    INSTALL_DIR=${INSTALL_DIR:-"$DEFAULT_INSTALL_DIR"}

    echo -e "\n${CYAN}${BOLD}Ringkasan Konfigurasi:${NC}"
    echo -e "  - FreeRADIUS Server IP : ${GREEN}$RADIUS_IP${NC}"
    echo -e "  - FreeRADIUS Secret    : ${GREEN}$RADIUS_SECRET${NC}"
    echo -e "  - REST API CRM Port    : ${GREEN}$API_PORT${NC}"
    echo -e "  - REST API Key (CRM)   : ${GREEN}$API_KEY${NC}"
    echo -e "  - Lokasi Instalasi     : ${GREEN}$INSTALL_DIR${NC}"
    echo ""

    read -p "Lanjutkan proses instalasi? (y/n) [y]: " CONFIRM
    CONFIRM=${CONFIRM:-"y"}

    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo -e "${YELLOW}Instalasi dibatalkan oleh pengguna.${NC}"
        exit 0
    fi

    install_dependencies
    configure_host
    deploy_files "$INSTALL_DIR" "$RADIUS_IP" "$RADIUS_SECRET" "$API_KEY" "$API_PORT"
    start_containers "$INSTALL_DIR"
    setup_cli "$INSTALL_DIR"
    setup_watchdog_service "$INSTALL_DIR"
    setup_api_service "$INSTALL_DIR"

    echo -e "\n${GREEN}${BOLD}=================================================================${NC}"
    echo -e "${GREEN}${BOLD}   🎉 INSTALASI VPN SERVER BERHASIL DISELESAIKAN!               ${NC}"
    echo -e "${GREEN}${BOLD}=================================================================${NC}"
    echo -e "Untuk mengelola VPN Server, jalankan perintah:${NC}"
    echo -e "   ${CYAN}vpn-cli${NC}                  (Menu Interaktif TUI)"
    echo -e "   ${CYAN}vpn-cli status${NC}           (Melihat Dashboard Connection & Watchdog Status)"
    echo -e "   ${CYAN}vpn-cli users${NC}            (Melihat User VPN Aktif)"
    echo -e "   ${CYAN}vpn-cli api${NC}              (REST API Gateway CRM di Port $API_PORT)"
    echo -e "   ${CYAN}vpn-cli logs -s watchdog${NC} (Melihat Log Auto-Kick Watchdog)"
    echo -e "   ${CYAN}vpn-cli diag${NC}             (Menjalankan Pengujian Diagnostik RADIUS)"
    echo ""
    echo -e "${CYAN}${BOLD}🔑 Kredensial Integrasi CRM REST API:${NC}"
    echo -e "   - Endpoint URL : ${GREEN}http://<IP_SERVER>:${API_PORT}/api/users${NC}"
    echo -e "   - API Key      : ${YELLOW}${API_KEY}${NC}"
    echo -e "   - Header Auth  : ${CYAN}Authorization: Bearer ${API_KEY}${NC}"
    echo ""
}

# Function: Rebuild Containers
rebuild_containers() {
    local target_dir="$1"
    if [ ! -d "$target_dir" ]; then
        echo -e "${RED}[ERROR] Direktori $target_dir tidak ditemukan. Harap lakukan instalasi terlebih dahulu.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}[*] Melakukan Update & Rebuild Container Docker...${NC}"
    cd "$target_dir"
    docker compose up -d --build
    setup_watchdog_service "$target_dir"
    setup_api_service "$target_dir"
    echo -e "${GREEN}[✔] Rebuild selesai! Container, Watchdog & API telah diperbarui dan berjalan otomatis di background.${NC}"
}

# Function: Uninstall VPN Server
uninstall_vpn() {
    local target_dir="$1"
    echo -e "${RED}${BOLD}--- UNINSTALL VPN SERVER ---${NC}"
    read -p "Apakah Anda yakin ingin menghapus VPN Server & semua konfigurasinya dari $target_dir? (y/n): " CONFIRM
    if [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]]; then
        echo -e "${YELLOW}[*] Menghentikan container Docker...${NC}"
        if [ -d "$target_dir" ]; then
            cd "$target_dir" && docker compose down -v --rmi all 2>/dev/null || true
        fi
        
        echo -e "${YELLOW}[*] Menghentikan dan menghapus API & watchdog service...${NC}"
        systemctl stop vpn-api.service 2>/dev/null || true
        systemctl disable vpn-api.service 2>/dev/null || true
        rm -f /etc/systemd/system/vpn-api.service
        systemctl stop vpn-watchdog.service 2>/dev/null || true
        systemctl disable vpn-watchdog.service 2>/dev/null || true
        rm -f /etc/systemd/system/vpn-watchdog.service
        rm -f /var/log/vpn-watchdog.log
        systemctl daemon-reload 2>/dev/null || true

        echo -e "${YELLOW}[*] Menghapus symlink CLI & file instalasi...${NC}"
        rm -f /usr/local/bin/vpn-cli
        rm -rf "$target_dir"
        
        echo -e "${GREEN}[✔] Uninstall selesai! VPN Server berhasil dihapus dari sistem.${NC}"
    else
        echo -e "${YELLOW}Uninstall dibatalkan.${NC}"
    fi
}

# MAIN ENTRY POINT
if [ -d "$DEFAULT_INSTALL_DIR" ] && [ -f "$DEFAULT_INSTALL_DIR/.env" ]; then
    show_banner
    check_root
    echo -e "${YELLOW}[!] VPN Server terdeteksi sudah terinstall di $DEFAULT_INSTALL_DIR.${NC}\n"
    echo -e "Pilih opsi:"
    echo -e "  [1] Re-install / Re-configure RADIUS Settings"
    echo -e "  [2] Update & Rebuild Docker Containers"
    echo -e "  [3] Uninstall VPN Server & Remove CLI"
    echo -e "  [4] Keluar"
    echo ""
    read -p "Pilihan Anda [1-4]: " CHOICE

    case "$CHOICE" in
        1)
            run_installation
            ;;
        2)
            rebuild_containers "$DEFAULT_INSTALL_DIR"
            ;;
        3)
            uninstall_vpn "$DEFAULT_INSTALL_DIR"
            ;;
        4)
            echo -e "${GREEN}Keluar.${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Pilihan tidak valid.${NC}"
            exit 1
            ;;
    esac
else
    run_installation
fi
