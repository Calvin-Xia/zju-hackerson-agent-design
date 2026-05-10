import React from 'react';
import { Button, Input, Space, Typography } from 'antd';
import { SendOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { TextArea } = Input;

const DialogueTab: React.FC = () => {
  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>
        通过对话优化整合方案
      </Text>
      <div
        style={{
          height: 200,
          border: '1px solid #d9d9d9',
          borderRadius: 6,
          marginBottom: 16,
          padding: 12,
          overflow: 'auto',
        }}
      >
        <Text type="secondary">对话历史将在此处显示</Text>
      </div>
      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          placeholder="输入您的指令..."
          rows={2}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          style={{ height: 'auto' }}
          disabled
        />
      </Space.Compact>
    </div>
  );
};

export default DialogueTab;
