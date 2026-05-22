# multi-agent-data-factory

多 Agent 社会模拟数据合成平台。

当前版本：`v1.1.0`

## 项目定位

本项目用于生成高质量 AI 训练对话数据。当前阶段已支持 Code Review、客服投诉、技术面试三个数据合成场景，并接入 DeepSeek / OpenAI-compatible Chat Completions。未配置 API Key 时，系统会自动回退到本地中文 mock，保证接口仍然可运行。

v1.1 在 LangGraph `StateGraph` 之上，把角色从 prompt 标签升级为独立运行的 Agent 节点。每个 Agent 节点只读取当前 state，只生成自己当前轮的一条发言，然后把消息写回共享状态。

## 当前功能

- FastAPI 后端服务
- 通用 Scenario 注册与路由结构
- LangGraph StateGraph 多 Agent 工作流
- 独立 Agent 节点逐轮执行
- Code Review 多 Agent 中文对话生成
- 客服投诉多 Agent 中文对话生成
- 技术面试多 Agent 中文对话生成
- DeepSeek 真实 LLM 生成
- LLM 调用失败时回退到本地中文 mock
- 质量评分器：规则评分 + DeepSeek LLM-as-a-Judge
- SQLite 保存 conversation
- conversation 分页查询、搜索、筛选
- JSONL 数据集导出
- Agent Persona 默认池
- Persona 使用次数、平均分、成功次数、权重与记忆更新
- Persona 查询接口
- Swagger API 文档

## 技术栈

- Python
- FastAPI
- Pydantic
- LangGraph
- LangChain Core
- SQLite
- Uvicorn
- DeepSeek API / OpenAI-compatible Chat Completions

后续计划接入：

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
cd "D:\Code\codex\AI lab\multi-agent-data-factory"
D:\Download\Coding\CondaData\envs_dirs\llm_env\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

访问：

```text
http://localhost:8001
http://localhost:8001/docs
http://localhost:8001/health
http://localhost:8001/api/scenarios
```

## DeepSeek 配置

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

- `.env` 已被 `.gitignore` 忽略，不要提交 API Key。
- 如果没有配置 `DEEPSEEK_API_KEY`，接口仍然可用，但会回退到 `langgraph_mock` 模式。
- 如果 DeepSeek 调用失败，结果里会写入 `llm_error`，评分失败时会写入 `scoring_error`。

## LangGraph 工作流

v1.1 的生成流程由 `app/core/workflow.py` 中的 `StateGraph` 编排。每个 `agent_turn_*` 都是一个独立节点。

```text
START
-> select_personas
-> detect_signals
-> agent_turn_01_developer
-> agent_turn_02_reviewer
-> agent_turn_03_developer
-> ...
-> quality_score
-> END
```

实际业务闭环：

```text
Scenario Input
-> 从 Persona 池选择 Agent
-> 识别场景问题线索
-> LangGraph 调度独立 Agent 节点逐轮发言
-> 每个 Agent 节点优先调用 DeepSeek
-> 单个 Agent 节点失败时只回退该轮本地中文 mock
-> LLM-as-a-Judge 或规则评分
-> ConversationRecord 标准化
-> SQLite 保存
-> 更新 Persona 记忆与权重
-> 分页 / 搜索 / 筛选
-> JSONL 导出
```

每条 conversation 会返回：

```json
{
  "workflow_engine": "langgraph_agent_nodes",
  "agent_trace": [],
  "workflow_steps": [
    "select_personas",
    "detect_signals",
    "agent_turn_01_developer",
    "agent_turn_02_reviewer",
    "quality_score"
  ],
  "generation_mode": "langgraph_agent_mock"
}
```

如果配置了 DeepSeek 且所有 Agent 节点调用成功，`generation_mode` 会是 `langgraph_agent_llm`。如果部分节点成功、部分节点回退，则是 `langgraph_agent_mixed`。

## 主要 API

### GET /health

健康检查。

### GET /api/scenarios

查看当前已注册的数据合成场景。

### GET /api/personas

查看当前 Persona 池。支持按场景筛选。

```text
GET /api/personas
GET /api/personas?scenario=code_review
```

响应包含每个 Persona 的角色、性格、目标、使用次数、平均分、成功次数、权重和最近记忆。

### GET /api/personas/{persona_id}

查看单个 Persona 详情。

### POST /api/simulations/code-review

生成一条 Code Review 多 Agent 中文对话。

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

```json
{
  "industry": "电商",
  "complaint_type": "退款纠纷",
  "customer_profile": "老用户，最近一次订单体验很差",
  "complaint_detail": "商品显示已发货，但物流三天没有更新。客服一直让我等，现在我要求退款并给出明确处理时间。",
  "company_policy": "支持在符合规则时退款；涉及高额赔付时需要升级主管审核。",
  "emotion_level": "high",
  "max_turns": 8
}
```

### POST /api/simulations/technical-interview

生成一条技术面试多 Agent 中文对话。

```json
{
  "target_role": "AI 工程师",
  "candidate_level": "中级",
  "topic": "RAG",
  "difficulty": "medium",
  "candidate_profile": "候选人有 Python、FastAPI 和本地 RAG Demo 经验。",
  "interview_context": "考察检索、chunking、相似度阈值、上下文拼接和幻觉控制。",
  "max_turns": 8
}
```

### GET /api/conversations

查看已生成的对话列表。支持分页、搜索和筛选。

常用参数：

```text
scenario=code_review | customer_complaint | technical_interview
accepted=true | false
min_score=8
max_score=10
q=关键词
page=1
page_size=10
```

示例：

```text
GET /api/conversations?scenario=code_review&accepted=true&min_score=8&q=SQL&page=1&page_size=10
```

### GET /api/conversations/{conversation_id}

查看单条对话详情。

### GET /api/datasets/export.jsonl

按当前筛选条件导出 JSONL 训练数据。

示例：

```text
GET /api/datasets/export.jsonl?scenario=technical_interview&accepted=true&min_score=8&q=RAG
```

JSONL 会包含：

- conversation 基本信息
- task_input
- workflow_engine
- workflow_steps
- agent_trace
- generation_mode
- agents
- messages
- scores

## 前端联调

启动个人主页后访问：

```text
http://localhost:3000/demos/multi-agent-data-factory
```

前端 Demo 支持：

- 三场景切换
- 场景模板快速填充
- 生成中文多 Agent 对话
- 查看 LangGraph 工作流节点
- 查看每个 Agent 节点的执行轨迹
- 查看质量评分
- 数据集搜索、筛选、分页
- 按当前筛选条件导出 JSONL
- 查看 Persona 池、历史表现和最近记忆

## 下一步计划

- v1.2：条件路由与动态对话
- v1.3：Agent Memory 长期记忆
- v1.4：Persona Generator 与场景模板管理
- v1.5：批量生成任务队列
