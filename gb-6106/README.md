# 砺光玻璃·压模履历槽页检修

撤销空跑、补录压模复测，在清班前验证单页压实和追溯槽号。

## 业务流程

1. 模具交班
2. 压模变更单
3. 槽页重放
4. 追溯地址表

定长槽目录、UTF-8 字节数组、页内更新迁移与压实，活记录的槽号保持稳定。

砺光玻璃 C4 线的 7 人工装和质保小组依靠手写压模工票交班。撤销的空跑容易混入合格履历，返工备注扩大后占用空间难预估，压实时偏移变化也容易被误认为追溯地址失效。上游提供模具传感器和复测工票。本应用在交班前重放变更，下游由质保主管读取稳定槽号和逐步证据。

06:50 录 GM-071 首件，06:52 录 GM-072 空跑，06:57 录 GM-073 更换下压块。08:10 撤销空跑，08:15 为 GM-071 补录裂纹复测。08:20 提交清班履历，08:25 检查压实前后偏移，08:30 下载 JSON 证据随工票交班。

页头 16 字节，槽目录每条 8 字节，记录头部偏移按原始 UTF-8 字节计算。页底向前分配，压实时只移动正文并改写目录偏移。删除保留槽项，防止旧地址指向其他履历。空间不足或重复写入不会改变已有记录。应用在 MySQL 保存批单和重放报告，页内算法独立在 Python 中运行。

## 启动

```sh
cp -n .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
```

打开 <http://localhost:18255>。OpenAPI 在 <http://localhost:19255/docs>，数据库映射到本机 17755。所有暴露端口只绑定回环地址。Compose 启动 frontend、backend、worker、db、redis，各自通过健康探针检查。数据库、Redis 和共享产物目录各有命名卷；任务状态及导出内容以数据库中的证据为准。

首次启动时幂等载入演示数据。手动载入可运行 `docker compose exec -T backend python -m scripts.seed_demo`。常规停止可用 `docker compose down`。验收环境清理才加 `-v`，它会删除本项目的数据卷。

## 角色与交接

演示账号共用口令 `Demo-DbWorkbench-2026`。

| 登录名 | 角色 | 可执行操作 |
|---|---|---|
| operator | 资料操作员 | 登记业务资料、设置「模拟页容量（字节，16–4096）」、提交、查看和下载结果 |
| reviewer | 业务复核员 | 查看执行证据、签署单次复核、下载交接单 |
| viewer | 只读观察员 | 查看资料、执行结果及审计，下载证据 |

选用「C4#03 · GM-C4-P07」对应的演示资料，保存一份复演资料，再以默认参数 192 提交。worker 保存结果摘要、业务明细和 SHA-256。复核员登录后在「追溯地址表」签署。

## 开发说明

| 部分 | 实现 |
|---|---|
| 前端 | 原生 HTML、CSS、JavaScript ES Modules、Nginx |
| 后端 | Python 3.11、FastAPI、SQLAlchemy、JWT |
| 数据库 | MySQL 8.0 |
| 后台执行 | Redis 通知、数据库持久任务队列和行锁、Python worker |

从 `backend/src/domain/scenario.py` 修改业务入口和演示口径，运行 `docker compose up -d --build --wait` 查看变更。数据库表结构在 `backend/src/models` 和 `backend/migrations`，输入模型在 `backend/src/schemas`。业务页和请求接口在 `frontend/src/pages`、`frontend/src/api`。资料、执行、复核三个工作流实体各有独立表和 API；场景输入及结果保留在所属资料和批次中。

角色枚举在 `backend/src/constants/roles.py`、`frontend/src/constants/roles.js`，用于服务端访问控制、账号初始化、前端导航与签署。批次状态在 `backend/src/constants/job_state.py`、`frontend/src/constants/states.js`，用于队列、状态 API、状态标记与轮询。登记、提交、完成和签署事件写入审计表。

`COMPOSE_PROJECT_NAME` 设置栈名，`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 设置端口。通过 `DB_PASSWORD`、`JWT_SECRET`、`DEMO_PASSWORD` 配置本地凭据。设置 `SEED_DEMO=false` 可关闭演示数据载入，此时数据库初始没有演示账号。数据库密码调整后，已有数据卷需在数据库内同步修改用户密码。

## 验收范围

在内存维护一个字节页，卷宗由 MySQL 持久化。没有多页分配器。 当前界面用 JSON 编辑业务资料，以 JSON 下载证据。过程和截图保存在批次的 [验收记录](../../test-artifacts/gb-6106/TESTING.md)。

[MIT License](LICENSE)
