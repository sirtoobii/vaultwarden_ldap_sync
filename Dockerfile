FROM debian:12-slim
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-suggests --no-install-recommends \
        libldap2-dev \
        libsasl2-dev \
        python3-dev \
        python3-pip && \
    rm -rf /var/lib/apt/lists/*

COPY . /src

RUN cd /src && pip install -r requirements.txt --break-system-packages


RUN chmod +x /src/.docker/check_health.sh

ENV LOGFILE=/tmp/ldap_sync.log
ENV LOGLEVEL=INFO
ENV SYNC_INTERVAL_SECONDS=360

HEALTHCHECK --interval=30s --timeout=2s --start-period=60s CMD /src/.docker/check_health.sh /tmp/ldap_sync_health $SYNC_INTERVAL_SECONDS

ENV PYTHONPATH=/src
ENTRYPOINT /usr/bin/python3 /src/scripts/sync.py --interval $SYNC_INTERVAL_SECONDS --heartbeat_file /tmp/ldap_sync_health --logfile $LOGFILE --loglevel $LOGLEVEL
