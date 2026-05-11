import React, { useState, useEffect, useRef } from 'react';
import { Button, Input, Space, Typography, message, List, Tag } from 'antd';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { sendChatMessage, getChatHistory } from '../../api/client';

const { Text } = Typography;
const { TextArea } = Input;

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

const DialogueTab: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) {
      message.warning('请输入消息');
      return;
    }
    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const res = await sendChatMessage(input, conversationId || undefined);
      if (!conversationId) {
        setConversationId(res.conversation_id);
      }
      const assistantMessage: Message = {
        role: 'assistant',
        content: res.response,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      message.error('发送失败');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setMessages([]);
    setConversationId(null);
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>通过对话优化整合方案</Text>
        <Button icon={<ClearOutlined />} size="small" onClick={handleClear}>清空</Button>
      </div>
      <div
        style={{
          height: 250,
          border: '1px solid #d9d9d9',
          borderRadius: 6,
          marginBottom: 12,
          padding: 12,
          overflow: 'auto',
          background: '#fafafa',
        }}
      >
        {messages.length === 0 ? (
          <Text type="secondary">对话历史将在此处显示</Text>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                marginBottom: 8,
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  maxWidth: '80%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: msg.role === 'user' ? '#1890ff' : '#f0f0f0',
                  color: msg.role === 'user' ? '#fff' : '#000',
                }}
              >
                {msg.content}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          placeholder="输入您的指令..."
          rows={2}
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={loading}
          onClick={handleSend}
          style={{ height: 'auto' }}
        />
      </Space.Compact>
    </div>
  );
};

export default DialogueTab;
