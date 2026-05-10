# Phase 3: 知识图谱构建与可视化 Spec

## Why
知识图谱是整个系统的核心展示和交互载体，需要将教材内容转化为结构化的知识点网络，并通过可视化方式直观展示。高质量的知识图谱构建和交互直接影响后续的跨教材整合、RAG问答和多轮对话功能。

## What Changes
- 实现LLM驱动的知识点提取
- 构建知识图谱数据结构（节点和关系）
- 实现单本教材知识图谱可视化
- 实现知识图谱交互功能（点击、缩放、拖拽等）
- 支持频次可视化和教材来源区分

## Impact
- Affected specs: Phase 2（依赖教材解析数据）
- Affected code:
  - 新增: `src/kg/`（知识图谱模块）
  - 新增: `src/llm/`（LLM调用模块）
  - 新增: `src/visualization/`（可视化模块）
  - 修改: `src/api/`（添加知识图谱API）

## ADDED Requirements

### Requirement: 知识点提取
系统 SHALL 使用LLM从教材章节中提取核心知识点，包括概念、定理、方法、现象等。

#### Scenario: LLM知识点提取
- **WHEN** 对章节内容调用LLM
- **THEN** 提取该章节中的核心知识点
- **AND** 每个知识点包含结构化信息：
```json
{
  "id": "node_001",
  "name": "动作电位",
  "definition": "细胞受到刺激后，膜电位发生的一次快速而可逆的倒转...",
  "category": "核心概念",
  "chapter": "第二章 细胞的基本功能",
  "page": 35
}
```
- **AND** 知识点粒度适中（不过粗不过细）

#### Scenario: 关系识别
- **WHEN** 提取知识点时
- **THEN** 识别知识点之间的关系
- **AND** 关系类型至少包含以下四种中的三种：
  - 前置依赖（prerequisite）：学习B之前必须先掌握A
  - 并列关系（parallel）：同一层级的平行概念
  - 包含关系（contains）：上位概念与下位概念
  - 应用关系（applies_to）：某知识点是另一个的应用场景
- **AND** 关系输出结构：
```json
{
  "source": "node_001",
  "target": "node_002",
  "relation_type": "prerequisite",
  "description": "理解动作电位需要先掌握静息电位的概念"
}
```

#### Scenario: Prompt工程
- **WHEN** 调用LLM提取知识点
- **THEN** 使用优化的Prompt模板
- **AND** 明确要求输出JSON格式
- **AND** 给出few-shot示例
- **AND** 限制每次调用只处理一个章节（避免上下文过长）

### Requirement: 知识图谱数据结构
系统 SHALL 构建标准化的知识图谱数据结构，支持节点和关系的存储、查询和更新。

#### Scenario: 节点数据结构
- **WHEN** 存储知识点
- **THEN** 使用标准化节点结构：
```json
{
  "id": "node_001",
  "name": "动作电位",
  "definition": "细胞受到刺激后，膜电位发生的一次快速而可逆的倒转...",
  "category": "核心概念",
  "chapter": "第二章 细胞的基本功能",
  "page": 35,
  "textbook_id": "book_01",
  "frequency": 1
}
```

#### Scenario: 关系数据结构
- **WHEN** 存储知识点关系
- **THEN** 使用标准化关系结构：
```json
{
  "source": "node_001",
  "target": "node_002",
  "relation_type": "prerequisite",
  "description": "理解动作电位需要先掌握静息电位的概念",
  "confidence": 0.95
}
```

#### Scenario: 图谱存储
- **WHEN** 构建知识图谱
- **THEN** 支持持久化存储
- **AND** 支持高效的节点和关系查询
- **AND** 支持图谱的增量更新

### Requirement: 知识图谱可视化
系统 SHALL 将知识图谱以可视化形式展示，支持用户交互操作。

#### Scenario: 可视化渲染
- **WHEN** 选择一本教材
- **THEN** 生成该教材的知识图谱可视化
- **AND** 使用专业可视化库（D3.js/ECharts/Cytoscape.js/AntV G6）
- **AND** 节点和关系清晰展示
- **AND** 布局合理，不重叠

#### Scenario: 频次可视化
- **WHEN** 加载多本教材后
- **THEN** 节点大小或颜色深度反映该知识点在多本教材中出现的频次
- **AND** 出现次数越多 → 节点越大或颜色越深
- **AND** 视觉差异明显

#### Scenario: 教材来源区分
- **WHEN** 显示多本教材的知识图谱
- **THEN** 不同教材来源的知识点用不同颜色标识
- **AND** 颜色区分清晰
- **AND** 有图例说明

### Requirement: 知识图谱交互
系统 SHALL 支持丰富的用户交互操作，提升用户体验。

#### Scenario: 节点点击
- **WHEN** 用户点击任意节点
- **THEN** 弹出或侧边展示该知识点的详细信息
- **AND** 显示：名称、定义、所在章节、原文出处
- **AND** 信息展示清晰完整

#### Scenario: 基本交互
- **WHEN** 用户操作知识图谱
- **THEN** 支持鼠标滚轮缩放
- **AND** 支持拖拽移动画布
- **AND** 支持拖拽移动单个节点
- **AND** 交互流畅

#### Scenario: 搜索功能（建议）
- **WHEN** 用户输入关键词搜索
- **THEN** 高亮匹配的节点
- **AND** 支持模糊搜索
- **AND** 搜索结果统计

### Requirement: LLM调用优化
系统 SHALL 优化LLM调用策略，提高知识点提取的准确性和效率。

#### Scenario: Prompt模板设计
- **WHEN** 调用LLM提取知识点
- **THEN** 使用精心设计的Prompt模板
- **AND** 包含明确的输出格式要求
- **AND** 包含few-shot示例
- **AND** 限制输出范围（单个章节）

#### Scenario: 错误处理
- **WHEN** LLM调用失败
- **THEN** 记录错误日志
- **AND** 实现重试机制
- **AND** 返回友好的错误提示

#### Scenario: 成本控制
- **WHEN** 调用LLM API
- **THEN** 控制Token使用量
- **AND** 记录API调用成本
- **AND** 优化Prompt长度

## MODIFIED Requirements

### Requirement: 文件解析结果增强
现有的文件解析结果需要支持知识点提取的输入。

#### Scenario: 章节内容预处理
- **WHEN** 准备调用LLM提取知识点
- **THEN** 对章节内容进行预处理
- **AND** 清理无关字符
- **AND** 分割过长的章节
- **AND** 保留章节元数据

## REMOVED Requirements
无

## Technical Constraints
- 推荐使用D3.js、ECharts、Cytoscape.js或AntV G6进行可视化
- LLM调用需要考虑API成本和响应时间
- 知识图谱数据需要持久化存储
- 可视化需要支持主流浏览器
- 交互操作需要流畅响应

## Dependencies
- Phase 2: 教材解析与处理（章节内容数据）

## Success Criteria
1. 能准确提取教材中的知识点（准确率≥85%）
2. 能识别知识点之间的关系（至少3种类型）
3. 知识图谱可视化正常渲染
4. 交互操作流畅（点击、缩放、拖拽）
5. 频次可视化和来源区分清晰
6. LLM调用成本可控
