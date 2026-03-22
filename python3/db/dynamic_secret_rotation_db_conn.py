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

import hashlib
import logging
import random
import threading
import time

import mysql.connector
from mysql.connector import pooling

from ssm.requester import Error, get_current_account


class Config:
    """完整配置信息类，包括数据库连接配置和 SSM 账号信息。"""

    DEFAULT_WATCH_FREQ = 10
    DEFAULT_BORROW_RETRY_COUNT = 3
    DEFAULT_BORROW_RETRY_INTERVAL_MS = 50

    def __init__(self, params=None):
        params = params or {}
        self.db_config = params.get("db_config")
        self.ssm_service_config = params.get("ssm_service_config")
        self.watch_freq = params.get("WATCH_FREQ", self.DEFAULT_WATCH_FREQ)
        self.rotation_grace_period = params.get("ROTATION_GRACE_PERIOD")
        self.borrow_retry_count = params.get(
            "BORROW_RETRY_COUNT", self.DEFAULT_BORROW_RETRY_COUNT
        )
        self.borrow_retry_interval_ms = params.get(
            "BORROW_RETRY_INTERVAL_MS", self.DEFAULT_BORROW_RETRY_INTERVAL_MS
        )

    def validate(self):
        if self.db_config is None:
            return Error("db_config is required")
        err = self.db_config.validate()
        if err:
            return err
        if self.ssm_service_config is None:
            return Error("ssm_service_config is required")
        if not getattr(self.ssm_service_config, "region", None):
            return Error("region is required")
        if self.watch_freq is None or self.watch_freq <= 0:
            return Error("WATCH_FREQ must be greater than 0")
        if self.rotation_grace_period is not None and self.rotation_grace_period <= 0:
            return Error("ROTATION_GRACE_PERIOD must be greater than 0")
        if self.borrow_retry_count <= 0:
            return Error("BORROW_RETRY_COUNT must be greater than 0")
        if self.borrow_retry_interval_ms < 0:
            return Error("BORROW_RETRY_INTERVAL_MS must be greater than or equal to 0")
        return None


class DbConfig:
    """数据库连接配置类。"""

    def __init__(self, params=None):
        params = params or {}
        self.secret_name = params.get("secret_name")
        self.ip_address = params.get("ip_address")
        self.port = params.get("port")
        self.db_name = params.get("db_name")
        self.param_str = params.get("param_str")
        self.pool_size = params.get("pool_size", 5)
        self.pool_name = params.get("pool_name", "ssm_pool")

    def validate(self):
        if not self.secret_name:
            return Error("secret_name is required")
        if not self.ip_address:
            return Error("ip_address is required")
        if not self.port:
            return Error("port is required")
        if self.pool_size <= 0:
            return Error("pool_size must be greater than 0")
        return None


class ConnCache:
    """当前连接池缓存。"""

    def __init__(self, conn_key=None, user_name=None, pool=None):
        self.conn_key = conn_key
        self.user_name = user_name
        self.pool = pool


class RetiredPool:
    def __init__(self, pool=None, expire_at=0.0):
        self.pool = pool
        self.expire_at = expire_at


class DynamicSecretRotationDb:
    """支持动态凭据轮转的数据库连接类。"""

    MAX_WATCH_FAILURES = 5
    # 指数退避最大倍数（2^5 = 32 倍）
    MAX_BACKOFF_MULTIPLIER = 5
    AUTH_ERROR_CODES = {1044, 1045, 1698}
    UNSUPPORTED_PARAMS = {"loc", "parseTime"}

    def __init__(self, params=None):
        params = params or {}
        self.config = params.get("config")
        self.db_conn = params.get("db_conn")
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._watch_thread = None
        self.closed = False
        self.watch_failures = 0
        self.last_error = None
        self._retired_pools = []

    def get_conn(self):
        """从当前连接池中获取一个连接。"""
        with self._lock:
            if self.closed or self.db_conn is None or self.db_conn.pool is None:
                return None
            pool = self.db_conn.pool

        for attempt in range(self.config.borrow_retry_count):
            try:
                return pool.get_connection()
            except mysql.connector.Error as exc:
                if self.__is_authentication_error(exc):
                    logging.warning("authentication failed when borrowing connection, refreshing pool")
                    err = self.__refresh_pool(force=True)
                    if err:
                        logging.error("failed to refresh pool after authentication error: %s", err.message)
                        return None
                    with self._lock:
                        if self.db_conn is None or self.db_conn.pool is None:
                            return None
                        pool = self.db_conn.pool
                    continue

                if self.__is_pool_exhausted(exc) and attempt + 1 < self.config.borrow_retry_count:
                    time.sleep(self.config.borrow_retry_interval_ms / 1000.0)
                    continue

                logging.error("failed to get connection from pool: %s", str(exc))
                return None

        return None

    def init(self, config):
        """初始化支持动态凭据轮转的数据库连接。"""
        self.config = config
        err = self.config.validate()
        if err:
            return err

        self.closed = False
        self._stop_event.clear()
        err = self.__refresh_pool(force=True)
        if err:
            return err

        self._watch_thread = threading.Thread(
            target=self.__watch_secret_change,
            name="SSMRotationWatcher",
            daemon=True,
        )
        self._watch_thread.start()
        logging.info("succeed to init db_conn")
        return None

    def close(self):
        """停止轮询并清理当前连接池中的空闲连接。"""
        with self._lock:
            if self.closed:
                return
            self.closed = True
            self._stop_event.set()
            current = self.db_conn
            self.db_conn = None
            retired_pools = self._retired_pools
            self._retired_pools = []

        if self._watch_thread and self._watch_thread.is_alive() and self._watch_thread is not threading.current_thread():
            self._watch_thread.join(timeout=1)

        self.__close_pool(current.pool if current else None)
        for retired in retired_pools:
            self.__close_pool(retired.pool)

    def is_healthy(self):
        with self._lock:
            return not self.closed and self.watch_failures < self.MAX_WATCH_FAILURES

    def __watch_secret_change(self):
        initial_delay = self.__randomized_initial_delay()
        if initial_delay > 0 and self._stop_event.wait(initial_delay):
            return

        interval = self.config.watch_freq
        while not self._stop_event.wait(interval):
            self.__cleanup_retired_pools(force=False)
            self.__watch_change()

            # 指数退避：连续失败超过阈值后，逐步增大轮询间隔
            with self._lock:
                failures = self.watch_failures
            if failures >= self.MAX_WATCH_FAILURES:
                exponent = min(failures - self.MAX_WATCH_FAILURES, self.MAX_BACKOFF_MULTIPLIER)
                interval = self.config.watch_freq * (1 << exponent)
                logging.warning("applying exponential backoff, next retry in %d seconds", interval)
            else:
                # 恢复正常后，重置为原始间隔
                interval = self.config.watch_freq

    def __watch_change(self):
        err = self.__refresh_pool(force=False)
        if err:
            with self._lock:
                self.watch_failures += 1
                self.last_error = err.message
            logging.error("failed to watch secret change (%d/%d): %s",
                          self.watch_failures, self.MAX_WATCH_FAILURES, err.message)
            return

        with self._lock:
            self.watch_failures = 0
            self.last_error = None

    def __refresh_pool(self, force=False):
        account, err = get_current_account(
            self.config.db_config.secret_name,
            self.config.ssm_service_config,
        )
        if err:
            return err

        conn_key = self.__build_conn_key(account)
        with self._lock:
            current = self.db_conn
            if (
                not force
                and not self.closed
                and current is not None
                and current.conn_key == conn_key
            ):
                return None

        pool_config = self.__build_pool_config(account)
        try:
            new_pool = pooling.MySQLConnectionPool(**pool_config)
            test_conn = new_pool.get_connection()
            try:
                test_conn.ping(reconnect=True)
            finally:
                test_conn.close()
        except mysql.connector.Error as exc:
            return Error("connect to cdb error: %s" % str(exc))

        cache = ConnCache(conn_key=conn_key, user_name=account.user_name, pool=new_pool)
        old_cache = None
        with self._lock:
            if self.closed:
                self.__close_pool(new_pool)
                return Error("dynamic secret rotation db is closed")
            old_cache = self.db_conn
            self.db_conn = cache

        if old_cache is not None and old_cache.user_name != account.user_name:
            logging.info("credential rotated: %s -> %s", old_cache.user_name, account.user_name)
        if old_cache is not None:
            self.__retire_pool(old_cache.pool)
        return None

    def __build_pool_config(self, account):
        db_config = self.config.db_config
        pool_config = {
            "pool_name": db_config.pool_name,
            "pool_size": db_config.pool_size,
            "pool_reset_session": True,
            "user": account.user_name,
            "password": account.password,
            "host": db_config.ip_address,
            "port": db_config.port,
        }
        if db_config.db_name:
            pool_config["database"] = db_config.db_name

        for key, value in self.__parse_extra_params(db_config.param_str).items():
            pool_config[key] = value
        return pool_config

    def __parse_extra_params(self, param_str):
        parsed = {}
        if not param_str:
            return parsed

        for param in param_str.split("&"):
            if "=" not in param:
                continue
            key, value = param.split("=", 1)
            if key in self.UNSUPPORTED_PARAMS:
                continue
            parsed[key] = value
        return parsed

    def __build_conn_key(self, account):
        key = "{0}\0{1}".format(account.user_name, account.password)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def __rotation_grace_period(self):
        if self.config.rotation_grace_period is not None:
            return float(self.config.rotation_grace_period)
        return max(30.0, float(self.config.watch_freq) * 3.0)

    def __retire_pool(self, pool):
        if pool is None:
            return
        with self._lock:
            self._retired_pools.append(
                RetiredPool(
                    pool=pool,
                    expire_at=time.time() + self.__rotation_grace_period(),
                )
            )

    def __cleanup_retired_pools(self, force=False):
        with self._lock:
            retired_pools = self._retired_pools
            if force:
                self._retired_pools = []
            else:
                now = time.time()
                self._retired_pools = [
                    item for item in retired_pools if item.pool is not None and item.expire_at > now
                ]

        now = time.time()
        for item in retired_pools:
            if item.pool is None:
                continue
            if not force and item.expire_at > now:
                continue
            self.__close_pool(item.pool)

    def __randomized_initial_delay(self):
        if self.config.watch_freq <= 0:
            return 0.0
        return random.uniform(0.0, float(self.config.watch_freq))

    def __close_pool(self, pool):
        if pool is None:
            return
        try:
            pool._remove_connections()
        except Exception:
            logging.debug("failed to eagerly close old pool", exc_info=True)

    def __is_authentication_error(self, exc):
        errno = getattr(exc, "errno", None)
        if errno in self.AUTH_ERROR_CODES:
            return True
        message = str(exc).lower()
        return "access denied" in message or "authentication" in message

    def __is_pool_exhausted(self, exc):
        return "pool exhausted" in str(exc).lower()
