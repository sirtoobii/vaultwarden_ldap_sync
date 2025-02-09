import os.path
import sqlite3
import time
import logging
from dataclasses import dataclass
from typing import Tuple, List, Literal

ALLOWED_USER_STATES = ['ENABLED', 'DISABLED', 'DELETED']


@dataclass
class ManagedUser:
    vw_user_id: str
    # Email kept in sync with Vaultwarden
    vw_email: str
    # Original invite email
    invite_email: str
    enabled: bool


class LocalStore:

    def __init__(self, sqlite_file: str):
        self.con = sqlite3.connect(sqlite_file)
        self.init_db()

    def init_db(self):
        schema = '''
                create table if not exists Users
        (
            id           integer not null
                constraint Users_pk
                    primary key autoincrement,
            invite_email TEXT    not null,
            vw_email     TEXT    not null,
            vw_user_id   TEXT    not null,
            last_touched TEXT    not null,
            state        TEXT    not null
        );
        '''

        self.con.cursor().execute(schema)
        self.con.commit()

    def get_all_managed_users(self) -> List[ManagedUser]:
        """
        Get all managed users (-> All users which have been invited by this script)
        :return: A 3-tuple containing enabled, disabled/deleted and all users
        """
        res = self.con.cursor().execute("SELECT invite_email, vw_email, vw_user_id, state FROM Users;")
        managed_users = []
        for invite_email, vw_email, vw_user_id, state in res.fetchall():
            managed_users.append(
                ManagedUser(
                    vw_user_id=vw_user_id,
                    vw_email=vw_email,
                    enabled=state == 'ENABLED',
                    invite_email=invite_email
                )
            )
        return managed_users

    def register_user(self, user_email: str, user_id: str,
                      state: Literal["ENABLED", "DISABLED", "DELETED"] = "ENABLED"):
        """
        Register user as a 'managed user'
        :param user_email: Invitation Email
        :param user_id: User ID returned by Vaultwarden
        :return: None
        """
        cursor = self.con.cursor()
        try:

            cursor.execute(
                'INSERT INTO Users (invite_email, vw_email, vw_user_id, last_touched, state) VALUES (?,?,?,?,?)',
                (user_email, user_email, user_id, time.time(), state))
            self.con.commit()
        except sqlite3.IntegrityError as e:
            logging.warning('Could not insert user {}: {}'.format(user_email, e))

    def set_user_state(self, vw_user_id: str, user_state: Literal["ENABLED", "DISABLED", "DELETED"]):
        """
        Set user state (meant to reflect the state in vaultwarden)
        :param vw_user_id: Vaultwarden User ID
        :param user_state: One of ENABLED,DISABLED or DELETED
        :return: None
        """
        if user_state not in ALLOWED_USER_STATES:
            raise ValueError('Invalid user state. Must be one of: {}'.format(ALLOWED_USER_STATES))
        else:
            self.con.cursor().execute('UPDATE Users SET state = ?, last_touched = ? WHERE vw_user_id = ?',
                                      (user_state, time.time(), vw_user_id))
            self.con.commit()

    def update_vw_email(self, vw_user_id: str, new_vw_email: str):
        """
        Update vaultwarden email (after user updated his email in vaultwarden)
        :param vw_user_id: Vaultwarden User ID
        :param new_vw_email: New email
        :return: None
        """
        self.con.cursor().execute('UPDATE Users SET vw_email = ?, last_touched = ? WHERE vw_user_id = ?',
                                  (new_vw_email, time.time(), vw_user_id))
        self.con.commit()

    def delete_user_by_id(self, vw_user_id: str):
        self.con.cursor().execute('DELETE FROM Users WHERE vw_user_id = ?', (vw_user_id,))
        self.con.commit()

    def delete_user_by_email(self, vw_user_email: str):
        self.con.cursor().execute('DELETE FROM Users WHERE vw_email = ?', (vw_user_email,))
        self.con.commit()

    def truncate(self):
        """
        Empty local database
        """
        self.con.cursor().execute('DELETE FROM Users;')

    def __del__(self):
        self.con.close()
