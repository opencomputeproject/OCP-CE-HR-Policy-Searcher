import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl, WS_BASE_URL } from '../config/api';
import { adminHeaders } from '../utils/adminAuth';

function notifyPolicyDataChanged() {
    window.dispatchEvent(new Event('policy-data-changed'));
}

function formatScanEvent(event) {
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
}

function useScanQueue({ onNotice }) {
    const scanWsRef = useRef(null);
    const scanQueueRef = useRef([]);
    const scanQueueCancelledRef = useRef(false);
    const [isScanRequestRunning, setIsScanRequestRunning] = useState(false);
    const [activeScanId, setActiveScanId] = useState(null);
    const [queuedScanCount, setQueuedScanCount] = useState(0);
    const isScanRunning = Boolean(activeScanId);
    const isQueueRunning = queuedScanCount > 0;

    const connectScanWebSocket = useCallback((scanId, callbacks = {}) => {
        scanWsRef.current?.close();

        const scanWs = new WebSocket(`${WS_BASE_URL}/api/scans/${scanId}/ws`);
        scanWsRef.current = scanWs;
        let settled = false;
        const finish = (completed) => {
            if (settled) return;
            settled = true;
            if (completed) {
                callbacks.onComplete?.();
            } else {
                callbacks.onError?.();
            }
        };

        scanWs.onmessage = (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                return;
            }

            const notice = formatScanEvent(payload);
            if (notice) {
                onNotice(payload.type === 'error' ? 'error' : 'system', notice);
            }

            if (payload.type === 'scan_complete' || payload.type === 'error') {
                if (payload.type === 'scan_complete') {
                    notifyPolicyDataChanged();
                }
                finish(payload.type === 'scan_complete');
                setActiveScanId(null);
                scanWs.close();
            }
        };

        scanWs.onerror = () => {
            onNotice('error', 'Scan progress connection error.');
            finish(false);
            scanWs.close();
        };

        scanWs.onclose = () => {
            if (scanWsRef.current === scanWs) {
                scanWsRef.current = null;
            }

            setActiveScanId((current) => {
                if (current === scanId) {
                    return null;
                }
                return current;
            });

            finish(false);
        };
    }, [onNotice]);

    const startScanRequest = useCallback(async (request, index, total) => {
        setIsScanRequestRunning(true);
        onNotice(
            'system',
            request.discover
                ? `Starting discovery ${index + 1}/${total} for "${request.domains}".`
                : `Starting scan ${index + 1}/${total} for "${request.domains}".`,
        );

        try {
            const response = await fetch(apiUrl('/api/scans'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...adminHeaders() },
                body: JSON.stringify(request),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || `Scan request failed with ${response.status}`);
            }

            const scan = await response.json();
            if (scan.discover) {
                onNotice(
                    'system',
                    scan.response || `Discovery for "${request.domains}" completed.`,
                );
                notifyPolicyDataChanged();
                return !scanQueueCancelledRef.current;
            }

            if (scanQueueCancelledRef.current) {
                await fetch(apiUrl(`/api/scans/${scan.scan_id}`), {
                    method: 'DELETE',
                    headers: adminHeaders(),
                });
                return false;
            }

            setActiveScanId(scan.scan_id);
            onNotice(
                'system',
                `Scan ${scan.scan_id} queued (${scan.domain_count} domains). Listening for progress.`,
            );

            return await new Promise((resolve) => {
                connectScanWebSocket(scan.scan_id, {
                    onComplete: () => resolve(true),
                    onError: () => resolve(false),
                });
            });
        } catch (error) {
            onNotice('error', `Could not start scan: ${error.message}`);
            return false;
        } finally {
            setIsScanRequestRunning(false);
        }
    }, [connectScanWebSocket, onNotice]);

    const runScanQueue = useCallback(async (requests) => {
        scanQueueRef.current = requests;
        scanQueueCancelledRef.current = false;
        setQueuedScanCount(requests.length);

        try {
            for (let index = 0; index < requests.length; index += 1) {
                if (scanQueueCancelledRef.current || scanQueueRef.current.length === 0) return;

                const completed = await startScanRequest(requests[index], index, requests.length);
                scanQueueRef.current = scanQueueRef.current.slice(1);
                setQueuedScanCount(scanQueueRef.current.length);

                if (!completed) {
                    scanQueueRef.current = [];
                    setQueuedScanCount(0);
                    onNotice('error', 'Scan queue stopped.');
                    return;
                }
            }

            if (requests.length > 1) {
                onNotice(
                    'system',
                    `Scan queue complete: ${requests.length} targets processed.`,
                );
            }
        } finally {
            scanQueueRef.current = [];
            setQueuedScanCount(0);
        }
    }, [onNotice, startScanRequest]);

    const stopActiveScan = useCallback(async () => {
        scanQueueRef.current = [];
        scanQueueCancelledRef.current = true;
        setQueuedScanCount(0);
        if (!activeScanId) {
            onNotice('system', 'Cleared scan queue.');
            return;
        }

        try {
            const scanId = activeScanId;
            const response = await fetch(apiUrl(`/api/scans/${scanId}`), {
                method: 'DELETE',
                headers: adminHeaders(),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || `Stop request failed with ${response.status}`);
            }

            scanWsRef.current?.close();
            scanWsRef.current = null;
            setActiveScanId(null);
            notifyPolicyDataChanged();
            onNotice('system', `Stopped scan ${scanId}.`);
        } catch (error) {
            onNotice('error', `Could not stop scan: ${error.message}`);
        }
    }, [activeScanId, onNotice]);

    useEffect(() => {
        return () => {
            scanWsRef.current?.close();
        };
    }, []);

    return {
        isScanRequestRunning,
        isScanRunning,
        isQueueRunning,
        queuedScanCount,
        runScanQueue,
        stopActiveScan,
    };
}

export default useScanQueue;
