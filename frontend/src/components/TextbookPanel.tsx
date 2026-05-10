import React from 'react';
import { Card, Typography } from 'antd';
import FileUpload from './FileUpload';
import FileList from './FileList';

const { Title } = Typography;

const TextbookPanel: React.FC = () => {
  return (
    <div style={{ padding: '16px' }}>
      <Title level={4} style={{ marginBottom: 16 }}>
        教材管理
      </Title>
      <Card
        title="上传教材"
        style={{ marginBottom: 16 }}
        styles={{ body: { padding: '12px' } }}
      >
        <FileUpload />
      </Card>
      <Card
        title="已上传文件"
        styles={{ body: { padding: '12px' } }}
      >
        <FileList />
      </Card>
    </div>
  );
};

export default TextbookPanel;
