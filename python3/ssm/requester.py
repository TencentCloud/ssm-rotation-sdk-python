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

import json
import logging
from enum import Enum
from threading import Timer
from tencentcloud.ssm.v20190923 import models, ssm_client
from tencentcloud.common.profile import client_profile
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


class CredentialType(Enum):
    """凭据类型枚举

    SDK 支持的三种核心认证方式：
    1. PERMANENT - 固定 AK/SK，不推荐在生产环境使用
    2. TEMPORARY - 临时凭据（AK/SK + Token）
    3. CAM_ROLE  - CVM 角色绑定（推荐用于 CVM），通过元数据服务自动获取临时凭据
    """
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    CAM_ROLE = "cam_role"


class Error:
    """自定义错误类

    """
    def __init__(self, message=None):
        """
        :param message: 错误信息
        :type message: str
        """
        if message is None:
            self.message = None
        else:
            self.message = message


class LoopTimer(Timer):
    """定时器类（守护线程），不会阻止主进程退出。

    """
    def __init__(self, interval, function, args=None, kwargs=None):
        Timer.__init__(self, interval, function, args or [], kwargs or {})
        self.daemon = True

    def run(self):
        """每隔指定时间调用一次函数

        """
        while True:
            self.finished.wait(self.interval)
            if self.finished.is_set():
                self.finished.set()
                break
            self.function(*self.args, **self.kwargs)


class DbAccount:
    """DB 账号信息类

    """
    def __init__(self, user_name=None, password=None):
        """
        :param user_name: 用户名
        :type user_name: str
        :param password: 密码
        :type password: str
        """
        self.user_name = user_name
        self.password = password


class SsmAccount:
    """SSM 账号信息类

    支持三种核心认证方式：
    1. 角色绑定（CAM_ROLE）- 推荐用于 CVM，通过元数据服务自动获取临时凭据
    2. 临时凭据（TEMPORARY）- 使用临时 AK/SK/Token
    3. 固定凭据（PERMANENT）- 使用固定 AK/SK，不推荐在生产环境使用

    推荐使用工厂方法创建：
    - SsmAccount.with_cam_role(role_name, region)
    - SsmAccount.with_temporary_credential(secret_id, secret_key, token, region)
    - SsmAccount.with_permanent_credential(secret_id, secret_key, region)
    """
    def __init__(self, params=None):
        """
        :param secret_id: 密钥ID，用于标识调用者身份
        :type secret_id: str
        :param secret_key: 密钥值，用于验证调用者身份
        :type secret_key: str
        :param token: 临时凭据 Token，仅 TEMPORARY 类型需要
        :type token: str
        :param role_name: CAM 角色名称，仅 CAM_ROLE 类型需要
        :type role_name: str
        :param url: SSM 服务地址
        :type url: str
        :param region: 地域
        :type region: str
        :param credential_type: 凭据类型，默认为 PERMANENT
        :type credential_type: CredentialType
        """
        if params is None:
            self.credential_type = CredentialType.PERMANENT
            self.secret_id = None
            self.secret_key = None
            self.token = None
            self.role_name = None
            self.url = None
            self.region = None
        else:
            self.credential_type = params.get('credential_type', CredentialType.PERMANENT)
            self.secret_id = params.get('secret_id')
            self.secret_key = params.get('secret_key')
            self.token = params.get('token')
            self.role_name = params.get('role_name')
            self.url = params.get('url')
            self.region = params.get('region')

    @staticmethod
    def with_cam_role(role_name, region):
        """创建角色绑定方式的凭据配置（推荐用于 CVM）

        SDK 会通过计算实例元数据服务自动获取临时凭据并在过期前自动刷新
        注意：只有 CVM 支持真正的角色绑定方式

        :param role_name: CVM 实例绑定的 CAM 角色名称
        :type role_name: str
        :param region: 地域
        :type region: str
        :rtype: SsmAccount
        """
        account = SsmAccount()
        account.credential_type = CredentialType.CAM_ROLE
        account.role_name = role_name
        account.region = region
        return account

    @staticmethod
    def with_temporary_credential(secret_id, secret_key, token, region):
        """创建临时凭据方式的配置

        用户自行获取临时凭据后传入 SDK
        注意：临时凭据有过期时间，SDK 不会自动刷新此方式的凭据

        :param secret_id: 临时 SecretId
        :type secret_id: str
        :param secret_key: 临时 SecretKey
        :type secret_key: str
        :param token: 临时 Token
        :type token: str
        :param region: 地域
        :type region: str
        :rtype: SsmAccount
        """
        account = SsmAccount()
        account.credential_type = CredentialType.TEMPORARY
        account.secret_id = secret_id
        account.secret_key = secret_key
        account.token = token
        account.region = region
        return account

    @staticmethod
    def with_permanent_credential(secret_id, secret_key, region):
        """创建固定 AK/SK 方式的凭据配置（不推荐）

        安全性较低，不推荐在生产环境使用
        生产环境请使用 with_cam_role() 或 with_temporary_credential()

        :param secret_id: 腾讯云 SecretId
        :type secret_id: str
        :param secret_key: 腾讯云 SecretKey
        :type secret_key: str
        :param region: 地域
        :type region: str
        :rtype: SsmAccount
        """
        account = SsmAccount()
        account.credential_type = CredentialType.PERMANENT
        account.secret_id = secret_id
        account.secret_key = secret_key
        account.region = region
        return account

    def with_endpoint(self, url):
        """设置自定义接入点（链式调用）

        :param url: 自定义接入点 URL
        :type url: str
        :rtype: SsmAccount
        """
        self.url = url
        return self


def __create_credential(ssm_acc):
    """根据凭据类型创建对应的 Credential 对象

    :param ssm_acc: SSM 账号信息
    :type ssm_acc: SsmAccount
    :rtype: credential 对象
    """
    cred_type = getattr(ssm_acc, 'credential_type', CredentialType.PERMANENT)

    if cred_type == CredentialType.TEMPORARY:
        if not ssm_acc.secret_id or not ssm_acc.secret_key:
            raise ValueError("secret_id and secret_key are required for TEMPORARY credential type")
        if not ssm_acc.token:
            raise ValueError("token is required for TEMPORARY credential type")
        return credential.Credential(ssm_acc.secret_id, ssm_acc.secret_key, ssm_acc.token)

    elif cred_type == CredentialType.CAM_ROLE:
        if not ssm_acc.role_name:
            raise ValueError("role_name is required for CAM_ROLE credential type")
        from tencentcloud.common.credential import CVMRoleCredential
        return CVMRoleCredential(ssm_acc.role_name)

    else:
        # PERMANENT（默认，向后兼容）
        if not ssm_acc.secret_id or not ssm_acc.secret_key:
            raise ValueError("secret_id and secret_key are required for PERMANENT credential type")
        return credential.Credential(ssm_acc.secret_id, ssm_acc.secret_key)


def __get_client(ssm_acc):
    """创建 SSM 客户端实例

    :param ssm_acc: SSM 账号信息
    :type ssm_acc: SsmAccount
    :rtype: (client, error)
    """
    if ssm_acc is None:
        return None, Error("ssm account is required")
    if not getattr(ssm_acc, "region", None):
        return None, Error("region is required")

    try:
        cred = __create_credential(ssm_acc)
    except ValueError as exc:
        return None, Error(str(exc))

    http_profile = client_profile.HttpProfile()
    http_profile.reqMethod = "POST"
    url = getattr(ssm_acc, 'url', None)
    if url and len(url) != 0:
        http_profile.endpoint = url
    # 客户端配置
    cpf = client_profile.ClientProfile()
    cpf.httpProfile = http_profile

    client, err = None, None
    try:
        # 创建 SSM 客户端对象
        client = ssm_client.SsmClient(cred, ssm_acc.region, cpf)
    except TencentCloudSDKException as e:
        err = Error(str(e.args[0]))
    return client, err


def __get_current_product_secret_value(secret_name, ssm_acc):
    """获取当前云产品凭据内容

    :param secret_name: 凭据名称
    :type secret_name: str
    :param ssm_acc: SSM 账号信息
    :type ssm_acc: SsmAccount class
    :rtype :str: 凭据内容
    :rtype :error: 异常报错信息

    """
    client, err = __get_client(ssm_acc)
    if err:
        logging.error("create ssm client error: %s", err.message)
        return None, Error("create ssm HTTP client error: %s" % err.message)

    # 获取凭据内容
    request = models.GetSecretValueRequest()
    request.SecretName = secret_name
    request.VersionId = "SSM_Current"  # hard-code

    rsp = None
    try:
        rsp = client.GetSecretValue(request)
    except TencentCloudSDKException as e:
        err = Error(str(e.args[0]))
    if err:
        logging.error("ssm GetSecretValue error: " + err.message)
        return None, Error("ssm GetSecretValue error: " + err.message)

    return rsp.SecretString, None


def get_current_account(secret_name, ssm_acc):
    """获取当前账号信息

    :param secret_name: 凭据名称
    :type secret_name: str
    :param ssm_acc: SSM 账号信息
    :type ssm_acc: SsmAccount class
    :rtype :DbAccount: 账号信息
    :rtype :error: 异常报错信息

    """
    # 获取 secret_name 对应的凭据内容
    secret_value, err = __get_current_product_secret_value(secret_name, ssm_acc)
    if err:
        logging.error("failed to GetSecretValue, err=" + err.message)
        return None, err
    # secret_value 是 JSON格式的字符串，形如： {"UserName":"test_user","Password":"test_pwd"}
    if len(secret_value) == 0:
        return None, Error("no valid account info found because secret value is empty")
    try:
        current_user_and_password = json.loads(secret_value)
    except Exception as exc:
        return None, Error("invalid secret value format: %s" % str(exc))
    if "UserName" not in current_user_and_password or "Password" not in current_user_and_password:
        return None, Error("secret value missing required fields: UserName and/or Password")
    account = DbAccount(current_user_and_password["UserName"], current_user_and_password["Password"])
    return account, None
