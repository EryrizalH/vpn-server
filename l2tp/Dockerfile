FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    xl2tpd \
    ppp \
    freeradius-utils \
    iptables \
    iproute2 \
    procps \
    logrotate \
    && rm -rf /var/lib/apt/lists/*

COPY xl2tpd.conf /etc/xl2tpd/xl2tpd.conf
COPY options.xl2tpd /etc/ppp/options.xl2tpd
COPY radiusclient.conf /etc/radiusclient/radiusclient.conf
COPY servers /etc/radiusclient/servers
COPY dictionary /etc/radiusclient/dictionary
COPY port-id-map /etc/radiusclient/port-id-map
COPY ip-up-active /etc/ppp/ip-up.d/active_user
COPY ip-down-active /etc/ppp/ip-down.d/active_user
COPY logrotate-ppp /etc/logrotate.d/ppp
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh /etc/ppp/ip-up.d/active_user /etc/ppp/ip-down.d/active_user && chmod 600 /etc/radiusclient/servers /etc/logrotate.d/ppp

EXPOSE 1701/udp

ENTRYPOINT ["/entrypoint.sh"]
