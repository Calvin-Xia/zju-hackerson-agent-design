import React from 'react';
import { List, Tag, Typography } from 'antd';
import { FilePdfOutlined, FileMarkdownOutlined, FileTextOutlined, FileExcelOutlined, FileUnknownOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface FileItem {
  id: string;
  name: string;
  size: number;
  status: 'uploading' | 'done' | 'error';
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

const FileList: React.FC = () => {
  const fileList: FileItem[] = [];

  return (
    <List
      dataSource={fileList}
      locale={{ emptyText: '暂无上传文件' }}
      renderItem={(item) => (
        <List.Item
          actions={[
            <Tag color={item.status === 'done' ? 'green' : item.status === 'error' ? 'red' : 'blue'}>
              {item.status === 'done' ? '已完成' : item.status === 'error' ? '失败' : '解析中'}
            </Tag>,
          ]}
        >
          <List.Item.Meta
            avatar={getFileIcon(item.name)}
            title={<Text>{item.name}</Text>}
            description={<Text type="secondary">{formatFileSize(item.size)}</Text>}
          />
        </List.Item>
      )}
    />
  );
};

export default FileList;
