import os
from unittest import TestCase

from bin.main import find_not_in_A_but_B, collect_change_set, sync_state
from src.VaultwardenConnector import VaultwardenConnector
from src.LocalStorage import LocalStore


class Test(TestCase):
    vwc = None
    ls = None

    @classmethod
    def setUp(cls) -> None:
        cls.vwc = VaultwardenConnector(test_mode=True)
        cls.ls = LocalStore('test.db')
        cls.ls.init_db()

    def test_find_users_to_delete_or_invite(self):
        # We are in sync
        self.ls.register_user('tester@test.com', self.vwc.invite_user('tester@test.com'))
        self.ls.register_user('blabla@tester.com', self.vwc.invite_user('blabla@tester.com'))
        change_set = collect_change_set(self.vwc, self.ls, ldap_users=['tester@test.com', 'blabla@tester.com'])

        self.assertEqual(change_set['invite'], set())
        self.assertEqual(change_set['disable'], set())

        # a user disappeared from ldap
        change_set = collect_change_set(self.vwc, self.ls, ldap_users=['tester@test.com'])
        self.assertEqual(change_set['disable'], {'blabla@tester.com'})

        # a user appeared on ldap
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=['tester@test.com', 'blabla@tester.com', 'new@tester.com'])
        self.assertEqual(change_set['invite'], {'new@tester.com'})

        # a user appeared on ldap but we already know him
        self.ls.register_user('old_user@test.com', 'uuuu-iiii-dddd')
        self.ls.set_user_state('uuuu-iiii-dddd', 'DISABLED')
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=['tester@test.com', 'blabla@tester.com', 'old_user@test.com'])
        self.assertEqual(change_set['invite'], set())

        # the user is present on ldap and in vaultwarden, but we don't know him
        self.vwc.invite_user('alien@mars.space')
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=['tester@test.com', 'blabla@tester.com', 'old_user@test.com',
                                                    'alien@mars.space'])

        self.assertEqual(change_set['invite'], set())
        self.assertEqual(change_set['disable'], set())

    def test_sync_state(self):
        # Nothing to sync
        user1_id = self.vwc.invite_user('tester@test.com')
        user2_id = self.vwc.invite_user('blabla@tester.com')
        self.ls.register_user('tester@test.com', user1_id)
        self.ls.register_user('blabla@tester.com', user2_id)

        state_update = sync_state(self.vwc, self.ls, ['tester@test.com', 'blabla@tester.com'])

        self.assertEqual(state_update['vanished'], set())
        self.assertEqual(state_update['deleted'], set())
        self.assertEqual(state_update['disabled'], set())

        # User disabled in Vaultwarden
        self.vwc.disable_user(user1_id)
        state_update = sync_state(self.vwc, self.ls, ['tester@test.com', 'blabla@tester.com'])
        self.assertEqual(state_update['disabled'], {'tester@test.com'})
        self.assertEqual(state_update['vanished'], set())
        self.assertEqual(state_update['deleted'], set())

        # User deleted in Vaultwarden
        self.vwc._delete_user(user1_id)
        state_update = sync_state(self.vwc, self.ls, ['tester@test.com', 'blabla@tester.com'])
        self.assertEqual(state_update['deleted'], {'tester@test.com'})
        self.assertEqual(state_update['disabled'], set())
        self.assertEqual(state_update['vanished'], set())

        # User enabled in vaultwarden
        user3_id = self.vwc.invite_user('blublu@tester.com')
        self.ls.register_user('blublu@tester.com', user3_id)
        self.ls.set_user_state(user3_id, 'DISABLED')
        state_update = sync_state(self.vwc, self.ls, ['tester@test.com', 'blabla@tester.com'])
        self.assertEqual(state_update['enabled'], {'blublu@tester.com'})

    @classmethod
    def tearDown(cls) -> None:
        os.unlink('test.db')
        cls.vwc._clear_test_data()
