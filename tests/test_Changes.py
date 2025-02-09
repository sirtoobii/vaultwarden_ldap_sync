from unittest import TestCase

from vaultwarden_user_sync.compare import SyncResult, UserWithEmailChanged
from vaultwarden_user_sync.backends.localstore import LocalStore
from vaultwarden_user_sync.backends.vaultwarden import MockVaultwardenConnector


class ChangesTest(TestCase):
    vwc: MockVaultwardenConnector = None
    ls: LocalStore = None
    user_id1 = ''
    user_id2 = ''
    user_email1 = 'user1@test.com'
    user_email2 = 'user2@test.com'

    @classmethod
    def setUp(cls) -> None:
        cls.vwc = MockVaultwardenConnector()
        cls.ls = LocalStore("file::test_changes:?cache=shared&mode=memory")
        cls.ls.init_db()
        cls.user_id1 = cls.vwc.invite_user(cls.user_email1)
        cls.user_id2 = cls.vwc.invite_user(cls.user_email2)
        cls.ls.register_user(cls.user_email1, cls.user_id1)
        cls.ls.register_user(cls.user_email2, cls.user_id2)

    def test_vw_admin_enable_disable(self):
        # User gets enabled again (by an admin in vaultwarden)
        self.ls.set_user_state(vw_user_id=self.user_id1, user_state='DISABLED')

        self.vwc.enable_user(self.user_id1)
        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=[self.user_email1, self.user_email2])

        self.assertEqual(set(), sync_result.pending_changes.invite_emails)
        self.assertEqual(set(), sync_result.pending_changes.disable_user_ids)

    def test_user_changed_email(self):
        self.vwc.set_user_email(self.user_id1, 'bla@external.com')

        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=[self.user_email1, self.user_email2])

        self.assertEqual(
            UserWithEmailChanged(user_id=self.user_id1, old_email=self.user_email1, new_email='bla@external.com'),
            sync_result.users_with_changed_email[0], "Incorrect email changed result")

        self.assertEqual(set(), sync_result.pending_changes.invite_emails, "Email change triggered invite")
        self.assertEqual(set(), sync_result.pending_changes.disable_user_ids, "Email change triggered disable")
        self.assertEqual(set(), sync_result.pending_changes.enable_user_ids, "Email change triggered enable")

        # and then this user registration address disappears from ldap
        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=[self.user_email2])

        self.assertEqual(set(), sync_result.pending_changes.invite_emails, 'Users to invite')
        self.assertEqual({self.user_id1}, sync_result.pending_changes.disable_user_ids, 'Users to disable')

    def test_unknown_only_to_us(self):
        self.vwc.invite_user('alien@mars.space')
        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=[self.user_email1, self.user_email2,
                                                                 'alien@mars.space'])
        self.assertEqual(set(), sync_result.pending_changes.invite_emails)
        self.assertEqual(set(), sync_result.pending_changes.disable_user_ids)
        self.assertEqual(set(), sync_result.pending_changes.enable_user_ids)

    def test_user_already_known(self):
        self.ls.register_user('old_user@test.com', 'uuuu-iiii-dddd')
        self.ls.set_user_state('uuuu-iiii-dddd', 'DISABLED')
        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=['old_user@test.com', self.user_email1,
                                                                 self.user_email2])
        self.assertEqual(sync_result.pending_changes.invite_emails, set())

    def test_user_appeared_on_ldap(self):
        sync_result = SyncResult.factory(self.vwc, self.ls,
                                         source_email_addresses=[self.user_email1, self.user_email2, 'new@tester.com'])
        self.assertEqual(sync_result.pending_changes.invite_emails, {'new@tester.com'})
        self.assertEqual(set(), sync_result.pending_changes.disable_user_ids, "Adding a new user triggered disabling of other users")
        self.assertEqual(set(), sync_result.pending_changes.enable_user_ids, "Adding a new user triggered enabling of other users")

    def test_user_disappeared_from_ldap(self):
        sync_result = SyncResult.factory(self.vwc, self.ls, source_email_addresses=[self.user_email1])
        self.assertEqual({self.user_id2}, sync_result.pending_changes.disable_user_ids)

    def test_user_reappeared_from_src(self):
        self.vwc.disable_user(self.user_id1)
        self.ls.set_user_state(self.user_id1, "DISABLED")

        sync_result = SyncResult.factory(self.vwc, self.ls, source_email_addresses=[self.user_email1])
        self.assertEqual({self.user_id1}, sync_result.pending_changes.enable_user_ids)


    def test_nothing_to_do(self):
        # We are in sync
        sync_result = SyncResult.factory(self.vwc, self.ls, source_email_addresses=[self.user_email1, self.user_email2])
        self.assertEqual(set(), sync_result.pending_changes.invite_emails)
        self.assertEqual(set(), sync_result.pending_changes.disable_user_ids)
        self.assertEqual(set(), sync_result.pending_changes.enable_user_ids)

    @classmethod
    def tearDown(cls) -> None:
        cls.ls.truncate()
        cls.vwc.clear_test_data()
