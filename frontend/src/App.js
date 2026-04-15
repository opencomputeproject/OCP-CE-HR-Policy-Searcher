import logo from './logo.svg';
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

        <div style={{ width: '80%', maxWidth: '700px', margin: '20px auto', textAlign: 'left' }}>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '12px' }}>
            <button
              onClick={connectWebSocket}
              disabled={isConnected}
              style={{
                padding: '10px 18px',
                backgroundColor: isConnected ? '#999' : '#1976d2',
                border: 'none',
                borderRadius: '4px',
                color: 'white',
                cursor: isConnected ? 'not-allowed' : 'pointer',
              }}
            >
              {isConnected ? 'Connected' : 'Connect to CLI Agent'}
            </button>
            <span style={{ alignSelf: 'center' }}>
              {isConnected ? 'Ready for CLI agent input.' : 'Click connect to start using the CLI agent.'}
            </span>
          </div>

          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your command here (like you would in terminal)..."
            style={{
              width: '100%',
              minHeight: '120px',
              padding: '12px',
              border: '1px solid #ccc',
              borderRadius: '6px',
              fontFamily: 'monospace',
              resize: 'vertical',
            }}
            disabled={!isConnected || isLoading}
          />

          <button
            onClick={sendMessage}
            disabled={!isConnected || isLoading || !message.trim()}
            style={{
              marginTop: '12px',
              padding: '10px 20px',
              backgroundColor: isConnected && !isLoading ? '#2e7d32' : '#ccc',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isConnected && !isLoading ? 'pointer' : 'not-allowed',
            }}
          >
            {isLoading ? 'Running CLI Agent...' : 'Send to CLI Agent'}
          </button>

          <div
            style={{
              marginTop: '20px',
              minHeight: '140px',
              padding: '12px',
              border: '1px solid #ddd',
              borderRadius: '6px',
              backgroundColor: '#fafafa',
              color: '#333',
              overflowY: 'auto',
              fontSize: '14px'
            }}
          >
            {messages.map((msg, index) => (
              <div
                key={index}
                style={{
                  marginBottom: '10px',
                  padding: '8px',
                  borderRadius: '5px',
                  backgroundColor:
                    msg.type === 'user'
                      ? '#e3f2fd'
                      : msg.type === 'agent'
                      ? '#f3e5f5'
                      : msg.type === 'error'
                      ? '#ffebee'
                      : '#e0e0e0',
                }}
              >
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

        <img src={TempLogoImage} alt="Temp Logo" style={{ width: '200px' }} />
      </header>
    </div>
  );
}

export default App;
