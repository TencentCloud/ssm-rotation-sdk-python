import sys
import os
import logging
from db.dynamic_secret_rotation_db_conn import DynamicSecretRotationDb, Config, DbConfig
from ssm.requester import LoopTimer, SsmAccount
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

sys.path.append(os.getcwd())  # 添加当前目录至python路径

db_conn = DynamicSecretRotationDb()  # 数据库连接
DB_FREQ = 20  # 数据库访问频率
WATCH_FREQ = 10  # 监控轮转频率

logging.basicConfig(filename='./demo.log', filemode='w', level=logging.DEBUG)


def access_db():
    """连接数据库

    """
    print("\033[33m--- access_db start\033[0m")
    c = db_conn.get_conn()
    try:
        c.ping()
    except TencentCloudSDKException as e:
        logging.error("failed to access db with err: {0}".format(str(
            e.args[0])).encode("utf-8"))
        print("\033[31m*** Connection break! ***\033[0m")  # red
        raise  # throw exception
    print("\033[33m--- succeed to access db\033[0m")


def main():
    # 获取 SSM API
    test_url = "ssm.test.tencentcloudapi.com"

    db_config = DbConfig(
        params={
            'secret_name': "test",  # 凭据名
            'ip_address': "127.0.0.1",  # 数据库地址
            'port': 58366,  # 数据库端口
            'db_name': "database_name",  # 可以为空，或指定具体的数据库名
            'param_str': "charset=utf8&loc=Local",
        })
    ssm_service_config = SsmAccount(
        params={
            'secret_id': "secret_id",  # 需填写实际可用的SecretId
            'secret_key': "secret_key",  # 需填写实际可用的SecretKey
            'url': test_url,
            'region': "ap-guangzhou"  # 选择凭据所存储的地域
        })
    config = Config(
        params={
            'db_config': db_config,
            'ssm_service_config': ssm_service_config,
            'WATCH_FREQ': WATCH_FREQ
        })

    err = db_conn.init(config)
    if err:
        logging.error("failed to init db_conn with err: {0}".format(
            err.message).encode("utf-8"))
        return

    # 轮询：连接数据库
    t1 = LoopTimer(DB_FREQ, access_db)
    t1.start()


if __name__ == "__main__":
    main()
