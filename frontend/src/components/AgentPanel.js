import React, { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../config/api';
import useAgentSocket from '../hooks/useAgentSocket';
import useCostEstimate from '../hooks/useCostEstimate';
import useScanQueue from '../hooks/useScanQueue';
import { buildScanRequests } from '../utils/scanTargets';
import AgentChatPanel from './AgentChatPanel';
import DomainScanPanel from './DomainScanPanel';
import PolicyScannerHeader from './PolicyScannerHeader';

function AgentPanel() {
    const [selectedRegions, setSelectedRegions] = useState([]);
    const [mode, setMode] = useState('standard');
    const [chatNotice, setChatNotice] = useState(null);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [hasApiKey, setHasApiKey] = useState(false);
    const isStandardMode = mode === 'standard';
    const scanOptions = {
        discover: mode === 'discover',
        deep: mode === 'deep',
    };

    const pushNotice = useCallback((type, text) => {
        setChatNotice({
            id: Date.now(),
            type,
            text,
        });
    }, []);

    const { wsRef, isChatRunning, setIsChatRunning } = useAgentSocket({
        onNotice: pushNotice,
    });
    const { costStatus, costEstimateText } = useCostEstimate({
        selectedRegions,
        isStandardMode,
    });
    const {
        isScanRequestRunning,
        isScanRunning,
        isQueueRunning,
        queuedScanCount,
        runScanQueue,
        stopActiveScan,
    } = useScanQueue({
        onNotice: pushNotice,
    });

    const isBusy = isChatRunning || isScanRunning || isScanRequestRunning || isQueueRunning;

    const fetchApiKeyStatus = useCallback(async () => {
        try {
            const res = await fetch(apiUrl('/api/settings/api-key'));
            if (!res.ok) throw new Error();
            const data = await res.json();
            setHasApiKey(data.exists);
        } catch {
            setHasApiKey(false);
        }
    }, []);

    const scanSelectedRegion = async () => {
        if (isBusy || selectedRegions.length === 0 || !hasApiKey) return;

        let requests;
        try {
            requests = await buildScanRequests(selectedRegions, scanOptions);
        } catch (error) {
            pushNotice('error', `Could not resolve selected domains: ${error.message}`);
            return;
        }

        if (requests.length > 1) {
            pushNotice('system', `Starting sequential scan queue for ${requests.length} targets.`);
        }

        await runScanQueue(requests);
    };

    useEffect(() => {
        fetchApiKeyStatus();
    }, [fetchApiKeyStatus]);

    return (
        <section className="Policy-scanner" aria-label="Policy Scanner">
            <PolicyScannerHeader onOpenSettings={() => setIsSettingsOpen(true)} />
            <DomainScanPanel
                selectedRegions={selectedRegions}
                onSelectionChange={(event, itemIds) => setSelectedRegions(itemIds)}
                mode={mode}
                onModeChange={setMode}
                costStatus={costStatus}
                costEstimateText={costEstimateText}
                isBusy={isBusy}
                hasApiKey={hasApiKey}
                isQueueRunning={isQueueRunning}
                queuedScanCount={queuedScanCount}
                isScanRequestRunning={isScanRequestRunning}
                isScanRunning={isScanRunning}
                onScan={scanSelectedRegion}
                onStop={stopActiveScan}
            />
            <AgentChatPanel
                isSettingsOpen={isSettingsOpen}
                onCloseSettings={() => {
                    setIsSettingsOpen(false);
                    fetchApiKeyStatus();
                }}
                wsRef={wsRef}
                notice={chatNotice}
                onRunningChange={setIsChatRunning}
            />
        </section>
    );
}

export default AgentPanel;
