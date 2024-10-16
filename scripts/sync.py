import argparse
import os
import time

from vaultwarden_ldap_sync.LdapConnector import LdapConnector

from dotenv import load_dotenv

from vaultwarden_ldap_sync.VaultwardenConnector import VaultwardenConnector
from vaultwarden_ldap_sync.LocalStorage import LocalStore
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()


def setup_cli_args():
    parser = argparse.ArgumentParser(
        prog='Vaultwarden LDAP sync',
        description='Keeps your LDAP and Vaultwarden users in sync',
        epilog='Note: environment (VARIABLES) take precedence')
    parser.add_argument('--loglevel', type=str, choices=['WARN', 'INFO', 'DEBUG', 'ERROR'],
                        help='Set loglevel (LOGLEVEL)', default='INFO')
    parser.add_argument('--logfile', type=str,
                        help='Path to logfile, defaults to /tmp/ldap_sync.log', default='/tmp/ldap_sync.log')
    parser.add_argument('--dryrun', action='store_true',
                        help='Do not do any changes just print out log messages (DRYRUN)',
                        default=False)
    parser.add_argument('--runonce', action='store_true',
                        help='Do not enter the main loop, terminate after first run',
                        default=False)
    parser.add_argument('--interval', type=int,
                        help='Interval between sync attempts in seconds (SYNC_INTERVAL_SECONDS)',
                        default=5000)
    parser.add_argument('--override_safe_guard', type=int,
                        help='Override invite/disable safeguard number (MAX_USERS_AT_ONCE)',
                        default=20)
    parser.add_argument('--heartbeat_file', type=str,
                        help='If the main loop processed without any Exception, touch this status file',
                        default='/tmp/ldap_sync_healthy')
    return parser.parse_args()


def setup_logging(logfile: str, loglevel: str):
    logging.basicConfig(format='%(asctime)s %(levelname)-3s [%(filename)s] %(message)s',
                        datefmt='%Y-%m-%d:%H:%M:%S',
                        handlers=[
                            RotatingFileHandler(logfile, maxBytes=5 * 1024 * 1024, backupCount=5),
                            logging.StreamHandler()
                        ],
                        level=logging.getLevelName(loglevel))


def collect_change_set(vwc: VaultwardenConnector, ls: LocalStore, source_email_addresses: list):
    """
    Finds changes made in vaultwarden (and email source) which are not yet reflected in our local state

    :param vwc: Vaultwarden connector instance
    :param ls: LocalStore instance
    :param source_email_addresses: List of source email addresses (invite candidates)
    :return: Returns a dict with the following structure:
        {
            'invite': [list of emails to invite],
            'disable': [list of user_ids to disable],
        }
    """
    _, _, vw_all = vwc.get_all_users()
    ma_enabled, ma_disabled, ma_all = ls.get_all_users()
    ma_enabled_current_email, _, _ = ls.get_all_users()

    vaultwarden_user_emails_all = [user_values for user_id, user_values in vw_all.items()]
    managed_user_emails_enabled = [user_values['invite_email'] for user_id, user_values in ma_enabled.items()]
    managed_users_emails_all_inv = [user_values['invite_email'] for user_id, user_values in ma_all.items()]
    managed_users_emails_all_vw = [user_values['vw_email'] for user_id, user_values in ma_all.items()]
    managed_user_emails_to_user_id = {user_data['invite_email']: user_id for user_id, user_data in
                                      ma_enabled.items()}

    # We want to disable users which are:
    # Present in our LocalStore (state=ENABLED) and NOT present in LDAP
    user_emails_to_disable = set(managed_user_emails_enabled).difference(set(source_email_addresses))

    # We want to invite users which are:
    # Present in LDAP but not preset in Vaultwarden AND NOT present in LocalStore
    known_user_emails = set(vaultwarden_user_emails_all) \
        .union(set(managed_users_emails_all_inv)) \
        .union(set(managed_users_emails_all_vw))
    users_to_invite = set(source_email_addresses).difference(known_user_emails)

    return {
        'invite': users_to_invite,
        'disable': [managed_user_emails_to_user_id[user_email] for user_email in user_emails_to_disable]
    }


def sync_state(vwc: VaultwardenConnector, ls: LocalStore, source_email_addresses: list):
    """
    Finds changes made in vaultwarden (and email source) which are not yet reflected in our local state

    :param vwc: Vaultwarden connector instance
    :param ls: LocalStore instance
    :param source_email_addresses: List of source email addresses (invite candidates)
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
    vanished_user_emails = set(managed_user_emails_all).difference(
        set(vaultwarden_user_emails_all).union(source_email_addresses))

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
            source_email_addresses.append(ma_all[user_id]['vw_email'])

    # find users which aren't present in LDAP and Vaultwarden (but our local state)
    vanished_user_emails = set(managed_user_emails_all).difference(
        set(vaultwarden_user_emails_all).union(source_email_addresses))

    return {
        'vanished': [managed_email_to_user_id[user_email] for user_email in vanished_user_emails],
        'deleted': deleted_user_ids,
        'disabled': disabled_user_ids,
        'enabled': enabled_user_ids,
        'email_changed': email_changed,
        'all_managed_users': ma_all,
        'vaultwarden_all_users': vw_all
    }


if __name__ == '__main__':
    args = setup_cli_args()
    log_level = os.getenv('LOGLEVEL', args.loglevel)
    log_file = os.getenv('LOGFILE', args.logfile)
    setup_logging(log_file, log_level)
    ls = LocalStore(os.getenv('SQLITE_DB'))
    vwc = VaultwardenConnector()
    ldc = LdapConnector(source_name="LDAP")
    safe_guard = int(os.getenv('MAX_USERS_AT_ONCE', args.override_safe_guard))
    is_dry_run = os.getenv('DRYRUN', 0) == '1' or args.dryrun
    ldap_emails = ldc.get_email_list()

    logging.info('Starting...')
    logging.info('DRYRUN: {}'.format(is_dry_run))
    logging.info('LDAP server: {}'.format(os.getenv('LDAP_SERVER')))
    logging.info('Vaultwarden url: {}'.format(os.getenv('VAULTWARDEN_URL')))

    log_prefix = ""
    if is_dry_run:
        log_prefix = "[DRYRUN] "

    while True:
        try:
            # first sync state
            state_update = sync_state(vwc, ls, ldap_emails)

            # State summary
            logging.debug('Found {} user(s) in Vaultwarden'.format(len(state_update['vaultwarden_all_users'])))
            logging.debug('Found {} vanished user(s)'.format(len(state_update['vanished'])))
            logging.debug('Found {} deleted user(s)'.format(len(state_update['deleted'])))
            logging.debug('Found {} disabled user(s)'.format(len(state_update['disabled'])))
            logging.debug('Found {} enabled user(s)'.format(len(state_update['enabled'])))
            logging.debug('Found {} user(s) with changed emails'.format(len(state_update['email_changed'])))

            for user_id in state_update['vanished']:
                if os.getenv('CLEANUP_VANISHED_USERS') == '1':
                    if not is_dry_run:
                        ls.delete_user(user_id)
                    logging.info(
                        '{}Cleanup vanished user: {}'.format(log_prefix,
                                                             state_update['all_managed_users'][user_id][
                                                                 'invite_email']))

            for user_id in state_update['deleted']:
                if not is_dry_run:
                    ls.set_user_state(user_id, 'DELETED')
                logging.info(
                    '{}Set state to DELETED for: {}'.format(log_prefix,
                                                            state_update['all_managed_users'][user_id]['invite_email']))

            for user_id in state_update['disabled']:
                if not is_dry_run:
                    ls.set_user_state(user_id, 'DISABLED')
                logging.info(
                    '{}Set state to DISABLED for: {}'.format(log_prefix,
                                                             state_update['all_managed_users'][user_id][
                                                                 'invite_email']))

            for user_id, change_data in state_update['email_changed'].items():
                if not is_dry_run:
                    ls.update_vw_email(user_id, change_data['to'])
                logging.info('{}Changed email from {} to {}'.format(log_prefix, change_data['from'], change_data['to']))

            for user_id in state_update['enabled']:
                if os.getenv('UNTIE_RE-ENABLED_USERS') == '1':
                    if not is_dry_run:
                        ls.delete_user(user_id)
                    logging.info(
                        '{}User {} forcefully enabled by Admin. Permanently untie this user from automatic management'.format(
                            log_prefix,
                            state_update['all_managed_users'][user_id]['invite_email']))

            # then search for users to invite or delete
            invite_or_delete = collect_change_set(vwc, ls, ldap_emails)

            # Change summary
            logging.debug('{}Found {} user(s) to invite'.format(log_prefix, len(invite_or_delete['invite'])))
            logging.debug('{}Found {} user(s) to disable'.format(log_prefix, len(invite_or_delete['disable'])))

            if len(invite_or_delete['disable']) > safe_guard or len(invite_or_delete['invite']) > safe_guard:
                logging.warning(
                    'Users to disable (or invite) exceed the safe guard limit {} if you are sure increase the MAX_USERS_AT_ONCE env var'.format(
                        safe_guard))
            else:
                for user_email in invite_or_delete['invite']:
                    if not is_dry_run:
                        user_id = vwc.invite_user(user_email)
                        ls.register_user(user_email, user_id)
                    logging.info('{}Invite user {}'.format(log_prefix, user_email))

                for user_id in invite_or_delete['disable']:
                    if not is_dry_run:
                        vwc.disable_user(user_id)
                        ls.set_user_state(user_id, 'DISABLED')
                    logging.info(
                        '{}Disable user {}'.format(log_prefix,
                                                   state_update['all_managed_users'][user_id]['invite_email']))
            if args.runonce:
                exit(0)
            # Touch heartbeat file
            with open(args.heartbeat_file, 'a'):
                os.utime(args.heartbeat_file, None)
            time.sleep(args.interval)
        except Exception as e:
            logging.error('Something went wrong. Error: {}'.format(e))
            time.sleep(args.interval)
