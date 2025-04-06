from typing import List

import random

from vaultwarden_user_sync.email_sources import EmailSource


class RandomEmailSource(EmailSource):
    """
    Dummy email source returning a random subset of emails
    """
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
