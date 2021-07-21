import logging
from threading import Timer
from tencentcloud.ssm.v20190923 import models, ssm_client
from tencentcloud.common.profile import client_profile
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


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
    """定时器类

    """
    def __init__(self, interval, function, args, kwargs):
        Timer.__init__(self, interval, function, args, kwargs)

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
    def __init__(self, params=None):
        """
        :param user_name: 用户名
        :type user_name: str
        :param password: 密码
        :type password: str
        """
        if params is None:
            self.user_name = None
            self.password = None
        else:
            self.user_name = params['user_name'] if 'user_name' in params else None
            self.password = params['password'] if 'password' in params else None


class SsmAccount:
    """SSM 账号信息类

    """
    def __init__(self, params=None):
        """
        :param secret_id: 密钥ID，用于标识调用者身份（类似用户名）
        :type secret_id: str
        :param secret_key: 密钥值，用于验证调用者身份（类似密码）
        :type secret_key: str
        :param url: SSM 服务地址
        :type url: str
        :param region: 地域
        :type region: str
        """
        if params is None:
            self.secret_id = None  # string   `yaml:"secret_id"`
            self.secret_key = None  # string   `yaml:"secret_key"`
            self.url = None  # string   `yaml:"url"`
            self.region = None  # string   `yaml:"region"`
        else:
            self.secret_id = params['secret_id'] if 'secret_id' in params else None
            self.secret_key = params[
                'secret_key'] if 'secret_key' in params else None
            self.url = params['url'] if 'url' in params else None
            self.region = params['region'] if 'region' in params else None


def __get_client(secret_id, secret_key, url, region):
    """创建 SSM 客户端实例

    :param secret_key: 密钥ID
    :type secret_key: str
    :param url: SSM 服务地址
    :type url: str
    :param region: 地域
    :type region: str
    :rtype :client: SSM 客户端实例
    :rtype :error: 异常报错信息

    """
    cred = credential.Credential(secret_id, secret_key)
    http_profile = client_profile.HttpProfile()
    http_profile.reqMethod = "POST"
    if url and len(url) != 0:
        http_profile.endpoint = url
    # 客户端配置
    cpf = client_profile.ClientProfile()
    cpf.httpProfile = http_profile

    client, err = None, None
    try:
        # 创建 SSM 客户端对象
        client = ssm_client.SsmClient(cred, region, cpf)
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
    print("get value for secret_name=%s" % secret_name)
    # print("get_client: ", ssm_acc.secret_id, ssm_acc.secret_key, ssm_acc.url, ssm_acc.region)
    client, err = __get_client(ssm_acc.secret_id, ssm_acc.secret_key, ssm_acc.url,
                            ssm_acc.region)
    if err:
        logging.error("create ssm client error: ", err.message)
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
        print("ssm GetSecretValue error: " + err.message)
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
    print("secret value: ", secret_value)
    if len(secret_value) == 0:
        return None, Error("no valid account info found because secret value is empty")
    current_user_and_password = eval(secret_value)
    account = DbAccount(current_user_and_password["UserName"], current_user_and_password["Password"])
    return account, None
