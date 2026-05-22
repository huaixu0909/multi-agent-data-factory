# multi-agent-data-factory

多 Agent 社会模拟数据合成平台第一版。

当前版本：`v0.6.0`

## 项目定位

本项目用于生成高质量 AI 训练对话数据。当前阶段已经支持 Code Review、客服投诉、技术面试三个数据合成场景，并接入 DeepSeek / OpenAI-compatible Chat Completions。v0.6 新增技术面试场景，用于模拟面试官提问、候选人回答、深度追问和能力评分。

## 当前功能

- FastAPI 后端服务
- 通用 Scenario 注册与路由结构
- Code Review 多 Agent 中文对话生成
- 客服投诉多 Agent 中文对话生成
- 技术面试多 Agent 中文对话生成
- 支持 DeepSeek API 真实 LLM 生成
- 未配置 API key 时自动回退到本地中文 mock
- 质量评分器：规则评分 + DeepSeek LLM-as-a-Judge
- 返回评分模式、评分模型、中文质量评语
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
- DeepSeek API / OpenAI-compatible Chat Completions

后续计划接入：

- LangGraph
- LangChain
- Qdrant
- PostgreSQL
- Celery + Redis

## DeepSeek 配置

可以添加 DeepSeek API。当前实现使用 OpenAI-compatible 的 `/chat/completions` 接口，默认配置如下：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

在项目根目录创建 `.env`：

```powershell
cd "D:\Code\codex\AI lab\multi-agent-data-factory"
notepad .env
```

写入：

```env
DEEPSEEK_API_KEY=你的_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=45
```

说明：

- `.env` 已被 `.gitignore` 忽略，不要提交 API key。
- 如果没有配置 `DEEPSEEK_API_KEY`，接口仍然可用，但会回退到 `mock` 模式。
- 如果 DeepSeek 调用失败，系统也会回退到本地中文 mock，并在返回结果里写入 `llm_error`。

## v0.5 架构

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
    llm.py                DeepSeek 调用与 JSON 解析
    models.py             通用数据模型
    scoring.py            规则评分与 LLM-as-a-Judge
    database.py           SQLite 持久化
    registry.py           Scenario 注册中心
    scenario.py           Scenario 抽象基类
  scenarios/
    code_review.py        Code Review 场景实现
    customer_complaint.py 客服投诉场景实现
    technical_interview.py 技术面试场景实现
```

核心流程：

```text
Scenario Input
-> 识别场景问题线索
-> 生成 Agent Persona
-> 优先调用 DeepSeek 生成中文多 Agent 对话
-> 失败时回退本地中文 mock
-> 优先调用 LLM-as-a-Judge 评分
-> 失败时回退规则评分器
-> ConversationRecord 标准化
-> SQLite 保存
-> JSONL 导出
```

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

生成一条 Code Review 多 Agent 中文对话。

请求示例：

```json
{
  "language": "python",
  "code_diff": "+ query = f\"SELECT * FROM users WHERE id = {user_id}\"\n+ cursor.execute(query)\n+ print(user)",
  "review_focus": ["security", "performance", "style"],
  "max_turns": 8
}
```

### POST /api/simulations/customer-complaint

生成一条客服投诉多 Agent 中文对话。

请求示例：

```json
{
  "industry": "电商",
  "complaint_type": "退款纠纷",
  "customer_profile": "老用户，最近一次订单体验很差",
  "complaint_detail": "商品显示已发货，但物流三天没有更新。客服一直让我等，现在我要求退款并给出明确处理时间。",
  "company_policy": "支持在符合规则时退款；涉及高额赔付时需要升级主管审核；客服必须避免承诺超出政策范围的补偿。",
  "emotion_level": "high",
  "max_turns": 8
}
```

### POST /api/simulations/technical-interview

生成一条技术面试多 Agent 中文对话。

请求示例：

```json
{
  "target_role": "AI 工程师",
  "candidate_level": "中级",
  "topic": "RAG",
  "difficulty": "medium",
  "candidate_profile": "候选人有 Python、FastAPI 和本地 RAG Demo 经验，但生产级监控、评估和故障恢复经验较少。",
  "interview_context": "希望考察候选人是否理解 RAG 的检索、chunking、相似度阈值、上下文拼接和幻觉控制。",
  "max_turns": 8
}
```

响应里会包含：

```json
{
  "generation_mode": "llm",
  "llm_provider": "deepseek",
  "llm_model": "deepseek-v4-flash",
  "scoring_mode": "llm_judge",
  "scoring_provider": "deepseek",
  "scoring_model": "deepseek-v4-flash",
  "score_feedback": ["对话引用了 diff 证据，冲突比较具体。"],
  "messages": []
}
```

如果未配置 DeepSeek：

```json
{
  "generation_mode": "mock",
  "llm_provider": null,
  "llm_model": null,
  "llm_error": "DEEPSEEK_API_KEY is not configured",
  "scoring_mode": "heuristic",
  "scoring_error": "DEEPSEEK_API_KEY is not configured"
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

## 下一步计划

- v0.7：前端多场景控制台增强
- v0.8：数据筛选、搜索和批量导出
- v0.9：Persona 生成器与场景模板管理
