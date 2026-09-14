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
当前测试启动依赖 `GAUSSDB_LIBPQ_PATH`。截至 2026-09-14，下述官方源码基线
尚未包含此功能，本仓库随附[库路径加载补丁](../patches/gaussdb-libpq-path.patch)。
请下载官方仓库固定提交
[`9481e9828c4c33157ec538a939059ad7a2bea08d`](https://github.com/huaweicloud-samples/database-gaussdb-python/tree/9481e9828c4c33157ec538a939059ad7a2bea08d)
的[完整源码 ZIP](https://github.com/huaweicloud-samples/database-gaussdb-python/archive/9481e9828c4c33157ec538a939059ad7a2bea08d.zip)，
解压到独立目录后，按下文应用补丁，再安装或构建其中的 `gaussdb` 子包。
这里是“官方源码 + 本仓库配套补丁”，不是声称官方上游或 PyPI 已发布此修复。
旧 PyPI 包不保证支持该变量，同为 1.0.4 也不能代替源码与补丁校验。
`gaussdb_c` 和 `gaussdb_binary` 不是该纯 Python 运行方式的必需品。

### 准备并构建 psycopg3 驱动

准备 Python、pip、Git 和 `build`。将官方源码解压目录作为下文
`/path/to/gaussdb-python`，不要指向本 SQLAlchemy 仓库。
从当前方言仓库根目录开始执行：

```bash
export GAUSSDB_DIALECT_SOURCE_DIR="$PWD"
cd /path/to/gaussdb-python
git apply --check "$GAUSSDB_DIALECT_SOURCE_DIR/patches/gaussdb-libpq-path.patch"
git apply "$GAUSSDB_DIALECT_SOURCE_DIR/patches/gaussdb-libpq-path.patch"
python -m pip install build
python -m build --wheel gaussdb
# 将 gaussdb/dist/gaussdb-1.0.4-py3-none-any.whl 带入内网。
```

补丁只应用一次；`--check` 失败时先核对源码基线、是否已经应用，不要跳过检查
直接交付旧驱动。若采用非 editable 源码安装，可以跳过 wheel 构建，但不能跳过补丁。
该补丁仅改变显式动态库路径查找，不提供 libpq、OpenSSL，也不修改系统库。

## psycopg3

返回当前 SQLAlchemy 仓库根目录，使用为本路线准备的虚拟环境：

```bash
python3 -m venv .venv-psycopg3
source .venv-psycopg3/bin/activate
# 必须是上节已应用补丁的独立驱动源码目录。
python -m pip install /path/to/gaussdb-python/gaussdb
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

### 本次准备流程验证（2026-09-14）

- 从上述官方固定提交的完整归档解压，在无 Git 仓库的源码目录中通过
  `git apply --check`、应用补丁，并成功构建 `gaussdb-1.0.4-py3-none-any.whl`。
- 校验显式绝对文件路径、相对路径、不存在路径、目录路径以及未指定路径时的回退行为。
- 在仓库外非 editable 安装新构建的驱动和方言 wheel，两条 DBAPI 路线均能构造
  engine，556 条方言非 integration 单测全部通过。
- 环境为 macOS ARM64、Python 3.11、PostgreSQL libpq 18（仅用于无连接加载检查）。
  本次未执行 Linux 环境或真实 GaussDB 回归，不能替代产品客户端及客户环境验收。

### 历史验证范围

历史首次启动验证（仅记录当时的范围）：Linux aarch64、Python 3.9、GaussDB 客户端 OpenSSL 3.0.9，
psycopg3 纯 Python 导入及 SQLAlchemy engine 构造成功。未执行真实库测试；
当时该容器未配备 Python 3.11，未验证官方 psycopg2 wheel 的运行。
后续两条路线的真实库专项结果见[第三轮修复验证](第三轮修复验证.md)；
本次文档更新提供官方源码加补丁的准备方式，不代表重新完成真实库验收。
