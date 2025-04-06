from dataclasses import dataclass, field, fields
from typing import Set, Dict, List, Optional

from vaultwarden_user_sync.backends.localstore import ManagedUser, LocalStore
from vaultwarden_user_sync.backends.vaultwarden import VaultwardenUser, VaultwardenConnector


@dataclass
class ChangeSet:
    """
    Representation of pending changes for the connected Vaultwarden instance
    """
    invite_emails: Set[str] = field(default_factory=set)
    enable_user_ids: Set[str] = field(default_factory=set)
    disable_user_ids: Set[str] = field(default_factory=set)


@dataclass
class UserWithEmailChanged:
    user_id: str
    old_email: str
    new_email: str


@dataclass
class SyncResult:
    _vw_users_by_id: Dict[str, VaultwardenUser] = field(default_factory=dict)
    _ma_users_by_id: Dict[str, ManagedUser] = field(default_factory=dict)

    # UserIDs ENABLED in Vaultwarden since the last sync (compared to local state)
    user_ids_enabled_in_vw: Set[str] = field(default_factory=set)
    # UserIDs ENABLED in Email source since last sync (compared to Vaultwarden state)
    user_ids_enable_in_src: Set[str] = field(default_factory=set)
    # UserIDs DISABLED in Vaultwarden since the last sync (compared to local state)
    user_ids_disabled_in_vw: Set[str] = field(default_factory=set)
    # UserIDs  addresses disappeared in Vaultwarden
    user_ids_vanished_in_vw: Set[str] = field(default_factory=set)

    # Email addresses disappeared from email source
    email_vanished_in_src: Set[str] = field(default_factory=set)
    email_vanished_in_both: Set[str] = field(default_factory=set)

    users_with_changed_email: List[UserWithEmailChanged] = field(default_factory=list)

    adoption_candidates: List[VaultwardenUser] = field(default_factory=list)

    pending_changes: ChangeSet = field(default_factory=ChangeSet)

    @staticmethod
    def factory(vwc: VaultwardenConnector, ls: LocalStore, source_email_addresses: List[str]) -> "SyncResult":
        """
        Finds changes made in Vaultwarden (and email source) that are not yet reflected in our local state

        :param vwc: Vaultwarden connector instance
        :param ls: LocalStore instance
        :param source_email_addresses: List of source email addresses (invite candidates)
        :return: Populated SyncResult object
        """

        vw_users = vwc.get_all_users()
        ma_users = ls.get_all_managed_users()

        # prepare sets (Local state)
        # user_id
        ma_user_ids_all = set()
        ma_user_ids_disabled = set()
        ma_user_ids_enabled = set()
        ma_users_by_id = {}
        ma_id_by_email = {}

        # user_email
        ma_user_emails_all_vw = set()
        ma_user_emails_enabled = set()
        ma_user_emails_disabled = set()
        ma_users_emails_all_inv = set()
        ma_users_emails_all_vw = set()
        for ma_user in ma_users:
            # user ids
            ma_user_ids_all.add(ma_user.vw_user_id)
            ma_users_by_id[ma_user.vw_user_id] = ma_user
            ma_id_by_email[ma_user.invite_email] = ma_user.vw_user_id
            if ma_user.enabled:
                ma_user_ids_enabled.add(ma_user.vw_user_id)
            else:
                ma_user_ids_disabled.add(ma_user.vw_user_id)

            # emails
            ma_user_emails_all_vw.add(ma_user.vw_email)
            ma_users_emails_all_vw.add(ma_user.vw_email)
            ma_users_emails_all_inv.add(ma_user.invite_email)
            if ma_user.enabled:
                ma_user_emails_enabled.add(ma_user.invite_email)
            else:
                ma_user_emails_disabled.add(ma_user.invite_email)

        # prepare sets (Vaultwarden)
        vw_user_emails = set()
        vw_user_ids_all = set()
        vw_user_ids_disabled = set()
        vw_user_ids_enabled = set()
        vw_users_by_id = {}
        vw_users_by_email = {}

        # user_emails
        vw_user_emails_all = set()
        vw_user_emails_disabled = set()
        for vw_user in vw_users:
            # userIds
            vw_user_ids_all.add(vw_user.user_id)
            vw_users_by_id[vw_user.user_id] = vw_user
            vw_users_by_email[vw_user.email] = vw_user
            if vw_user.enabled:
                vw_user_ids_enabled.add(vw_user.user_id)
            else:
                vw_user_ids_disabled.add(vw_user.user_id)

            # emails
            vw_user_emails.add(vw_user.email)
            if not vw_user.enabled:
                vw_user_emails_disabled.add(vw_user.email)
            vw_user_emails_all.add(vw_user.email)

        sync_result = SyncResult(_ma_users_by_id=ma_users_by_id, _vw_users_by_id=vw_users_by_id)
        # find users who aren't present in the email source and Vaultwarden (but our local state)
        sync_result.email_vanished_in_src = ma_user_emails_all_vw.difference(vw_user_emails.union(source_email_addresses))

        # find deleted in Vaultwarden
        sync_result.user_ids_vanished_in_vw = ma_user_ids_all.difference(vw_user_ids_all)

        # find disabled users in Vaultwarden
        sync_result.user_ids_disabled_in_vw = vw_user_ids_disabled.intersection(ma_user_ids_enabled)

        # find enabled users in Vaultwarden
        sync_result.user_ids_enabled_in_vw = vw_user_ids_enabled.intersection(ma_user_ids_disabled)

        # find users who changed their email address (in Vaultwarden)
        users_with_email_changes = []
        for user_id in ma_user_ids_all.intersection(vw_user_ids_all):
            if ma_users_by_id[user_id].vw_email != vw_users_by_id[user_id].email:
                users_with_email_changes.append(UserWithEmailChanged(
                    user_id=user_id,
                    old_email=ma_users_by_id[user_id].vw_email,
                    new_email=vw_users_by_id[user_id].email
                ))
        sync_result.users_with_changed_email = users_with_email_changes

        # find users who aren't present in email source and Vaultwarden (but our local state)
        sync_result.email_vanished_in_both = ma_user_emails_all_vw.difference(
            vw_user_emails.union(set(source_email_addresses)))

        # find adoption candidates: Users present in email source + Vaultwarden but not in our local state
        sync_result.adoption_candidates = [vw_users_by_email[em] for em in
                                           (set(source_email_addresses).intersection(vw_user_emails)).difference(
                                               ma_users_emails_all_inv)]

        # And figure out pending changes
        change_set = ChangeSet()

        # We want to invite users who are:
        # Present in email source but not preset in Vaultwarden AND NOT present in LocalStore
        known_user_emails = (set(vw_user_emails_all)
                             .union(set(ma_users_emails_all_inv))
                             .union(set(ma_users_emails_all_vw)))
        change_set.invite_emails = set(source_email_addresses).difference(known_user_emails)

        # We want to disable users who are:
        # Present in our LocalStore (state=ENABLED) and NOT present in email source
        disabled_emails = ma_user_emails_enabled.difference(set(source_email_addresses))

        try:
            change_set.disable_user_ids = {ma_id_by_email[ue] for ue in disabled_emails}
        except KeyError as ke:
            print("MA_BY", ma_id_by_email)
            print("SETS", ma_user_emails_enabled, set(source_email_addresses), disabled_emails)
            raise KeyError(ke)

        # We want to enable users who are currently disabled both in our local state and in Vaultwarden
        # and appear in the source email list again
        enabled_emails = (ma_user_emails_disabled.union(vw_user_emails_disabled)).intersection(
            source_email_addresses)
        change_set.enable_user_ids = {ma_id_by_email[ue] for ue in enabled_emails}

        sync_result.pending_changes = change_set
        return sync_result

    def get_vw_user_by_id(self, user_id: str) -> Optional[VaultwardenUser]:
        return self._vw_users_by_id.get(user_id)

    def get_ma_user_by_id(self, user_id: str) -> Optional[ManagedUser]:
        return self._ma_users_by_id.get(user_id)

    def summary(self) -> str:
        summary = "Difference compared to local state/emails source:\n"
        for field in filter(lambda f: f.name not in [
            "_vw_users_by_id",
            "_ma_users_by_id",
            "pending_changes"
        ], fields(self)):
            summary += f" * {field.name}: {len(self.__getattribute__(field.name))} \n"
        summary += "Pending changes: \n"
        summary += f" * Invite: {len(self.pending_changes.invite_emails)}\n"
        summary += f" * Enable: {len(self.pending_changes.enable_user_ids)}\n"
        summary += f" * Disable: {len(self.pending_changes.disable_user_ids)}\n"
        return summary
