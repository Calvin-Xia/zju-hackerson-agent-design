# Phase 2: 教材解析与处理 Spec

## Why
教材解析是整个系统的基础，需要将不同格式的教材文件统一转化为结构化数据，为后续的知识图谱构建、跨教材整合和RAG问答提供标准化的数据源。解析质量直接影响后续所有功能的准确性。

## What Changes
- 实现多格式教材文件解析（PDF、Markdown、TXT必须，Word .docx建议，Excel可选）
- 提取教材章节结构
- 统一数据输出格式
- 处理大文件解析（逐页解析，避免内存溢出）
- 过滤页眉页脚、图表区域等非内容元素

## Impact
- Affected specs: Phase 1（依赖文件上传功能）
- Affected code:
  - 新增: `src/parsers/`（解析器模块）
  - 新增: `src/models/`（数据模型）
  - 修改: `src/api/upload.py`（集成解析功能）
  - 修改: `src/api/files.py`（返回解析状态）

## ADDED Requirements

### Requirement: 多格式教材加载与解析
系统 SHALL 支持加载多种格式的教材文件，解析后统一转化为结构化数据。

#### Scenario: PDF文件解析
- **WHEN** 用户上传PDF教材
- **THEN** 系统自动识别章节标题（通过字体大小、加粗或正则匹配"第X章"）
- **AND** 过滤页眉页脚
- **AND** 跳过图表区域
- **AND** 逐页解析，避免一次性加载整本书到内存
- **AND** 输出结构化数据

#### Scenario: Markdown文件解析
- **WHEN** 用户上传Markdown教材
- **THEN** 系统解析标题层级（# ## ### 等）
- **AND** 识别章节结构
- **AND** 提取正文内容
- **AND** 输出结构化数据

#### Scenario: TXT文件解析
- **WHEN** 用户上传TXT教材
- **THEN** 系统尝试识别章节标题（通过正则匹配"第X章"、"Chapter X"等）
- **AND** 按章节分割内容
- **AND** 输出结构化数据

#### Scenario: Word .docx文件解析（建议）
- **WHEN** 用户上传Word .docx教材
- **THEN** 系统解析文档结构（标题样式）
- **AND** 提取正文内容
- **AND** 输出结构化数据

#### Scenario: Excel文件解析（可选）
- **WHEN** 用户上传Excel文件
- **THEN** 系统解析表格数据
- **AND** 提取结构化信息
- **AND** 输出统一格式

### Requirement: 章节结构识别
系统 SHALL 自动识别教材的章节结构，为每个章节创建独立的数据单元。

#### Scenario: 章节标题识别
- **WHEN** 解析教材文件
- **THEN** 系统自动识别章节标题
- **AND** 识别方式包括：
  - 字体大小差异（PDF）
  - 加粗格式（PDF、Word）
  - 标题样式（Markdown、Word）
  - 正则匹配"第X章"、"Chapter X"等模式
- **AND** 识别准确率不低于90%

#### Scenario: 章节内容提取
- **WHEN** 识别到章节标题
- **THEN** 提取该章节的完整内容
- **AND** 记录起始页码和结束页码
- **AND** 统计字符数
- **AND** 过滤非内容元素（页眉页脚、页码、图表等）

### Requirement: 统一数据输出格式
系统 SHALL 将所有解析结果统一为标准化的JSON格式，便于后续处理。

#### Scenario: 教材级数据结构
- **WHEN** 解析完成一本教材
- **THEN** 输出以下数据结构：
```json
{
  "textbook_id": "book_01",
  "filename": "生理学.pdf",
  "title": "生理学",
  "total_pages": 520,
  "total_chars": 385000,
  "chapters": [...]
}
```

#### Scenario: 章节级数据结构
- **WHEN** 解析完成一个章节
- **THEN** 输出以下数据结构：
```json
{
  "chapter_id": "ch_01",
  "title": "第一章 绪论",
  "page_start": 1,
  "page_end": 15,
  "content": "生理学是研究生物体正常生命活动规律的科学...",
  "char_count": 8500
}
```

### Requirement: 大文件处理优化
系统 SHALL 支持大文件解析，避免内存溢出和性能问题。

#### Scenario: 逐页解析
- **WHEN** 解析大型PDF文件（超过100页）
- **THEN** 系统逐页解析，不一次性加载整本书
- **AND** 内存使用保持稳定
- **AND** 解析进度可追踪

#### Scenario: 错误处理
- **WHEN** 解析过程中遇到错误
- **THEN** 记录错误日志
- **AND** 跳过有问题的页面或章节
- **AND** 继续解析剩余内容
- **AND** 在解析状态中报告错误

### Requirement: 解析状态管理
系统 SHALL 实时跟踪和显示文件解析状态。

#### Scenario: 解析状态更新
- **WHEN** 文件开始解析
- **THEN** 状态更新为"解析中"
- **AND** 显示解析进度（如可能）
- **AND** 解析完成后状态更新为"已完成"
- **AND** 解析失败时状态更新为"失败"

#### Scenario: 解析结果查询
- **WHEN** 用户查询文件列表
- **THEN** 显示每个文件的解析状态
- **AND** 已完成的文件显示章节统计
- **AND** 失败的文件显示错误原因

## MODIFIED Requirements

### Requirement: 文件上传功能增强
现有的文件上传功能需要集成解析状态显示。

#### Scenario: 上传后自动解析
- **WHEN** 文件上传完成
- **THEN** 自动触发解析流程
- **AND** 解析状态实时更新
- **AND** 解析完成后通知用户

## REMOVED Requirements
无

## Technical Constraints
- PDF解析推荐使用PyMuPDF或pdfplumber
- Word解析推荐使用python-docx
- 大文件处理需要内存优化
- 解析过程需要异步处理，不阻塞前端
- 解析结果需要持久化存储

## Dependencies
- Phase 1: 项目搭建与基础框架（文件上传功能）

## Success Criteria
1. 能正确解析PDF、Markdown、TXT三种必须格式
2. 能准确识别章节结构（准确率≥90%）
3. 输出统一的JSON数据格式
4. 大文件解析不导致内存溢出
5. 解析状态实时更新
6. 错误处理机制完善
