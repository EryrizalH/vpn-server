# Docker VPN Server All-In-One (PPTP & Plain L2TP)

Skrip instalasi dan manajemen otomatis **VPN Server (PPTP & Plain L2TP)** berbasis **Docker** dengan autentikasi **FreeRADIUS** dan **Python Rich CLI**.

Sangat cocok digunakan untuk koneksi VPN MikroTik & Windows Client dengan dukungan routing penuh.

---

## 🚀 Fitur Utama

- **All-in-One Installer (`install.sh`)**: Skrip instalasi interaktif wizard otomatis (install Docker, sysctl, kernel module, UFW rules, & CLI).
- **FreeRADIUS Integration**: Menggunakan `radiusclient` untuk autentikasi user PPTP dan L2TP ke server FreeRADIUS terpusat.
- **Python TUI CLI (`vpn-cli`)**: Tampilan antarmuka terminal interaktif berbasis `python3-rich` untuk monitoring status real-time, statistik koneksi user, filter user, kick/disconnect user, dan log tailing.
- **Auto-Kick User Duplikat & Stuck**: Mekanisme dual-tier (kick-on-connect instan via `ip-up` + background systemd watchdog tiap 10 detik) untuk memutus sesi stuck dan membersihkan user dobel lintas protokol (L2TP/PPTP).
- **REST API Gateway CRM**: Server HTTP REST API terintegrasi (`vpn-api.service` di port `6155`) untuk mengambil data user & IP aktif secara real-time, filter query, dan disconnect/kick user langsung dari CRM.
- **Tuned LCP Echo Keepalive**: Interval LCP echo dioptimalkan ke 10s / 3 failure (30 detik) untuk mendeteksi koneksi terputus dengan cepat.
- **Auto Environment Configuration**: Menjaga kerahasiaan kredensial RADIUS & API Key menggunakan file `.env` lokal tanpa pembocoran rahasia di repositori.

---

## 🛠️ Persyaratan Sistem

- **OS**: Ubuntu 20.04 / 22.04 / 24.04 atau Debian 11 / 12
- **Akses**: Root / Sudo privileges
- **Port**:
  - `1723/tcp` (PPTP)
  - `1701/udp` (L2TP)
  - `500/udp`, `4500/udp` (IPsec / IKE)
  - `6155/tcp` (REST API CRM Gateway)

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

# Jalankan REST API Server di Foreground
vpn-cli api --port 6155
```

---

## 🌐 Integrasi REST API (Untuk CRM)

VPN Server menyediakan REST API internal di port `6155` (dikelola oleh `vpn-api.service`).

### Autentikasi
Gunakan Header `Authorization: Bearer <API_KEY>` atau `X-API-Key: <API_KEY>`.
* **API Key**: Dibuat secara otomatis (*random secure token*) saat menjalankan wizard `install.sh` atau dapat diisi manual pada file `.env` (`API_KEY=...`)
* **Port API**: Default `6155` (dapat diubah di `.env` via `API_PORT=...`)

### Daftar Endpoint

| Method | Endpoint | Keterangan |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check & jumlah user aktif (tanpa auth) |
| `GET` | `/api/users` | List seluruh user & IP aktif terhubung |
| `GET` | `/api/users?username=alice` | Filter data aktif berdasarkan username |
| `GET` | `/api/users?ip=192.168.100.10` | Filter data aktif berdasarkan IP VPN |
| `GET` | `/api/users/<username>` | Detail user aktif tertentu |
| `POST` | `/api/users/<username>/kick` | Disconnect / Kick sesi user dari server |
| `POST` | `/api/kick` | Disconnect dengan query `?target=...` atau body JSON |

### Contoh Request (cURL)

**1. Ambil Semua User & IP Aktif:**
```bash
curl -s -H "Authorization: Bearer <API_KEY>" \
  http://<IP_VPN_SERVER>:6155/api/users
```

*Contoh Respon:*
```json
{
  "status": "success",
  "total": 1,
  "data": [
    {
      "username": "client_abc",
      "ip": "192.168.100.10",
      "protocol": "L2TP",
      "interface": "ppp0",
      "connected_at": "2026-09-18T10:15:30Z",
      "timestamp": 1726629330,
      "uptime_seconds": 360
    }
  ]
}
```

**2. Filter Berdasarkan Username:**
```bash
curl -s -H "Authorization: Bearer <API_KEY>" \
  "http://<IP_VPN_SERVER>:6155/api/users?username=client_abc"
```

**3. Kick / Putuskan Koneksi User:**
```bash
curl -s -X POST -H "Authorization: Bearer <API_KEY>" \
  http://<IP_VPN_SERVER>:6155/api/users/client_abc/kick
```

*Contoh Respon:*
```json
{
  "status": "success",
  "message": "User 'client_abc' successfully disconnected",
  "kicked": true,
  "total_kicked": 1
}
```

---

## 📄 Lisensi

MIT License.
