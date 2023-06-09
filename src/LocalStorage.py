import sqlite3
import time
import logging
from typing import Tuple, List

ALLOWED_USER_STATES = ['ENABLED', 'DISABLED', 'DELETED']


class LocalStore:

    def __init__(self, sqlite_file: str, dry_run=False):
        self.con = sqlite3.connect(sqlite_file)
        self.dry_run_state = {}
        self.is_dry_run = dry_run

    def init_db(self):
        schema = '''
                create table Users
        (
            id           integer not null
                constraint Users_pk
                    primary key autoincrement,
            vw_email     TEXT    not null,
            vw_user_id   TEXT    not null,
            last_touched TEXT    not null,
            state        TEXT    not null
        );
        '''

        self.con.cursor().execute(schema)
        self.con.commit()

    def get_all_users(self) -> tuple:
        res = self.con.cursor().execute("SELECT vw_email, vw_user_id, state FROM Users;")
        enabled = {}
        disabled = {}
        for user_email, user_id, state in res.fetchall():
            if state == 'ENABLED':
                enabled[user_id] = user_email
            else:
                disabled[user_id] = user_email
        return enabled, disabled, {**enabled, **disabled}

    def register_user(self, user_email: str, user_id: str):
        if self.is_dry_run:
            self.dry_run_state[user_id] = {
                'email': user_email,
                'state': 'ENABLED'
            }
        else:
            cursor = self.con.cursor()
            try:
                cursor.execute('INSERT INTO Users (vw_email, vw_user_id, last_touched, state) VALUES (?,?,?,?)',
                               (user_email, user_id, time.time(), 'ENABLED'))
                self.con.commit()
            except sqlite3.IntegrityError as e:
                logging.warning('Could not insert user {}: {}'.format(user_email, e))

    def set_user_state(self, vw_user_id: str, user_state):
        if user_state not in ALLOWED_USER_STATES:
            raise ValueError('Invalid user state. Must be one of: {}'.format(ALLOWED_USER_STATES))
        if self.is_dry_run:
            self.dry_run_state[user_state] = {
                'state': user_state
            }
        else:
            self.con.cursor().execute('UPDATE Users SET state = ?, last_touched = ? WHERE vw_user_id = ?',
                                      (user_state, time.time(), vw_user_id))
            self.con.commit()

    def __del__(self):
        self.con.close()
