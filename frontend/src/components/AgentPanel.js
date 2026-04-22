import React, { useState, useEffect, useRef } from 'react';
import ConnectButton from './ConnectButton';
import MessageList from './MessageList';
import ModeSelector from './ModeSelector';
import RegionDropdown from './RegionDropdown';
import SendButton from './SendButton';
import Textarea from './Textarea';

/*Inte optimalt att funktionaliteten ligger gär också. Men är lite rädd för hur hookar fungerar så avvaktar lite -D*/

function AgentPanel() {
    const [message, setMessage] = useState('');
    const [messages, setMessages] = useState([]);
    const [region, setRegion] = useState('eu');
    const [mode, setMode] = useState('discover');
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const wsRef = useRef(null);
    const scrollRef = useRef(null);

    useEffect(() => {
        scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const getScanCommand = () => {
        const selectedRegion = region.toUpperCase();

        if (mode === 'discover') {
            return `--discover ${selectedRegion}`;
        }

        if (mode === 'deep') {
            return `--deep Scan ${selectedRegion}`;
        }

        return `Scan ${selectedRegion}`;
    };

    const sendAgentMessage = (agentMessage) => {
        const trimmedMessage = agentMessage.trim();
        if (!wsRef.current || !trimmedMessage) return;

        setMessages(prev => [...prev, { type: 'user', content: trimmedMessage }]);
        setIsLoading(true);

        wsRef.current.send(JSON.stringify({ message: trimmedMessage }));
    };

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
        sendAgentMessage(message);
        setMessage('');
    };

    const scanSelectedRegion = () => {
        sendAgentMessage(getScanCommand());
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="app-panel">
            <section className="settings-panel" aria-label="Search settings">
                <h2 className="panel-heading">Search settings</h2>
                <RegionDropdown
                    value={region}
                    onChange={(e) => setRegion(e.target.value)}
                />
                <ModeSelector
                    value={mode}
                    onChange={setMode}
                />
                <button
                    type="button"
                    className="scan-button"
                    onClick={scanSelectedRegion}
                    disabled={!isConnected || isLoading || !region || !mode}
                >
                    Scan
                </button>
            </section>

            <section className="chat-panel" aria-label="Agent chat">
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

                <MessageList messages={messages} scrollRef={scrollRef} />

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
            </section>
        </div>
    );
}

export default AgentPanel;
