### 应用程序使用自动轮换的凭据访问数据库 所需要使用的 lib 和 相应的代码示例


#### 使用场景

在应用程序的开发过程中，数据库是最常被用到的用于存储业务数据的基础服务。为了能够对数据库的访问权限进行有效的控制，应用程序只有在获得具有合适权限的账号和密码时，才能够创建数据库连接。为了降低账号和密码泄露的风险，应用程序需要定期更换使用的账号和密码信息。

SSM（凭据管理系统）能够完美的适用于上述场景，使得应用程序在避免频繁更换账号密码的麻烦的同时，保证业务数据的安全。



#### SSM SDK功能特性

基于 SSM（凭据管理系统）提供的数据库凭据功能，以及数据库账号安全管理的最佳实践，我们开发了一套可以方便应用程序集成的SSM SDK。应用程序只需要调用SSM SDK，传入必要的数据库连接相关的参数以及凭据名称，就可以直接获取到一个可用的数据库连接，而不必关心账号密码的获取和轮转的实现细节。

#### 风险提示

SSM在对数据库凭据进行周期性轮转的时候，会更新账号和密码。请严格按照**SDK使用说明**来使用SSM SDK。**不要在除了SSM SDK内部逻辑之外的任何地方缓存获取到的数据库连接，也不要缓存获取到的凭据中的任何信息**，以避免账号密码失效导致的数据库连接失败情况的发生。

#### 前置条件

1. 已在腾讯云平台开通了SSM服务（[开通SSM服务](https://console.cloud.tencent.com/ssm/cloud)）
2. 已在腾讯云平台购买了至少一台云数据库实例（目前只支持MySQL实例），完成了数据库的初始化，并创建了至少一个database。([MySQL控制台](https://console.cloud.tencent.com/cdb))
3. 已在SSM控制台创建了一个[数据库凭据](https://cloud.tencent.com/document/product/1140/57647)，并和指定的数据库做了关联。（具体操作指南参见：[创建数据库凭据](https://cloud.tencent.com/document/product/1140/57648)）
4. 已在腾讯云平台的[访问管理（CAM）控制台](https://console.cloud.tencent.com/cam/overview)创建了一个能够访问SSM凭据资源和MySQL实例资源的子账号，并给该子账号分配了[API密钥](https://console.cloud.tencent.com/cam/capi)（以便获取SecretId 和 SecretKey 用于API的访问）


#### 支持的Python 版本
python 2.7 及以上版本, python 3 及以上版本

#### SDK使用的代码示例

1. 安装依赖包

   ```shell
   $ pip install -r requirements.txt
   ```

2. 配置信息

   ```python
   db_config = DbConfig(
       params={
           'secret_name': "test",  # 凭据名
           'ip_address': "127.0.0.1",  # 数据库地址
           'port': 58366,  # 数据库端口
           'db_name': "database_name",  # 指定具体的数据库名，如果为空，则只连接到数据库实例，不连接具体的数据库
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
           'WATCH_FREQ': 10  # 监控凭据内容发生变化的间隔，一般间隔时间设置为10秒~60秒之间为宜
       })
   ```

3. 初始化数据库对象

   ```python
   db_conn = DynamicSecretRotationDb()
   err = db_conn.init(config)
   ```

4. 获取数据库连接

   ```python
   c = db_conn.get_conn()  # 警告：每次需要访问数据库时，都需要调用GetConn()来获取最新的DB连接，请不要在业务代码中缓存此对象，以免DB访问失败！
   try:
       c.ping()  # 示例中只是调用ping()方法测试账号密码的可用性。实际业务中，这里就可以执行具体的db操作了。
   except TencentCloudSDKException as e:
   	logging.error("failed to access db with err: {0}".format(str(
               e.args[0])).encode("utf-8"))
   ```

5. 关闭数据库连接

   ```python
   c.close()  # 当应用程序退出时，可主动关闭数据库连接。这是个通用的操作，和数据库凭据没有直接关系
   ```

   

