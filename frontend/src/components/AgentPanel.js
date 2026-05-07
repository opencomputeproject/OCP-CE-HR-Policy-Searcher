import React, { useEffect, useRef, useState } from 'react';
import Chatbot from './Chatbot';
import ConnectButton from './ConnectButton';
import ModeSelector from './ModeSelector';
import RegionDropdown from './RegionDropdown';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

function AgentPanel() {
    const [selectedRegions, setSelectedRegions] = useState([]);
    const [mode, setMode] = useState('discover');
    const [isConnected, setIsConnected] = useState(false);
    const [isChatRunning, setIsChatRunning] = useState(false);
    const [activeScanId, setActiveScanId] = useState(null);
    const [chatNotice, setChatNotice] = useState(null);
    const wsRef = useRef(null);
    const scanWsRef = useRef(null);
    const isScanRunning = Boolean(activeScanId);
    const isBusy = isChatRunning || isScanRunning;

    const pushNotice = (type, text) => {
        setChatNotice({
            id: Date.now(),
            type,
            text,
        });
    };

    const connectWebSocket = () => {
        if (wsRef.current) return;

        const ws = new WebSocket(`${WS_BASE_URL}/api/agent/ws`);
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            pushNotice('system', 'Connected to policy agent API.');
        };

        ws.onclose = () => {
            setIsConnected(false);
            wsRef.current = null;
            setIsChatRunning(false);
            pushNotice('system', 'Disconnected from CLI agent.');
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            setIsChatRunning(false);
            pushNotice('error', 'Connection error.');
        };
    };

    const buildScanRequest = () => {
        const categories = selectedRegions
            .filter((item) => item.startsWith('category:'))
            .map((item) => item.slice('category:'.length));
        const tags = selectedRegions
            .filter((item) => item.startsWith('tag:'))
            .map((item) => item.slice('tag:'.length));
        const targets = selectedRegions.filter(
            (item) => !item.startsWith('category:') && !item.startsWith('tag:'),
        );

        return {
            request: {
                domains: targets[0] || 'all',
                max_concurrent: mode === 'deep' ? 10 : 5,
                skip_llm: false,
                dry_run: false,
                category: categories[0] || null,
                tags: tags.length > 0 ? tags : null,
            },
            ignoredTargets: targets.slice(1),
        };
    };

    const formatScanEvent = (event) => {
        const domainLabel = event.domain_id ? ` (${event.domain_id})` : '';
        const data = event.data || {};

        switch (event.type) {
            case 'scan_started':
                return `Scan ${event.scan_id} started with ${data.domain_count ?? '?'} domains.`;
            case 'domain_started':
                return `Started ${data.domain_name || event.domain_id || 'domain'}.`;
            case 'policy_found':
                return `Policy found${domainLabel}: ${data.policy_name || data.url || 'new policy'}.`;
            case 'domain_complete':
                return `Completed${domainLabel}: ${data.pages ?? 0} pages, ${data.policies ?? 0} policies, ${data.errors ?? 0} errors.`;
            case 'verification_complete':
                return `Verification complete: ${data.passed ?? 0} passed, ${data.flagged ?? 0} flagged.`;
            case 'audit_complete':
                return 'Audit advisory complete.';
            case 'scan_complete':
                return `Scan complete: ${data.total_policies ?? 0} policies found.`;
            case 'error':
                return `Scan error${domainLabel}: ${data.error || 'Unknown error'}.`;
            default:
                return null;
        }
    };

    const connectScanWebSocket = (scanId) => {
        scanWsRef.current?.close();

        const scanWs = new WebSocket(`${WS_BASE_URL}/api/scans/${scanId}/ws`);
        scanWsRef.current = scanWs;

        scanWs.onmessage = (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                return;
            }

            const notice = formatScanEvent(payload);
            if (notice) {
                pushNotice(payload.type === 'error' ? 'error' : 'system', notice);
            }

            if (payload.type === 'scan_complete' || payload.type === 'error') {
                setActiveScanId(null);
                scanWs.close();
            }
        };

        scanWs.onerror = () => {
            pushNotice('error', 'Scan progress connection error.');
        };

        scanWs.onclose = () => {
            if (scanWsRef.current === scanWs) {
                scanWsRef.current = null;
            }
        };
    };

    const scanSelectedRegion = async () => {
        if (isScanRunning || selectedRegions.length === 0) return;

        const { request, ignoredTargets } = buildScanRequest();

        if (ignoredTargets.length > 0) {
            pushNotice(
                'system',
                `Direct scan API runs one scan target at a time. Starting "${request.domains}" and ignoring: ${ignoredTargets.join(', ')}.`,
            );
        }

        try {
            pushNotice('system', `Starting scan for "${request.domains}" via /api/scans.`);
            const response = await fetch(`${API_BASE_URL}/api/scans`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || `Scan request failed with ${response.status}`);
            }

            const scan = await response.json();
            setActiveScanId(scan.scan_id);
            pushNotice(
                'system',
                `Scan ${scan.scan_id} queued (${scan.domain_count} domains). Listening for progress.`,
            );
            connectScanWebSocket(scan.scan_id);
        } catch (error) {
            pushNotice('error', `Could not start scan: ${error.message}`);
        }
    };

    const stopActiveScan = async () => {
        if (!activeScanId) return;

        try {
            const scanId = activeScanId;
            const response = await fetch(`${API_BASE_URL}/api/scans/${scanId}`, {
                method: 'DELETE',
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || `Stop request failed with ${response.status}`);
            }

            scanWsRef.current?.close();
            scanWsRef.current = null;
            setActiveScanId(null);
            pushNotice('system', `Stopped scan ${scanId}.`);
        } catch (error) {
            pushNotice('error', `Could not stop scan: ${error.message}`);
        }
    };

    useEffect(() => () => {
        scanWsRef.current?.close();
        wsRef.current?.close();
    }, []);

    return (
        <div className="app-panel">
            <section className="settings-panel" aria-label="Search settings">
                <div>
                    <h2 className="panel-heading">Search settings</h2>
                    <div className="region-dropdown-scroll">
                        <RegionDropdown
                            selectedItems={selectedRegions}
                            onSelectionChange={(event, itemIds) => setSelectedRegions(itemIds)}
                        />
                    </div>
                    <ModeSelector
                        value={mode}
                        onChange={setMode}
                    />
                </div>
                <div className="agent-action-row">
                    <button
                        type="button"
                        className="scan-button"
                        onClick={scanSelectedRegion}
                        disabled={isBusy || selectedRegions.length === 0 || !mode}
                    >
                        {isScanRunning ? 'Scan running' : 'Scan'}
                    </button>
                    <button
                        type="button"
                        className="stop-scan-button"
                        onClick={stopActiveScan}
                        disabled={!isScanRunning}
                    >
                        Stop scan
                    </button>
                </div>
            </section>

            <section className="chat-panel" aria-label="Agent chat">
                <div className="toolbar-row">
                    <ConnectButton
                        connected={isConnected}
                        onClick={connectWebSocket}
                        disabled={isConnected}
                    />
                    <span className="status-text">
                        {isScanRunning
                            ? `Scan ${activeScanId} is running.`
                            : isConnected
                                ? 'Ready for CLI agent input.'
                                : 'Click connect to start using the CLI agent.'}
                    </span>
                </div>

                <Chatbot
                    wsRef={wsRef}
                    isConnected={isConnected}
                    notice={chatNotice}
                    onRunningChange={setIsChatRunning}
                />
            </section>
        </div>
    );
}

export default AgentPanel;
