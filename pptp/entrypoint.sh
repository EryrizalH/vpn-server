#!/bin/bash
set -e

sysctl -w net.ipv4.ip_forward=1 || true

# ponytail: Universal NAT MASQUERADE for all outgoing interfaces, top-of-chain insert (-I) to bypass UFW default DROP
iptables -t nat -C POSTROUTING -s 192.168.0.0/16 ! -o ppp+ -j MASQUERADE 2>/dev/null || iptables -t nat -I POSTROUTING 1 -s 192.168.0.0/16 ! -o ppp+ -j MASQUERADE
iptables -C FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -C FORWARD -i ppp+ -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -i ppp+ -j ACCEPT
iptables -C FORWARD -o ppp+ -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -o ppp+ -j ACCEPT
iptables -C FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || iptables -I FORWARD 1 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

if [ ! -c /dev/ppp ]; then
    mknod /dev/ppp c 108 0
    chmod 600 /dev/ppp
fi

chmod 755 /usr/sbin/pppd 2>/dev/null || true
mkdir -p /var/run/vpn
touch /var/run/vpn/active_ppp_users.txt
ln -sf /var/run/vpn/active_ppp_users.txt /var/run/active_ppp_users.txt 2>/dev/null || true
echo "0" > /var/run/radius.seq
chmod 666 /var/run/radius.seq

echo "Starting PPTP Server..."
exec pptpd --fg
