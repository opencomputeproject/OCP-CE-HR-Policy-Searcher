import React, { useEffect, useRef, useState } from 'react';
import Chatbot from './Chatbot';
import ConnectButton from './ConnectButton';
import ModeSelector from './ModeSelector';
import RegionDropdown from './RegionDropdown';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

function AgentPanel() {
    const [selectedRegions, setSelectedRegions] = useState([]);
    const [mode, setMode] = useState('discover');
    const [isConnected, setIsConnected] = useState(false);
    const [isChatRunning, setIsChatRunning] = useState(false);
    const [activeScanId, setActiveScanId] = useState(null);
    const [costEstimate, setCostEstimate] = useState(null);
    const [costStatus, setCostStatus] = useState('idle');
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
        const normalizeTarget = (item) => {
            if (item.startsWith('group:') && item.includes(':region:')) {
                return item.slice(item.lastIndexOf(':region:') + ':region:'.length);
            }
            if (item.startsWith('group:')) {
                return item.slice('group:'.length);
            }
            if (item.startsWith('region:')) {
                return item.slice('region:'.length);
            }
            return item;
        };

        const categories = selectedRegions
            .filter((item) => item.startsWith('category:'))
            .map((item) => item.slice('category:'.length));
        const tags = selectedRegions
            .filter((item) => item.startsWith('tag:'))
            .map((item) => item.slice('tag:'.length));
        const targets = selectedRegions
            .filter((item) => !item.startsWith('category:') && !item.startsWith('tag:'))
            .map(normalizeTarget);

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

    const getCostEstimate = async (domains) => {
        const response = await fetch(
            `${API_BASE_URL}/api/cost-estimate?domains=${encodeURIComponent(domains)}`,
            { method: 'POST' },
        );

        if (!response.ok) {
            throw new Error(`Cost estimate failed for ${domains} (${response.status})`);
        }

        return response.json();
    };

    const sumCostEstimates = (estimates) => estimates.reduce(
        (total, estimate) => ({
            domain_count: total.domain_count + (estimate.domain_count || 0),
            estimated_pages: total.estimated_pages + (estimate.estimated_pages || 0),
            estimated_keyword_passes: total.estimated_keyword_passes + (estimate.estimated_keyword_passes || 0),
            estimated_screening_calls: total.estimated_screening_calls + (estimate.estimated_screening_calls || 0),
            estimated_analysis_calls: total.estimated_analysis_calls + (estimate.estimated_analysis_calls || 0),
            estimated_cost_usd: total.estimated_cost_usd + (estimate.estimated_cost_usd || 0),
        }),
        {
            domain_count: 0,
            estimated_pages: 0,
            estimated_keyword_passes: 0,
            estimated_screening_calls: 0,
            estimated_analysis_calls: 0,
            estimated_cost_usd: 0,
        },
    );

    useEffect(() => {
    let isCurrent = true;

    // Used to extract the actual target from various possible region/group identifiers for cost estimation
    // TODO: It should be possible to get correct formating directly from the API call, but this is a quick fix. First we need to setup the RegionDropdown in a more intuitive way.
    const normalizeTarget = (item) => {
        if (item.startsWith('group:') && item.includes(':region:')) {
            return item.slice(item.lastIndexOf(':region:') + ':region:'.length);
        }
        if (item.startsWith('group:')) {
            return item.slice('group:'.length);
        }
        if (item.startsWith('region:')) {
            return item.slice('region:'.length);
        }
        return item;
    };

    const categories = selectedRegions.filter((item) => item.startsWith('category:'));
    const tags = selectedRegions.filter((item) => item.startsWith('tag:'));

    const targets = selectedRegions
        .filter((item) => !item.startsWith('category:') && !item.startsWith('tag:'))
        .map(normalizeTarget);

    if (targets.length === 0) {
        setCostEstimate(null);
        setCostStatus(selectedRegions.length === 0 ? 'idle' : 'filters_only');
        return () => {
            isCurrent = false;
        };
    }

    setCostStatus('loading');

    Promise.all(targets.map((target) => getCostEstimate(target)))
        .then((estimates) => {
            if (!isCurrent) return;
            setCostEstimate({
                ...sumCostEstimates(estimates),
                target_count: targets.length,
                has_filters: categories.length > 0 || tags.length > 0,
            });
            setCostStatus('ready');
        })
        .catch(() => {
            if (!isCurrent) return;
            setCostEstimate(null);
            setCostStatus('error');
        });

    return () => {
        isCurrent = false;
    };
}, [selectedRegions]);

    const getCostEstimateText = () => {
        if (costStatus === 'loading') {
            return 'Estimating...';
        }
        if (costStatus === 'filters_only') {
            return 'Select a scan target';
        }
        if (costStatus === 'error') {
            return 'Estimate unavailable';
        }
        if (costStatus === 'ready' && costEstimate) {
            const cost = Number(costEstimate.estimated_cost_usd || 0).toFixed(2);
            const targetLabel = costEstimate.target_count > 1 ? `${costEstimate.target_count} targets` : '1 target';
            const filterNote = costEstimate.has_filters ? ', filters not included' : '';
            return `$${cost} (${targetLabel}${filterNote})`;
        }
        return 'No estimate';
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
                    <output className={`cost-estimate ${costStatus}`} aria-live="polite">
                        {getCostEstimateText()}
                    </output>
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
