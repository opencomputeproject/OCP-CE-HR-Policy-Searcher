import React, { useRef, useState } from 'react';
import Chatbot from './Chatbot';
import ConnectButton from './ConnectButton';
import ModeSelector from './ModeSelector';
import RegionDropdown from './RegionDropdown';

function AgentPanel() {
    const [region, setRegion] = useState('eu');
    const [mode, setMode] = useState('discover');
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [chatNotice, setChatNotice] = useState(null);
    const wsRef = useRef(null);
    const chatbotRef = useRef(null);

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

    const connectWebSocket = () => {
        if (wsRef.current) return;

        const ws = new WebSocket('ws://localhost:8001/ws');
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            setChatNotice({
                id: Date.now(),
                type: 'system',
                text: 'Connected to CLI agent!',
            });
        };

        ws.onclose = () => {
            setIsConnected(false);
            wsRef.current = null;
            setIsLoading(false);
            setChatNotice({
                id: Date.now(),
                type: 'system',
                text: 'Disconnected from CLI agent',
            });
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            setIsLoading(false);
            setChatNotice({
                id: Date.now(),
                type: 'error',
                text: 'Connection error',
            });
        };
    };

    const scanSelectedRegion = () => {
        chatbotRef.current?.sendCommand(getScanCommand());
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

                <Chatbot
                    ref={chatbotRef}
                    wsRef={wsRef}
                    isConnected={isConnected}
                    notice={chatNotice}
                    onRunningChange={setIsLoading}
                />
            </section>
        </div>
    );
}

export default AgentPanel;
