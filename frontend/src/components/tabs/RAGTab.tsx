import React, { useState, useEffect, useRef } from 'react';
import { Button, Input, Typography, message, List, Tag, Progress, Space, Alert } from 'antd';
import { SearchOutlined, BuildOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  fetchFiles,
  buildRAGIndex,
  getIndexTaskStatus,
  queryRAG,
  getRAGStatus,
  FileItem,
  QueryResponse,
  RAGStatus,
  Citation,
} from '../../api/client';

const { Text } = Typography;
const { TextArea } = Input;

const RAGTab: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [indexProgress, setIndexProgress] = useState(0);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [ragStatus, setRagStatus] = useState<RAGStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFiles = async () => {
    try {
      const data = await fetchFiles();
      setFiles(data.filter((f) => f.parse_status === 'completed'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取文件列表失败');
    }
  };

  const loadRAGStatus = async () => {
    try {
      setRagStatus(await getRAGStatus());
    } catch (err) {
      console.error('获取 RAG 状态失败', err);
    }
  };

  useEffect(() => {
    loadFiles();
    loadRAGStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleBuildIndex = async () => {
    if (files.length === 0) {
      message.warning('没有可索引的文件');
      return;
    }
    setIndexing(true);
    setIndexProgress(0);
    try {
      // 后端建索引是后台任务：这里轮询进度，完成后再刷新状态
      const task = await buildRAGIndex(files.map((f) => f.file_id));
      await new Promise<void>((resolve, reject) => {
        pollRef.current = setInterval(async () => {
          try {
            const status = await getIndexTaskStatus(task.task_id);
            setIndexProgress(Math.max(0, Math.min(100, status.progress)));
            if (status.status === 'completed') {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
              resolve();
            } else if (status.status === 'failed') {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
              reject(new Error(status.error_message ?? '建立索引失败'));
            }
          } catch (err) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            reject(err);
          }
        }, 800);
      });
      await loadRAGStatus();
      message.success('索引建立完成');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '建立索引失败');
    } finally {
      setIndexing(false);
    }
  };

  const handleQuery = async () => {
    if (!question.trim()) {
      message.warning('请输入问题');
      return;
    }
    setLoading(true);
    try {
      setResult(await queryRAG(question.trim()));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '查询失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>基于教材内容提问</Text>
        <Space size={4}>
          <Tag color={ragStatus?.is_ready ? 'green' : 'default'}>
            {ragStatus?.is_ready
              ? `${ragStatus.indexed_textbooks} 本教材 / ${ragStatus.total_chunks} 个片段`
              : '未索引'}
          </Tag>
          <Button size="small" icon={<ReloadOutlined />} onClick={loadRAGStatus} />
        </Space>
      </div>

      <Button
        icon={<BuildOutlined />}
        loading={indexing}
        onClick={handleBuildIndex}
        style={{ marginBottom: indexing ? 4 : 12 }}
        block
      >
        建立向量索引（{files.length} 本已解析教材）
      </Button>
      {indexing && <Progress percent={Math.round(indexProgress)} size="small" style={{ marginBottom: 12 }} />}

      <TextArea
        placeholder="输入您的问题..."
        rows={3}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault();
            void handleQuery();
          }
        }}
        style={{ marginBottom: 12 }}
      />
      <Button type="primary" icon={<SearchOutlined />} block loading={loading} onClick={handleQuery}>
        提问
      </Button>

      {result && (
        <div style={{ marginTop: 16 }}>
          <Space style={{ marginBottom: 8 }}>
            <Text strong>回答</Text>
            {result.retrieved_count > 0 && (
              <Text type="secondary">
                检索 {result.retrieved_count} 段 · 最高相似度 {result.top_score.toFixed(3)}
              </Text>
            )}
          </Space>
          <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
            {result.answer}
          </div>
          {result.citations.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">引用来源：</Text>
              <List
                size="small"
                dataSource={result.citations}
                renderItem={(item: Citation, index) => (
                  <List.Item>
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Space size={4} wrap>
                        <Tag color="blue">[{index + 1}]</Tag>
                        <Text>{item.textbook}</Text>
                        <Text type="secondary">{item.chapter}</Text>
                        <Tag>{item.relevance_score.toFixed(3)}</Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {item.content}
                      </Text>
                      {item.duplicate_sources.length > 0 && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          相同内容还出现于：{item.duplicate_sources.join('、')}
                        </Text>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            </div>
          )}
          {result.citations.length === 0 && (
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 8 }}
              message="未检索到足够相关的教材内容，回答未附带引用。"
            />
          )}
        </div>
      )}
    </div>
  );
};

export default RAGTab;
