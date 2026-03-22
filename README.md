# SSM Rotation SDK for Python

腾讯云凭据管理服务（SSM）轮转 SDK，支持数据库凭据自动轮转。

## 功能特性

- 自动从 SSM 获取数据库凭据
- 定期监控凭据变化，自动更新连接池
- 线程安全的连接池管理
- 支持多种凭据认证方式
- 健康检查 API
- 凭据轮转时旧连接池延迟退休，降低高并发下连接中断风险
- 指数退避：Watcher 连续失败后自动增大轮询间隔，避免频繁请求 SSM 服务

## 认证方式

| 方式 | 工厂方法 | 说明 | 推荐 |
|------|----------|------|------|
| **CAM_ROLE** | `SsmAccount.with_cam_role()` | CVM 实例角色（元数据服务自动获取临时凭据） | ✅ 推荐 |
| **TEMPORARY** | `SsmAccount.with_temporary_credential()` | 临时 AK/SK/Token（需自行管理刷新） | ⚠️ 可选 |
| **PERMANENT** | `SsmAccount.with_permanent_credential()` | 固定 AK/SK（存在泄露风险） | ❌ 不推荐 |

> 使用 CAM 角色前需为 CVM 绑定 CAM 角色：[CVM 绑定角色](https://cloud.tencent.com/document/product/213/47668)

## 快速开始

### 环境要求

- Python 3.6+（推荐）或 Python 2.7+
- Python 3 使用 `python3/` 目录，Python 2 使用 `python2/` 目录

### 安装依赖

```shell
pip install -r requirements.txt
```

### 使用示例

```python
from db.dynamic_secret_rotation_db_conn import DynamicSecretRotationDb, Config, DbConfig
from ssm.requester import SsmAccount

# 1. SSM 账号配置（三选一）

# 方式一：CVM 角色绑定（推荐）
ssm_account = SsmAccount.with_cam_role(
    role_name="your-role-name",
    region="ap-guangzhou",
)

# 方式二：临时凭据
# ssm_account = SsmAccount.with_temporary_credential(
#     secret_id="tmpSecretId",
#     secret_key="tmpSecretKey",
#     token="token",
#     region="ap-guangzhou",
# )

# 方式三：固定凭据（不推荐）
# ssm_account = SsmAccount.with_permanent_credential(
#     secret_id="secretId",
#     secret_key="secretKey",
#     region="ap-guangzhou",
# )

# 2. 数据库配置
db_config = DbConfig(params={
    'secret_name': "your-secret-name",   # SSM 凭据名称
    'ip_address': "127.0.0.1",           # 数据库 IP
    'port': 3306,                        # 数据库端口
    'db_name': "your_database",          # 数据库名称（可选）
    'param_str': "charset=utf8",         # 额外连接参数（可选）
})

# 3. 构建配置
config = Config(params={
    'db_config': db_config,
    'ssm_service_config': ssm_account,
    'WATCH_FREQ': 10,                    # 凭据监控间隔（秒），建议 10-60
})

# 4. 创建连接工厂
db_conn = DynamicSecretRotationDb()
err = db_conn.init(config)
if err:
    raise Exception("SDK init failed: %s" % err.message)

# 5. 获取连接（每次调用获取新连接，用完务必 close）
conn = db_conn.get_conn()
if conn is not None:
    try:
        # 执行数据库操作
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
    finally:
        conn.close()  # 归还连接到池中

# 6. 健康检查
healthy = db_conn.is_healthy()

# 7. 应用退出时关闭
db_conn.close()
```

## 配置参数

### DbConfig（数据库配置）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|-----|------|-----|--------|------|
| secret_name | str | ✅ | - | SSM 凭据名称 |
| ip_address | str | ✅ | - | 数据库 IP |
| port | int | ✅ | - | 数据库端口 |
| db_name | str | ❌ | - | 数据库名称 |
| param_str | str | ❌ | - | 额外连接参数（如 `charset=utf8`） |
| pool_size | int | ❌ | 5 | 连接池大小 |

### SsmAccount（SSM 账号配置）

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| region | str | ✅ | 地域，如 ap-guangzhou |
| role_name | str | 条件 | 角色名称（CAM_ROLE 时必填） |
| secret_id | str | 条件 | AK（PERMANENT/TEMPORARY 时必填） |
| secret_key | str | 条件 | SK（PERMANENT/TEMPORARY 时必填） |
| token | str | 条件 | 临时 Token（TEMPORARY 时必填） |
| url | str | ❌ | 自定义 SSM 接入点 |

### Config（轮转配置）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|-----|------|-----|--------|------|
| db_config | DbConfig | ✅ | - | 数据库配置 |
| ssm_service_config | SsmAccount | ✅ | - | SSM 账号配置 |
| WATCH_FREQ | int | ❌ | 10 | 凭据监控间隔（秒），建议 10-60 |
| ROTATION_GRACE_PERIOD | int | ❌ | max(30, WATCH_FREQ*3) | 轮转后旧连接池延迟退休时间（秒） |
| BORROW_RETRY_COUNT | int | ❌ | 3 | 连接池耗尽时重试次数 |
| BORROW_RETRY_INTERVAL_MS | int | ❌ | 50 | 每次重试间隔（毫秒） |

## 健康检查 API

```python
# 检查 SDK 是否健康（未关闭且 Watcher 失败未超限）
healthy = db_conn.is_healthy()
```

## 连接池使用与关闭

### 推荐使用模式

每次访问数据库时，调用 `get_conn()` 获取连接，操作完成后在 `finally` 块中调用 `conn.close()` 归还连接到池中：

```python
conn = db_conn.get_conn()
if conn is None:
    # 连接池为空或 SDK 已关闭，需做降级处理
    logging.error("failed to get connection")
    return

try:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchall()
    cursor.close()
finally:
    conn.close()  # 归还连接到池中（不是断开 TCP 连接）
```

> ⚠️ **重要**：`conn.close()` 是将连接**归还到连接池**，而非销毁底层 TCP 连接。不调用 `close()` 会导致连接泄漏，最终池耗尽。

### 连接池耗尽处理

当连接池中所有连接都被借出时，`get_conn()` 会自动重试（由 `BORROW_RETRY_COUNT` 和 `BORROW_RETRY_INTERVAL_MS` 控制）。如果重试后仍无可用连接，返回 `None`。建议根据业务并发量合理设置 `pool_size`：

| 并发量 | 推荐 pool_size |
|--------|---------------|
| 低（< 10 QPS） | 5（默认） |
| 中（10-50 QPS） | 10-20 |
| 高（> 50 QPS） | 20-50 |

### 关闭 SDK

应用退出时**必须**调用 `db_conn.close()` 释放资源，该方法会：

1. 停止后台 Watcher 线程（不再轮询 SSM）
2. 清理当前连接池中的空闲连接
3. 清理所有退休连接池（轮转后延迟退休的旧池）

```python
# 推荐：配合 try/finally 或信号处理使用
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    db_conn.close()  # 确保资源释放
```

> 调用 `close()` 后，`get_conn()` 将始终返回 `None`，`is_healthy()` 将返回 `False`。

## 注意事项

- `region` 必填
- 每次访问数据库请调用 `get_conn()` 获取连接，使用完后务必 `close()` 归还
- **请勿缓存** `get_conn()` 返回的连接对象，凭据轮转后旧连接会失效
- **请勿跨线程共享**单个连接对象，`get_conn()` 本身是线程安全的
- 临时凭据有过期时间，SDK 不会自动刷新 TEMPORARY 类型凭据
- CAM_ROLE 方式通过元数据服务自动获取和刷新凭据，仅限 CVM 环境
- `param_str` 需使用 `mysql.connector` 支持的参数
- Python 2 版本请使用 `python2/` 目录下的代码

## 项目结构

```
ssm-rotation-sdk-python/
├── python3/                               # Python 3.6+ 版本
│   ├── db/
│   │   └── dynamic_secret_rotation_db_conn.py  # 连接工厂（核心类）
│   ├── ssm/
│   │   └── requester.py                        # SSM 请求器
│   └── demo.py                                 # 使用示例
├── python2/                               # Python 2.7+ 兼容版本（结构同上）
├── requirements.txt                       # 依赖包
├── CHANGELOG.md                           # 变更日志
├── CONTRIBUTING.md                        # 贡献指南
└── LICENSE                                # Apache License 2.0
```

## License

Apache License 2.0
