import React from 'react';
import { Button, Select, Typography } from 'antd';
import { MergeOutlined } from '@ant-design/icons';

const { Text } = Typography;

const IntegrationTab: React.FC = () => {
  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>
        选择要整合的教材
      </Text>
      <Select
        mode="multiple"
        placeholder="选择教材文件"
        style={{ width: '100%', marginBottom: 16 }}
        options={[]}
      />
      <Button
        type="primary"
        icon={<MergeOutlined />}
        block
        disabled
      >
        开始整合
      </Button>
    </div>
  );
};

export default IntegrationTab;
