# Phase 2: 教材解析与处理 Tasks

## Task 1: 数据模型设计
**Priority**: P0 (必须实现)
**Estimated Time**: 30分钟

### SubTask 1.1: 定义教材数据模型
- [ ] 创建Textbook数据类
- [ ] 定义字段：textbook_id, filename, title, total_pages, total_chars, chapters
- [ ] 实现数据验证逻辑
- [ ] 创建序列化/反序列化方法

### SubTask 1.2: 定义章节数据模型
- [ ] 创建Chapter数据类
- [ ] 定义字段：chapter_id, title, page_start, page_end, content, char_count
- [ ] 实现数据验证逻辑
- [ ] 创建序列化/反序列化方法

### SubTask 1.3: 定义解析状态模型
- [ ] 创建ParseStatus枚举（解析中/已完成/失败）
- [ ] 创建FileInfo数据类
- [ ] 定义字段：file_id, filename, format, size, status, error_message
- [ ] 实现状态更新逻辑

**Acceptance Criteria**:
- 数据模型定义完整
- 数据验证逻辑正确
- 序列化/反序列化正常工作
- 符合统一输出格式要求

## Task 2: PDF解析器实现
**Priority**: P0 (必须实现)
**Estimated Time**: 90分钟

### SubTask 2.1: 选择并集成PDF解析库
- [ ] 选择PDF解析库（PyMuPDF或pdfplumber）
- [ ] 安装依赖
- [ ] 创建基础解析器类

### SubTask 2.2: 实现章节标题识别
- [ ] 通过字体大小识别标题
- [ ] 通过加粗格式识别标题
- [ ] 通过正则匹配"第X章"、"Chapter X"等模式
- [ ] 实现标题层级判断
- [ ] 测试识别准确率

### SubTask 2.3: 实现内容提取
- [ ] 提取章节正文内容
- [ ] 过滤页眉页脚
- [ ] 跳过图表区域
- [ ] 记录起始页码和结束页码
- [ ] 统计字符数

### SubTask 2.4: 实现逐页解析
- [ ] 实现逐页读取逻辑
- [ ] 避免一次性加载整本书
- [ ] 内存使用优化
- [ ] 解析进度追踪

### SubTask 2.5: 错误处理
- [ ] 处理PDF格式错误
- [ ] 处理页面解析异常
- [ ] 记录错误日志
- [ ] 跳过有问题的页面

**Acceptance Criteria**:
- 能正确解析PDF文件
- 章节识别准确率≥90%
- 内存使用稳定
- 错误处理完善

## Task 3: Markdown解析器实现
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 3.1: 实现标题层级解析
- [ ] 解析# ## ###等标题标记
- [ ] 识别标题层级关系
- [ ] 创建章节结构

### SubTask 3.2: 实现内容提取
- [ ] 提取标题下的正文内容
- [ ] 保留Markdown格式（如需要）
- [ ] 统计字符数

### SubTask 3.3: 实现章节分割
- [ ] 按标题层级分割章节
- [ ] 创建章节ID
- [ ] 记录章节顺序

### SubTask 3.4: 错误处理
- [ ] 处理Markdown格式错误
- [ ] 处理编码问题
- [ ] 记录错误日志

**Acceptance Criteria**:
- 能正确解析Markdown文件
- 章节结构识别准确
- 内容提取完整
- 错误处理完善

## Task 4: TXT解析器实现
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 4.1: 实现章节标题识别
- [ ] 通过正则匹配"第X章"、"Chapter X"等模式
- [ ] 支持多种标题格式
- [ ] 识别准确率优化

### SubTask 4.2: 实现内容分割
- [ ] 按标题分割内容
- [ ] 创建章节结构
- [ ] 统计字符数

### SubTask 4.3: 实现编码处理
- [ ] 自动检测文件编码
- [ ] 支持UTF-8、GBK等常见编码
- [ ] 处理编码错误

### SubTask 4.4: 错误处理
- [ ] 处理文件读取错误
- [ ] 处理编码错误
- [ ] 记录错误日志

**Acceptance Criteria**:
- 能正确解析TXT文件
- 章节识别基本准确
- 编码处理正常
- 错误处理完善

## Task 5: Word .docx解析器实现（建议）
**Priority**: P1 (建议实现)
**Estimated Time**: 60分钟

### SubTask 5.1: 集成Word解析库
- [ ] 安装python-docx依赖
- [ ] 创建Word解析器类

### SubTask 5.2: 实现文档结构解析
- [ ] 解析标题样式
- [ ] 识别章节结构
- [ ] 提取正文内容

### SubTask 5.3: 实现内容提取
- [ ] 提取纯文本内容
- [ ] 保留结构信息
- [ ] 统计字符数

### SubTask 5.4: 错误处理
- [ ] 处理Word格式错误
- [ ] 处理文件损坏情况
- [ ] 记录错误日志

**Acceptance Criteria**:
- 能正确解析Word .docx文件
- 章节结构识别准确
- 内容提取完整
- 错误处理完善

## Task 6: 统一解析器接口
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 6.1: 创建解析器工厂
- [ ] 根据文件格式选择解析器
- [ ] 支持格式：PDF、Markdown、TXT、DOCX（可选）
- [ ] 实现解析器注册机制

### SubTask 6.2: 实现统一解析接口
- [ ] 创建parse_file函数
- [ ] 输入：文件路径
- [ ] 输出：Textbook数据对象
- [ ] 统一错误处理

### SubTask 6.3: 实现异步解析
- [ ] 使用异步编程（asyncio）
- [ ] 避免阻塞主线程
- [ ] 实现解析进度回调

### SubTask 6.4: 实现解析状态管理
- [ ] 更新文件解析状态
- [ ] 记录解析开始/结束时间
- [ ] 记录解析错误信息

**Acceptance Criteria**:
- 统一接口正常工作
- 异步解析不阻塞主线程
- 解析状态实时更新
- 错误处理统一

## Task 7: API集成
**Priority**: P0 (必须实现)
**Estimated Time**: 30分钟

### SubTask 7.1: 修改文件上传API
- [ ] 上传完成后自动触发解析
- [ ] 返回解析任务ID
- [ ] 异步处理解析任务

### SubTask 7.2: 创建解析状态API
- [ ] `GET /api/parse/status/{file_id}` 接口
- [ ] 返回解析状态和进度
- [ ] 返回解析结果（如完成）

### SubTask 7.3: 修改文件列表API
- [ ] 返回解析状态信息
- [ ] 返回章节统计信息
- [ ] 返回错误信息（如失败）

**Acceptance Criteria**:
- 上传后自动解析正常
- 解析状态API正常工作
- 文件列表显示解析状态
- 前端能实时更新状态

## Task 8: 测试与优化
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 8.1: 功能测试
- [ ] 测试PDF解析功能
- [ ] 测试Markdown解析功能
- [ ] 测试TXT解析功能
- [ ] 测试Word解析功能（如实现）

### SubTask 8.2: 性能测试
- [ ] 测试大文件解析性能
- [ ] 测试内存使用情况
- [ ] 测试并发解析能力

### SubTask 8.3: 错误处理测试
- [ ] 测试格式错误处理
- [ ] 测试文件损坏处理
- [ ] 测试编码错误处理

### SubTask 8.4: 优化改进
- [ ] 优化解析性能
- [ ] 优化内存使用
- [ ] 优化错误提示

**Acceptance Criteria**:
- 所有格式解析正常
- 性能满足要求
- 错误处理完善
- 用户体验良好

# Task Dependencies

- [Task 1] 必须在 [Task 2, 3, 4, 5, 6] 之前完成，数据模型是所有解析器的基础
- [Task 2, 3, 4, 5] 可以并行进行，各格式解析器独立开发
- [Task 6] 依赖 [Task 2, 3, 4, 5]，需要各解析器完成后才能创建统一接口
- [Task 7] 依赖 [Task 6]，需要统一接口完成后才能集成到API
- [Task 8] 依赖 [Task 7]，需要API集成完成后才能进行完整测试

# Priority Order

1. **P0 - 高优先级**: Task 1, Task 2, Task 3, Task 4, Task 6, Task 7, Task 8（核心功能）
2. **P1 - 中优先级**: Task 5（Word解析器，建议实现）

# Estimated Total Time: 7小时

# Notes
- 优先实现PDF、Markdown、TXT三种必须格式
- Word解析器可以后续补充
- 重点保证解析准确性和稳定性
- 大文件处理需要特别注意内存优化
- 异步解析避免阻塞前端
