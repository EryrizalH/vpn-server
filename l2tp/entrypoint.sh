#!/bin/bash
set -e

sysctl -w net.ipv4.ip_forward=1 || true

# IPTables forwarding and NAT setup for Full Tunnel & Inter-VPN routing
iptables -t nat -C POSTROUTING -s 192.168.0.0/16 -o eth0 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 192.168.0.0/16 -o eth0 -j MASQUERADE
iptables -C FORWARD -i ppp+ -j ACCEPT 2>/dev/null || iptables -A FORWARD -i ppp+ -j ACCEPT
iptables -C FORWARD -o ppp+ -j ACCEPT 2>/dev/null || iptables -A FORWARD -o ppp+ -j ACCEPT
iptables -C FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

if [ ! -c /dev/ppp ]; then
    mknod /dev/ppp c 108 0
    chmod 600 /dev/ppp
fi

if ! mountpoint -q /dev/pts; then
    mkdir -p /dev/pts
    mount -t devpts devpts /dev/pts || true
fi

chmod 755 /usr/sbin/pppd 2>/dev/null || true

mkdir -p /var/run/xl2tpd /var/run/vpn
touch /var/run/vpn/active_ppp_users.txt
ln -sf /var/run/vpn/active_ppp_users.txt /var/run/active_ppp_users.txt 2>/dev/null || true
echo "0" > /var/run/radius.seq
chmod 666 /var/run/radius.seq

echo "Starting L2TP Server (xl2tpd)..."
exec xl2tpd -D -c /etc/xl2tpd/xl2tpd.conf
