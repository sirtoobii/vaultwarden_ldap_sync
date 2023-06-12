FROM debian:11-slim

ENV DEBIAN_FRONTEND noninteractive
RUN apt update && apt install -y libldap2-dev libsasl2-dev python3-dev python3-venv

COPY . /src

RUN cd /src && pip install -r requirements.txt

