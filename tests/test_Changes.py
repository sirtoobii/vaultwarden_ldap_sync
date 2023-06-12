import os
from unittest import TestCase

from bin.sync import collect_change_set, sync_state
from src.VaultwardenConnector import VaultwardenConnector
from src.LocalStorage import LocalStore


class ChangesTest(TestCase):
    vwc = None
    ls = None
    user_id1 = ''
    user_id2 = ''
    user_email1 = 'user1@test.com'
    user_email2 = 'user2@test.com'

    @classmethod
    def setUp(cls) -> None:
        cls.vwc = VaultwardenConnector(test_mode=True)
        cls.ls = LocalStore('test_changes.db')
        cls.ls.init_db()
        cls.user_id1 = cls.vwc.invite_user(cls.user_email1)
        cls.user_id2 = cls.vwc.invite_user(cls.user_email2)
        cls.ls.register_user(cls.user_email1, cls.user_id1)
        cls.ls.register_user(cls.user_email2, cls.user_id2)

    def test_vw_admin_enable_disable(self):
        # User gets enabled again (by an admin in vaultwarden)
        self.ls.set_user_state(vw_user_id=self.user_id1, user_state='DISABLED')

        self.vwc.enable_user(self.user_id1)
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=[self.user_email1, self.user_email2])

        self.assertEqual(change_set['invite'], set())
        self.assertEqual(change_set['disable'], set())

    def test_user_changed_email(self):
        self.vwc._set_user_email(self.user_id1, 'bla@external.com')
        self.ls.update_vw_email(self.user_id1, 'bla@external.com')
        _, _, t = self.ls.get_all_users()
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=[self.user_email1, self.user_email2])
        self.assertEqual(set(), change_set['invite'])
        self.assertEqual(set(), change_set['disable'])

        # and then this user registration address disappears from ldap
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=[self.user_email2])

        self.assertEqual(set(), change_set['invite'], 'Users to invite')
        self.assertEqual({self.user_email1}, change_set['disable'], 'Users to disable')

    def test_unknown_only_to_us(self):
        self.vwc.invite_user('alien@mars.space')
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=[self.user_email1, self.user_email2, 'alien@mars.space'])
        self.assertEqual(change_set['invite'], set())
        self.assertEqual(change_set['disable'], set())

    def test_user_already_known(self):
        self.ls.register_user('old_user@test.com', 'uuuu-iiii-dddd')
        self.ls.set_user_state('uuuu-iiii-dddd', 'DISABLED')
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=['old_user@test.com', self.user_email1, self.user_email2])
        self.assertEqual(change_set['invite'], set())

    def test_user_appeared_on_ldap(self):
        change_set = collect_change_set(self.vwc, self.ls,
                                        ldap_users=[self.user_email1, self.user_email2, 'new@tester.com'])
        self.assertEqual(change_set['invite'], {'new@tester.com'})

    def test_user_disappeared_from_ldap(self):
        change_set = collect_change_set(self.vwc, self.ls, ldap_users=[self.user_email1])
        self.assertEqual(change_set['disable'], {self.user_email2})

    def test_nothing_to_do(self):
        # We are in sync
        change_set = collect_change_set(self.vwc, self.ls, ldap_users=[self.user_email1, self.user_email2])
        self.assertEqual(change_set['invite'], set())
        self.assertEqual(change_set['disable'], set())

    @classmethod
    def tearDown(cls) -> None:
        os.unlink('test_changes.db')
        cls.vwc._clear_test_data()
