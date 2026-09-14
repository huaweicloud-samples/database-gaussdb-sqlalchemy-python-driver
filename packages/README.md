# 预构建方言 wheel

构建日期：2026-09-14。直接下载本目录的wheel即可，无需在内网重新构建。
本包属于 `feature/sqlalchemy-dialect-psycopg2-psycopg3` 分支，不是 `main` 的 ODBC 包。

- 文件：[gaussdb_sqlalchemy-0.1.0-py3-none-any.whl](gaussdb_sqlalchemy-0.1.0-py3-none-any.whl)，26,169字节。
- SHA256：`53a9c8f8f5845ac5a2e2d7ceb26e8c873bb82a117e03e4c81ff74c1471e06142`。
- 四个运行时模块与本仓库提交 [18bc1e1](https://github.com/huaweicloud-samples/database-gaussdb-sqlalchemy-python-driver/tree/18bc1e156d83d04a1cae49c73703c4ea7b14467e/src/gaussdb_sqlalchemy) 完全一致。
- 包含唯一约束/索引隐藏系统列修复、普通非RETURNING INSERT rowcount修复。
- 本次方言wheel仅更新内嵌README，不改变运行时代码；许可证已包含在wheel中。
- 仅包含SQLAlchemy方言，不包含psycopg2、gaussdb驱动或libpq/OpenSSL。
- Python要求为3.9+，SQLAlchemy要求为 `>=2.0,<2.2`；底层驱动仍须匹配目标环境。

## 校验和离线安装

将wheel和本目录的[SHA256SUMS](SHA256SUMS)一起下载到内网，在文件所在目录执行：

```bash
sha256sum -c SHA256SUMS
python -m pip install --no-index --no-deps --force-reinstall \
  gaussdb_sqlalchemy-0.1.0-py3-none-any.whl
python -m pip check
```

macOS可用 `shasum -a 256 -c SHA256SUMS` 校验。
版本仍为0.1.0，必须强制重装并重启实际测试的Python进程；不要仅看版本号或文件大小判断更新。
因内嵌README更新后重新构建，本包校验值与上一份成品不同。
请使用实际测试虚拟环境中的python。命令不联网、不替换已安装的底层驱动；
SQLAlchemy等运行/测试依赖必须事先准备好，不应与ODBC路线同名方言包混装。

连接串显式选择 `gaussdb+psycopg://` 或 `gaussdb+psycopg2://`。底层驱动需独立安装，
获取方式和动态库设置见[Linux双驱动启动](../docs/Linux双驱动启动.md)，
完整依赖清单及测试步骤见[真实库测试指导](../docs/真实库AI测试指导.md)。

## 本次迁移与构建检查

- 已检查wheel成员，没有混入底层驱动、vendor、测试、开发目录或凭据。
- 已在仓库之外的隔离目录离线安装，验证四个SQLAlchemy入口及执行上下文。
- 安装后四个运行时模块与当前修复源码SHA256一致。
- macOS ARM64、Python 3.11.15、SQLAlchemy 2.0.52：非integration测试556条全部通过。
- 仓库外隔离安装本wheel并明确从安装目录加载，再次运行556条单测全部通过。
- 四个入口及两条DBAPI路线能够构造engine，没有建立数据库连接。
- 26条基础+6条专项真实库用例均可收集；本次只收集，未执行真实数据库测试。
- 本机使用PostgreSQL libpq 18、PyPI psycopg2-binary作为无连接单测依赖；
  这不是GaussDB产品客户端或Linux官方psycopg2 wheel的验收。
- 此前本地B/M双驱动相关真库专项共28通过属于历史结果，不是本次重跑。
- 客户x86_64/Python 3.12环境仍需复测，不能据此宣称全量验收通过。
- 2026-09-14另验证了“官方驱动固定源码 + 随附库路径加载补丁”的构建、非 editable
  安装及加载流程，配合本wheel运行556条单测通过；本次未重跑Linux或真实数据库。

复测命令和范围见[第三轮修复验证](../docs/第三轮修复验证.md)。

若自行重建，wheel的ZIP时间戳和构建工具版本可能导致文件校验值不同；
本目录SHA256SUMS用于校验这里发布的这一份成品，不是任意重建产物的校验值。

## 自行构建与校验

在本方言仓库根目录执行，只构建一个方言wheel：

```bash
python -m pip install build
python -m build --wheel
# 输出 dist/gaussdb_sqlalchemy-0.1.0-py3-none-any.whl
python tools/verify_wheel.py dist/gaussdb_sqlalchemy-0.1.0-py3-none-any.whl
```

直接校验随仓库交付成品的运行时、README、许可证和四个入口，可执行
`python tools/verify_wheel.py`。
