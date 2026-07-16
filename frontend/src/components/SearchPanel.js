import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl, WS_BASE_URL } from '../config/api';
import { adminHeaders } from '../utils/adminAuth';

const PLAN_DEBOUNCE_MS = 450;

const KIND_LABELS = {
    law_api: 'Law database',
    transposition: 'EU transposition',
    website: 'Government website',
};

function notifyPolicyDataChanged() {
    window.dispatchEvent(new Event('policy-data-changed'));
}

export function summarizePlanSources(sources) {
    const websites = sources.filter((s) => s.kind === 'website');
    const rest = sources.filter((s) => s.kind !== 'website');
    const parts = rest.map((s) => s.name);
    if (websites.length === 1) {
        parts.push(websites[0].name);
    } else if (websites.length > 1) {
        parts.push(`${websites.length} government websites`);
    }
    return parts.join(' · ');
}

function PlanPreview({ plan }) {
    if (!plan) return null;
    const { sources, estimate, warnings } = plan;
    const legiscan = estimate?.legiscan;

    return (
        <div className="search-plan" aria-label="Search plan">
            {sources.length > 0 && (
                <>
                    <p className="search-plan-line">
                        <strong>Will search:</strong> {summarizePlanSources(sources)}
                    </p>
                    <ul className="search-plan-sources">
                        {sources.filter((s) => s.kind !== 'website').map((s) => (
                            <li key={s.id}>
                                <span className="search-plan-kind">{KIND_LABELS[s.kind]}</span>
                                {s.description}
                            </li>
                        ))}
                    </ul>
                    <p className="search-plan-line">
                        <strong>Estimated cost:</strong>{' '}
                        up to ~${(estimate?.llm_ceiling_usd ?? 0).toFixed(2)} in AI analysis
                        {' '}(cost level: {estimate?.cost_level})
                        {legiscan && (
                            <>
                                {' '}· uses at most {legiscan.max_queries} LegiScan queries
                                {' '}({legiscan.remaining.toLocaleString()} of{' '}
                                {legiscan.limit.toLocaleString()} left this month)
                            </>
                        )}
                    </p>
                </>
            )}
            {warnings.map((warning) => (
                <p key={warning} className="search-plan-warning" role="note">
                    {warning}
                </p>
            ))}
        </div>
    );
}

function SearchPanel({ hasApiKey, isBusy, onBusyChange }) {
    const [place, setPlace] = useState('');
    const [topic, setTopic] = useState('');
    const [plan, setPlan] = useState(null);
    const [isPlanning, setIsPlanning] = useState(false);
    const [regions, setRegions] = useState([]);
    const [scan, setScan] = useState(null);
    const wsRef = useRef(null);
    const planRequestRef = useRef(0);

    useEffect(() => {
        let cancelled = false;
        fetch(apiUrl('/api/regions'))
            .then((res) => (res.ok ? res.json() : {}))
            .then((data) => {
                if (!cancelled) setRegions(Object.values(data || {}));
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, []);

    useEffect(() => () => wsRef.current?.close(), []);

    useEffect(() => {
        const trimmed = place.trim();
        if (trimmed.length < 2) {
            setPlan(null);
            return undefined;
        }

        const requestId = planRequestRef.current + 1;
        planRequestRef.current = requestId;
        setIsPlanning(true);

        const timer = setTimeout(async () => {
            try {
                const params = new URLSearchParams({ place: trimmed });
                if (topic.trim()) params.set('terms', topic.trim());
                const res = await fetch(apiUrl(`/api/search/plan?${params.toString()}`));
                if (!res.ok) throw new Error();
                const data = await res.json();
                if (planRequestRef.current === requestId) setPlan(data);
            } catch {
                if (planRequestRef.current === requestId) setPlan(null);
            } finally {
                if (planRequestRef.current === requestId) setIsPlanning(false);
            }
        }, PLAN_DEBOUNCE_MS);

        return () => clearTimeout(timer);
    }, [place, topic]);

    const runSearch = useCallback(async (event) => {
        event.preventDefault();
        if (!plan || !plan.targets || isBusy) return;

        onBusyChange?.(true);
        setScan({ status: 'starting', found: 0, sourcesDone: 0, names: [] });

        try {
            const response = await fetch(apiUrl('/api/scans'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...adminHeaders() },
                body: JSON.stringify({
                    domains: plan.targets,
                    channels: plan.channels,
                    source_params: Object.keys(plan.source_params).length > 0
                        ? plan.source_params
                        : null,
                    max_concurrent: 5,
                }),
            });
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || `Search failed with ${response.status}`);
            }
            const job = await response.json();
            setScan((prev) => ({
                ...prev,
                status: 'running',
                scanId: job.scan_id,
                sourceCount: job.domain_count,
            }));

            const ws = new WebSocket(`${WS_BASE_URL}/api/scans/${job.scan_id}/ws`);
            wsRef.current = ws;
            ws.onmessage = (msg) => {
                let payload;
                try {
                    payload = JSON.parse(msg.data);
                } catch {
                    return;
                }
                if (payload.type === 'policy_found') {
                    setScan((prev) => prev && ({
                        ...prev,
                        found: prev.found + 1,
                        names: [...prev.names, payload.data?.policy_name].slice(-5),
                    }));
                } else if (payload.type === 'domain_complete') {
                    setScan((prev) => prev && ({
                        ...prev,
                        sourcesDone: prev.sourcesDone + 1,
                    }));
                } else if (payload.type === 'scan_complete') {
                    setScan((prev) => prev && ({
                        ...prev,
                        status: 'complete',
                        found: payload.data?.total_policies ?? prev.found,
                    }));
                    notifyPolicyDataChanged();
                    onBusyChange?.(false);
                    ws.close();
                } else if (payload.type === 'error') {
                    setScan((prev) => prev && ({ ...prev, status: 'error' }));
                    onBusyChange?.(false);
                    ws.close();
                }
            };
            ws.onerror = () => {
                setScan((prev) => prev && ({ ...prev, status: 'error' }));
                onBusyChange?.(false);
            };
        } catch (error) {
            setScan({ status: 'error', message: error.message, found: 0 });
            onBusyChange?.(false);
        }
    }, [plan, isBusy, onBusyChange]);

    const stopSearch = useCallback(async () => {
        if (!scan?.scanId) return;
        try {
            await fetch(apiUrl(`/api/scans/${scan.scanId}`), {
                method: 'DELETE',
                headers: adminHeaders(),
            });
        } catch {
            // Best effort; the WS close event settles state either way.
        }
        wsRef.current?.close();
        setScan((prev) => prev && ({ ...prev, status: 'stopped' }));
        onBusyChange?.(false);
        notifyPolicyDataChanged();
    }, [scan, onBusyChange]);

    const canSearch = Boolean(
        plan && plan.targets && hasApiKey && !isBusy && scan?.status !== 'running',
    );
    const isRunning = scan?.status === 'starting' || scan?.status === 'running';

    return (
        <section className="search-panel" aria-label="Find new policies">
            <div className="settings-heading-panel">
                <h2 className="panel-heading">Find new policies</h2>
                <p className="text-block-small">
                    Pick a place; the right sources are chosen for you and you see the
                    cost before anything runs. This uses paid AI analysis.
                </p>
            </div>
            <form className="search-panel-form" onSubmit={runSearch}>
                <label className="visually-hidden" htmlFor="search-place-input">
                    Place to search
                </label>
                <input
                    id="search-place-input"
                    className="ask-box-input"
                    type="text"
                    list="search-place-options"
                    placeholder='Where? e.g. "California", "Sweden", "EU"'
                    value={place}
                    onChange={(event) => setPlace(event.target.value)}
                    disabled={isRunning}
                />
                <datalist id="search-place-options">
                    {regions.map((name) => <option key={name} value={name} />)}
                </datalist>
                <label className="visually-hidden" htmlFor="search-topic-input">
                    Topic (optional)
                </label>
                <input
                    id="search-topic-input"
                    className="ask-box-input"
                    type="text"
                    placeholder="Topic (optional), e.g. thermal energy network"
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    disabled={isRunning}
                />
                <button type="submit" className="ask-box-button" disabled={!canSearch}>
                    {isRunning ? 'Searching...' : 'Search'}
                </button>
            </form>
            {isPlanning && (
                <p className="search-plan-status" role="status">Planning search...</p>
            )}
            {!isPlanning && <PlanPreview plan={plan} />}
            {!hasApiKey && (
                <p className="text-block-small">
                    Add an Anthropic API key in Settings to enable searching.
                </p>
            )}
            {scan && (
                <div className="search-progress" role="status" aria-live="polite">
                    {isRunning && (
                        <>
                            <p className="search-progress-line">
                                Searching {scan.sourceCount ?? '...'} sources
                                {' '}· {scan.sourcesDone} done · {scan.found} policies found
                                <button
                                    type="button"
                                    className="leads-dismiss-button search-stop-button"
                                    onClick={stopSearch}
                                >
                                    Stop
                                </button>
                            </p>
                            {scan.names?.length > 0 && (
                                <p className="search-progress-names">
                                    Latest: {scan.names[scan.names.length - 1]}
                                </p>
                            )}
                        </>
                    )}
                    {scan.status === 'complete' && scan.found > 0 && (
                        <p className="search-progress-line search-progress-done">
                            Done: {scan.found} {scan.found === 1 ? 'policy' : 'policies'} found
                            and added to review. New rows are in the Staging sheet.
                        </p>
                    )}
                    {scan.status === 'complete' && scan.found === 0 && (
                        <div className="search-plan-warning">
                            <p>
                                Nothing new found. {plan ? `Searched ${plan.sources.length} sources
                                for ${plan.place.display}.` : ''} That usually means no new or
                                changed policies since the last search - already-known items are
                                skipped, not re-reported.
                            </p>
                            <p>
                                Try a broader place (a whole country or &quot;EU&quot;), a different
                                topic wording, or ask the admin assistant to investigate.
                            </p>
                        </div>
                    )}
                    {scan.status === 'stopped' && (
                        <p className="search-progress-line">Search stopped.</p>
                    )}
                    {scan.status === 'error' && (
                        <p className="ask-box-error" role="alert">
                            The search could not be completed.
                            {scan.message ? ` ${scan.message}` : ''}
                        </p>
                    )}
                </div>
            )}
        </section>
    );
}

export default SearchPanel;
