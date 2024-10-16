import os
from typing import List

from ldap.ldapobject import SimpleLDAPObject

import ldap
import logging
import contextlib

from vaultwarden_ldap_sync.EmailSource import EmailSource


class LdapConnector(EmailSource):

    def __init__(self, source_name: str):
        super().__init__(source_name)
        self.ldap_server = os.getenv('LDAP_SERVER')
        self.ldap_scheme = os.getenv('LDAP_SCHEME', 'ldaps')
        self.ldap_tls = os.getenv('LDAP_TLS', 'true')
        self.ldap_bind_dn = os.getenv('LDAP_BIND_DN')
        self.ldap_bind_pw = os.getenv('LDAP_BIND_PW')
        self.ldap_search_filter = os.getenv('LDAP_SEARCH_FILTER')
        self.ldap_base_dn = os.getenv('LDAP_BASE_DN')
        self.ldap_email_attr = os.getenv('LDAP_EMAIL_ATTR', 'email')

    @contextlib.contextmanager
    def connect(self) -> SimpleLDAPObject:
        conn = ldap.initialize('{}://{}'.format(self.ldap_scheme, self.ldap_server))
        try:
            # if self.ldap_tls:
            #     conn.start_tls_s()
            conn.simple_bind_s(who=self.ldap_bind_dn, cred=self.ldap_bind_pw)
            yield conn
        finally:
            conn.unbind_s()

    def get_email_list(self) -> List[str]:
        """
        Performs a ldap search based on the filter setting in LDAP_SEARCH_FILTER

        :return: A (possibly) empty list of email addresses (or technically speaking the content of the LDAP_EMAIL_ATTR field)
        """
        with self.connect() as ldap_server:
            try:
                results = ldap_server.search_s(self.ldap_base_dn, ldap.SCOPE_SUBTREE, self.ldap_search_filter)
            except ldap.NO_SUCH_OBJECT:
                logging.warning('Ldap search returned no results')
                return []
        ldap_email_list = []
        for e in results:
            try:
                ldap_email_list.append(e[1][self.ldap_email_attr][0].decode())
            except KeyError:
                logging.warning('One of returned objects missing your LDAP_EMAIL_ATTR')
                logging.debug('LDAP request object returned following keys: {}'.format(e[1].keys()))
                continue
            except IndexError:
                logging.warning('LDAP request object returned badly formatted response')
                logging.debug('Response: {}'.format(e))
                continue
            except Exception as err:
                logging.warning('Oops, something went wrong')
                logging.debug('Exception was: {}'.format(err))
                continue
        return ldap_email_list
