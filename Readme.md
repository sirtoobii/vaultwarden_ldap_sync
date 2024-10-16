# Vaultwarden LDAP sync adapter

This python library is a lightweight alternative to the official [Bitwarden Directory Connector](https://bitwarden.com/help/directory-sync/)
aiming to be less "clunkly" than the [vaultwarden_ldap](https://github.com/ViViDboarder/vaultwarden_ldap) (written in Rust) implementation.

Specifically, it invites unseen LDAP users (according to filter) and disables users which vanished from LDAP while even surviving
a user initiated change of the email address in Vaultwarden. Furthermore, its simple architecture should allow for easy integration of other email sources.

## Configuration

In general, this libray is configured using environment variables and supports `.env` files. See [.env.dist](.env.dist)
for a comprehensive list of configuration options.

## Usage

Configure the `.env` file according your needs and run `docker-compose up -d`.

## Development

- Install os requirements: `apt install libldap2-dev libsasl2-dev python3-dev python3-venv`
- Then, after repo checkout:
```shell
cd vaultwarden_ldap_sync

# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Run tests
python3 -m unittest discover -s tests/

# Run main script locally
python3 -m scripts.sync --help
```

### Adding another email source

Adding another email source is as simple as subclassing `EmailSource` and implementing the `get_email_list()` method

Contributions and feedback welcome

