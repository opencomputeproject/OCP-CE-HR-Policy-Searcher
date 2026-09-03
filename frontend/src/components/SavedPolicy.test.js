import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import SavedPolicy from './SavedPolicy';

function policy(overrides = {}) {
    return {
        policy_name: 'Heat Reuse Act',
        jurisdiction: 'Sweden',
        policy_type: 'law',
        relevance_score: 7,
        summary: 'A summary',
        review_status: 'new',
        scan_id: 'scan-12345',
        domain_id: 'de-federal-heat',
        crawl_status: 'success',
        ...overrides,
    };
}

function expandCard() {
    fireEvent.click(screen.getByRole('button', { name: /Heat Reuse Act/ }));
}

describe('SavedPolicy review status badge', () => {
    it('shows "new" as a friendly awaiting-review label', () => {
        render(<SavedPolicy policy={policy({ review_status: 'new' })} tags={{}} />);
        expect(screen.getByText(/awaiting review/i)).toBeInTheDocument();
        expect(screen.queryByText('new')).not.toBeInTheDocument();
    });

    it('shows "promoted" as a friendly reviewed label', () => {
        render(<SavedPolicy policy={policy({ review_status: 'promoted' })} tags={{}} />);
        expect(screen.getByText(/reviewed/i)).toBeInTheDocument();
        expect(screen.queryByText('promoted')).not.toBeInTheDocument();
    });

    it('shows "reviewed" as-is', () => {
        render(<SavedPolicy policy={policy({ review_status: 'reviewed' })} tags={{}} />);
        expect(screen.getByText(/reviewed/i)).toBeInTheDocument();
    });

    it('falls back to the raw status for an unrecognized value', () => {
        render(<SavedPolicy policy={policy({ review_status: 'archived' })} tags={{}} />);
        expect(screen.getByText('archived')).toBeInTheDocument();
    });
});

describe('SavedPolicy pipeline meta (Scan ID / Domain ID / Crawl Status)', () => {
    it('hides pipeline internals from a public (non-admin) viewer', () => {
        render(<SavedPolicy policy={policy()} tags={{}} />);
        expandCard();

        expect(screen.queryByText('Scan ID:')).not.toBeInTheDocument();
        expect(screen.queryByText('Domain ID:')).not.toBeInTheDocument();
        expect(screen.queryByText('Crawl Status:')).not.toBeInTheDocument();
        expect(screen.queryByText('scan-12345')).not.toBeInTheDocument();
    });

    it('shows pipeline internals to an admin viewer', () => {
        render(<SavedPolicy policy={policy()} tags={{}} isAdmin />);
        expandCard();

        expect(screen.getByText('Scan ID:')).toBeInTheDocument();
        expect(screen.getByText('scan-12345')).toBeInTheDocument();
        expect(screen.getByText('Domain ID:')).toBeInTheDocument();
        expect(screen.getByText('de-federal-heat')).toBeInTheDocument();
        expect(screen.getByText('Crawl Status:')).toBeInTheDocument();
        expect(screen.getByText('success')).toBeInTheDocument();
    });

    it('defaults to hidden when isAdmin is not passed at all', () => {
        render(<SavedPolicy policy={policy()} tags={{}} />);
        expandCard();
        expect(screen.queryByText('Scan ID:')).not.toBeInTheDocument();
    });
});

describe('SavedPolicy relevance chip on curated records', () => {
    it('shows the numeric score and "relevance" label for a normal scored record', () => {
        render(<SavedPolicy policy={policy({ relevance_score: 7 })} tags={{}} />);
        expect(screen.getByText('7')).toBeInTheDocument();
        expect(screen.getByText('relevance')).toBeInTheDocument();
        expect(screen.queryByText('Curated')).not.toBeInTheDocument();
    });

    it('shows "Curated" instead of "0 relevance" for a curated master record', () => {
        render(<SavedPolicy policy={policy({ domain_id: 'curated_master_tab', relevance_score: 0 })} tags={{}} />);
        expect(screen.getByText('Curated')).toBeInTheDocument();
        expect(screen.queryByText('0')).not.toBeInTheDocument();
        expect(screen.queryByText('relevance')).not.toBeInTheDocument();
    });

    it('shows "Curated" for a curated master record with no relevance_score at all', () => {
        const curatedPolicy = policy({ domain_id: 'curated_master_tab' });
        delete curatedPolicy.relevance_score;
        render(<SavedPolicy policy={curatedPolicy} tags={{}} />);
        expect(screen.getByText('Curated')).toBeInTheDocument();
    });

    it('shows "Curated" for any record with a falsy relevance_score, even outside the curated domain', () => {
        // Judgment call: relevance_score 0/null reads as "hand-verified, no
        // score applies" everywhere, not just on curated_master_tab records -
        // see the fix report for the product-decision note on this heuristic.
        render(<SavedPolicy policy={policy({ domain_id: 'de-federal-heat', relevance_score: 0 })} tags={{}} />);
        expect(screen.getByText('Curated')).toBeInTheDocument();
    });
});

describe('SavedPolicy English title (WP-35)', () => {
    it('leads with policy_name_en and shows the original name beneath when present and different', () => {
        const { container } = render(
            <SavedPolicy
                policy={policy({
                    policy_name: 'Energiewendegesetz',
                    policy_name_en: 'Energy Transition Act',
                })}
                tags={{}}
            />
        );
        expect(screen.getByText('Energy Transition Act')).toBeInTheDocument();
        const originalName = container.querySelector('.original-name');
        expect(originalName).toBeInTheDocument();
        expect(originalName).toHaveTextContent('Energiewendegesetz');
    });

    it('renders exactly as today when policy_name_en is absent', () => {
        const { container } = render(
            <SavedPolicy policy={policy({ policy_name: 'Heat Reuse Act' })} tags={{}} />
        );
        expect(screen.getByText('Heat Reuse Act')).toBeInTheDocument();
        expect(container.querySelector('.original-name')).not.toBeInTheDocument();
    });

    it('shows no original-name line when policy_name_en is identical to policy_name', () => {
        const { container } = render(
            <SavedPolicy
                policy={policy({
                    policy_name: 'Data Center Efficiency Act',
                    policy_name_en: 'Data Center Efficiency Act',
                })}
                tags={{}}
            />
        );
        expect(screen.getByText('Data Center Efficiency Act')).toBeInTheDocument();
        expect(container.querySelector('.original-name')).not.toBeInTheDocument();
    });
});

describe('SavedPolicy Read in English link (WP-9b)', () => {
    function dualLanguagePolicy(overrides = {}) {
        return policy({
            url: 'https://wetten.overheid.nl/wet-collectieve-warmte',
            source_language: 'nl',
            policy_name: 'Wet collectieve warmte',
            policy_name_en: 'Collective Heat Act',
            read_in_english_url: 'https://example.translate.goog/wet-collectieve-warmte',
            ...overrides,
        });
    }

    function expandDualLanguageCard() {
        fireEvent.click(screen.getByRole('button', { name: /Collective Heat Act/ }));
    }

    it('renders the English name, the original name, and a Read in English link when read_in_english_url is present', () => {
        const { container } = render(<SavedPolicy policy={dualLanguagePolicy()} tags={{}} />);

        expect(screen.getByText('Collective Heat Act')).toBeInTheDocument();
        const originalName = container.querySelector('.original-name');
        expect(originalName).toBeInTheDocument();
        expect(originalName).toHaveTextContent('Wet collectieve warmte');

        expandDualLanguageCard();

        const readLink = screen.getByRole('link', { name: 'Read in English' });
        expect(readLink).toHaveAttribute(
            'href', 'https://example.translate.goog/wet-collectieve-warmte',
        );
        expect(readLink).toHaveAttribute('target', '_blank');
        expect(readLink).toHaveAttribute('rel', 'noopener noreferrer');
        expect(readLink).toHaveAttribute(
            'title',
            'Machine translation of the original page by Google Translate. '
            + 'The original link stays the link of record.',
        );
    });

    it('keeps the original View Full Policy link unchanged alongside the new one', () => {
        render(<SavedPolicy policy={dualLanguagePolicy()} tags={{}} />);
        expandDualLanguageCard();

        const viewLink = screen.getByRole('link', { name: 'View Full Policy' });
        expect(viewLink).toHaveAttribute('href', 'https://wetten.overheid.nl/wet-collectieve-warmte');
    });

    it('renders no Read in English link when read_in_english_url is null', () => {
        render(<SavedPolicy policy={dualLanguagePolicy({ read_in_english_url: null })} tags={{}} />);
        expandDualLanguageCard();

        expect(screen.queryByRole('link', { name: 'Read in English' })).not.toBeInTheDocument();
    });

    it('renders no Read in English link when read_in_english_url is absent', () => {
        const policyWithoutField = dualLanguagePolicy();
        delete policyWithoutField.read_in_english_url;
        render(<SavedPolicy policy={policyWithoutField} tags={{}} />);
        expandDualLanguageCard();

        expect(screen.queryByRole('link', { name: 'Read in English' })).not.toBeInTheDocument();
    });

    it('shows the name once when policy_name_en equals policy_name, but still shows the Read in English link', () => {
        render(
            <SavedPolicy
                policy={dualLanguagePolicy({ policy_name_en: 'Wet collectieve warmte' })}
                tags={{}}
            />
        );
        expect(screen.getByText('Wet collectieve warmte')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: /Wet collectieve warmte/ }));
        expect(screen.getByRole('link', { name: 'Read in English' })).toHaveAttribute(
            'href', 'https://example.translate.goog/wet-collectieve-warmte',
        );
    });
});
