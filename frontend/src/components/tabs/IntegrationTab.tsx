import React, { useState, useEffect } from 'react';
import { Button, Select, Typography, message, Progress, Spin } from 'antd';
import { MergeOutlined } from '@ant-design/icons';
import { fetchFiles, startIntegration, getIntegrationStatus, FileItem } from '../../api/client';

const { Text } = Typography;

const IntegrationTab: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [taskStatus, setTaskStatus] = useState<string>('');

  useEffect(() => {
    loadFiles();
  }, []);

  useEffect(() => {
    if (!taskId) return;
    const interval = setInterval(async () => {
      try {
        const status = await getIntegrationStatus(taskId);
        setProgress(status.progress * 100);
        setTaskStatus(status.status);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(interval);
          setLoading(false);
          if (status.status === 'completed') {
            message.success('整合完成！');
          } else {
            message.error(`整合失败: ${status.error_message}`);
          }
        }
      } catch (err) {
        clearInterval(interval);
        setLoading(false);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [taskId]);

  const loadFiles = async () => {
    try {
      const data = await fetchFiles();
      setFiles(data.filter(f => f.parse_status === 'completed'));
    } catch (err) {
      message.error('获取文件列表失败');
    }
  };

  const handleStart = async () => {
    if (selectedFiles.length < 2) {
      message.warning('请至少选择2个文件进行整合');
      return;
    }
    setLoading(true);
    try {
      const result = await startIntegration(selectedFiles);
      setTaskId(result.task_id);
      setTaskStatus('running');
      localStorage.setItem('last_integration_task', result.task_id);
    } catch (err) {
      setLoading(false);
      message.error('启动整合失败');
    }
  };

  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>
        选择要整合的教材（至少2个）
      </Text>
      <Select
        mode="multiple"
        placeholder="选择教材文件"
        style={{ width: '100%', marginBottom: 16 }}
        value={selectedFiles}
        onChange={setSelectedFiles}
        options={files.map(f => ({ label: f.filename, value: f.file_id }))}
      />
      {taskId && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">状态: {taskStatus}</Text>
          <Progress percent={Math.round(progress)} status={taskStatus === 'failed' ? 'exception' : 'active'} />
        </div>
      )}
      <Button
        type="primary"
        icon={<MergeOutlined />}
        block
        loading={loading}
        disabled={selectedFiles.length < 2}
        onClick={handleStart}
      >
        开始整合
      </Button>
    </div>
  );
};

export default IntegrationTab;
