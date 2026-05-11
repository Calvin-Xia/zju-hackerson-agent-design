import React, { useState, useEffect } from 'react';
import { List, Tag, Typography, Spin } from 'antd';
import { FilePdfOutlined, FileMarkdownOutlined, FileTextOutlined, FileExcelOutlined, FileUnknownOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Text } = Typography;

interface FileItem {
  file_id: string;
  filename: string;
  size: number;
  status: string;
  parse_status: string;
  chapter_count: number;
  error_message?: string;
}

const getFileIcon = (fileName: string) => {
  const extension = fileName.split('.').pop()?.toLowerCase();
  switch (extension) {
    case 'pdf':
      return <FilePdfOutlined style={{ color: '#ff4d4f' }} />;
    case 'md':
      return <FileMarkdownOutlined style={{ color: '#1677ff' }} />;
    case 'txt':
      return <FileTextOutlined style={{ color: '#52c41a' }} />;
    case 'docx':
      return <FileTextOutlined style={{ color: '#722ed1' }} />;
    case 'xlsx':
    case 'xls':
      return <FileExcelOutlined style={{ color: '#52c41a' }} />;
    default:
      return <FileUnknownOutlined />;
  }
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getParseStatusTag = (status: string, chapterCount: number, errorMessage?: string) => {
  switch (status) {
    case 'completed':
      return <Tag color="green">已完成 ({chapterCount}章)</Tag>;
    case 'parsing':
      return <Tag color="blue"><Spin size="small" /> 解析中</Tag>;
    case 'failed':
      return <Tag color="red" title={errorMessage}>解析失败</Tag>;
    case 'pending':
    default:
      return <Tag color="orange">等待解析</Tag>;
  }
};

const FileList: React.FC = () => {
  const [fileList, setFileList] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);

  const hasActiveParsing = fileList.some(
    f => f.parse_status === 'parsing' || f.parse_status === 'pending'
  );

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/files/');
      setFileList(response.data);
    } catch (error) {
      console.error('Failed to fetch files:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  useEffect(() => {
    if (!hasActiveParsing) return;

    const interval = setInterval(fetchFiles, 5000);
    return () => clearInterval(interval);
  }, [hasActiveParsing]);

  return (
    <List
      loading={loading}
      dataSource={fileList}
      locale={{ emptyText: '暂无上传文件' }}
      renderItem={(item) => (
        <List.Item
          actions={[
            getParseStatusTag(item.parse_status, item.chapter_count, item.error_message),
          ]}
        >
          <List.Item.Meta
            avatar={getFileIcon(item.filename)}
            title={<Text>{item.filename}</Text>}
            description={
              <Text type="secondary">
                {formatFileSize(item.size)}
                {item.parse_status === 'completed' && ` · ${item.chapter_count} 个章节`}
              </Text>
            }
          />
        </List.Item>
      )}
    />
  );
};

export default FileList;
