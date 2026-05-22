# multi-agent-data-factory

多 Agent 社会模拟数据合成平台第一版。

当前版本：`v0.2.0`

## 项目定位

本项目用于生成高质量 AI 训练对话数据。当前阶段聚焦 Code Review 数据合成，同时已经把后端重构为通用 Scenario 架构，后续可以逐步接入客服投诉、技术面试等场景。

## 当前功能

- FastAPI 后端服务
- 通用 Scenario 注册与路由结构
- Code Review 多 Agent 对话生成
- Persona 自动生成
- 基于代码 diff 的问题线索识别
- 自动质量评分
- SQLite 保存 conversation
- JSONL 数据集导出
- Swagger API 文档

## 技术栈

- Python
- FastAPI
- Pydantic
- SQLite
- Uvicorn

后续计划接入：

- LangGraph
- LangChain
- DeepSeek / OpenAI-compatible API
- Qdrant
- PostgreSQL
- Celery + Redis

## v0.2 架构

```text
app/
  main.py                 应用入口，只负责注册中间件和路由
  api/
    scenarios.py          场景列表接口
    simulations.py        数据生成接口
    conversations.py      对话查询接口
    datasets.py           数据集导出接口
  core/
    config.py             基础配置
    models.py             通用数据模型
    database.py           SQLite 持久化
    registry.py           Scenario 注册中心
    scenario.py           Scenario 抽象基类
  scenarios/
    code_review.py        Code Review 场景实现
```

核心思路：

```text
Scenario Request
-> Scenario.simulate()
-> ConversationRecord
-> SQLite Storage
-> JSONL Export
```

每个新场景都应该实现：

- 请求模型
- Persona 生成
- 多 Agent 对话生成
- 质量评分
- `Scenario.simulate()` 方法
- API 路由接入

## 本地运行

推荐使用当前 Conda 环境：

```text
D:\Download\Coding\CondaData\envs_dirs\llm_env\python.exe
```

安装依赖：

```powershell
cd "D:\Code\codex\AI lab\multi-agent-data-factory"
D:\Download\Coding\CondaData\envs_dirs\llm_env\python.exe -m pip install -r requirements.txt
```

启动服务：

```powershell
D:\Download\Coding\CondaData\envs_dirs\llm_env\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

访问：

```text
http://localhost:8001
http://localhost:8001/docs
http://localhost:8001/health
http://localhost:8001/api/scenarios
```

## API

### GET /health

健康检查。

### GET /api/scenarios

查看当前已注册的数据合成场景。

### POST /api/simulations/code-review

生成一条 Code Review 多 Agent 对话。

请求示例：

```json
{
  "language": "python",
  "code_diff": "+ query = f\"SELECT * FROM users WHERE id = {user_id}\"\n+ cursor.execute(query)\n+ print(user)",
  "review_focus": ["security", "performance", "style"],
  "max_turns": 8
}
```

### GET /api/conversations

查看已生成的对话列表。

支持按场景过滤：

```text
GET /api/conversations?scenario=code_review
```

### GET /api/conversations/{conversation_id}

查看单条对话详情。

### GET /api/datasets/export.jsonl

导出 JSONL 训练数据。

## v0.2 范围

当前版本重点完成架构升级：

```text
输入代码 diff
-> Code Review Scenario
-> 生成 Persona
-> 多 Agent 冲突讨论
-> Judge 总结
-> Quality Scorer 评分
-> ConversationRecord 标准化
-> SQLite 保存
-> JSONL 导出
```

这一步的价值是让项目从单一 Demo 变成可扩展的数据工厂骨架。

## 下一步计划

- v0.3：Code Review 接入真实 LLM
- v0.4：强化质量评分器
- v0.5：客服投诉场景
- v0.6：技术面试场景
- v0.7：前端多场景控制台

