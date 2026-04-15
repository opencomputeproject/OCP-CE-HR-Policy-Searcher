import './App.css';
import Button from './components/Button';
import MessageList from './components/MessageList';
import Textarea from './components/Textarea';
import TempLogoImage from './assets/templogo.png';
import React, { useState, useEffect, useRef } from 'react';

function App() {
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

    // Connect to the CLI agent web interface on port 8001
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

    // Send message to CLI agent via WebSocket
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
    <div className="App">
      <header className="App-header">
        <h1>OCP Policy Searcher</h1>

        <div className="app-panel">
          <div className="toolbar-row">
            <Button
              onClick={connectWebSocket}
              disabled={isConnected}
              variant="primary"
            >
              {isConnected ? 'Connected' : 'Connect to CLI Agent'}
            </Button>
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

          <Button
            onClick={sendMessage}
            disabled={!isConnected || isLoading || !message.trim()}
            variant="secondary"
          >
            {isLoading ? 'Running CLI Agent...' : 'Send to CLI Agent'}
          </Button>

          <MessageList messages={messages} scrollRef={scrollRef} />
        </div>

        <img src={TempLogoImage} alt="Temp Logo" className="logo-image" />
      </header>
    </div>
  );
}

export default App;
