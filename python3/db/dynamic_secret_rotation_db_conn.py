import logging
import threading
import mysql.connector
from ssm.requester import Error, LoopTimer, get_current_account
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


class Config:
    """完整配置信息类，包括数据库连接配置，SSM 账号信息等

    """
    def __init__(self, params=None):
        """
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
            self.db_config = params['db_config'] if 'db_config' in params else None
            self.ssm_service_config = params[
                'ssm_service_config'] if 'ssm_service_config' in params else None
            self.watch_freq = params[
                'WATCH_FREQ'] if 'WATCH_FREQ' in params else None

    def build_conn_str(self):
        """构造数据库连接串

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


class DbConfig:
    """数据库连接配置类

    """
    def __init__(self, params=None):
        """
        :param secret_name: 凭据名称
        :type secret_name: str
        :param ip_address: ip地址
        :type ip_address: str
        :param port: 端口
        :type port: int
        :param db_name: 数据库名称
        :type db_name: str
        :param param_str: 参数字符串，例如：charset=utf8&loc=Local
        :type param_str: str
        """
        if params is None:
            self.secret_name = None
            self.ip_address = None
            self.port = None
            self.db_name = None
            self.param_str = None
        else:
            self.secret_name = params['secret_name'] if 'secret_name' in params else None
            self.ip_address = params['ip_address'] if 'ip_address' in params else None
            self.port = params['port'] if 'port' in params else None
            self.db_name = params['db_name'] if 'db_name' in params else None
            self.param_str = params['param_str'] if 'param_str' in params else None


class ConnCache:
    """连接缓存类

    """
    def __init__(self, params=None):
        """
        :param conn_str: 缓存的当前正在使用的连接信息
        :type conn_str: str
        :param conn: MySQLConnection 连接实例
        :type conn: MySQLConnection class
        """
        if params is None:
            self.conn_str = None
            self.conn = None
        else:
            self.conn_str = params['conn_str'] if 'conn_str' in params else None
            self.conn = params['conn'] if 'conn' in params else None


class DynamicSecretRotationDb:
    """支持动态凭据轮转的数据库连接类

    """
    def __init__(self, params=None):
        """
        :param config: 配置信息
        :type config: Config class
        :param db_conn: 连接信息
        :type db_conn: ConnCache class
        """
        if params is None:
            self.config = None  # 初始化配置
            self.db_conn = None  # 存储的是 ConnCache 结构体
        else:
            self.config = params['config'] if 'config' in params else None
            self.db_conn = params['db_conn'] if 'db_conn' in params else None

    """
        调用方每次访问db时，需通过调用本方法获取db连接。
        注意：请不要在调用端缓存获取到的 *sql.DB, 以便确保在凭据发生轮换后，能及时的获得到最新的用户名和密码，防止由于用户名密码过期，而造成数据库连接失败！
    """
    def get_conn(self):
        """获取数据库连接

        :rtype :class: 数据库连接实例

        """
        print("get_conn, connstr=" + self.db_conn.conn_str)
        return self.db_conn.conn

    def __get_conn_str(self):
        """获取数据库连接串

        :rtype :str: 数据库连接串

        """
        print("get_conn_str, connstr=" + self.db_conn.conn_str)
        return self.db_conn.conn_str

    def __init_conn(self):
        """初始化数据库连接

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
        except TencentCloudSDKException as e:
            err = Error(str(e.args[0]))
        if err:
            return Error("connect to cdb error: %s" % err.message)

        # 将有效的 conn_str 缓存起来
        cur_conn = self.get_conn()
        self.db_conn = ConnCache(conn_str, mysql_conn)
        cur_conn.close()

        return None

    def __watch_change(self):
        """监控凭据变化

        :rtype None

        """
        conn_str, err = self.config.build_conn_str()
        if err:
            logging.error("failed to build conn_str, err= " + err.message)
            return
        if conn_str == self.__get_conn_str():
            print("secret value is not changed")
            return

        print("secret value changed from %s to %s" %
              (self.__get_conn_str(), conn_str))
        err = self.__init_conn()
        if err:
            logging.error("failed to init_conn, err=" + err.message)
            return
        print("**** succeed to change db_conn, new connStr=%s ****" %
              self.__get_conn_str())

    def __watch_secret_change(self):
        """轮询：监控凭据是否发生变化

        :rtype None

        """
        t = LoopTimer(self.config.WATCH_FREQ, self.__watch_change)
        t.start()

    """
        在服务初始化的时候，可调用本方法来完成数据库连接的初始化。
        本方法根据提供的凭据相关的信息（服务账号，凭据名），获得真实的数据库用户名和密码信息，然后生成数据库连接
    """
    def init(self, config):
        """初始化支持动态凭据轮转的数据库连接

        :param config: 配置信息
        :type config: Config class
        :rtype :error: 异常报错信息

        """
        self.config = config
        # 初始化数据库连接
        err = self.__init_conn()
        if err:
            return err
        print("succeed to init db_conn")

        # 开启轮转监控线程
        thread = threading.Thread(target=self.__watch_secret_change)
        thread.start()
        return None
