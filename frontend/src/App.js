import './App.css';
import PolicyList from './components/PolicyList';
import TempLogoImage from './assets/templogo.png';
import MyButton from './components/TempButton';
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
        <MyButton />

        <div className="app-panel">
          <div className="toolbar-row">
            <button
              onClick={connectWebSocket}
              disabled={isConnected}
              className="connect-button"
            >
              {isConnected ? 'Connected' : 'Connect to CLI Agent'}
            </button>
            <span className="status-text">
              {isConnected ? 'Ready for CLI agent input.' : 'Click connect to start using the CLI agent.'}
            </span>
          </div>

          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your command here (like you would in terminal)..."
            className="cli-textarea"
            disabled={!isConnected || isLoading}
          />

          <button
            onClick={sendMessage}
            disabled={!isConnected || isLoading || !message.trim()}
            className="send-button"
          >
            {isLoading ? 'Running CLI Agent...' : 'Send to CLI Agent'}
          </button>

          <div className="message-panel">
            {messages.map((msg, index) => (
              <div key={index} className={`message-item ${msg.type}`}>
                <strong>
                  {msg.type === 'user'
                    ? 'You:'
                    : msg.type === 'agent'
                    ? 'CLI Agent:'
                    : msg.type === 'error'
                    ? 'Error:'
                    : 'System:'}
                </strong>{' '}
                {msg.content}
              </div>
            ))}
            <div ref={scrollRef} />
          </div>
        </div>

        <img src={TempLogoImage} alt="Temp Logo" className="logo-image" />
      </header>
    </div>
  );
}

export default App;
