import logging
import os
import http.cookiejar
from typing import List, Dict

import requests
from requests import Response

from dataclasses import dataclass


@dataclass
class VaultwardenUser:
    user_id: str
    email: str
    enabled: bool


ADMIN_COOKIE_NAME = 'VW_ADMIN'
COOKIE_JAR_NAME = '../vaultwarden_cookies.txt'


class VaultwardenConnector:

    def __init__(self):
        self.vaultwarden_url = os.getenv('VAULTWARDEN_URL')
        self.vaultwarden_admin_token = os.getenv('VAULTWARDEN_ADMIN_TOKEN')
        self._auth_cookie = None
        self.client = requests.Session()
        self.client.cookies = http.cookiejar.MozillaCookieJar(COOKIE_JAR_NAME)

    def make_authenticated_request(self, url: str, payload: dict = None, method='GET',
                                   expected_return_code=200, timeout=5) -> Response:
        """
        Make an authenticated request against the vaultwarden admin API by either using the stored cookie or the VAULTWARDEN_ADMIN_TOKEN
        :param url: Full request url
        :param payload: Json payload
        :param method: GET, POST
        :param expected_return_code: Expected return code, raises an exception if not matching
        :param timeout: Request and connect timeout in seconds
        :return: On success, the Response object
        """
        if os.path.exists(COOKIE_JAR_NAME):
            self.client.cookies.load()
            logging.debug('Cookie store found, loading')
        req = self.client.request(method, url, json=payload, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if req.status_code == expected_return_code:
            return req
        elif req.status_code == 401:
            logging.debug('Could not authenticate using cookie, trying token')
            auth_request = self.client.post('{}/admin'.format(self.vaultwarden_url),
                                            data={'token': self.vaultwarden_admin_token}, timeout=(timeout, timeout))
            if auth_request.status_code == 200:
                self.client.cookies.save()
                logging.debug('Authentication using token successful, storing cookie')
                # Try again
                return self.make_authenticated_request(url, payload, method, expected_return_code)
            else:
                raise ConnectionError(
                    'Could not authenticate against {}/admin: {}'.format(self.vaultwarden_url, req.reason))
        else:
            raise ConnectionError(
                'Request returned unexpected return code expected: {} actual: {}'.format(expected_return_code,
                                                                                         req.status_code))

    def get_all_users(self) -> List[VaultwardenUser]:
        result = self.make_authenticated_request('{}/admin/users'.format(self.vaultwarden_url),
                                                 expected_return_code=200)
        all_vw_users = []
        for user_item in result.json():
            # Starting with v1.32.0, Vaultwarden starts using (proper) CamelCase fields
            normalized_user_item = {key.lower(): value for key, value in user_item.items()}
            all_vw_users.append(
                VaultwardenUser(
                    user_id=normalized_user_item['id'],
                    enabled=normalized_user_item['userenabled'],
                    email=normalized_user_item['email']
                )
            )
        return all_vw_users

    def disable_user(self, vw_user_id: str):
        self.make_authenticated_request('{}/admin/users/{}/disable'.format(self.vaultwarden_url, vw_user_id),
                                        expected_return_code=200, method='POST')

    def enable_user(self, vw_user_id: str):
        self.make_authenticated_request('{}/admin/users/{}/enable'.format(self.vaultwarden_url, vw_user_id),
                                        expected_return_code=200, method='POST')

    def invite_user(self, user_email: str) -> str:

        result = self.make_authenticated_request('{}/admin/invite'.format(self.vaultwarden_url), method='POST',
                                                 expected_return_code=200,
                                                 payload={'email': user_email})
        normalized_user_item = {key.lower(): value for key, value in result.json().items()}
        created_user_id = normalized_user_item['id']
        logging.info('Successfully invited user {} with ID {}'.format(user_email, created_user_id))
        return created_user_id


class MockVaultwardenConnector(VaultwardenConnector):
    _vw_user_by_id: Dict[str, VaultwardenUser] = {}

    def get_all_users(self) -> List[VaultwardenUser]:
        return list(self._vw_user_by_id.values())

    def disable_user(self, vw_user_id: str):
        if vw_user_id in self._vw_user_by_id:
            self._vw_user_by_id[vw_user_id].enabled = False

    def enable_user(self, vw_user_id: str):
        if vw_user_id in self._vw_user_by_id:
            self._vw_user_by_id[vw_user_id].enabled = True

    def invite_user(self, user_email: str) -> str:
        user_id = 'ID_{}'.format(user_email)

        self._vw_user_by_id[user_id] = VaultwardenUser(
            user_id=user_id,
            email=user_email,
            enabled=True
        )

        return user_id

    def delete_user(self, vw_user_id: str):
        if vw_user_id in self._vw_user_by_id:
            del self._vw_user_by_id[vw_user_id]

    def set_user_email(self, vw_user_id: str, user_email: str):
        if vw_user_id in self._vw_user_by_id:
            self._vw_user_by_id[vw_user_id].email = user_email

    def clear_test_data(self):
        self._vw_user_by_id = {}
