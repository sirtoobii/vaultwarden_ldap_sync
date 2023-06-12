import argparse
import os

from src.LdapConnector import LdapConnector

from dotenv import load_dotenv

from src.VaultwardenConnector import VaultwardenConnector
from src.LocalStorage import LocalStore
import logging

load_dotenv()

parser = argparse.ArgumentParser(
    prog='Vaultwarden LDAP sync',
    description='Keeps your LDAP and Vaultwarden users in sync',
    epilog='This program comes with no warranty and I´m happy to review your contributions')

parser.add_argument('--loglevel', metavar='L', type=str, choices=['WARN', 'INFO', 'DEBUG', 'ERROR'],
                    help='Set loglevel', default='INFO')
parser.add_argument('--dryrun', metavar='D', action='store_true',
                    help='Do not do any changes just print out log messages',
                    default=False)

logging.basicConfig(format='%(asctime)s %(levelname)-3s [%(filename)s] %(message)s',
                    datefmt='%Y-%m-%d:%H:%M:%S',
                    level=logging.INFO)


def collect_change_set(vwc: VaultwardenConnector, ls: LocalStore, ldap_users: list):
    """
    Finds changes made in vaultwarden (and ldap) which are not yet reflected in our local state

    :param vwc: Vaultwarden connector instance
    :param ls: LocalStore instance
    :param ldap_users: List of email addresses resulting from the LDAP query
    :return: Returns a dict with the following structure:
        {
            'invite': [list of emails to invite],
            'disable': [list of user_id to disable],
        }
    """
    _, _, vw_all = vwc.get_all_users()
    ma_enabled, ma_disabled, ma_all = ls.get_all_users()
    ma_enabled_current_email, _, _ = ls.get_all_users()

    vaultwarden_user_emails_all = [user_values for user_id, user_values in vw_all.items()]
    managed_user_emails_enabled = [user_values['invite_email'] for user_id, user_values in ma_enabled.items()]
    managed_users_emails_all_inv = [user_values['invite_email'] for user_id, user_values in ma_all.items()]
    managed_users_emails_all_vw = [user_values['vw_email'] for user_id, user_values in ma_all.items()]
    managed_user_emails_to_user_id = {user_data['invite_email']: user_id for user_id, user_data in ma_enabled.items()}

    # We want to disable users which are:
    # Present in our LocalStore (state=ENABLED) and NOT present in LDAP
    user_emails_to_disable = set(managed_user_emails_enabled).difference(set(ldap_users))

    # We want to invite users which are:
    # Present in LDAP but not preset in Vaultwarden AND NOT present in LocalStore
    known_user_emails = set(vaultwarden_user_emails_all) \
        .union(set(managed_users_emails_all_inv)) \
        .union(set(managed_users_emails_all_vw))
    users_to_invite = set(ldap_users).difference(known_user_emails)

    return {
        'invite': users_to_invite,
        'disable': [managed_user_emails_to_user_id[user_email] for user_email in user_emails_to_disable]
    }


def sync_state(vwc: VaultwardenConnector, ls: LocalStore, ldap_users: list):
    """
    Finds changes made in vaultwarden (and ldap) which are not yet reflected in our local state

    :param vwc: Vaultwarden connector instance
    :param ls: LocalStore instance
    :param ldap_users: List of email addresses resulting from the LDAP query
    :return: Returns a dict with the following structure:
        {
            'vanished': [managed_email_to_user_id[user_email] for user_email in vanished_user_emails],
            'deleted': deleted_user_ids,
            'disabled': disabled_user_ids,
            'enabled': enabled_user_ids,
            'email_changed': {user_id: {'from': xy@old.com, 'to': xy@new.com}}
        }
    """

    vw_enabled, vw_disabled, vw_all = vwc.get_all_users()
    ma_enabled, ma_disabled, ma_all = ls.get_all_users()

    vaultwarden_user_emails_all = [user_values for user_id, user_values in vw_all.items()]
    managed_user_emails_all = [user_values['vw_email'] for user_id, user_values in ma_all.items()]
    managed_email_to_user_id = {user_data['invite_email']: user_id for user_id, user_data in ma_all.items()}

    # find users which aren't present in LDAP and Vaultwarden (but our local state)
    vanished_user_emails = set(managed_user_emails_all).difference(set(vaultwarden_user_emails_all).union(ldap_users))

    # find deleted in vaultwarden
    deleted_user_ids = set(ma_all.keys()).difference(vw_all.keys())

    # find disabled users in vaultwarden
    disabled_user_ids = set(vw_disabled.keys()).intersection(set(ma_enabled.keys()))

    # find enabled users in vaultwarden
    enabled_user_ids = set(vw_enabled.keys()).intersection(set(ma_disabled.keys()))

    # find users which changed their email address (in vaultwarden)
    email_changed = {}
    for user_id in set(ma_all.keys()).intersection(vw_all.keys()):
        if ma_all[user_id]['vw_email'] != vw_all[user_id]:
            email_changed[user_id] = {'from': ma_all[user_id]['vw_email'], 'to': vw_all[user_id]}
            # temporarily add old email to ldap users to prevent it from appearing in vanished
            ldap_users.append(ma_all[user_id]['vw_email'])

    # find users which aren't present in LDAP and Vaultwarden (but our local state)
    vanished_user_emails = set(managed_user_emails_all).difference(set(vaultwarden_user_emails_all).union(ldap_users))

    return {
        'vanished': [managed_email_to_user_id[user_email] for user_email in vanished_user_emails],
        'deleted': deleted_user_ids,
        'disabled': disabled_user_ids,
        'enabled': enabled_user_ids,
        'email_changed': email_changed,
        'all_managed_users': ma_all
    }


if __name__ == '__main__':
    ls = LocalStore(os.getenv('SQLITE_DB'))
    vwc = VaultwardenConnector()
    ldc = LdapConnector()
    safe_guard = int(os.getenv('MAX_USERS_AT_ONCE', 20))
    ldap_emails = ldc.get_email_list()

    # first sync state
    state_update = sync_state(vwc, ls, ldap_emails)

    # State summary
    logging.info('Found {} vanished user(s)'.format(len(state_update['vanished'])))
    logging.info('Found {} deleted user(s)'.format(len(state_update['deleted'])))
    logging.info('Found {} disabled user(s)'.format(len(state_update['disabled'])))
    logging.info('Found {} enabled user(s)'.format(len(state_update['enabled'])))
    logging.info('Found {} user(s) with changed emails'.format(len(state_update['email_changed'])))

    for user_id in state_update['vanished']:
        if os.getenv('CLEANUP_VANISHED_USERS') == '1':
            ls.delete_user(user_id)
            logging.info('Cleanup vanished user: {}'.format(state_update['all_managed_users'][user_id]['invite_email']))

    for user_id in state_update['deleted']:
        ls.set_user_state(user_id, 'DELETED')
        logging.info('Set state to DELETED for: {}'.format(state_update['all_managed_users'][user_id]['invite_email']))

    for user_id in state_update['disabled']:
        ls.set_user_state(user_id, 'DISABLED')
        logging.info('Set state to DISABLED for: {}'.format(state_update['all_managed_users'][user_id]['invite_email']))

    for user_id, change_data in state_update['email_changed'].items():
        ls.update_vw_email(user_id, change_data['to'])
        logging.info('Changed email from {} to {}'.format(change_data['from'], change_data['to']))

    for user_id in state_update['enabled']:
        if os.getenv('UNTIE_RE-ENABLED_USERS') == '1':
            ls.delete_user(user_id)
            logging.info(
                'User {} forcefully enabled by Admin. Permanently untie this user from automatic management'.format(
                    state_update['all_managed_users'][user_id]['invite_email']))

    # then search for users to invite or delete
    invite_or_delete = collect_change_set(vwc, ls, ldap_emails)

    # Change summary
    logging.info('Found {} user(s) to invite'.format(len(invite_or_delete['invite'])))
    logging.info('Found {} user(s) to disable'.format(len(invite_or_delete['disable'])))

    if len(invite_or_delete['disable']) > safe_guard or len(invite_or_delete['invite']) > safe_guard:
        logging.warning(
            'Users to disable (or invite) exceed the safe guard limit {} if you are sure increase the MAX_USERS_AT_ONCE env var'.format(
                safe_guard))
    else:
        for user_email in invite_or_delete['invite']:
            user_id = vwc.invite_user(user_email)
            ls.register_user(user_email, user_id)
            logging.info('Invite user {}'.format(user_email))

        for user_id in invite_or_delete['disable']:
            vwc.disable_user(user_id)
            ls.set_user_state(user_id, 'DISABLED')
            logging.info('Disable user {}'.format(state_update['all_managed_users'][user_id]['invite_email']))
