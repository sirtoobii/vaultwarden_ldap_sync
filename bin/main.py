import os

from src.LdapConnector import LdapConnector

from dotenv import load_dotenv

from src.VaultwardenConnector import VaultwardenConnector
from src.LocalStorage import LocalStore
import logging

load_dotenv()

logging.basicConfig(format='%(asctime)s %(levelname)-3s [%(filename)s] %(message)s',
                    datefmt='%Y-%m-%d:%H:%M:%S',
                    level=logging.DEBUG)

DRYRUN = False if os.getenv('DRYRUN') is None else True


def collect_change_set(vwc: VaultwardenConnector, ls: LocalStore, ldap_users: list):
    _, _, vw_all = vwc.get_all_users()
    ma_enabled, ma_disabled, ma_all = ls.get_all_users()

    vaultwarden_user_emails_all = [user_values for user_id, user_values in vw_all.items()]
    managed_user_emails_enabled = [user_values for user_id, user_values in ma_enabled.items()]
    managed_user_emails_disabled = [user_values for user_id, user_values in ma_disabled.items()]

    # We want to disable users which are:
    # Present in our LocalStore (state=ENABLED) and NOT present in LDAP
    users_to_disable = set(managed_user_emails_enabled).difference(set(ldap_users))

    # We want to invite users which are:
    # Present in LDAP but not preset in Vaultwarden AND NOT present in LocalStore (state=DISABLED|DELETED)
    users_to_invite = set(ldap_users).difference(
        set(vaultwarden_user_emails_all).union(set(managed_user_emails_disabled)))
    return {
        'invite': users_to_invite,
        'disable': users_to_disable
    }


def sync_state(vwc: VaultwardenConnector, ls: LocalStore, ldap_users: list):
    vw_enabled, vw_disabled, vw_all = vwc.get_all_users()
    ma_enabled, ma_disabled, ma_all = ls.get_all_users()

    vaultwarden_user_emails_disabled = [user_values for user_id, user_values in vw_disabled.items()]
    vaultwarden_user_emails_enabled = [user_values for user_id, user_values in vw_enabled.items()]
    vaultwarden_user_emails_all = [user_values for user_id, user_values in vw_all.items()]
    managed_user_emails_enabled = [user_values for user_id, user_values in ma_enabled.items()]
    managed_user_emails_disabled = [user_values for user_id, user_values in ma_disabled.items()]
    managed_user_emails_all = [user_values for user_id, user_values in ma_all.items()]

    # find users which aren't present in LDAP and Vaultwarden (but our local state)
    vanished_user_emails = set(managed_user_emails_all).difference(set(vaultwarden_user_emails_all).union(ldap_users))

    # find deleted in vaultwarden
    deleted_in_vaultwarden = set(managed_user_emails_all).difference(vaultwarden_user_emails_all)

    # find disabled users in vaultwarden
    disabled_in_vaultwarden = set(vaultwarden_user_emails_disabled).intersection(set(managed_user_emails_enabled))

    enabled_in_vaultwarden = set(vaultwarden_user_emails_enabled).intersection(set(managed_user_emails_disabled))

    return {
        'vanished': vanished_user_emails,
        'deleted': deleted_in_vaultwarden,
        'disabled': disabled_in_vaultwarden,
        'enabled': enabled_in_vaultwarden
    }


if __name__ == '__main__':
    pass