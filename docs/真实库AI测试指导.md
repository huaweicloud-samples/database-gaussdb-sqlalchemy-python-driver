# GaussDB SQLAlchemy psycopg2/psycopg3 真实库测试指导

本文面向内网测试人员或自动化测试 AI，用于验证 `feature/sqlalchemy-dialect-psycopg2-psycopg3` 分支中的 SQLAlchemy 方言是否能通过 psycopg3 和 psycopg2 连接真实 GaussDB 数据库。

当前仓库为 [`huaweicloud-samples/database-gaussdb-sqlalchemy-python-driver`](https://github.com/huaweicloud-samples/database-gaussdb-sqlalchemy-python-driver/tree/feature/sqlalchemy-dialect-psycopg2-psycopg3)。
`main` 保留 ODBC 方案，本分支是 psycopg 方言；两者不能装在同一个虚拟环境中。
本仓库没有 `gaussdb` 底层驱动源码，必须另行获取下文指定的修复版驱动。

## 1. 测试范围

本指导只验证 `src/gaussdb_sqlalchemy/` 方言包，不验证 ODBC 版本。

覆盖内容：

- SQLAlchemy 方言注册：`gaussdb://`、`gaussdb+psycopg://`、`gaussdb+psycopg2://`
- psycopg3 路线：底层使用 `gaussdb` Python 包
- psycopg2 路线：底层使用 `psycopg2`
- CPU 架构区分：`x86_64` 和 `arm64/aarch64`
- 真实库连接、`select 1`、驱动与 CPU 架构识别
- 数据库兼容模式识别：A/ORA→A、B/MYSQL→旧B、M→新MySQL M模式、PG→PG
- 命名参数绑定和标量结果
- SQLAlchemy Core 建表、插入、查询、反射、删表
- Unicode、空字符串、NULL 和长文本往返
- Numeric、Boolean、Date、DateTime 和二进制类型往返
- BIGINT 边界、Float 和嵌套 JSON 类型往返
- executemany 批量插入、UPDATE 和 DELETE
- 查询结果字段顺序、mapping 和 rowcount
- 事务提交、事务回滚和保存点回滚
- 复合主键、字段、索引和唯一约束反射
- 保留字字段引用、引号编译和反射
- 唯一约束冲突、SQLSTATE 与连接错误恢复
- 连接生命周期、连接池重复签入/签出
- 同一参数SQL跨事务重复执行
- SQLAlchemy ORM 增删改查、过滤、排序、聚合和 limit

当前有 **26 类真实库基础测试 + 6 类专项回归测试**。每配置一个有效的真实库
URL，两个测试文件共执行32条；完整的 psycopg2/psycopg3 × x86_64/ARM64
四组合矩阵最多执行128次，分别配置 A/B/M 三种模式最多执行384次。

专项回归位于 `tests/test_result_regressions_integration.py`：JSON对象及标量、
自定义JSON解码器、二进制返回类型及内容、唯一约束与复合列顺序、
INSERT游标关闭后rowcount、实际影响行数与参数数量不一致。唯一约束
用例把默认分布键包含在约束中，避免依赖全局二级索引功能。

本次修复及实际测试结果见[结果转换与约束反射修复验证](结果转换与约束反射修复验证.md)。

第二轮新增的隐藏系统列问题见[隐藏系统列反射修复](隐藏系统列反射修复.md)。
原有唯一约束专项已增强：同时检查唯一约束和索引的单表/批量反射结果，
不要只检查插入冲突或conkey解析是否报错。第三轮另新增2条行数专项，
默认总数为32条，实际验证范围见[第三轮修复验证](第三轮修复验证.md)。

测试矩阵：

| 场景 | CPU 架构 | 底层驱动 | SQLAlchemy URL 前缀 | 安装要求 |
|------|----------|----------|---------------------|----------|
| 1 | x86_64 | psycopg3 | `gaussdb+psycopg://` | 安装下文官方源码应用配套补丁后的 `gaussdb` |
| 2 | arm64/aarch64 | psycopg3 | `gaussdb+psycopg://` | 安装下文官方源码应用配套补丁后的 `gaussdb` |
| 3 | x86_64 | psycopg2 | `gaussdb+psycopg2://` | 安装 x86_64 对应的 psycopg2 whl 包 |
| 4 | arm64/aarch64 | psycopg2 | `gaussdb+psycopg2://` | 安装 arm64/aarch64 对应的 psycopg2 whl 包 |

## 2. 前置条件

Linux 优先按 [双驱动启动指导](Linux双驱动启动.md) 分别启动两条路线。
其中包含动态库目录配置、严格加载检查和独立进程测试命令。

### 2.1 代码分支

确认当前分支：

```bash
git branch --show-current
```

期望输出：

```text
feature/sqlalchemy-dialect-psycopg2-psycopg3
```

如果不是该分支：

```bash
git switch feature/sqlalchemy-dialect-psycopg2-psycopg3
```

### 2.2 Python 环境

建议优先使用 Python 3.11。psycopg2 路线以仓库随附的 GaussDB 官方 wheel
为准，不使用 PyPI 公共 `psycopg2` / `psycopg2-binary`。

Python 版本支持验证结论：

| Python 版本 | SQLAlchemy 方言包 | psycopg3 / gaussdb 路线 | psycopg2 路线 |
|-------------|-------------------|--------------------------|---------------|
| 3.8 | 不支持 | 不在当前方言交付范围 | 不支持 |
| 3.9 | 支持 | 支持 | 随附 wheel 不支持 |
| 3.10 | 支持 | 支持 | 随附 wheel 不支持 |
| 3.11 | 支持，单元测试已验证 | 支持 | 支持，需按 CPU 架构选择 x86_64 或 aarch64 wheel |
| 3.12 | 支持，单元测试已验证 | 支持 | 随附 wheel 不支持 |

说明：

- psycopg2 官方 wheel 安装后导出的 Python 顶层包为 `psycopg2`。
- 当前随附 wheel 只有 `py311-none-linux_x86_64` 和
  `py311-none-linux_aarch64` 两类，测试验收以 wheel tag 为准。
- 其他 Python 版本的 psycopg2 路线，需要驱动侧提供对应 Python 版本、
  Linux 平台和 CPU 架构的官方 wheel，并重新执行全部真实库测试。
- psycopg3 路线依赖 `gaussdb>=1.0.4`，要求 Python 3.9+；Linux 显式动态库路径
  还依赖下文的库路径加载补丁，不能仅凭版本号确认。
- 此表记录方言版本范围及历史验证，不表示所有 Python / CPU / 数据库模式组合
  已完成真实库验收；实际边界见前述修复报告。

```bash
python --version
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell 创建环境的写法如下，但这不代表本分支已有可直接使用的
Windows 底层驱动；Windows 的现成 ODBC 方案请使用主分支及独立环境：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2.3 安装 SQLAlchemy 方言

在仓库根目录执行：

```bash
python -m pip install '.[test]'
```

测试所需内容及来源：

| 内容 | 是否已在仓库 | 获取或配置方式 |
|------|---------------|----------------|
| 方言源码 | 是 | `src/gaussdb_sqlalchemy/` |
| 单元和真实库测试 | 是 | `tests/` |
| pytest、SQLAlchemy、Alembic | 否 | 安装 `.[test]` 时由 pip 获取；内网需提前同步这些 Python 包 |
| psycopg3 驱动 `gaussdb` | 仅含配套补丁 | 从官方仓库下载独立源码，应用 `patches/gaussdb-libpq-path.patch` 后非 editable 安装或构建 wheel |
| psycopg2 官方 wheel | 是 | `vendor/gaussdb_psycopg2/`，按 CPU 架构二选一 |
| psycopg3 所需 libpq / OpenSSL 等动态库 | 否 | 由目标环境提供匹配 CPU 架构的 GaussDB 客户端库 |
| GaussDB 地址和测试账号 | 否 | 测试人员通过环境变量提供，禁止写入仓库 |

完全离线测试前，还需要把 SQLAlchemy、Alembic、pytest 及其依赖同步到内网
Python 制品库或 wheelhouse。数据库地址、用户名和密码属于环境配置，不应提交
到 Git。

按需要安装底层驱动。

psycopg3 路线：官方来源为
[`huaweicloud-samples/database-gaussdb-python`](https://github.com/huaweicloud-samples/database-gaussdb-python)。
Linux 启动脚本依赖 `GAUSSDB_LIBPQ_PATH`；官方源码基线尚未包含此功能。
请先按[Linux 双驱动启动](Linux双驱动启动.md)下载官方固定基线源码并应用
本仓库[库路径加载补丁](../patches/gaussdb-libpq-path.patch)。
以下 `/path/to/gaussdb-python` 均指已经应用该补丁的独立源码目录。
完成准备后，从当前方言仓库根目录执行：

```bash
python -m pip install /path/to/gaussdb-python/gaussdb
python -m pip install '.[test]'
```

驱动不要用 editable 安装。离线交付时，在上述独立驱动目录执行
`python -m build --wheel gaussdb`，把 `gaussdb/dist/gaussdb-1.0.4-py3-none-any.whl`
带入内网安装；构建及动态库细节见[Linux 双驱动启动](Linux双驱动启动.md)。
本方言仓库不存在 `./gaussdb`，不可在这里执行驱动源码安装命令。
旧 PyPI / 内网制品库的同版本包不保证包含 `GAUSSDB_LIBPQ_PATH` 修复。

psycopg2 路线：

```bash
python -m pip install vendor/gaussdb_psycopg2/*-py311-none-linux_对应CPU架构.whl
python -m pip install '.[test]'
```

仓库随附两个 GaussDB 官方 psycopg2 wheel：

```text
*-py311-none-linux_x86_64.whl
*-py311-none-linux_aarch64.whl
```

psycopg2 路线需要安装与当前机器匹配的 GaussDB 官方 wheel，至少要匹配：

- Python 版本：当前仅 `py311`
- 操作系统：当前仅 Linux
- CPU 架构，例如 x86_64、aarch64、arm64

同一方言包可支持两种底层驱动，但 Linux 配套动态库可能不同，推荐按
[Linux 双驱动启动](Linux双驱动启动.md)创建独立环境和进程逐条验证。
如果目标环境已确认两种驱动的依赖可以同装，准备命令为：

```bash
python -m pip install /path/to/gaussdb-python/gaussdb
python -m pip install vendor/gaussdb_psycopg2/*-py311-none-linux_对应CPU架构.whl
python -m pip install '.[test]'
```

### 2.4 原生客户端库

psycopg3 和 psycopg2 都属于 libpq 协议路线。测试机器必须能加载对应驱动需要的 GaussDB/libpq 原生库。

检查重点：

- `import gaussdb` 是否成功
- `import psycopg2` 是否成功
- 运行进程能找到底层 `libpq` 及相关动态库
- 测试机器网络能访问 GaussDB 的 IP 和端口

检查命令：

```bash
python -c "import platform; print(platform.machine())"
python -c "import gaussdb; print('gaussdb ok')"
python -c "import psycopg2; print('psycopg2 ok')"
```

如果只验证其中一种驱动，另一种 import 失败可以忽略。

### 2.5 数据库账号权限

测试账号至少需要：

- 连接目标数据库
- 查询 `pg_database`
- 创建和删除测试表
- 插入、更新、删除、查询测试数据

测试表名统一使用 `gdb_sa_live_*` 前缀，测试结束会自动清理。

## 3. 连接串配置

不要修改测试脚本中的源码。请通过环境变量传入真实数据库地址。

### 3.1 psycopg3 显式入口（推荐）

`gaussdb+psycopg://` 走 psycopg3，也就是 `gaussdb` Python 包：

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG3_URL='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

本分支还保留 `gaussdb://` 默认入口，含义是 psycopg3；主分支同一入口含义是
ODBC，因此新配置不要省略驱动名。

建议按架构显式配置。x86_64 机器：

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG3_X86_URL='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

arm64/aarch64 机器：

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG3_ARM_URL='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

### 3.2 psycopg2 入口

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG2_URL='gaussdb+psycopg2://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

建议按架构显式配置。x86_64 机器：

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG2_X86_URL='gaussdb+psycopg2://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

arm64/aarch64 机器：

```bash
export GAUSSDB_SQLALCHEMY_PSYCOPG2_ARM_URL='gaussdb+psycopg2://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

测试用例会读取当前机器架构。如果在 arm64 机器上误配置了 `_X86_URL`，或在 x86_64 机器上误配置了 `_ARM_URL`，对应用例会自动 skipped，并在 `pytest -rs` 输出中说明原因。

### 3.3 单连接串入口

如果只验证一个数据库和一个驱动，也可以使用：

```bash
export GAUSSDB_SQLALCHEMY_TEST_URL='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
```

### 3.4 A/B/M 兼容库入口

如果有 A/B/M 三个兼容库，建议分别配置：

```bash
export GAUSSDB_SQLALCHEMY_TEST_URL_A='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/A兼容数据库名?sslmode=disable'
export GAUSSDB_SQLALCHEMY_TEST_URL_B='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/B兼容数据库名?sslmode=disable'
export GAUSSDB_SQLALCHEMY_TEST_URL_M='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/M兼容数据库名?sslmode=disable'
```

如果要让 A/B/M 都走 psycopg2，把协议头改成 `gaussdb+psycopg2://`。

变量名仅是测试标签，不会改变数据库实际模式。请先查询
`select datcompatibility from pg_database where datname=current_database()`：
`MYSQL` 表示旧 B 模式，`M` 才是新 MySQL M 模式；不能把两者混为一类。
模式识别修复后的实际结果和当前全量复测阻碍见
[模式识别修复验证](模式识别修复验证.md)。

### 3.5 多连接串入口

也可以用换行写多个 URL：

```bash
export GAUSSDB_SQLALCHEMY_TEST_URLS='
gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/db_a?sslmode=disable
gaussdb+psycopg2://用户名:URL编码后的密码@数据库IP:端口/db_b?sslmode=disable
'
```

### 3.6 密码 URL 编码

密码中如果包含特殊字符，需要 URL 编码。

常见字符：

```text
@  -> %40
#  -> %23
:  -> %3A
/  -> %2F
?  -> %3F
&  -> %26
```

生成编码：

```bash
python -c "from urllib.parse import quote_plus; print(quote_plus('你的密码'))"
```

## 4. 执行命令

### 4.1 单元测试

单元测试不连接真实数据库：

```bash
python -m pytest tests -m 'not integration' -v -rs
```

### 4.2 真实库测试

真实库测试需要先配置至少一个 `GAUSSDB_SQLALCHEMY_*URL` 环境变量：

```bash
python -m pytest tests -m integration -v -rs
```

上述直接运行方式要求当前进程已能正确加载驱动及配套动态库。Linux 推荐按
[双驱动启动指导](Linux双驱动启动.md)准备独立环境，设置当前路线的
`GAUSSDB_TEST_URL` 后执行 `bash tools/run_driver_test.sh psycopg3` 或
`bash tools/run_driver_test.sh psycopg2`；脚本先做严格加载检查再运行真实库测试。

### 4.3 本分支全部测试

```bash
python -m pytest tests -v -rs
```

如果没有配置真实库 URL，`test_dialect_integration.py` 会显示 skipped；这属于预期行为，不代表测试失败。

## 5. 通过标准

真实库测试通过时，至少应看到以下场景通过：

- `test_runtime_driver_and_architecture`
- `test_live_select_and_compatibility_detection`
- `test_bound_parameters_and_scalar_results`
- `test_bigint_boundaries_round_trip`
- `test_float_values_round_trip`
- `test_json_nested_values_round_trip`
- `test_result_metadata_mappings_and_rowcount`
- `test_quoted_reserved_identifier_and_reflection`
- `test_core_create_insert_query_reflect_drop`
- `test_transaction_rollback`
- `test_transaction_commit_persists_data`
- `test_savepoint_rollback_keeps_outer_transaction`
- `test_unicode_null_empty_and_long_text_round_trip`
- `test_numeric_boolean_date_datetime_round_trip`
- `test_binary_round_trip`
- `test_executemany_update_and_delete`
- `test_primary_key_and_column_reflection`
- `test_index_reflection`
- `test_unique_constraint_and_integrity_error`
- `test_statement_error_then_connection_rollback_and_reuse`
- `test_database_error_exposes_sqlstate`
- `test_connection_close_and_new_checkout`
- `test_repeated_parameter_execution_across_transactions`
- `test_connection_pool_repeated_checkouts`
- `test_orm_crud`
- `test_orm_filter_order_count_and_limit`

如果同时配置 psycopg3 和 psycopg2 两个 URL，每个场景会分别执行一遍。pytest `-v` 输出中的用例参数会带上环境变量名、驱动类型和架构，例如：

```text
GAUSSDB_SQLALCHEMY_PSYCOPG3_X86_URL:psycopg3:x86_64
GAUSSDB_SQLALCHEMY_PSYCOPG2_ARM_URL:psycopg2:arm64
```

通过示例：

```text
tests/test_dialect_integration.py::test_live_select_and_compatibility_detection[...] PASSED
tests/test_dialect_integration.py::test_bound_parameters_and_scalar_results[...] PASSED
tests/test_dialect_integration.py::test_core_create_insert_query_reflect_drop[...] PASSED
tests/test_dialect_integration.py::test_transaction_rollback[...] PASSED
tests/test_dialect_integration.py::test_savepoint_rollback_keeps_outer_transaction[...] PASSED
tests/test_dialect_integration.py::test_numeric_boolean_date_datetime_round_trip[...] PASSED
tests/test_dialect_integration.py::test_index_reflection[...] PASSED
tests/test_dialect_integration.py::test_orm_crud[...] PASSED
```

## 6. 常见问题

### 6.1 skipped

如果输出 skipped，并提示未设置 URL，说明没有配置真实库连接串。

处理：

```bash
export GAUSSDB_SQLALCHEMY_TEST_URL='gaussdb+psycopg://用户名:URL编码后的密码@数据库IP:端口/数据库名?sslmode=disable'
python -m pytest tests/test_dialect_integration.py -v -rs
```

### 6.2 No module named gaussdb

说明 psycopg3 路线的底层驱动未安装。

处理：

```bash
python -m pip install /path/to/gaussdb-python/gaussdb
```

独立驱动源码下载及离线 wheel 构建见 2.3 节；不能在本方言仓库查找 `gaussdb/`。

或只配置 `gaussdb+psycopg2://` URL，改测 psycopg2 路线。

### 6.3 No module named psycopg2

说明 psycopg2 未安装。

处理：

安装仓库中与当前 Python 和 CPU 架构匹配的 GaussDB 官方 wheel，不要安装
公共 `psycopg2-binary`：

```bash
python -m pip install vendor/gaussdb_psycopg2/*-py311-none-linux_对应CPU架构.whl
```

或只配置 `gaussdb://` / `gaussdb+psycopg://` URL，改测 psycopg3 路线。

### 6.4 连接失败

请检查：

- 数据库 IP 和端口是否能访问
- 账号密码是否正确
- 密码是否做了 URL 编码
- `sslmode` 是否符合数据库要求
- 测试机器是否能加载 GaussDB/libpq 原生库

### 6.5 建表权限失败

真实库测试会创建并删除 `gdb_sa_live_*` 表。请确认测试账号有建表、删表和 DML 权限。

## 7. 可直接交给测试 AI 的任务说明

```text
请在当前仓库执行 GaussDB SQLAlchemy 方言真实库测试。

1. 确认分支为 feature/sqlalchemy-dialect-psycopg2-psycopg3。
2. 创建 Python 虚拟环境。
3. 在本方言仓库根目录安装 '.[test]'。
   - psycopg3 按 docs/Linux双驱动启动.md 下载官方固定基线源码，应用本仓库的
     patches/gaussdb-libpq-path.patch 后，从独立源码目录非 editable 安装驱动，
     或安装应用补丁后构建的 wheel；本方言仓库不含 gaussdb 驱动完整源码。
   - psycopg2 使用 vendor/gaussdb_psycopg2/ 中与
     Python 版本和 CPU 架构匹配的官方 wheel，不安装公共 psycopg2-binary
4. 根据实际数据库信息和机器架构设置以下环境变量中的一个或多个：
   - GAUSSDB_SQLALCHEMY_PSYCOPG3_X86_URL
   - GAUSSDB_SQLALCHEMY_PSYCOPG3_ARM_URL
   - GAUSSDB_SQLALCHEMY_PSYCOPG2_X86_URL
   - GAUSSDB_SQLALCHEMY_PSYCOPG2_ARM_URL
   - GAUSSDB_SQLALCHEMY_TEST_URL_A
   - GAUSSDB_SQLALCHEMY_TEST_URL_B
   - GAUSSDB_SQLALCHEMY_TEST_URL_M
5. 运行：
   python -m pytest tests -m 'not integration' -v -rs
   Linux 按 docs/Linux双驱动启动.md 为当前路线配置 GAUSSDB_TEST_URL、动态库与
   独立环境，再执行 bash tools/run_driver_test.sh psycopg3 或 psycopg2。
   只有驱动和动态库已正确配置时，才直接运行：
   python -m pytest tests -m integration -v -rs
6. 汇总 Python 版本、驱动版本、数据库版本、兼容模式、pytest 结果。
7. 如失败，保留完整错误栈、连接串脱敏后的协议头和数据库兼容模式，不要输出真实密码。
```

## 8. 测试报告模板

```text
测试日期：
测试人员/执行工具：
代码分支：
提交号：
操作系统：
Python 版本：
CPU 架构：
SQLAlchemy 版本：
gaussdb 驱动版本：
psycopg2 驱动版本：
GaussDB 服务端版本：
数据库兼容模式：A / B / M / PG
连接串是否已脱敏：是 / 否

1. 单元测试结果：
命令：
结果：

2. psycopg3 真实库测试结果：
CPU 架构：x86_64 / arm64
连接串协议头：gaussdb:// 或 gaussdb+psycopg://
结果：
失败详情：

3. psycopg2 真实库测试结果：
CPU 架构：x86_64 / arm64
psycopg2 whl 包名：
连接串协议头：gaussdb+psycopg2://
结果：
失败详情：

4. 结论：
```
