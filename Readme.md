# Vaultwarden LDAP sync adapter

This python libray combines the functionality of the
official [Bitwarden Directory Connector](https://bitwarden.com/help/directory-sync/)
and [vaultwarden_ldap](https://github.com/ViViDboarder/vaultwarden_ldap). Namely, it invites unseen LDAP users (
according to filter) and disables users which vanished from ldap while even surviving
a user initiated change of the email address in vaultwarden.

## Configuration

In general, this libray is configured using environment variables and supports `.env` files. See [.env.dist](.env.dist)
for a comprehensive list of configuration options.

## Usage

## Development

## TL;DR;

Configure `.env` according your needs and hit `docker-compose up -d`. 

## OS requirements

```shell
apt install libldap2-dev libsasl2-dev python3-dev
```

- User changes email

