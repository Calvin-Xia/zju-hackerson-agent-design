import React, { useState, useEffect } from 'react';
import { Button, Input, Typography, message, List, Tag, Spin } from 'antd';
import { SearchOutlined, BuildOutlined } from '@ant-design/icons';
import { fetchFiles, buildRAGIndex, queryRAG, getRAGStatus, FileItem, QueryResponse, RAGStatus } from '../../api/client';

const { Text } = Typography;
const { TextArea } = Input;

const RAGTab: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [ragStatus, setRagStatus] = useState<RAGStatus | null>(null);

  useEffect(() => {
    loadFiles();
    loadRAGStatus();
  }, []);

  const loadFiles = async () => {
    try {
      const data = await fetchFiles();
      setFiles(data.filter(f => f.parse_status === 'completed'));
    } catch (err) {
      message.error('获取文件列表失败');
    }
  };

  const loadRAGStatus = async () => {
    try {
      const status = await getRAGStatus();
      setRagStatus(status);
    } catch (err) {
      console.error('获取RAG状态失败');
    }
  };

  const handleBuildIndex = async () => {
    if (files.length === 0) {
      message.warning('没有可索引的文件');
      return;
    }
    setIndexing(true);
    try {
      await buildRAGIndex(files.map(f => f.file_id));
      message.success('索引建立完成');
      await loadRAGStatus();
    } catch (err) {
      message.error('建立索引失败');
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
      const res = await queryRAG(question);
      setResult(res);
    } catch (err) {
      message.error('查询失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>基于教材内容提问</Text>
        <Tag color={ragStatus?.is_ready ? 'green' : 'default'}>
          {ragStatus?.is_ready ? `已索引 ${ragStatus.total_chunks} 个片段` : '未索引'}
        </Tag>
      </div>
      <Button
        icon={<BuildOutlined />}
        loading={indexing}
        onClick={handleBuildIndex}
        style={{ marginBottom: 12 }}
        block
      >
        建立向量索引
      </Button>
      <TextArea
        placeholder="输入您的问题..."
        rows={3}
        value={question}
        onChange={e => setQuestion(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Button
        type="primary"
        icon={<SearchOutlined />}
        block
        loading={loading}
        onClick={handleQuery}
      >
        提问
      </Button>
      {result && (
        <div style={{ marginTop: 16 }}>
          <Text strong>回答：</Text>
          <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, marginTop: 8 }}>
            {result.answer}
          </div>
          {result.citations.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">引用来源：</Text>
              <List
                size="small"
                dataSource={result.citations}
                renderItem={(item, idx) => (
                  <List.Item>
                    <Tag color="blue">{item.source}</Tag>
                    <Text ellipsis style={{ flex: 1 }}>{item.text}</Text>
                  </List.Item>
                )}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RAGTab;
