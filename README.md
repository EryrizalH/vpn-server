# Docker VPN Server All-In-One (PPTP & Plain L2TP)

Skrip instalasi dan manajemen otomatis **VPN Server (PPTP & Plain L2TP)** berbasis **Docker** dengan autentikasi **FreeRADIUS** dan **Python Rich CLI**.

Sangat cocok digunakan untuk koneksi VPN MikroTik & Windows Client dengan dukungan routing penuh.

---

## 🚀 Fitur Utama

- **All-in-One Installer (`install.sh`)**: Skrip instalasi interaktif wizard otomatis (install Docker, sysctl, kernel module, UFW rules, & CLI).
- **FreeRADIUS Integration**: Menggunakan `radiusclient` untuk autentikasi user PPTP dan L2TP ke server FreeRADIUS terpusat.
- **Python TUI CLI (`vpn-cli`)**: Tampilan antarmuka terminal interaktif berbasis `python3-rich` untuk monitoring status real-time, statistik koneksi user, filter user, kick/disconnect user, dan log tailing.
- **Auto-Kick User Duplikat & Stuck**: Mekanisme dual-tier (kick-on-connect instan via `ip-up` + background systemd watchdog tiap 10 detik) untuk memutus sesi stuck dan membersihkan user dobel lintas protokol (L2TP/PPTP).
- **Tuned LCP Echo Keepalive**: Interval LCP echo dioptimalkan ke 10s / 3 failure (30 detik) untuk mendeteksi koneksi terputus dengan cepat.
- **Auto Environment Configuration**: Menjaga kerahasiaan kredensial RADIUS menggunakan file `.env` lokal tanpa pembocoran rahasia di repositori.

---

## 🛠️ Persyaratan Sistem

- **OS**: Ubuntu 20.04 / 22.04 / 24.04 atau Debian 11 / 12
- **Akses**: Root / Sudo privileges
- **Port**:
  - `1723/tcp` (PPTP)
  - `1701/udp` (L2TP)
  - `500/udp`, `4500/udp` (IPsec / IKE)

---

## 📥 Instalasi Cepat

Jalankan perintah berikut di terminal server Linux Anda:

```bash
git clone https://github.com/EryrizalH/vpn-server.git /opt/vpn-server
cd /opt/vpn-server
sudo ./install.sh
```

Ikuti petunjuk di layar:
1. Masukkan **IP Server FreeRADIUS** (Contoh: `10.0.0.1`)
2. Masukkan **Shared Secret FreeRADIUS** (Contoh: `my_radius_secret`)
3. Tekan `y` untuk memulai instalasi otomatis.

---

## 🖥️ Penggunaan CLI (`vpn-cli`)

Setelah instalasi selesai, perintah `vpn-cli` dapat dipanggil langsung dari mana saja di terminal:

```bash
# Buka Menu Interaktif TUI
vpn-cli

# Tampilkan Dashboard Status Server
vpn-cli status

# Tampilkan Tabel User Aktif Terhubung
vpn-cli users

# Cari User Berdasarkan Keyword / IP
vpn-cli users -f username_atau_ip

# Disconnect / Kick User Aktif
vpn-cli kick <username_atau_ip>

# Jalankan Uji Diagnostik Server & RADIUS
vpn-cli diag

# Tail Log PPP Real-Time
vpn-cli logs -s l2tp

# Jalankan 1x Pemeriksaan User Duplikat Stuck
vpn-cli watchdog --once

# Jalankan Watchdog Daemon (Foreground)
vpn-cli watchdog --interval 10

# Tail Log Auto-Kick Watchdog
vpn-cli logs -s watchdog
```

---

## 📄 Lisensi

MIT License.
