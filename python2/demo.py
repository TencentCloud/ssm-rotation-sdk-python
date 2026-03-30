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

import logging
import os
import sys
import time

from db.dynamic_secret_rotation_db_conn import Config, DbConfig, DynamicSecretRotationDb
from ssm.requester import LoopTimer, SsmAccount

sys.path.append(os.getcwdu())

db_conn = DynamicSecretRotationDb()
DB_FREQ = 20
WATCH_FREQ = 10

logging.basicConfig(filename=u"./demo.log", filemode=u"w", level=logging.DEBUG)


def access_db():
    print u"\033[33m--- access_db start\033[0m"
    conn = db_conn.get_conn()
    if conn is None:
        logging.error(u"failed to borrow db connection")
        print u"\033[31m*** Connection break! ***\033[0m"
        return
    try:
        conn.ping(reconnect=True)
    except Exception as exc:
        logging.error(u"failed to access db with err: %s", unicode(exc))
        print u"\033[31m*** Connection break! ***\033[0m"
        raise
    finally:
        conn.close()
    print u"\033[33m--- succeed to access db\033[0m"


def main():
    # ==================== 选择认证方式（三选一）====================

    # 方式一：固定 AK/SK（向后兼容，不推荐在生产环境使用）
    ssm_service_config = SsmAccount.with_permanent_credential(
        u"secret_id",       # 需填写实际可用的 SecretId
        u"secret_key",      # 需填写实际可用的 SecretKey
        u"ap-guangzhou",    # 选择凭据所存储的地域
    )

    # 方式二：临时凭据
    # ssm_service_config = SsmAccount.with_temporary_credential(
    #     u"tmp_secret_id",    # 临时 SecretId
    #     u"tmp_secret_key",   # 临时 SecretKey
    #     u"token",            # 临时 Token
    #     u"ap-guangzhou",     # 选择凭据所存储的地域
    # )

    # 方式三：CVM 角色绑定（推荐，仅限 CVM 环境）
    # ssm_service_config = SsmAccount.with_cam_role(
    #     u"your-cam-role-name",   # CVM 实例绑定的 CAM 角色名称
    #     u"ap-guangzhou",         # 选择凭据所存储的地域
    # )

    # 旧写法仍然兼容（等同于方式一）：
    # ssm_service_config = SsmAccount({
    #     u'secret_id': u"secret_id",
    #     u'secret_key': u"secret_key",
    #     u'url': u"",
    #     u'region': u"ap-guangzhou",
    # })

    # 可选：设置自定义接入点
    # ssm_service_config.with_endpoint(u"ssm.tencentcloudapi.com")

    db_config = DbConfig({
        u"secret_name": u"test",          # 凭据名
        u"ip_address": u"127.0.0.1",      # 数据库地址
        u"port": 3306,                    # 数据库端口
        u"db_name": u"database_name",     # 可以为空，或指定具体的数据库名
        u"param_str": u"charset=utf8",
    })
    config = Config({
        u"db_config": db_config,
        u"ssm_service_config": ssm_service_config,
        u"WATCH_FREQ": WATCH_FREQ,
    })

    err = db_conn.init(config)
    if err:
        logging.error(u"failed to init db_conn with err: %s", err.message)
        return

    LoopTimer(DB_FREQ, access_db).start()

    # 主线程阻塞等待，支持 Ctrl+C 优雅退出
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        db_conn.close()


if __name__ == u"__main__":
    main()
