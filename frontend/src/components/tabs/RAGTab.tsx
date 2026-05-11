import React from 'react';
import { Button, Input, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { TextArea } = Input;

const RAGTab: React.FC = () => {
  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>
        基于教材内容提问
      </Text>
      <TextArea
        placeholder="输入您的问题..."
        rows={4}
        style={{ marginBottom: 16 }}
      />
      <Button
        type="primary"
        icon={<SearchOutlined />}
        block
        disabled
      >
        提问
      </Button>
    </div>
  );
};

export default RAGTab;
