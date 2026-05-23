# multi-agent-data-factory

多 Agent 社会模拟数据合成平台。

当前版本：`v1.5.0`

## 项目定位

本项目用于生成高质量 AI 训练对话数据。当前阶段支持 Code Review、客服投诉、技术面试三个数据合成场景，并接入 DeepSeek / OpenAI-compatible Chat Completions。未配置 API Key 时，系统会自动回退到本地中文 mock，保证接口仍然可运行。

v1.5 在 Agent Memory 基础上加入本地批量生成任务队列。系统可以通过 `/api/jobs` 提交一批数据生产任务，接口立即返回 `job_id`，后台按顺序生成多条 conversation、保存到 SQLite、更新 Persona Memory，并持续记录任务进度。

## 当前功能

- FastAPI 后端服务
- 通用 Scenario 注册与路由结构
- LangGraph StateGraph 条件路由工作流
- 独立 Agent 节点逐轮执行
- Agent 生成前读取长期记忆
- 生成后按成功经验、失败教训和策略建议沉淀记忆
- 本地后台批量生成任务队列
- 批量任务进度查询、成功/失败统计和生成 conversation 追踪
- Code Review 多 Agent 中文对话生成
- 客服投诉多 Agent 中文对话生成
- 技术面试多 Agent 中文对话生成
- DeepSeek 真实 LLM 生成
- 单个 Agent 节点调用失败时只回退该轮本地中文 mock
- 质量评分器：规则评分 + DeepSeek LLM-as-a-Judge
- SQLite 保存 conversation
- conversation 分页查询、搜索、筛选
- JSONL 数据集导出
- Agent Persona 默认池
- Persona 使用次数、平均分、成功次数、权重与长期记忆更新
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

## 本地运行

```powershell
cd "D:\Code\codex\AI lab\multi-agent-data-factory"
D:\Download\Coding\CondaData\envs_dirs\llm_env\python.exe -m pip install -r requirements.txt
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

```env
DEEPSEEK_API_KEY=你的_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=45
```

说明：

- `.env` 已被 `.gitignore` 忽略，不要提交 API Key。
- 如果没有配置 `DEEPSEEK_API_KEY`，接口仍然可用，但会回退到 `langgraph_routed_mock`。
- 如果部分 Agent 节点调用成功、部分失败，会返回 `langgraph_routed_mixed`。

## LangGraph + Agent Memory

v1.3 的生成流程由 `app/core/workflow.py` 中的 `StateGraph` 编排。

```text
START
-> select_personas
-> detect_signals
-> router
   -> agent_node_developer / agent_node_reviewer / ...
   -> router
   -> agent_node_...
   -> router
   -> quality_score
-> END
```

实际业务闭环：

```text
Scenario Input
-> 从 Persona 池选择 Agent
-> 识别场景问题线索
-> router 判断下一个 Agent
-> Agent 节点独立生成当前轮发言
-> Agent prompt 注入自身长期记忆
-> 发言写回 shared state
-> router 根据最新 state 继续判断
-> 满足停止条件后进入 quality_score
-> SQLite 保存 conversation
-> 更新 Persona 长期记忆与权重
-> 分页 / 搜索 / 筛选
-> JSONL 导出
```

批量生成闭环：
```text
POST /api/jobs
-> 创建 batch_jobs 记录
-> 后台线程逐条生成 conversation
-> 保存 conversation
-> 更新 Persona Memory
-> 持续更新 completed / accepted / failed / conversation_ids
-> GET /api/jobs/{job_id} 查询进度
```

## 路由策略

Code Review：

```text
Developer -> Reviewer
高危风险 -> Challenger
需要回应 -> Developer
信息足够 -> Judge
```

客服投诉：

```text
Customer -> SupportAgent
涉及赔付 / 隐私 / 政策边界 -> ComplianceReviewer
升级风险 -> EscalationManager
方案明确 -> SupportAgent 收尾
```

技术面试：

```text
Interviewer -> Candidate
回答需要深挖 -> FollowupInterviewer
信息足够 -> Evaluator
```

## 返回字段

每条 conversation 会返回：

```json
{
  "workflow_engine": "langgraph_memory_agents",
  "generation_mode": "langgraph_routed_mock",
  "workflow_steps": [
    "select_personas",
    "detect_signals",
    "route_to_developer",
    "agent_turn_01_developer",
    "route_to_reviewer",
    "agent_turn_02_reviewer",
    "route_to_quality_score",
    "quality_score"
  ],
  "agent_trace": [
    {
      "turn": 2,
      "role": "Reviewer",
      "node": "agent_turn_02_reviewer",
      "mode": "mock",
      "route_reason": "开发者完成初始说明，进入代码审查。"
    }
  ]
}
```

## 主要 API

### GET /api/personas

查看当前 Persona 池。支持按场景筛选。

```text
GET /api/personas
GET /api/personas?scenario=code_review
```

### POST /api/jobs

提交批量生成任务。

```json
{
  "scenario": "code_review",
  "total": 5,
  "min_score": 7,
  "payload": {
    "language": "python",
    "code_diff": "+ query = f\"SELECT * FROM users WHERE id = {user_id}\"",
    "review_focus": ["security", "testing"],
    "max_turns": 6
  }
}
```

### GET /api/jobs

查看最近批量任务。

### GET /api/jobs/{job_id}

查看单个任务进度、状态、失败原因和生成的 conversation id。

### POST /api/simulations/code-review

生成一条 Code Review 多 Agent 中文对话。

```json
{
  "language": "python",
  "code_diff": "+ query = f\"SELECT * FROM users WHERE id = {user_id}\"\n+ cursor.execute(query)",
  "review_focus": ["security", "performance"],
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
  "complaint_detail": "商品显示已发货，但物流三天没有更新。现在我要求退款。",
  "company_policy": "符合规则可退款；高额赔付需要升级主管审核。",
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

```text
GET /api/conversations?scenario=code_review&accepted=true&min_score=8&page=1&page_size=10
```

### GET /api/datasets/export.jsonl

按当前筛选条件导出 JSONL 训练数据。

```text
GET /api/datasets/export.jsonl?scenario=technical_interview&accepted=true&min_score=8&q=RAG
```

JSONL 包含：

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
- 查看 LangGraph 条件路由节点
- 查看每个 Agent 节点的执行轨迹和 route_reason
- 查看质量评分
- 数据集搜索、筛选、分页
- 按当前筛选条件导出 JSONL
- 查看 Persona 池、历史表现和最近记忆

## 下一步计划

- v1.4：Persona Generator 与场景模板管理
- v1.6：数据集版本管理
- v1.7：质量评估增强与多 Judge 投票
- v1.6：数据集版本管理
