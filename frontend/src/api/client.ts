const API_BASE = 'http://localhost:8001/api';

export interface FileItem {
  file_id: string;
  filename: string;
  size: number;
  status: string;
  parse_status: string;
  chapter_count: number;
  error_message: string | null;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  error_message?: string;
}

export interface RAGStatus {
  total_chunks: number;
  indexed_textbooks: number;
  is_ready: boolean;
}

export interface QueryResponse {
  answer: string;
  citations: Array<{ source: string; text: string }>;
  source_chunks: string[];
}

export interface ChatResponse {
  conversation_id: string;
  response: string;
  suggestions: string[];
}

export interface HistoryResponse {
  conversation_id: string;
  messages: Array<{ role: string; content: string; timestamp: string }>;
}

export interface Statistics {
  total_files: number;
  total_nodes: number;
  total_relations: number;
  compression_ratio: number;
}

export async function fetchFiles(): Promise<FileItem[]> {
  const res = await fetch(`${API_BASE}/files/`);
  if (!res.ok) throw new Error('获取文件列表失败');
  return res.json();
}

export async function startIntegration(fileIds: string[]): Promise<{ task_id: string }> {
  const res = await fetch(`${API_BASE}/integration/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ textbook_ids: fileIds }),
  });
  if (!res.ok) throw new Error('启动整合失败');
  return res.json();
}

export async function getIntegrationStatus(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`${API_BASE}/integration/status/${taskId}`);
  if (!res.ok) throw new Error('获取整合状态失败');
  return res.json();
}

export async function getIntegrationStatistics(taskId: string): Promise<Statistics> {
  const res = await fetch(`${API_BASE}/integration/statistics/${taskId}`);
  if (!res.ok) throw new Error('获取统计数据失败');
  return res.json();
}

export async function getRAGStatus(): Promise<RAGStatus> {
  const res = await fetch(`${API_BASE}/rag/status`);
  if (!res.ok) throw new Error('获取RAG状态失败');
  return res.json();
}

export async function buildRAGIndex(fileIds: string[]): Promise<{ task_id: string }> {
  const res = await fetch(`${API_BASE}/rag/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_ids: fileIds }),
  });
  if (!res.ok) throw new Error('建立索引失败');
  return res.json();
}

export async function queryRAG(question: string): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/rag/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error('查询失败');
  return res.json();
}

export async function sendChatMessage(message: string, conversationId?: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/dialogue/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!res.ok) throw new Error('发送消息失败');
  return res.json();
}

export async function getChatHistory(conversationId: string): Promise<HistoryResponse> {
  const res = await fetch(`${API_BASE}/dialogue/history/${conversationId}`);
  if (!res.ok) throw new Error('获取历史失败');
  return res.json();
}
