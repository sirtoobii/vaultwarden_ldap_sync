from abc import ABC, abstractmethod
from typing import List


class EmailSource(ABC):
    """
    Generic Email source base class
    """
    source_name: str

    def __init__(self, source_name: str):
        self.source_name = source_name

    @abstractmethod
    def get_email_list(self) -> List[str]:
        """
        Get email addresses to invite
        :return: A (possibly) empty list of email addresses
        """
        ...
