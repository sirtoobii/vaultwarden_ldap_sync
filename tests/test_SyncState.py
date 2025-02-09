import os
import unittest

from vaultwarden_user_sync.backends.localstore import LocalStore
from vaultwarden_user_sync.backends.vaultwarden import MockVaultwardenConnector
from vaultwarden_user_sync.compare import SyncResult, UserWithEmailChanged


class SyncStateTest(unittest.TestCase):
    vwc: MockVaultwardenConnector = None
    ls: LocalStore = None
    user_id1 = ''
    user_id2 = ''
    user_email1 = 'user1@test.com'
    user_email2 = 'user2@test.com'

    @classmethod
    def setUp(cls) -> None:
        cls.vwc = MockVaultwardenConnector()
        cls.ls = LocalStore("file::test_sync:?cache=shared&mode=memory")
        cls.ls.init_db()
        cls.user_id1 = cls.vwc.invite_user(cls.user_email1)
        cls.user_id2 = cls.vwc.invite_user(cls.user_email2)
        cls.ls.register_user(cls.user_email1, cls.user_id1)
        cls.ls.register_user(cls.user_email2, cls.user_id2)

    def test_nothing_to_sync(self):
        # Nothing to sync
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update.email_vanished_in_both, set())
        self.assertEqual(state_update.user_ids_vanished_in_vw, set())
        self.assertEqual(state_update.user_ids_disabled_in_vw, set())

    def test_user_disabled_in_vw(self):
        # User disabled in Vaultwarden
        self.vwc.disable_user(self.user_id1)
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update.user_ids_disabled_in_vw, {self.user_id1})
        self.assertEqual(state_update.email_vanished_in_both, set())
        self.assertEqual(state_update.user_ids_vanished_in_vw, set())

    def test_user_deleted_in_vw(self):
        # User deleted in Vaultwarden
        self.vwc.delete_user(self.user_id1)
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update.user_ids_vanished_in_vw, {self.user_id1})
        self.assertEqual(state_update.user_ids_disabled_in_vw, set())
        self.assertEqual(state_update.email_vanished_in_both, set())

    def test_user_enabled_in_vw(self):
        # User enabled in vaultwarden
        user3_id = self.vwc.invite_user('blublu@tester.com')
        self.ls.register_user('blublu@tester.com', user3_id)
        self.ls.set_user_state(user3_id, 'DISABLED')
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update.user_ids_enabled_in_vw, {user3_id})
        self.assertEqual(state_update.user_ids_disabled_in_vw, set())
        self.assertEqual(state_update.email_vanished_in_both, set())

    def test_user_changed_email(self):
        self.vwc.set_user_email(self.user_id1, 'new@example.com')
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1, self.user_email2])
        self.assertEqual(state_update.user_ids_vanished_in_vw, set())
        self.assertEqual(state_update.user_ids_disabled_in_vw, set())
        self.assertEqual(state_update.email_vanished_in_both, set())
        self.assertEqual(UserWithEmailChanged(user_id=self.user_id1, old_email=self.user_email1, new_email="new@example.com"), state_update.users_with_changed_email[0])

    def test_user_vanished_both(self):
        self.vwc.delete_user(self.user_id2)
        state_update = SyncResult.factory(self.vwc, self.ls, [self.user_email1])
        self.assertEqual(state_update.user_ids_vanished_in_vw, {self.user_id2})  # the user is obviously also deleted
        self.assertEqual(state_update.email_vanished_in_both, {self.user_email2})

    @classmethod
    def tearDown(cls) -> None:
        cls.ls.truncate()
        cls.vwc.clear_test_data()
