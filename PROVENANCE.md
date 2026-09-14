# 分支来源与许可说明

本分支是 psycopg2 / psycopg3 SQLAlchemy 方言的独立维护分支，不是对主分支
ODBC 方案的替换。`main` 的源码、Windows 方案和发布包保持不变。

## 来源

- 分支基线：目标仓库 ODBC `main` 提交
  [`3e472ed465875bd3e47ed384e86e9c1e4a824016`](https://github.com/huaweicloud-samples/database-gaussdb-sqlalchemy-python-driver/commit/3e472ed465875bd3e47ed384e86e9c1e4a824016)。
- 方言、测试、指导和随附 psycopg2 文件的本仓库引入基线为
  [`18bc1e156d83d04a1cae49c73703c4ea7b14467e`](https://github.com/huaweicloud-samples/database-gaussdb-sqlalchemy-python-driver/commit/18bc1e156d83d04a1cae49c73703c4ea7b14467e)。
- `src/gaussdb_sqlalchemy/` 四个运行时模块保持该引入基线的内容不变。
- 未迁入 `gaussdb` / `gaussdb_pool` 驱动源码或 libpq/OpenSSL；驱动独立获取、安装。
  修复版底层驱动的获取和构建步骤见 [Linux 双驱动启动](docs/Linux双驱动启动.md)。
- 底层驱动采用[官方源码基线 9481e982](https://github.com/huaweicloud-samples/database-gaussdb-python/tree/9481e9828c4c33157ec538a939059ad7a2bea08d)
  加本仓库的 [GAUSSDB_LIBPQ_PATH 配套补丁](patches/gaussdb-libpq-path.patch)；
  补丁不代表官方上游已合入，不包含其他底层驱动改动，也不打入方言 wheel。

## 许可范围

- 本分支方言发行包沿用来源包声明的 `LGPL-3.0-only`，完整原文保留于
  [LICENSE.txt](LICENSE.txt)，并随方言 wheel 分发；本次不将其重新授权为 Apache。
- 原 ODBC 分支的 Apache-2.0 许可保留于
  [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)，用于追溯从原仓库继承的内容；
  不以该文本替换新增方言代码的许可。
- `vendor/gaussdb_psycopg2/` 的官方二进制保持原文件名和原始内容，其使用与分发
  仍遵循对应产品驱动自身条款，不因放入本仓库而改为方言代码的许可。

## 独立发布边界

该分支发布 `gaussdb-sqlalchemy`；`main` 发布 ODBC 路线的
`gaussdb-sqlalchemy-python-driver`。两者共享 Python 导入名和部分 SQLAlchemy
入口，必须放入不同虚拟环境，不能原样同装。不要把本分支整分支合入 `main`。
