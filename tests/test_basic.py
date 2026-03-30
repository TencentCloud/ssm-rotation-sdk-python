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

"""ssm_rotation_sdk 包的基础单元测试（不依赖外部服务）"""

import unittest


class TestImport(unittest.TestCase):
    """验证包可以正常导入"""

    def test_import_package(self):
        import ssm_rotation_sdk
        self.assertTrue(hasattr(ssm_rotation_sdk, "__version__"))
        self.assertEqual(ssm_rotation_sdk.__version__, "1.0.1")

    def test_import_public_classes(self):
        from ssm_rotation_sdk import (
            SsmAccount,
            CredentialType,
            Error,
            DbAccount,
            DynamicSecretRotationDb,
            Config,
            DbConfig,
        )
        # 确保所有类都可以实例化
        self.assertIsNotNone(SsmAccount)
        self.assertIsNotNone(DynamicSecretRotationDb)


class TestSsmAccount(unittest.TestCase):
    """验证 SsmAccount 工厂方法"""

    def test_with_cam_role(self):
        from ssm_rotation_sdk import SsmAccount, CredentialType
        acc = SsmAccount.with_cam_role(role_name="test-role", region="ap-guangzhou")
        self.assertEqual(acc.credential_type, CredentialType.CAM_ROLE)
        self.assertEqual(acc.role_name, "test-role")
        self.assertEqual(acc.region, "ap-guangzhou")

    def test_with_temporary_credential(self):
        from ssm_rotation_sdk import SsmAccount, CredentialType
        acc = SsmAccount.with_temporary_credential(
            secret_id="sid", secret_key="skey", token="tok", region="ap-beijing"
        )
        self.assertEqual(acc.credential_type, CredentialType.TEMPORARY)
        self.assertEqual(acc.secret_id, "sid")
        self.assertEqual(acc.token, "tok")

    def test_with_permanent_credential(self):
        from ssm_rotation_sdk import SsmAccount, CredentialType
        acc = SsmAccount.with_permanent_credential(
            secret_id="sid", secret_key="skey", region="ap-shanghai"
        )
        self.assertEqual(acc.credential_type, CredentialType.PERMANENT)

    def test_with_endpoint(self):
        from ssm_rotation_sdk import SsmAccount
        acc = SsmAccount.with_cam_role("role", "ap-guangzhou").with_endpoint("custom.endpoint.com")
        self.assertEqual(acc.url, "custom.endpoint.com")


class TestConfig(unittest.TestCase):
    """验证 Config / DbConfig 校验逻辑"""

    def test_db_config_validate_missing_secret_name(self):
        from ssm_rotation_sdk import DbConfig
        cfg = DbConfig(params={"ip_address": "127.0.0.1", "port": 3306})
        err = cfg.validate()
        self.assertIsNotNone(err)
        self.assertIn("secret_name", err.message)

    def test_db_config_validate_ok(self):
        from ssm_rotation_sdk import DbConfig
        cfg = DbConfig(params={
            "secret_name": "test",
            "ip_address": "127.0.0.1",
            "port": 3306,
        })
        err = cfg.validate()
        self.assertIsNone(err)

    def test_config_validate_missing_db_config(self):
        from ssm_rotation_sdk import Config
        cfg = Config(params={"ssm_service_config": object()})
        err = cfg.validate()
        self.assertIsNotNone(err)
        self.assertIn("db_config", err.message)

    def test_config_validate_missing_ssm_config(self):
        from ssm_rotation_sdk import Config, DbConfig
        db_cfg = DbConfig(params={
            "secret_name": "test",
            "ip_address": "127.0.0.1",
            "port": 3306,
        })
        cfg = Config(params={"db_config": db_cfg})
        err = cfg.validate()
        self.assertIsNotNone(err)
        self.assertIn("ssm_service_config", err.message)


class TestDynamicSecretRotationDb(unittest.TestCase):
    """验证 DynamicSecretRotationDb 基础行为"""

    def test_get_conn_before_init_returns_none(self):
        from ssm_rotation_sdk import DynamicSecretRotationDb
        db = DynamicSecretRotationDb()
        self.assertIsNone(db.get_conn())

    def test_is_healthy_before_init(self):
        from ssm_rotation_sdk import DynamicSecretRotationDb
        db = DynamicSecretRotationDb()
        # 未初始化时 closed=False, watch_failures=0 → healthy=True
        self.assertTrue(db.is_healthy())

    def test_close_sets_unhealthy(self):
        from ssm_rotation_sdk import DynamicSecretRotationDb
        db = DynamicSecretRotationDb()
        db.close()
        self.assertFalse(db.is_healthy())
        self.assertIsNone(db.get_conn())


class TestError(unittest.TestCase):
    """验证 Error 类"""

    def test_error_message(self):
        from ssm_rotation_sdk import Error
        err = Error("something went wrong")
        self.assertEqual(err.message, "something went wrong")

    def test_error_none_message(self):
        from ssm_rotation_sdk import Error
        err = Error()
        self.assertIsNone(err.message)


if __name__ == "__main__":
    unittest.main()
