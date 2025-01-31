from typing import List

from vaultwarden_ldap_sync.EmailSource import EmailSource
import random


class RandomEmailSource(EmailSource):
    _internal_email_list = [
        "tester_1@exmaple.com",
        "tester_2@example.com",
        "tester_3@example.com",
        "tester_4@example.com",
        "tester_5@example.com",
        "tester_6@example.com",
    ]

    def get_email_list(self) -> List[str]:
        idx = random.choice([0, 1, 3, 4, 5, 6])
        return self._internal_email_list[:idx]
