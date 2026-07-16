import { apiUrl } from '../config/api';

export function splitSelection(items) {
    return {
        categories: items
            .filter((item) => item.startsWith('category:'))
            .map((item) => item.slice('category:'.length)),
        tags: items
            .filter((item) => item.startsWith('tag:'))
            .map((item) => item.slice('tag:'.length)),
        targets: items.filter(
            (item) => !item.startsWith('category:') && !item.startsWith('tag:'),
        ),
    };
}

export function normalizeTarget(item) {
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
}

export function parseDomainTarget(item) {
    if (!item.startsWith('group:') || !item.includes(':region:')) {
        return { group: normalizeTarget(item), region: null };
    }

    const regionMarker = ':region:';
    const markerIndex = item.lastIndexOf(regionMarker);
    return {
        group: item.slice('group:'.length, markerIndex),
        region: item.slice(markerIndex + regionMarker.length),
    };
}

export async function resolveDomainsForTargets(targets) {
    const domainById = new Map();

    await Promise.all(targets.map(async (target) => {
        const { group, region } = parseDomainTarget(target);
        const response = await fetch(
            apiUrl(`/api/domains?group=${encodeURIComponent(group)}`),
        );

        if (!response.ok) {
            throw new Error(`Could not resolve domains for ${group} (${response.status})`);
        }

        const data = await response.json();
        (data.domains || [])
            .filter((domain) => !region || (domain.region || []).includes(region))
            .forEach((domain) => {
                if (domain.id) {
                    domainById.set(domain.id, domain);
                }
            });
    }));

    return [...domainById.values()];
}

export const DEFAULT_CHANNELS = ['crawl', 'law_apis', 'transposition'];

export function buildChannels(selectedChannels) {
    return Array.isArray(selectedChannels) && selectedChannels.length > 0
        ? selectedChannels
        : ['crawl'];
}

export async function buildScanRequests(selectedItems, scanOptions) {
    const { categories, tags, targets } = splitSelection(selectedItems);
    const domainMatchesFilters = (domain) => (
        (!categories[0] || domain.category === categories[0])
        && (tags.length === 0 || tags.some((tag) => (domain.tags || []).includes(tag)))
    );
    const baseRequest = {
        max_concurrent: scanOptions.deep ? 10 : 5,
        skip_llm: false,
        dry_run: false,
        deep: scanOptions.deep,
        discover: scanOptions.discover,
        category: categories[0] || null,
        tags: tags.length > 0 ? tags : null,
        channels: buildChannels(scanOptions.channels),
    };

    // Discovery runs an agent workflow per country, so it stays per-target.
    if (scanOptions.discover) {
        const discoverTargets = targets.map(normalizeTarget);
        return (discoverTargets.length > 0 ? discoverTargets : ['all']).map((target) => ({
            ...baseRequest,
            domains: target,
        }));
    }

    // Everything else is ONE consolidated scan: the backend accepts a
    // comma-separated union, so one intent never fans out into a scan
    // per domain (which looked broken and buried the real results).
    const domainIds = (await resolveDomainsForTargets(targets))
        .filter(domainMatchesFilters)
        .map((domain) => domain.id);

    return [{
        ...baseRequest,
        domains: domainIds.length > 0 ? domainIds.join(',') : 'all',
    }];
}
