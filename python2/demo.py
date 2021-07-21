# -*- coding: utf-8 -*
import sys
import os
import logging
from __future__ import absolute_import
from db.dynamic_secret_rotation_db_conn import DynamicSecretRotationDb, Config, DbConfig
from ssm.requester import LoopTimer, SsmAccount
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

sys.path.append(os.getcwdu())  # 添加当前目录至python路径

db_conn = DynamicSecretRotationDb()  # 数据库连接
DB_FREQ = 20  # 数据库访问频率
WATCH_FREQ = 10  # 监控轮转频率

logging.basicConfig(filename=u'./demo.log', filemode=u'w', level=logging.DEBUG)


def access_db():
    u"""连接数据库

    """
    print u"\033[33m--- access_db start\033[0m"
    c = db_conn.get_conn()
    try:
        c.ping()
    except TencentCloudSDKException, e:
        logging.error(u"failed to access db with err: {0}".format(e.message))
        print u"\033[31m*** Connection break! ***\033[0m"  # red
        raise  # throw exception
    print u"\033[33m--- succeed to access db\033[0m"


def main():
    # 获取 SSM API
    test_url = u"ssm.test.tencentcloudapi.com"

    db_config = DbConfig(
        params={
            u'secret_name': u"test",  # 凭据名
            u'ip_address': u"127.0.0.1",  # 数据库地址
            u'port': 58366,  # 数据库端口
            u'db_name': u"database_name",  # 可以为空，或指定具体的数据库名
            u'param_str': u"charset=utf8&loc=Local",
        })
    ssm_service_config = SsmAccount(
        params={
            u'secret_id': u"secret_id",  # 需填写实际可用的SecretId
            u'secret_key': u"secret_key",  # 需填写实际可用的SecretKey
            u'url': test_url,
            u'region': u"ap-guangzhou"  # 选择凭据所存储的地域
        })
    config = Config(
        params={
            u'db_config': db_config,
            u'ssm_service_config': ssm_service_config,
            u'WATCH_FREQ': WATCH_FREQ
        })

    err = db_conn.init(config)
    if err:
        logging.error(u"failed to init db_conn with err: {0}".format(
            err.message).encode(u"utf-8"))
        return

    # 轮询：连接数据库
    t1 = LoopTimer(DB_FREQ, access_db)
    t1.start()


if __name__ == u"__main__":
    main()
