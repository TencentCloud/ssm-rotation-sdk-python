# Changelog

本项目的所有重要变更将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.1] - 2026-03-22

### 优化

- Watcher 连续失败超过阈值后自动启用指数退避，避免频繁请求 SSM 服务
- 对齐 Java/Go SDK 的指数退避策略（最大退避倍数 2^5 = 32 倍）

## [1.0.0] - 2026-03-22

### 新增

- 支持从 SSM 自动获取数据库凭据
- 定期监控凭据变化，自动更新数据库连接池
- 线程安全的连接池管理（基于 `mysql.connector.pooling`）
- 三种认证方式：CAM_ROLE（推荐）、TEMPORARY、PERMANENT
- 健康检查 API（`is_healthy()`）
- 凭据轮转时旧连接池延迟退休（Grace Period），降低高并发下连接中断风险
- 连接池耗尽时支持短暂重试
- Watcher 启动随机抖动，避免多实例同时请求 SSM
- 认证错误时自动触发凭据刷新
- 指数退避：Watcher 连续失败超过阈值后逐步增大轮询间隔
- 支持自定义 SSM 接入点（endpoint）
- 支持额外数据库连接参数透传
- 同时支持 Python 2.7+ 和 Python 3.6+
- 使用示例（demo.py）
- Apache License 2.0
