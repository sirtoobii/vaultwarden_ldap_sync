import logging
import os
import http.cookiejar

import requests
from requests import Response

ADMIN_COOKIE_NAME = 'VW_ADMIN'
COOKIE_JAR_NAME = '../vaultwarden_cookies.txt'


class VaultwardenConnector:

    def __init__(self, test_mode=False):
        self.vaultwarden_url = os.getenv('VAULTWARDEN_URL')
        self.vaultwarden_admin_token = os.getenv('VAULTWARDEN_ADMIN_TOKEN')
        self._auth_cookie = None
        self.client = requests.Session()
        self.client.cookies = http.cookiejar.MozillaCookieJar(COOKIE_JAR_NAME)
        self.is_test_mode = test_mode
        self._tm_enabled = {}
        self._tm_disabled = {}

    def make_authenticated_request(self, url: str, payload: dict = None, method='GET',
                                   expected_return_code=200) -> Response:
        """
        Make an authenticated request against the vaultwarden admin API by either using the stored cookie or the VAULTWARDEN_ADMIN_TOKEN
        :param url: Full request url
        :param payload: Json payload
        :param method: GET, POST
        :param expected_return_code: Expected return code, raises an exception if not matching
        :return: On success, the Response object
        """
        if os.path.exists(COOKIE_JAR_NAME):
            self.client.cookies.load()
            logging.debug('Cookie store found, loading')
        req = self.client.request(method, url, json=payload)
        if req.status_code == expected_return_code:
            return req
        elif req.status_code == 401:
            logging.debug('Could not authenticate using cookie, trying token')
            auth_request = self.client.post('{}/admin'.format(self.vaultwarden_url),
                                            data={'token': self.vaultwarden_admin_token})
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

    def get_all_users(self) -> tuple:

        if self.is_test_mode:
            return self._tm_enabled, self._tm_disabled, {**self._tm_enabled, **self._tm_disabled}

        enabled = {}
        disabled = {}
        all_users = {}
        result = self.make_authenticated_request('{}/admin/users'.format(self.vaultwarden_url),
                                                 expected_return_code=200)
        for user_item in result.json():
            if user_item['UserEnabled']:
                enabled[user_item['Id']] = user_item['Email']
            else:
                disabled[user_item['Id']] = user_item['Email']
            all_users[user_item['Id']] = user_item['Email']
        return enabled, disabled, all_users

    def disable_user(self, user_id: str):
        if self.is_test_mode:
            if user_id in self._tm_enabled:
                self._tm_disabled[user_id] = self._tm_enabled[user_id]
                del self._tm_enabled[user_id]
        else:
            self.make_authenticated_request('{}/admin/users/{}/disable'.format(self.vaultwarden_url, user_id),
                                            expected_return_code=200, method='POST')

    def enable_user(self, user_id: str):
        if self.is_test_mode:
            if user_id in self._tm_disabled:
                self._tm_enabled[user_id] = self._tm_disabled[user_id]
                del self._tm_disabled[user_id]
        else:
            self.make_authenticated_request('{}/admin/users/{}/enable'.format(self.vaultwarden_url, user_id),
                                            expected_return_code=200, method='POST')

    def invite_user(self, user_email: str) -> str:
        if self.is_test_mode:
            user_id = 'ID_{}'.format(user_email)
            self._tm_enabled[user_id] = user_email
            return user_id
        else:
            result = self.make_authenticated_request('{}/admin/invite'.format(self.vaultwarden_url), method='POST',
                                                     expected_return_code=200,
                                                     payload={'email': user_email})
            created_user_id = result.json()['Id']
            logging.info('Successfully invited user {} with ID {}'.format(user_email, created_user_id))
            return created_user_id

    def _delete_user(self, user_id):
        if not self.is_test_mode:
            raise RuntimeError('This method is only for testing')
        if user_id in self._tm_enabled:
            del self._tm_enabled[user_id]
        if user_id in self._tm_disabled:
            del self._tm_disabled[user_id]

    def _set_user_email(self, user_id: str, user_email: str):
        if not self.is_test_mode:
            raise RuntimeError('This method is only for testing')
        if user_id in self._tm_enabled:
            self._tm_enabled[user_id] = user_email
        if user_id in self._tm_disabled:
            self._tm_disabled[user_id] = user_email

    def _clear_test_data(self):
        self._tm_enabled = {}
        self._tm_disabled = {}
