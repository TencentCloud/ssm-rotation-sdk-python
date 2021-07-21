# -*- coding: utf-8 -*
import logging
import threading
import mysql.connector
from __future__ import absolute_import
from ssm.requester import Error, LoopTimer, get_current_account
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


class Config(object):
    u"""完整配置信息类，包括数据库连接配置，SSM 账号信息等

    """
    def __init__(self, params=None):
        u"""
        :param db_config: 数据库连接配置
        :type db_config: DbConfig class
        :param ssm_service_config: SSM 账号信息
        :type ssm_service_config: SsmAccount class
        :param WATCH_FREQ: 监控轮转频率，以秒为单位
        :type WATCH_FREQ: int
        """
        if params is None:
            self.db_config = None
            self.ssm_service_config = None
            self.watch_freq = None
        else:
            self.db_config = params[
                u'db_config'] if u'db_config' in params else None
            self.ssm_service_config = params[
                u'ssm_service_config'] if u'ssm_service_config' in params else None
            self.watch_freq = params[
                u'WATCH_FREQ'] if u'WATCH_FREQ' in params else None

    def build_conn_str(self):
        u"""构造数据库连接串

        :rtype :str: 数据库连接信息
        :rtype :error: 异常报错信息

        """
        # secret_value里面存储了用户名和密码，格式为：user_name:password
        account, err = get_current_account(self.db_config.secret_name, self.ssm_service_config)
        if err:
            return "", err
        # connection string 的格式： {user}:{password}@tcp({ip}:{port})/{dbName}?charset=utf8&loc=Local
        conn_str = account.user_name + ":" + account.password + "@tcp(" + self.db_config.ip_address + ":" + \
                   str(self.db_config.port) + ")/" + self.db_config.db_name
        if self.db_config.param_str is not None and len(self.db_config.param_str) != 0:
            conn_str = conn_str + "?" + self.db_config.param_str
        return conn_str, None


class DbConfig(object):
    u"""数据库连接配置类

    """
    def __init__(self, params=None):
        u"""
        :param timeout: 连接超时时长
        :type timeout: int
        :param pool_size: 连接池大小，默认值为5
        :type pool_size: int
        :param conn_str: 数据库连接串，包含连接凭据（或用户名，登录密码）、主机号、端口号等，格式为"{secret_name}@tcp({ip}:{port})/{dbName}?charset=utf8&loc=Local"
        :type conn_str: str
        """
        if params is None:
            self.timeout = None
            self.pool_size = None
            self.conn_str = None
        else:
            self.timeout = params[u'timeout'] if u'timeout' in params else None
            self.pool_size = params[
                u'pool_size'] if u'pool_size' in params else None
            self.conn_str = params[u'conn_str'] if u'conn_str' in params else None


class ConnCache:
    u"""连接缓存类

    """
    def __init__(self, params=None):
        u"""
        :param conn_str: 缓存的当前正在使用的连接信息
        :type conn_str: str
        :param conn: MySQLConnection 连接实例
        :type conn: MySQLConnection class
        """
        if params is None:
            self.conn_str = None
            self.conn = None
        else:
            self.conn_str = params[u'conn_str'] if u'conn_str' in params else None
            self.conn = params[u'conn'] if u'conn' in params else None


class DynamicSecretRotationDb(object):
    u"""支持动态凭据轮转的数据库连接类

    """
    def __init__(self, params=None):
        u"""
        :param config: 配置信息
        :type config: Config class
        :param db_conn: 连接信息
        :type db_conn: ConnCache class
        """
        if params is None:
            self.config = None  # 初始化配置
            self.db_conn = None  # 存储的是 ConnCache 结构体
        else:
            self.config = params[u'config'] if u'config' in params else None
            self.db_conn = params[u'db_conn'] if u'db_conn' in params else None

    """
        调用方每次访问db时，需通过调用本方法获取db连接。
        注意：请不要在调用端缓存获取到的 *sql.DB, 以便确保在凭据发生轮换后，能及时的获得到最新的用户名和密码，防止由于用户名密码过期，而造成数据库连接失败！
    """
    def get_conn(self):
        """获取数据库连接

        :rtype :class: 数据库连接实例

        """
        print u"get_conn, connstr=" + self.db_conn.conn_str
        return self.db_conn.conn

    def __get_conn_str(self):
        """获取数据库连接串

        :rtype :str: 数据库连接串

        """
        print u"get_conn_str, connstr=" + self.db_conn.conn_str
        return self.db_conn.conn_str

    def __init_conn(self):
        u"""初始化数据库连接

        :rtype :error: 异常报错信息

        """
        account, err = get_current_account(self.config.db_config.secret_name, self.config.ssm_service_config)
        if err:
            return err
        conn_str, err = self.config.build_conn_str()
        if err:
            return err

        mysql_conn = None
        try:
            # 创建 MySql 数据库连接对象
            mysql_conn = mysql.connector.connect(user=account.user_name,
                                                  password=account.password,
                                                  host=self.config.db_config.ip_address,
                                                  port=self.config.db_config.port)
            mysql_conn.ping()
        except TencentCloudSDKException, e:
            err = Error(e.message)
        if err:
            return Error(u"connect to cdb error: %s" % err.message)

        # 将有效的 conn_str 缓存起来
        cur_conn = self.get_conn()
        self.db_conn = ConnCache(conn_str, mysql_conn)
        cur_conn.close()

        return None

    def __watch_change(self):
        u"""监控凭据变化

        :rtype None

        """
        conn_str, err = self.config.build_conn_str()
        if err:
            logging.error(u"failed to GetSecretValue, err=" + err.message)
            return
        if conn_str == self.__get_conn_str():
            print u"secret value is not changed"
            return

        print u"secret value changed from %s to %s" % (self.__get_conn_str(), conn_str)
        err = self.__init_conn()
        if err:
            logging.error(u"failed to init_conn, err=" + err.message)
            return
        print u"**** succeed to change db_conn, new connStr=%s ****" % self.__get_conn_str()

    def __watch_secret_change(self):
        u"""轮询：监控凭据是否发生变化

        :rtype None

        """
        t = LoopTimer(self.config.WATCH_FREQ, self.__watch_change)
        t.start()

    """
        在服务初始化的时候，可调用本方法来完成数据库连接的初始化。
        本方法根据提供的凭据相关的信息（服务账号，凭据名），获得真实的数据库用户名和密码信息，然后生成数据库连接
    """
    def init(self, config):
        u"""初始化支持动态凭据轮转的数据库连接

        :param config: 配置信息
        :type config: Config class
        :rtype :error: 异常报错信息

        """
        self.config = config
        # 初始化数据库连接
        err = self.__init_conn()
        if err:
            return err
        print u"succeed to init db_conn"

        # 开启轮转监控线程
        thread = threading.Thread(target=self.__watch_secret_change)
        thread.start()
        return None
