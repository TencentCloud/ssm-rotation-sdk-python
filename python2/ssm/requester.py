# -*- coding: utf-8 -*-
#
# Copyright 2017-2026 Tencent Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import absolute_import

import json
import logging
from threading import _Timer

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile import client_profile
from tencentcloud.ssm.v20190923 import models, ssm_client


class CredentialType(object):
    PERMANENT = u"permanent"
    TEMPORARY = u"temporary"
    CAM_ROLE = u"cam_role"


class Error(object):
    def __init__(self, message=None):
        self.message = message


class LoopTimer(_Timer):
    def __init__(self, interval, function, args=None, kwargs=None):
        _Timer.__init__(self, interval, function, args or [], kwargs or {})
        self.daemon = True

    def run(self):
        while True:
            self.finished.wait(self.interval)
            if self.finished.is_set():
                break
            self.function(*self.args, **self.kwargs)


class DbAccount(object):
    def __init__(self, user_name=None, password=None):
        self.user_name = user_name
        self.password = password


class SsmAccount(object):
    def __init__(self, params=None):
        params = params or {}
        self.credential_type = params.get(u"credential_type", CredentialType.PERMANENT)
        self.secret_id = params.get(u"secret_id")
        self.secret_key = params.get(u"secret_key")
        self.token = params.get(u"token")
        self.role_name = params.get(u"role_name")
        self.url = params.get(u"url")
        self.region = params.get(u"region")

    @staticmethod
    def with_cam_role(role_name, region):
        return SsmAccount({
            u"credential_type": CredentialType.CAM_ROLE,
            u"role_name": role_name,
            u"region": region,
        })

    @staticmethod
    def with_temporary_credential(secret_id, secret_key, token, region):
        return SsmAccount({
            u"credential_type": CredentialType.TEMPORARY,
            u"secret_id": secret_id,
            u"secret_key": secret_key,
            u"token": token,
            u"region": region,
        })

    @staticmethod
    def with_permanent_credential(secret_id, secret_key, region):
        return SsmAccount({
            u"credential_type": CredentialType.PERMANENT,
            u"secret_id": secret_id,
            u"secret_key": secret_key,
            u"region": region,
        })

    def with_endpoint(self, url):
        self.url = url
        return self


def __create_credential(ssm_acc):
    cred_type = getattr(ssm_acc, u"credential_type", CredentialType.PERMANENT)

    if cred_type == CredentialType.TEMPORARY:
        if not ssm_acc.secret_id or not ssm_acc.secret_key:
            raise ValueError(u"secret_id and secret_key are required for TEMPORARY credential type")
        if not ssm_acc.token:
            raise ValueError(u"token is required for TEMPORARY credential type")
        return credential.Credential(ssm_acc.secret_id, ssm_acc.secret_key, ssm_acc.token)

    if cred_type == CredentialType.CAM_ROLE:
        if not ssm_acc.role_name:
            raise ValueError(u"role_name is required for CAM_ROLE credential type")
        from tencentcloud.common.credential import CVMRoleCredential
        return CVMRoleCredential(ssm_acc.role_name)

    if not ssm_acc.secret_id or not ssm_acc.secret_key:
        raise ValueError(u"secret_id and secret_key are required for PERMANENT credential type")
    return credential.Credential(ssm_acc.secret_id, ssm_acc.secret_key)


def __get_client(ssm_acc):
    if ssm_acc is None:
        return None, Error(u"ssm account is required")
    if not getattr(ssm_acc, u"region", None):
        return None, Error(u"region is required")

    try:
        cred = __create_credential(ssm_acc)
    except ValueError as exc:
        return None, Error(unicode(exc))

    http_profile = client_profile.HttpProfile()
    http_profile.reqMethod = u"POST"
    if getattr(ssm_acc, u"url", None):
        http_profile.endpoint = ssm_acc.url

    cpf = client_profile.ClientProfile()
    cpf.httpProfile = http_profile

    try:
        return ssm_client.SsmClient(cred, ssm_acc.region, cpf), None
    except TencentCloudSDKException as exc:
        return None, Error(exc.message)


def __get_current_product_secret_value(secret_name, ssm_acc):
    client, err = __get_client(ssm_acc)
    if err:
        logging.error(u"create ssm client error: %s", err.message)
        return None, Error(u"create ssm HTTP client error: %s" % err.message)

    request = models.GetSecretValueRequest()
    request.SecretName = secret_name
    request.VersionId = u"SSM_Current"

    try:
        rsp = client.GetSecretValue(request)
    except TencentCloudSDKException as exc:
        err = Error(exc.message)
        logging.error(u"ssm GetSecretValue error: %s", err.message)
        return None, Error(u"ssm GetSecretValue error: %s" % err.message)

    return rsp.SecretString, None


def get_current_account(secret_name, ssm_acc):
    secret_value, err = __get_current_product_secret_value(secret_name, ssm_acc)
    if err:
        return None, err
    if not secret_value:
        return None, Error(u"no valid account info found because secret value is empty")

    try:
        current_user_and_password = json.loads(secret_value)
    except (ValueError, KeyError, TypeError) as exc:
        return None, Error(u"invalid secret value format: %s" % unicode(exc))
    if u"UserName" not in current_user_and_password or u"Password" not in current_user_and_password:
        return None, Error(u"secret value missing required fields: UserName and/or Password")

    return DbAccount(
        current_user_and_password[u"UserName"],
        current_user_and_password[u"Password"],
    ), None
