import React, { useState, useEffect, useRef } from 'react';
import ConnectButton from './ConnectButton';
import MessageList from './MessageList';
import SendButton from './SendButton';
import Textarea from './Textarea';

function AgentPanel() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const wsRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const connectWebSocket = () => {
    if (wsRef.current) return;

    const ws = new WebSocket('ws://localhost:8001/ws');
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setMessages(prev => [...prev, { type: 'system', content: 'Connected to CLI agent!' }]);
    };

    ws.onmessage = (event) => {
      setMessages(prev => [...prev, { type: 'agent', content: event.data }]);
      setIsLoading(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
      setMessages(prev => [...prev, { type: 'system', content: 'Disconnected from CLI agent' }]);
      wsRef.current = null;
      setIsLoading(false);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setMessages(prev => [...prev, { type: 'error', content: 'Connection error' }]);
      setIsLoading(false);
    };
  };

  const sendMessage = () => {
    if (!wsRef.current || !message.trim()) return;

    setMessages(prev => [...prev, { type: 'user', content: message }]);
    setIsLoading(true);

    wsRef.current.send(JSON.stringify({ message }));
    setMessage('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app-panel">
      <div className="toolbar-row">
        <ConnectButton
          connected={isConnected}
          onClick={connectWebSocket}
          disabled={isConnected}
        />
        <span className="status-text">
          {isConnected ? 'Ready for CLI agent input.' : 'Click connect to start using the CLI agent.'}
        </span>
      </div>

      <Textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyPress={handleKeyPress}
        placeholder="Type your command here (like you would in terminal)..."
        disabled={!isConnected || isLoading}
      />

      <SendButton
        isLoading={isLoading}
        onClick={sendMessage}
        disabled={!isConnected || isLoading || !message.trim()}
      />

      <MessageList messages={messages} scrollRef={scrollRef} />
    </div>
  );
}

export default AgentPanel;
