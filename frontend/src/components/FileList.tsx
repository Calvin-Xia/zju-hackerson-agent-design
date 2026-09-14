import React, { useState, useEffect, useCallback } from 'react';
import { List, Tag, Typography, Spin, Popconfirm, Button, Space, Tooltip } from 'antd';
import {
  FilePdfOutlined,
  FileMarkdownOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  FileUnknownOutlined,
  ReloadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { fetchFiles, deleteFile, parseTextbook, FileItem } from '../api/client';

const { Text } = Typography;

export const FILES_CHANGED_EVENT = 'textbooks-changed';

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
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
};

const getParseStatusTag = (item: FileItem) => {
  switch (item.parse_status) {
    case 'completed':
      return (
        <Tooltip title={`${item.chapter_count} 个章节 · ${item.total_chars.toLocaleString()} 字`}>
          <Tag color="green">已解析</Tag>
        </Tooltip>
      );
    case 'parsing':
      return (
        <Tag color="blue">
          <Spin size="small" /> 解析中
        </Tag>
      );
    case 'failed':
      return (
        <Tooltip title={item.error_message ?? '解析失败'}>
          <Tag color="red">解析失败</Tag>
        </Tooltip>
      );
    default:
      return <Tag color="orange">等待解析</Tag>;
  }
};

const FileList: React.FC = () => {
  const [fileList, setFileList] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);

  const hasActiveParsing = fileList.some(
    (f) => f.parse_status === 'parsing' || f.parse_status === 'pending',
  );

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      setFileList(await fetchFiles());
    } catch (error) {
      console.error('获取文件列表失败', error);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
    const onChanged = () => void load(true);
    window.addEventListener(FILES_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(FILES_CHANGED_EVENT, onChanged);
  }, [load]);

  useEffect(() => {
    if (!hasActiveParsing) return;
    const interval = setInterval(() => void load(), 3000);
    return () => clearInterval(interval);
  }, [hasActiveParsing, load]);

  const handleReparse = async (fileId: string) => {
    try {
      await parseTextbook(fileId);
      setFileList((prev) =>
        prev.map((f) => (f.file_id === fileId ? { ...f, parse_status: 'parsing', error_message: null } : f)),
      );
    } catch (err) {
      console.error(err);
      void load(true);
    }
  };

  const handleDelete = async (fileId: string) => {
    try {
      await deleteFile(fileId);
      setFileList((prev) => prev.filter((f) => f.file_id !== fileId));
      window.dispatchEvent(new Event(FILES_CHANGED_EVENT));
    } catch (err) {
      console.error(err);
      void load(true);
    }
  };

  return (
    <List
      loading={loading}
      dataSource={fileList}
      locale={{ emptyText: '暂无上传文件' }}
      renderItem={(item) => (
        // 侧边栏只有 22% 宽，不用 antd List.Item 的 actions 布局
        // （状态标签 + 两个按钮会把文件名挤到「一行一个字」）
        <List.Item style={{ padding: '10px 0', display: 'block' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <span style={{ fontSize: 18, lineHeight: '22px' }}>{getFileIcon(item.filename)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Text ellipsis={{ tooltip: item.filename }} style={{ display: 'block' }}>
                {item.filename}
              </Text>
              <Space size={4} wrap style={{ marginTop: 2 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {formatFileSize(item.size)}
                  {item.parse_status === 'completed' && ` · ${item.chapter_count} 章`}
                </Text>
                {getParseStatusTag(item)}
                {item.has_graph && <Tag color="blue">图谱</Tag>}
              </Space>
            </div>
            <Space size={0} style={{ flexShrink: 0 }}>
              <Tooltip title="重新解析" key="reparse">
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  disabled={item.parse_status === 'parsing'}
                  onClick={() => handleReparse(item.file_id)}
                />
              </Tooltip>
              <Popconfirm
                key="delete"
                title="删除该教材及其知识图谱？"
                onConfirm={() => handleDelete(item.file_id)}
                okText="删除"
                cancelText="取消"
              >
                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          </div>
        </List.Item>
      )}
    />
  );
};

export default FileList;
