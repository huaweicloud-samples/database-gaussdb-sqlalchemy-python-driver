# Linux 双驱动测试启动

两条路线使用同一个方言 wheel，但使用独立虚拟环境和进程。启动脚本只影响
子进程，不修改系统 OpenSSL 或数据库服务环境。

## 准备文件

- 当前 SQLAlchemy 分支完整源码（含 `src/gaussdb_sqlalchemy/`、`tests/` 和 `tools/`）。
- Python、SQLAlchemy、pytest、Alembic、typing-extensions 及其安装依赖。
- psycopg2：vendor 中与机器架构匹配的官方 wheel，要求 Linux Python 3.11。
- psycopg3：独立驱动仓中的修复版 `gaussdb` 驱动，以及目标架构的 GaussDB 客户端 lib
  目录，包含 libpq、libcrypto、libssl 和它们的依赖。库目录由测试环境提供。

本方言仓库不包含 `gaussdb/` 驱动源码。底层驱动官方来源是
[`huaweicloud-samples/database-gaussdb-python`](https://github.com/huaweicloud-samples/database-gaussdb-python)。
当前测试启动依赖的 `GAUSSDB_LIBPQ_PATH` 修复位于
[`JarrenL/gaussdb-python` 固定提交 bbb81f44](https://github.com/jarrenL/gaussdb-python/tree/bbb81f44a0d46483961d30a58ab2171e4af384ac)。
请下载其[完整源码 ZIP](https://github.com/jarrenL/gaussdb-python/archive/bbb81f44a0d46483961d30a58ab2171e4af384ac.zip)
并解压到独立目录，安装其中 `gaussdb` 子目录或从其构建的 wheel。
旧 PyPI 包不保证支持该变量，同为 1.0.4 也不能代替源码提交校验。
`gaussdb_c` 和 `gaussdb_binary` 不是该纯 Python 运行方式的必需品。

联网机器准备驱动 wheel（若直接安装源码，可跳过构建）：

```bash
# 进入独立驱动源码目录，不是在当前 SQLAlchemy 仓库中执行。
cd /path/to/gaussdb-python-bbb81f44a0d46483961d30a58ab2171e4af384ac
python -m pip install build
python -m build --wheel gaussdb
# 将 gaussdb/dist/gaussdb-1.0.4-py3-none-any.whl 带入内网。
```

## psycopg3

在仓库根目录执行，使用为本路线准备的虚拟环境：

```bash
python3 -m venv .venv-psycopg3
source .venv-psycopg3/bin/activate
python -m pip install /path/to/gaussdb-python-bbb81f44a0d46483961d30a58ab2171e4af384ac/gaussdb
# 离线时将上一行替换为：python -m pip install /path/to/gaussdb-1.0.4-py3-none-any.whl
python -m pip install '.[test]'
export PYTHON_BIN="$VIRTUAL_ENV/bin/python"
export GAUSSDB_LIB_DIR=/实际安装目录/app/lib
bash tools/run_driver_test.sh psycopg3 --check-only
```

目录必须是绝对路径，包含 `libpq.so.5`；如果其他依赖在不同目录，可配置
`GAUSSDB_EXTRA_LIB_DIRS`（多个目录用冒号分隔）。脚本在启动 Python 前设置
LD_LIBRARY_PATH、GAUSSDB_IMPL=python、GAUSSDB_LIBPQ_PATH。

验证输出应有模块绝对路径、pyformat、Implementation: python 和 libpq 版本。
检查还会构造 SQLAlchemy engine，但不连接数据库。

```bash
export GAUSSDB_TEST_URL='gaussdb+psycopg://用户:URL编码的密码@主机:端口/测试库'
bash tools/run_driver_test.sh psycopg3
```

## psycopg2

新终端中执行，架构后缀 x86_64 或 aarch64 二选一：

```bash
python3.11 -m venv .venv-psycopg2
source .venv-psycopg2/bin/activate
python -m pip install vendor/gaussdb_psycopg2/*-py311-none-linux_aarch64.whl
python -m pip install '.[test]'
export PYTHON_BIN="$VIRTUAL_ENV/bin/python"
bash tools/run_driver_test.sh psycopg2 --check-only
export GAUSSDB_TEST_URL='gaussdb+psycopg2://用户:URL编码的密码@主机:端口/测试库'
bash tools/run_driver_test.sh psycopg2
```

脚本清除继承的 psycopg3 库路径，使用官方 wheel 自带依赖。确实需要额外库时，
用 PSYCOPG2_EXTRA_LIB_DIRS 指定与这个 wheel 配套的目录。

## 失败排查与验收

- 脚本清除 LD_PRELOAD，避免继承旧预加载方案。
- 导入失败、缺少 paramstyle/ClientCursor、缺少 URL 都直接报错，不会跳过。
- 使用专门测试库和拥有建表、删表、DML、目录查询权限的账号。
- 不要将真实 URL、密码或含敏感信息的测试日志提交到仓库。
- OpenSSL 符号错误：检查配套库和架构，不能用重命名系统库的方式解决。
- Linux 可用 `LD_LIBRARY_PATH="$GAUSSDB_LIB_DIR" ldd "$GAUSSDB_LIB_DIR/libpq.so.5"`
  检查依赖；存在 not found 时先补齐同套客户端库。
- --check-only 成功仅代表驱动和方言能加载；真实库测试通过后才代表连接路线通过。

历史首次启动验证（仅记录当时的范围）：Linux aarch64、Python 3.9、GaussDB 客户端 OpenSSL 3.0.9，
psycopg3 纯 Python 导入及 SQLAlchemy engine 构造成功。未执行真实库测试；
当时该容器未配备 Python 3.11，未验证官方 psycopg2 wheel 的运行。
后续两条路线的真实库专项结果见[第三轮修复验证](第三轮修复验证.md)；
本次仓库迁移只调整结构和指引，不代表重新完成真实库验收。
