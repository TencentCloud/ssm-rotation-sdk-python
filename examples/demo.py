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

"""
使用示例：通过 pip install ssm-rotation-sdk 安装后使用

    pip install ssm-rotation-sdk
"""

import logging
import time

from ssm_rotation_sdk import DynamicSecretRotationDb, Config, DbConfig, SsmAccount
from ssm_rotation_sdk.requester import LoopTimer

DB_FREQ = 20   # 数据库访问频率（秒）
WATCH_FREQ = 10  # 监控轮转频率（秒）

logging.basicConfig(filename='./demo.log', filemode='w', level=logging.DEBUG)

db_conn = DynamicSecretRotationDb()


def access_db():
    """连接数据库"""
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
        print("\033[31m*** Connection break! ***\033[0m")
        raise
    finally:
        c.close()
    print("\033[33m--- succeed to access db\033[0m")


def main():
    # ==================== 选择认证方式（三选一）====================

    # 方式一：CVM 角色绑定（推荐，仅限 CVM 环境）
    # ssm_account = SsmAccount.with_cam_role(
    #     role_name="your-cam-role-name",
    #     region="ap-guangzhou",
    # )

    # 方式二：临时凭据
    # ssm_account = SsmAccount.with_temporary_credential(
    #     secret_id="tmp_secret_id",
    #     secret_key="tmp_secret_key",
    #     token="token",
    #     region="ap-guangzhou",
    # )

    # 方式三：固定凭据（不推荐）
    ssm_account = SsmAccount.with_permanent_credential(
        secret_id="your_secret_id",
        secret_key="your_secret_key",
        region="ap-guangzhou",
    )

    # 可选：设置自定义接入点
    # ssm_account.with_endpoint("ssm.tencentcloudapi.com")

    db_config = DbConfig(params={
        'secret_name': "your-secret-name",
        'ip_address': "127.0.0.1",
        'port': 3306,
        'db_name': "your_database",
        'param_str': "charset=utf8",
    })

    config = Config(params={
        'db_config': db_config,
        'ssm_service_config': ssm_account,
        'WATCH_FREQ': WATCH_FREQ,
    })

    err = db_conn.init(config)
    if err:
        logging.error("failed to init db_conn with err: %s", err.message)
        return

    # 轮询：连接数据库
    t1 = LoopTimer(DB_FREQ, access_db)
    t1.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断，正在关闭...")
    finally:
        db_conn.close()


if __name__ == "__main__":
    main()
