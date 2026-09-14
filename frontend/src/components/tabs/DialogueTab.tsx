import React, { useState, useEffect, useRef } from 'react';
import { Button, Input, Space, Typography, message, Tag } from 'antd';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { sendChatMessage, getChatHistory, clearChatHistory } from '../../api/client';

const { Text } = Typography;
const { TextArea } = Input;

const CONVERSATION_KEY = 'dialogue_conversation_id';

interface Message {
  role: string;
  content: string;
  timestamp: string;
}

const DialogueTab: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 面板在切换 Tab 时会被销毁重建，用 localStorage 恢复会话
    const stored = localStorage.getItem(CONVERSATION_KEY);
    if (!stored) return;
    setConversationId(stored);
    getChatHistory(stored)
      .then((history) => setMessages(history.messages))
      .catch(() => {
        // 会话在后端已不存在时忽略，从头开始
        localStorage.removeItem(CONVERSATION_KEY);
        setConversationId(null);
      });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content) {
      message.warning('请输入消息');
      return;
    }
    setMessages((prev) => [...prev, { role: 'user', content, timestamp: new Date().toISOString() }]);
    setInput('');
    setSuggestions([]);
    setLoading(true);

    try {
      const res = await sendChatMessage(content, conversationId ?? undefined);
      if (!conversationId) {
        setConversationId(res.conversation_id);
        localStorage.setItem(CONVERSATION_KEY, res.conversation_id);
      }
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.response, timestamp: new Date().toISOString() },
      ]);
      setSuggestions(res.suggestions ?? []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '发送失败');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (conversationId) {
      try {
        await clearChatHistory(conversationId);
      } catch {
        /* 后端历史清空失败不阻塞本地清空 */
      }
    }
    setMessages([]);
    setSuggestions([]);
    setConversationId(null);
    localStorage.removeItem(CONVERSATION_KEY);
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>通过对话优化整合方案</Text>
        <Button icon={<ClearOutlined />} size="small" onClick={handleClear}>
          清空
        </Button>
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
              key={`${msg.timestamp}-${idx}`}
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
                  whiteSpace: 'pre-wrap',
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

      {suggestions.length > 0 && (
        <Space size={4} wrap style={{ marginBottom: 8 }}>
          {suggestions.map((suggestion) => (
            <Tag
              key={suggestion}
              color="blue"
              style={{ cursor: 'pointer' }}
              onClick={() => handleSend(suggestion)}
            >
              {suggestion}
            </Tag>
          ))}
        </Space>
      )}

      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          placeholder="输入您的指令..."
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={loading}
          onClick={() => handleSend()}
          style={{ height: 'auto' }}
        />
      </Space.Compact>
    </div>
  );
};

export default DialogueTab;
