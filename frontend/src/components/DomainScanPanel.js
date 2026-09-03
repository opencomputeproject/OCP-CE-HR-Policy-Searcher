import React, { useState } from 'react';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import Tooltip from '@mui/material/Tooltip';
import useScopePreview from '../hooks/useScopePreview';
import { describeSelectionLabels, splitSelection } from '../utils/scanTargets';
import CostFunnelDiagram from './CostFunnelDiagram';
import HelpNote from './HelpNote';
import InfoHotspot from './InfoHotspot';
import ModeSelector from './ModeSelector';
import RegionSelector from './RegionSelector';

// "news" is deliberately absent: news signals run on their own weekly
// schedule, not inside a scan - a checkbox here would silently do nothing.
const CHANNEL_OPTIONS = [
    { id: 'crawl', label: 'Government websites' },
    { id: 'law_apis', label: 'Law databases' },
    { id: 'transposition', label: 'EU transposition' },
];

// Plain-language copy for the "Why this price?" breakdown (WP-26) - one
// entry per channel the cost estimate can itemize. Keeps the tone rule
// (no "LLM"/"token"/"API") in one place rather than repeated per channel.
const CHANNEL_BREAKDOWN_COPY = {
    crawl: { noun: 'government websites', itemNoun: 'pages checked' },
    law_apis: { noun: 'law databases', itemNoun: 'entries checked' },
    transposition: { noun: 'EU law trackers', itemNoun: 'entries checked' },
};

// WP-30b - one-sentence hotspot tips for the three channel kinds, shared by
// the "Why this price?" breakdown lines below and the "Where will this
// search?" scope-preview group headings in useScopePreview's render.
const CHANNEL_HOTSPOT_TEXT = {
    crawl: 'Sites we read page by page, the way a visitor would.',
    law_apis: 'Official legal databases we query directly - faster and more precise than reading pages.',
    transposition: "Trackers for how EU directives become each member country's national law.",
};

function formatUsd(value) {
    return `$${Number(value || 0).toFixed(2)}`;
}

// Fixed abbreviations rather than Intl.DateTimeFormat: 'en-GB' renders
// September as "Sept" (four letters), and locale-dependent month/day
// ordering would make this line read differently depending on the
// browser's locale - a plain "D Mon YYYY" is unambiguous either way.
const MONTH_ABBREVIATIONS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

function formatHumanDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return `${date.getDate()} ${MONTH_ABBREVIATIONS[date.getMonth()]} ${date.getFullYear()}`;
}

// WP-6b: the backend names the default budget inside a plain-language
// warning sentence ("This scan stops itself at $25.00, the default
// budget...") rather than as its own field - parsed back out here so the
// budget input can start prefilled with the same number a scan would
// otherwise be capped at.
const DEFAULT_BUDGET_WARNING_RE = /stops itself at \$([0-9,]+(?:\.[0-9]+)?)/;

function parseDefaultBudgetFromWarnings(warningsList) {
    for (let i = 0; i < warningsList.length; i += 1) {
        const match = DEFAULT_BUDGET_WARNING_RE.exec(warningsList[i]);
        if (match) return Number(match[1].replace(/,/g, ''));
    }
    return null;
}

// Returns JSX (not a plain string, unlike its Phase-C shape) so the sentence
// can carry a trailing InfoHotspot - the sentence itself stays in its own
// <span> so it is still findable as one exact text node.
function channelBreakdownLine(channelId, channel) {
    const copy = CHANNEL_BREAKDOWN_COPY[channelId];
    if (!copy) return null;
    const sentence = `${channel.domain_count} ${copy.noun} - about ${channel.estimated_items_or_pages} `
        + `${copy.itemNoun}, ~${channel.screening_calls} get a fast AI pass, `
        + `~${channel.analysis_calls} get a full AI read - ${formatUsd(channel.cost_usd)} `
        + `(range ${formatUsd(channel.cost_low_usd)}-${formatUsd(channel.cost_high_usd)})`;
    return (
        <>
            <span>{sentence}</span>
            <InfoHotspot label={`More about ${copy.noun}`}>{CHANNEL_HOTSPOT_TEXT[channelId]}</InfoHotspot>
        </>
    );
}

// A click that lands on a HelpNote's summary while it is still closed is
// about to open it - this is the "open" signal WP-28's scope preview waits
// for before it fetches anything. (The native <details> "toggle" event would
// be the obvious hook, but it fires as an async, unlisenable-in-jsdom task in
// some environments, so this reads the pre-toggle DOM state on the click
// itself instead - reliable in both real browsers and the test suite.)
function isOpeningClick(event) {
    const summary = event.target.closest('.help-note-summary');
    if (!summary) return false;
    const details = summary.closest('details');
    return Boolean(details) && !details.open;
}

function DomainScanPanel({
    selectedRegions,
    onSelectionChange,
    mode,
    onModeChange,
    channels,
    onChannelsChange,
    costStatus,
    costEstimateText,
    costEstimate,
    standardEstimate,
    deepEstimate,
    sourceCount,
    isBusy,
    hasApiKey,
    isQueueRunning,
    queuedScanCount,
    isScanRequestRunning,
    isScanRunning,
    funnelSummary,
    onScan,
    onStop,
}) {
    const [isScopePreviewActive, setIsScopePreviewActive] = useState(false);
    // WP-6b: null means "not yet touched by the admin" - the displayed
    // value is derived from the estimate's default-budget warning below,
    // so it stays in sync with the current scope until the admin types
    // their own number.
    const [budgetInput, setBudgetInput] = useState(null);
    const [noBudget, setNoBudget] = useState(false);
    const [confirmPending, setConfirmPending] = useState(false);

    const handleChannelToggle = (channelId, checked) => {
        const nextChannels = checked
            ? [...channels, channelId]
            : channels.filter((id) => id !== channelId);
        onChannelsChange(nextChannels);
    };

    const handleScopePreviewAreaClick = (event) => {
        if (isOpeningClick(event)) setIsScopePreviewActive(true);
    };

    // What-you-launch-is-unambiguous summary, kept directly above the
    // Scan/Stop buttons. sourceCount is the cost estimate's domain_count
    // once that request is ready (the backend's actual resolved-domain
    // count - the single source of truth); while it's loading/idle/absent,
    // fall back to the number of scope entries currently selected so the
    // line still shows a number rather than "unknown".
    const scopeTargets = splitSelection(selectedRegions || []).targets;
    const hasScope = scopeTargets.length > 0;
    const selectionLabels = describeSelectionLabels(selectedRegions);
    const scopeText = selectionLabels.length > 0 ? selectionLabels.join(', ') : 'nothing selected';
    const resolvedSourceCount = sourceCount != null ? sourceCount : scopeTargets.length;
    const sourceLabel = `${resolvedSourceCount} source${resolvedSourceCount === 1 ? '' : 's'}`;
    const scanScopeSummary = `Scanning: ${scopeText} - ${sourceLabel} - ${costEstimateText}`;

    // "Why this price?" breakdown (WP-26) - only channels the backend
    // actually itemized are shown, in the same order as the checkboxes
    // above. Requires a ready estimate carrying a channels breakdown.
    const channelEntries = costStatus === 'ready' && costEstimate && costEstimate.channels
        ? CHANNEL_OPTIONS
            .map((option) => [option.id, costEstimate.channels[option.id]])
            .filter(([, channel]) => Boolean(channel))
        : [];
    const hasCostBreakdown = channelEntries.length > 0;

    // WP-6b: last_actual + warnings ride along on the same cost-estimate
    // response costEstimate already carries (useCostEstimate spreads the
    // whole payload through), so no separate fetch is needed here.
    const lastActual = costStatus === 'ready' && costEstimate ? costEstimate.last_actual : null;
    const warningsList = costStatus === 'ready' && costEstimate && Array.isArray(costEstimate.warnings)
        ? costEstimate.warnings
        : [];

    const defaultBudget = parseDefaultBudgetFromWarnings(warningsList);
    const displayedBudgetInput = budgetInput !== null
        ? budgetInput
        : (defaultBudget != null ? String(defaultBudget) : '');
    const parsedBudget = displayedBudgetInput !== '' && !Number.isNaN(Number(displayedBudgetInput))
        ? Number(displayedBudgetInput)
        : null;

    // A budget more than 3x the last measured run for this scope gets a
    // confirmation, same as checking "No budget" - both are ways to start
    // a scan with a much higher ceiling than the evidence on hand supports.
    const overThreeXRatio = (!noBudget && parsedBudget != null && lastActual && lastActual.cost_usd > 0
        && parsedBudget > 3 * lastActual.cost_usd)
        ? parsedBudget / lastActual.cost_usd
        : null;
    const needsConfirm = noBudget || overThreeXRatio != null;

    const handleBudgetInputChange = (event) => {
        setBudgetInput(event.target.value);
        setConfirmPending(false);
    };

    const handleNoBudgetChange = (event) => {
        setNoBudget(event.target.checked);
        setConfirmPending(false);
    };

    const handleStartClick = () => {
        if (needsConfirm && !confirmPending) {
            setConfirmPending(true);
            return;
        }
        setConfirmPending(false);
        onScan({
            budget_usd: noBudget ? null : parsedBudget,
            no_budget: noBudget,
        });
    };

    // WP-28: "Where will this search?" - the resolved source list for the
    // current selection, fetched lazily (only once the note is opened).
    const scopePreview = useScopePreview({ selectedRegions, active: isScopePreviewActive });

    return (
        <div className="domain-scan" aria-label="Domain scan">
            <div>
                <div className="settings-heading-panel">
                    <div className="settings-heading-row">
                        <h2 className="panel-heading">Search Government Sources</h2>
                    </div>
                    <p className="text-block-small">Choose countries or regions to search for policies.</p>
                </div>

                <div className="region-selector-scroll">
                    <RegionSelector
                        selectedItems={selectedRegions}
                        onSelectionChange={onSelectionChange}
                    />
                </div>
                <ModeSelector
                    value={mode}
                    onChange={onModeChange}
                    hasScope={hasScope}
                    standardEstimate={standardEstimate}
                    deepEstimate={deepEstimate}
                />
                <HelpNote label="Which depth should I pick?" className="mode-help-note">
                    <p>
                        Standard is right for routine checking - it visits the government sites
                        already on the watch list and spots new or changed policies. Discover casts
                        a wider net: it searches the web for government sites we don&apos;t watch yet
                        and adds what it finds, so use it when coverage of a place feels thin. Deep
                        rereads every page of the watched sites more thoroughly and costs several
                        times more - save it for when you suspect something was missed. The price on
                        each card updates as you change your selection.
                    </p>
                </HelpNote>
                <div className="channels-group" role="group" aria-label="Sources to check">
                    <p className="text-block-small channels-heading">Sources to check</p>
                    <FormGroup row>
                        {CHANNEL_OPTIONS.map((option) => (
                            <FormControlLabel
                                key={option.id}
                                control={
                                    <Checkbox
                                        size="small"
                                        checked={channels.includes(option.id)}
                                        onChange={(event) => handleChannelToggle(option.id, event.target.checked)}
                                    />
                                }
                                label={option.label}
                            />
                        ))}
                    </FormGroup>
                    <p className="text-block-small">
                        Law databases and transposition checks are free data sources; website crawling is
                        the main driver of scan cost.
                    </p>
                </div>
                <Tooltip title="Please note that this is only an estimate and may not reflect the actual cost" placement="top" arrow>
                    <output className={`cost-estimate ${costStatus}`} aria-live="polite">
                        {costEstimateText}
                    </output>
                </Tooltip>
                {lastActual && (
                    <p className="last-actual-line">
                        {`Last measured run of this scope: ${formatUsd(lastActual.cost_usd)} on `
                            + `${formatHumanDate(lastActual.completed_at)}, ${lastActual.domains_scanned} `
                            + `sources, ${lastActual.policies_found} policies`}
                    </p>
                )}
                {warningsList.length > 0 && (
                    <div className="cost-warnings">
                        {warningsList.map((sentence) => (
                            <p key={sentence} className="cost-warning-line" role="status">{sentence}</p>
                        ))}
                    </div>
                )}
            </div>
            <div className="scan-decision">
                <p className="scan-scope-summary" aria-live="polite">{scanScopeSummary}</p>
                {hasCostBreakdown && (
                    <HelpNote label="Why this price?" className="cost-breakdown">
                        <ul className="cost-breakdown-channels">
                            {channelEntries.map(([channelId, channel]) => (
                                <li key={channelId}>{channelBreakdownLine(channelId, channel)}</li>
                            ))}
                        </ul>
                        <p className="cost-breakdown-auditor">
                            Report generation: {formatUsd(costEstimate.auditor_cost_usd)}
                        </p>
                        {Array.isArray(costEstimate.assumptions) && costEstimate.assumptions.length > 0 && (
                            <div className="cost-breakdown-assumptions">
                                <p className="cost-breakdown-assumptions-heading">What we assumed</p>
                                <ul>
                                    {costEstimate.assumptions.map((assumption) => (
                                        <li key={assumption}>{assumption}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        <HelpNote label="See it as a picture" className="cost-funnel-note">
                            <CostFunnelDiagram estimate={costEstimate} />
                        </HelpNote>
                    </HelpNote>
                )}
                {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events */}
                <div className="scope-preview-area" onClick={handleScopePreviewAreaClick}>
                    <HelpNote label="Where will this search?" className="scope-preview">
                        {scopePreview.status === 'empty' && (
                            <p>Pick a place or sources first.</p>
                        )}
                        {scopePreview.status === 'loading' && (
                            <p>Loading sources...</p>
                        )}
                        {scopePreview.status === 'error' && (
                            <p>Could not load the source list.</p>
                        )}
                        {scopePreview.status === 'ready' && (
                            <>
                                {scopePreview.groups.map((group) => (
                                    <div key={group.id} className="scope-preview-group">
                                        <p className="scope-preview-group-heading">
                                            <span>{group.label} ({group.entries.length})</span>
                                            <InfoHotspot label={`More about ${group.label}`}>
                                                {CHANNEL_HOTSPOT_TEXT[group.id]}
                                            </InfoHotspot>
                                        </p>
                                        <ul>
                                            {group.entries.map((entry) => (
                                                <li key={entry.id}>{entry.name} - {entry.region}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ))}
                                <p className="scope-preview-total">
                                    {scopePreview.totalCount} source{scopePreview.totalCount === 1 ? '' : 's'} total
                                </p>
                            </>
                        )}
                    </HelpNote>
                </div>
                <div className="budget-control">
                    <label htmlFor="scan-budget-usd">Budget (USD)</label>
                    <input
                        id="scan-budget-usd"
                        className="budget-input"
                        type="number"
                        min="0"
                        step="0.01"
                        value={displayedBudgetInput}
                        onChange={handleBudgetInputChange}
                        disabled={noBudget}
                    />
                    <FormControlLabel
                        control={(
                            <Checkbox
                                size="small"
                                checked={noBudget}
                                onChange={handleNoBudgetChange}
                            />
                        )}
                        label="No budget (run uncapped)"
                    />
                </div>
                {confirmPending && (
                    <p className="budget-confirm" role="alert">
                        {noBudget
                            ? 'This run has no cost cap. Start anyway?'
                            : `This budget is ${overThreeXRatio.toFixed(1)}x the last measured run. Start anyway?`}
                    </p>
                )}
                <div className="agent-action-row">
                    <button
                        type="button"
                        className="scan-button button"
                        onClick={handleStartClick}
                        disabled={isBusy || selectedRegions.length === 0 || !hasApiKey}
                    >
                        {isQueueRunning
                            ? `Queued (${queuedScanCount})`
                            : isScanRequestRunning || isScanRunning ? 'Scan running' : 'Scan'}
                    </button>
                    <button
                        type="button"
                        className="stop-scan-button button"
                        onClick={onStop}
                        disabled={!isScanRunning && !isQueueRunning && !isScanRequestRunning}
                    >
                        Stop scan
                    </button>
                </div>
                {Array.isArray(funnelSummary) && funnelSummary.length > 0 && (
                    <div className="funnel-summary">
                        <p className="funnel-summary-heading">What happened</p>
                        <ul>
                            {funnelSummary.map((sentence) => (
                                <li key={sentence}>{sentence}</li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
            {!hasApiKey && (
                <p className="text-block-small">
                    Add an Anthropic API key in Settings to enable scanning.
                </p>
            )}
        </div>
    );
}

export default DomainScanPanel;
