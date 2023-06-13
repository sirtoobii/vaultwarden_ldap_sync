import os
import unittest

from scripts.sync import sync_state
from vaultwarden_ldap_sync.LocalStorage import LocalStore
from vaultwarden_ldap_sync.VaultwardenConnector import VaultwardenConnector


class SyncStateTest(unittest.TestCase):
    vwc = None
    ls = None
    user_id1 = ''
    user_id2 = ''
    user_email1 = 'user1@test.com'
    user_email2 = 'user2@test.com'

    @classmethod
    def setUp(cls) -> None:
        cls.vwc = VaultwardenConnector(test_mode=True)
        cls.ls = LocalStore('test_sync.db')
        cls.ls.init_db()
        cls.user_id1 = cls.vwc.invite_user(cls.user_email1)
        cls.user_id2 = cls.vwc.invite_user(cls.user_email2)
        cls.ls.register_user(cls.user_email1, cls.user_id1)
        cls.ls.register_user(cls.user_email2, cls.user_id2)

    def test_nothing_to_sync(self):
        # Nothing to sync
        state_update = sync_state(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update['vanished'], [])
        self.assertEqual(state_update['deleted'], set())
        self.assertEqual(state_update['disabled'], set())

    def test_user_disabled_in_vw(self):
        # User disabled in Vaultwarden
        self.vwc.disable_user(self.user_id1)
        state_update = sync_state(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update['disabled'], {self.user_id1})
        self.assertEqual(state_update['vanished'], [])
        self.assertEqual(state_update['deleted'], set())

    def test_user_deleted_in_vw(self):
        # User deleted in Vaultwarden
        self.vwc._delete_user(self.user_id1)
        state_update = sync_state(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update['deleted'], {self.user_id1})
        self.assertEqual(state_update['disabled'], set())
        self.assertEqual(state_update['vanished'], [])

    def test_user_enabled_in_vw(self):
        # User enabled in vaultwarden
        user3_id = self.vwc.invite_user('blublu@tester.com')
        self.ls.register_user('blublu@tester.com', user3_id)
        self.ls.set_user_state(user3_id, 'DISABLED')
        state_update = sync_state(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update['enabled'], {user3_id})
        self.assertEqual(state_update['disabled'], set())
        self.assertEqual(state_update['vanished'], [])

    def test_user_changed_email(self):
        self.vwc._set_user_email(self.user_id1, 'new@example.com')
        state_update = sync_state(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update['deleted'], set())
        self.assertEqual(state_update['disabled'], set())
        self.assertEqual(state_update['vanished'], [])
        self.assertEqual({self.user_id1: {'from': self.user_email1, 'to': 'new@example.com'}},
                         state_update['email_changed'])

    def test_user_vanished(self):
        self.vwc._delete_user(self.user_id2)
        state_update = sync_state(self.vwc, self.ls, [self.user_email1])
        self.assertEqual(state_update['deleted'], {self.user_id2})  # the user is obviously also deleted
        self.assertEqual(state_update['disabled'], set())
        self.assertEqual(state_update['vanished'], [self.user_id2])

    @classmethod
    def tearDown(cls) -> None:
        os.unlink('test_sync.db')
        cls.vwc._clear_test_data()
