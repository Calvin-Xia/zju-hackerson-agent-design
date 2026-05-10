# Phase 5: RAG精准问答系统 Spec

## Why
RAG（Retrieval-Augmented Generation）精准问答是系统的核心功能之一，要求每一个回答都有据可查，必须引用原文来源。这不仅是普通聊天机器人，而是基于教材内容的精准问答系统。

## What Changes
- 实现完整的RAG Pipeline（文档分块、向量嵌入、向量存储与检索、生成回答）
- 支持带引用来源的回答
- 实现索引状态管理
- 提供问答界面和API接口
- 支持自建RAG Benchmark（建议）

## Impact
- Affected specs: Phase 2（依赖教材解析数据）、Phase 4（依赖整合后的知识库）
- Affected code:
  - 新增: `src/rag/`（RAG模块）
  - 新增: `src/embedding/`（向量嵌入模块）
  - 新增: `src/vectorstore/`（向量存储模块）
  - 修改: `src/api/`（添加RAG API）

## ADDED Requirements

### Requirement: 文档分块（Chunking）
系统 SHALL 将教材内容拆分为适当大小的块，为向量化做准备。

#### Scenario: 分块策略
- **WHEN** 对教材内容进行分块
- **THEN** 将每本教材的正文拆分为小块（chunk）
- **AND** 每块约500–800字
- **AND** 相邻块之间有50–100字的重叠（sliding window）
- **AND** 防止知识点被截断

#### Scenario: 元数据保留
- **WHEN** 创建文档块
- **THEN** 每个chunk必须保留元数据：
  - 教材名称
  - 章节标题
  - 起始页码
- **AND** 元数据完整准确

#### Scenario: 分块粒度说明
- **WHEN** 选择分块粒度
- **THEN** 在文档中说明选择这个分块粒度的理由
- **AND** 理由充分合理

### Requirement: 向量嵌入（Embedding）
系统 SHALL 将文档块转化为向量表示，支持语义检索。

#### Scenario: 嵌入模型选择
- **WHEN** 选择嵌入模型
- **THEN** 推荐使用sentence-transformers（本地运行，免费）或OpenAI Embedding API
- **AND** 如果使用中文教材，建议选择支持中文的模型（如paraphrase-multilingual-MiniLM-L12-v2或BGE-small-zh）
- **AND** 模型选择合理

#### Scenario: 向量生成
- **WHEN** 对文档块进行向量化
- **THEN** 将每个chunk转化为向量表示
- **AND** 向量维度合理
- **AND** 生成速度满足要求

#### Scenario: 批量处理
- **WHEN** 处理大量文档块
- **THEN** 支持批量向量化
- **AND** 实现进度追踪
- **AND** 优化处理性能

### Requirement: 向量存储与检索
系统 SHALL 将向量存入向量数据库，支持高效的语义检索。

#### Scenario: 向量数据库选择
- **WHEN** 选择向量数据库
- **THEN** 推荐使用FAISS或ChromaDB（轻量级）
- **AND** 支持高效的向量检索
- **AND** 支持持久化存储

#### Scenario: 向量索引
- **WHEN** 建立向量索引
- **THEN** 将所有chunk的向量存入向量数据库
- **AND** 建立高效的索引结构
- **AND** 支持增量更新

#### Scenario: 语义检索
- **WHEN** 用户提问时
- **THEN** 将问题转为向量
- **AND** 检索top-5最相关的chunk
- **AND** 返回检索结果和相似度分数

#### Scenario: 混合检索（加分）
- **WHEN** 实现高级检索
- **THEN** 可选实现混合检索：向量检索 + BM25关键词检索
- **AND** 取并集后重排序
- **AND** 提高检索准确率

### Requirement: 生成回答
系统 SHALL 基于检索到的内容生成带引用来源的回答。

#### Scenario: Prompt设计
- **WHEN** 生成回答
- **THEN** 将检索到的top-5 chunk作为上下文注入LLM prompt
- **AND** Prompt必须包含以下约束：
  - 只基于提供的上下文回答，不使用自身知识
  - 每个回答附带来源引用，格式为[教材名称, 第X章, 第X页]
  - 如果上下文中找不到答案，回复"当前知识库中未找到相关信息"

#### Scenario: 回答数据结构
- **WHEN** 生成回答
- **THEN** 返回标准化数据结构：
```json
{
  "answer": "炎症是机体对致炎因子的损伤所发生的防御性反应...",
  "citations": [
    {
      "textbook": "病理学",
      "chapter": "第四章 炎症",
      "page": 78,
      "relevance_score": 0.92
    }
  ],
  "source_chunks": [
    "炎症(inflammation)是具有血管系统的活体组织对各种损伤因子的刺激...",
    "机体免疫系统在炎症反应中发挥重要作用..."
  ]
}
```

#### Scenario: 引用准确性
- **WHEN** 生成回答
- **THEN** 引用的教材和章节与问题内容相关
- **AND** 引用来源准确可靠
- **AND** 相关度分数合理

### Requirement: 索引状态管理
系统 SHALL 管理向量索引的状态，支持索引的建立、查询和更新。

#### Scenario: 索引建立
- **WHEN** 用户请求建立索引
- **THEN** 调用 `POST /api/rag/index` 接口
- **AND** 对已上传教材建立向量索引
- **AND** 返回索引任务ID

#### Scenario: 索引状态查询
- **WHEN** 用户查询索引状态
- **THEN** 调用 `GET /api/rag/status` 接口
- **AND** 返回索引状态（已索引X本教材，共X个知识块）
- **AND** 返回索引进度

#### Scenario: 索引更新
- **WHEN** 教材内容更新
- **THEN** 支持增量更新索引
- **AND** 避免全量重建
- **AND** 保持索引一致性

### Requirement: 问答界面
系统 SHALL 提供用户友好的问答界面。

#### Scenario: 问答输入
- **WHEN** 用户输入问题
- **THEN** 提供问答输入框
- **AND** 支持回车提交
- **AND** 支持多行输入

#### Scenario: 回答展示
- **WHEN** 系统返回回答
- **THEN** 回答区域展示：回答正文 + 引用来源列表
- **AND** 每条引用显示：教材名、章节、页码、相关度分数
- **AND** 点击引用可展开查看原文chunk内容

#### Scenario: 索引状态显示
- **WHEN** 用户查看界面
- **THEN** 界面上方显示索引状态（已索引X本教材，共X个知识块）
- **AND** 状态实时更新

### Requirement: RAG Benchmark（建议）
系统 SHALL 支持自建RAG Benchmark，用数据驱动的方式优化RAG pipeline。

#### Scenario: 测试问题集
- **WHEN** 构建RAG Benchmark
- **THEN** 自己利用AI编写20–50个测试问题
- **AND** 覆盖不同难度和类型（事实性/比较性/推理性/跨教材）
- **AND** 为每个问题标注预期答案和预期引用来源（ground truth）

#### Scenario: 自动化评测
- **WHEN** 运行RAG Benchmark
- **THEN** 跑自动化评测
- **AND** 统计回答准确率、引用准确率、平均响应时间、Token消耗
- **AND** 对比不同分块策略、不同embedding模型、有无rerank的效果差异

#### Scenario: 评测结果分析
- **WHEN** 完成评测
- **THEN** 将评测结果整理成表格或图表
- **AND** 写入docs/Agent架构说明.md或P2技术报告中
- **AND** 用数据驱动优化RAG pipeline

## MODIFIED Requirements

### Requirement: 教材解析结果增强
现有的教材解析结果需要支持RAG分块的输入。

#### Scenario: 内容预处理
- **WHEN** 准备进行RAG分块
- **THEN** 对教材内容进行预处理
- **AND** 清理无关字符
- **AND** 保留结构信息
- **AND** 格式化为分块输入格式

## REMOVED Requirements
无

## Technical Constraints
- 推荐使用FAISS或ChromaDB作为向量数据库
- 推荐使用sentence-transformers或OpenAI Embedding API
- 分块大小约500–800字，重叠50–100字
- 检索top-5最相关的chunk
- 回答必须引用原文来源

## Dependencies
- Phase 2: 教材解析与处理（教材内容数据）
- Phase 4: 跨教材知识整合（整合后的知识库）

## Success Criteria
1. RAG Pipeline完整实现
2. 回答准确，引用来源正确
3. 索引状态管理正常
4. 问答界面用户友好
5. 检索响应时间<3秒
6. 回答质量满足要求
