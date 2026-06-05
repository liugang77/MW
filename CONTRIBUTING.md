# 贡献指南（Contributing）

感谢你对本项目的关注！本项目是一个**个人学习性质**的记账理财 Web 应用（仿照「财智8」的交互与功能），欢迎以 Issue 和 Pull Request 的形式参与改进。

## 开发环境准备

- **Python** ≥ 3.10
- **Node.js** ≥ 18（建议 LTS）
- **包管理**：后端用 `pip`，前端用 `npm`

```powershell
# 克隆仓库
git clone <your-fork-url>
cd MW

# 后端依赖
cd backend
pip install -r requirements.txt
cd ..

# 前端依赖
cd frontend
npm install
cd ..
```

## 本地运行

```powershell
# 开发模式（前后端热更新）
python main.py

# 生成演示数据（覆盖全部功能）
python main.py --demo

# 重置为初始空账本
python main.py --init
```

- 后端 API：<http://localhost:8000>
- 前端页面：<http://localhost:5173>

## 提交规范

1. 从 `main` 分支创建特性分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
2. 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)：
   - `feat: 新增外汇账户买卖功能`
   - `fix: 修正交易编辑后持仓重算`
   - `docs: 补充 README 启动说明`
3. 提交前请确保：
   - 前端通过类型检查：`cd frontend; npm run type-check`
   - 前端可正常构建：`npm run build`
   - 后端可正常导入：`cd backend; python -c "import app.main"`
4. 一个 PR 尽量只解决一个问题，保持改动聚焦。

## 代码风格

- **后端**：遵循 PEP 8；类型注解尽量完整；API 路由按业务域拆分到 `backend/app/api/`。
- **前端**：Vue 3 `<script setup>` + TypeScript；组件、Store、视图分目录组织；UI 使用 Element Plus。
- 不要提交本地数据库文件（`data/*.db`）、`node_modules/`、构建产物（`frontend/dist/`）。

## 报告问题

请使用 Issue 模板提交 Bug 报告或功能建议，并尽量附上复现步骤、期望结果与运行环境。

## 行为准则

参与本项目即表示你同意遵守 [行为准则](CODE_OF_CONDUCT.md)。
