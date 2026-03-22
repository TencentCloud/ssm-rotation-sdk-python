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

import os
import logging
import sys
import time

from db.dynamic_secret_rotation_db_conn import DynamicSecretRotationDb, Config, DbConfig
from ssm.requester import LoopTimer, SsmAccount

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
    if c is None:
        logging.error("failed to borrow db connection")
        print("\033[31m*** Connection break! ***\033[0m")
        return
    try:
        c.ping(reconnect=True)
    except Exception as e:
        logging.error("failed to access db with err: %s", str(e))
        print("\033[31m*** Connection break! ***\033[0m")  # red
        raise  # throw exception
    finally:
        c.close()
    print("\033[33m--- succeed to access db\033[0m")


def main():
    # ==================== 选择认证方式（三选一）====================

    # 方式一：固定 AK/SK（向后兼容，不推荐在生产环境使用）
    ssm_service_config = SsmAccount.with_permanent_credential(
        secret_id="secret_id",      # 需填写实际可用的 SecretId
        secret_key="secret_key",    # 需填写实际可用的 SecretKey
        region="ap-guangzhou",      # 选择凭据所存储的地域
    )

    # 方式二：临时凭据
    # ssm_service_config = SsmAccount.with_temporary_credential(
    #     secret_id="tmp_secret_id",    # 临时 SecretId
    #     secret_key="tmp_secret_key",  # 临时 SecretKey
    #     token="token",                # 临时 Token
    #     region="ap-guangzhou",        # 选择凭据所存储的地域
    # )

    # 方式三：CVM 角色绑定（推荐，仅限 CVM 环境）
    # ssm_service_config = SsmAccount.with_cam_role(
    #     role_name="your-cam-role-name",  # CVM 实例绑定的 CAM 角色名称
    #     region="ap-guangzhou",            # 选择凭据所存储的地域
    # )

    # 旧写法仍然兼容（等同于方式一）：
    # ssm_service_config = SsmAccount(params={
    #     'secret_id': "secret_id",
    #     'secret_key': "secret_key",
    #     'url': "",
    #     'region': "ap-guangzhou",
    # })

    # 可选：设置自定义接入点
    # ssm_service_config.with_endpoint("ssm.test.tencentcloudapi.com")

    db_config = DbConfig(
        params={
            'secret_name': "test",          # 凭据名
            'ip_address': "127.0.0.1",      # 数据库地址
            'port': 58366,                  # 数据库端口
            'db_name': "database_name",     # 可以为空，或指定具体的数据库名
            'param_str': "charset=utf8",
        })
    config = Config(
        params={
            'db_config': db_config,
            'ssm_service_config': ssm_service_config,
            'WATCH_FREQ': WATCH_FREQ
        })

    err = db_conn.init(config)
    if err:
        logging.error("failed to init db_conn with err: %s", err.message)
        return

    # 轮询：连接数据库（LoopTimer 为守护线程，主线程退出时自动停止）
    t1 = LoopTimer(DB_FREQ, access_db)
    t1.start()

    # 主线程阻塞等待，支持 Ctrl+C 优雅退出
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断，正在关闭...")
    finally:
        db_conn.close()


if __name__ == "__main__":
    main()
