# multi-agent-data-factory

多 Agent 社会模拟数据合成平台第一版。

当前版本：`v0.1.0`

## 项目定位

本项目用于生成高质量 AI 训练对话数据。第一版聚焦 Code Review 场景，通过 Developer、Reviewer、Challenger、Judge 四类 Agent 模拟真实代码审查讨论，并对生成数据进行自动评分与保存。

## 当前功能

- FastAPI 后端服务
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
```

## API

### GET /health

健康检查。

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

### GET /api/conversations/{conversation_id}

查看单条对话详情。

### GET /api/datasets/export.jsonl

导出 JSONL 训练数据。

## v0.1 范围

当前版本不追求复杂平台化，重点验证：

```text
输入代码 diff
-> 生成 Persona
-> 多 Agent 冲突讨论
-> Judge 总结
-> Quality Scorer 评分
-> SQLite 保存
-> JSONL 导出
```

这是一条最小可运行的数据生产闭环。
