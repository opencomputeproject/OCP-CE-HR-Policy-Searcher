import React from 'react';
import Chatbot from './Chatbot';

function AgentChatPanel({
    wsRef,
    notice,
    onRunningChange,
    isRunning = false,
}) {
    return (
        <div className="Agent-scanner" aria-label="Agent chat">
            <Chatbot
                wsRef={wsRef}
                notice={notice}
                onRunningChange={onRunningChange}
            />
            {isRunning && (
                <p className="chat-working-note" role="status">
                    <span className="search-pulse-dot" aria-hidden="true" />
                    The assistant is working - long steps (scans, cost checks) can
                    take a minute.
                </p>
            )}
        </div>
    );
}

export default AgentChatPanel;
