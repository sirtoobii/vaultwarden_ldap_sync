import argparse
import os
import time
import traceback

from dotenv import load_dotenv

from vaultwarden_user_sync.backends.vaultwarden import VaultwardenConnector
from vaultwarden_user_sync.backends.localstore import LocalStore
import logging
from logging.handlers import RotatingFileHandler

from vaultwarden_user_sync.compare import SyncResult
from vaultwarden_user_sync.email_sources.ldap import LdapConnector

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
                        default=10)
    parser.add_argument('--override_safe_guard', type=int,
                        help='Override invite/disable safeguard number (MAX_USERS_AT_ONCE)',
                        default=20)
    parser.add_argument('--heartbeat_file', type=str,
                        help='If the main loop processed without any Exception, touch this status file',
                        default='/tmp/ldap_sync_healthy')
    parser.add_argument('--reset',
                        help='Clears local state, unties all users from management! Exits after completion. Use with caution (VUS_RESET)',
                        action="store_true", default=False)
    parser.add_argument('--adopt',
                        help='Adopt users who are present both in the email source and Vaultwarden. Exits after completion. (VUS_ADOPT)',
                        action="store_true", default=False)
    return parser.parse_args()


def setup_logging(logfile: str, loglevel: str):
    logging.basicConfig(format='%(asctime)s %(levelname)-3s [%(filename)s] %(message)s',
                        datefmt='%Y-%m-%d:%H:%M:%S',
                        handlers=[
                            RotatingFileHandler(logfile, maxBytes=5 * 1024 * 1024, backupCount=5),
                            logging.StreamHandler()
                        ],
                        level=logging.getLevelName(loglevel))


if __name__ == '__main__':
    args = setup_cli_args()
    log_level = os.getenv('LOGLEVEL', args.loglevel)
    log_file = os.getenv('LOGFILE', args.logfile)
    setup_logging(log_file, log_level)
    ls = LocalStore(os.getenv('SQLITE_DB'))
    vwc = VaultwardenConnector()
    ems = LdapConnector(source_name="LDAP")
    safe_guard = int(os.getenv('MAX_USERS_AT_ONCE', args.override_safe_guard))
    is_dry_run = os.getenv('DRYRUN', "0") == '1' or args.dryrun
    is_reset = os.getenv('VUS_RESET', "0") == '1' or args.reset
    should_adopt = os.getenv('VUS_ADOPT', "0") == '1' or args.adopt

    logging.info('Starting...')
    logging.info(f'DRYRUN: {is_dry_run}')
    logging.info(f"LDAP server: {os.getenv('LDAP_SERVER')}")
    logging.info(f"Vaultwarden URL: {os.getenv('VAULTWARDEN_URL')}")

    log_prefix = ""
    if is_dry_run:
        log_prefix = "[DRYRUN] "

    if args.reset:
        if not is_dry_run:
            ls.truncate()
        args.runonce = True
        logging.warning(f"{log_prefix} Local state reset! Will terminate afterwards!")

    if should_adopt:
        args.runonce = True
        logging.warning(f"{log_prefix} Running in adaption mode. Will terminate after this attempt")

    while True:
        try:
            # first sync state
            ldap_emails = ems.get_email_list()
            sync_result = SyncResult.factory(vwc, ls, ldap_emails)

            logging.debug(sync_result.summary())

            if args.adopt:
                if len(sync_result.adoption_candidates) == 0:
                    logging.info("Nothing to adopt")
                else:
                    for vw_user in sync_result.adoption_candidates:
                        state = "ENABLED" if vw_user.enabled else "DISABLED"
                        if not is_dry_run:
                            ls.register_user(user_email=vw_user.email, user_id=vw_user.user_id, state=state)
                        logging.info(f"{log_prefix} Adopted {vw_user.email}")

            for user_email in sync_result.email_vanished_in_both:
                if os.getenv('CLEANUP_VANISHED_USERS') == '1':
                    if not is_dry_run:
                        ls.delete_user_by_email(user_email)
                    logging.info(
                        f'{log_prefix} Cleanup vanished user: {user_email}')

            for user_id in sync_result.user_ids_vanished_in_vw:
                if not is_dry_run:
                    ls.set_user_state(user_id, 'DELETED')
                logging.info(
                    f"{log_prefix} Set state to DELETED for: {sync_result.get_ma_user_by_id(user_id).invite_email}")

            for user_id in sync_result.user_ids_disabled_in_vw:
                if not is_dry_run:
                    ls.set_user_state(user_id, 'DISABLED')
                logging.info(
                    f"{log_prefix} Set state to DISABLED for: {sync_result.get_ma_user_by_id(user_id).invite_email}")

            for changed_user in sync_result.users_with_changed_email:
                if not is_dry_run:
                    ls.update_vw_email(changed_user.user_id, changed_user.new_email)
                logging.info(f'{log_prefix}Changed email from {changed_user.old_email} to {changed_user.new_email}')

            for user_id in sync_result.user_ids_enabled_in_vw:
                if os.getenv('UNTIE_RE-ENABLED_USERS') == '1':
                    if not is_dry_run:
                        ls.delete_user_by_id(user_id)
                    logging.warning(
                        f"{log_prefix} User {sync_result.get_ma_user_by_id(user_id).invite_email} forcefully enabled by Admin. Permanently untie this user from automatic management")

            if (len(sync_result.pending_changes.enable_user_ids) > safe_guard or
                    len(sync_result.pending_changes.disable_user_ids) > safe_guard or
                    len(sync_result.pending_changes.invite_emails) > safe_guard):
                logging.warning(
                    f"{log_prefix} Users to disable/invite/enable exceed the safe guard limit {safe_guard} if you are sure increase the MAX_USERS_AT_ONCE env var")
            else:
                for user_email in sync_result.pending_changes.invite_emails:
                    if not is_dry_run:
                        user_id = vwc.invite_user(user_email)
                        ls.register_user(user_email, user_id)
                    logging.info(f'{log_prefix} Invite user {user_email}')

                for user_id in sync_result.pending_changes.disable_user_ids:
                    if not is_dry_run:
                        vwc.disable_user(user_id)
                        ls.set_user_state(user_id, 'DISABLED')
                    logging.info(
                        f'{log_prefix} User {sync_result.get_ma_user_by_id(user_id).vw_email} DISABLED in Vaultwarden')

                for user_id in sync_result.pending_changes.enable_user_ids:
                    if not is_dry_run:
                        vwc.enable_user(user_id)
                        ls.set_user_state(user_id, 'ENABLED')
                    logging.info(
                        f'{log_prefix} User {sync_result.get_ma_user_by_id(user_id).vw_email} ENABLED in Vaultwarden')

            if args.runonce:
                logging.warning(
                    "Exiting as requested. Either --run_once is explicitly set or implicitly through --reset or --adopt")
                exit(0)
            # Touch heartbeat file
            with open(args.heartbeat_file, 'a'):
                os.utime(args.heartbeat_file, None)
            time.sleep(args.interval)
        except Exception as e:
            logging.error(f'Something went wrong. Error: {e}')
            logging.debug(traceback.format_exc())
            time.sleep(args.interval)
