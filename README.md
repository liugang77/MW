# 财智8 Web 版

[![CI](https://github.com/KyleZhang/MW/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Vue 3](https://img.shields.io/badge/Vue-3-42b883.svg)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab.svg)](https://www.python.org/)

个人记账理财应用 Web 版（Vue 3 + FastAPI），支持 PC 与移动端，无需登录，开箱即用。

> **声明**：本项目为个人**学习用途**，功能与界面参考桌面软件「财智8」实现，与其原始产品及出品方**无任何隶属或授权关系**，相关商标归各自所有者所有。请勿用于商业用途。

> 功能与架构设计详见 [docs/财智8-Web版-功能设计.md](docs/财智8-Web版-功能设计.md)

## 技术栈

- **前端**：Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router + ECharts
- **后端**：FastAPI + SQLAlchemy 2.x + Pydantic v2
- **存储**：SQLite（通用库 + 每账本独立库）

## 目录结构

```
MW/
├── main.py            # 一键启动入口（开发/生产模式）
├── backend/           # FastAPI 后端
│   ├── app/
│   └── requirements.txt
├── frontend/          # Vue 3 前端
│   └── package.json
└── docs/              # 设计文档
```

## 环境要求

- **Python** ≥ 3.10
- **Node.js** ≥ 18（建议 LTS）

## 首次安装

```powershell
# 后端依赖
cd backend
pip install -r requirements.txt
cd ..

# 前端依赖
cd frontend
npm install
cd ..
```

> 提示：`python main.py` 首次运行会自动检测并安装前后端依赖，可跳过上述手动步骤。

## 启动

### 开发模式（前后端热更新）

```powershell
python main.py
```

- 后端 API：<http://localhost:8000>
- 前端页面：<http://localhost:5173>（Vite 代理 `/api` 到后端）

### 生产/自用模式（单进程）

```powershell
python main.py --prod
```

构建前端后由后端单进程托管，访问 <http://localhost:8000> 即可。

### 其他命令

```powershell
python main.py --demo   # 生成覆盖全部功能的演示数据
python main.py --init   # 重置为初始默认（空）账本
```

## 已实现功能

- **多账本**：默认账本自动初始化，预置常用收支分类与账户
- **账户管理**：现金 / 储蓄卡 / 信用卡 / 钱包 / 储值 / 投资等，余额自动计算
- **记账**：支出 / 收入 / 转账 / 货币兑换 / 分拆 / 借入借出 / 工资收入，账户余额实时变更
- **流水**：类型筛选、关键词搜索、分页、编辑、删除
- **投资理财**：证券、基金、理财、债券、贵金属、外汇、网贷（P2P）等独立页面与买卖，持仓与盈亏计算
- **行情/汇率同步**：股票、基金、贵金属、外汇牌价在线更新
- **预算 / 分类 / 人员机构 / 财务计划与提醒**
- **统计**：收支概览、支出分类饼图、收支趋势图、投资收益报表
- **响应式**：桌面端顶部导航 + 移动端底部 Tab

## 数据存储

数据保存在本地 `backend/data/` 目录下的 SQLite 文件中：

- `common.db`：通用设置（账本、分类、币种、汇率、产品资料与价格等）
- `ledger_{id}.db`：每个账本一个独立文件（账户、流水、持仓、借贷、预算等）

> 数据库文件已在 `.gitignore` 中忽略，不会被提交；请自行备份。

## 安全须知

本应用**默认无登录鉴权**，仅适合本地或受信任的私有网络自用。请勿将服务直接暴露到公网，详见 [SECURITY.md](SECURITY.md)。

## 参与贡献

欢迎提交 Issue 与 Pull Request，详见 [贡献指南](CONTRIBUTING.md) 与 [行为准则](CODE_OF_CONDUCT.md)。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
```
