import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ApiKeySettingsModal from './ApiKeySettingsModal';

const COST_SETTINGS = {
    cost_level: 'standard',
    ask_daily_limit: 50,
    ask_enabled: true,
};

function mockFetch({ hasKey = false } = {}) {
    let exists = hasKey;
    return jest.fn(async (url, options = {}) => {
        const path = String(url);
        if (path.includes('/api/settings/api-key')) {
            if (options.method === 'POST') {
                exists = true;
                return { ok: true, json: async () => ({ exists: true, masked: 'sk-ant-...abcd' }) };
            }
            if (options.method === 'DELETE') {
                exists = false;
                return { ok: true, json: async () => ({ exists: false, masked: null }) };
            }
            return {
                ok: true,
                json: async () => (
                    exists ? { exists: true, masked: 'sk-ant-...abcd' } : { exists: false, masked: null }
                ),
            };
        }
        if (path.includes('/api/settings/costs')) {
            return { ok: true, json: async () => COST_SETTINGS };
        }
        return { ok: false, json: async () => ({}) };
    });
}

afterEach(() => {
    jest.restoreAllMocks();
});

describe('ApiKeySettingsModal', () => {
    it('renders nothing when closed', () => {
        global.fetch = mockFetch();
        const { container } = render(<ApiKeySettingsModal open={false} onClose={jest.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('manages only the Anthropic API key, with no admin token field', async () => {
        global.fetch = mockFetch();
        render(<ApiKeySettingsModal open onClose={jest.fn()} />);

        expect(screen.getByRole('heading', { name: 'Anthropic API key' })).toBeInTheDocument();
        expect(screen.getByText(/stored server-side in \.env/i)).toBeInTheDocument();

        await waitFor(() => {
            expect(screen.getByLabelText('Anthropic API key', { selector: 'input' })).toBeInTheDocument();
        });

        expect(screen.queryByText('Administrator token')).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/admin/i)).not.toBeInTheDocument();
    });

    it('adds a new API key', async () => {
        const fetchMock = mockFetch();
        global.fetch = fetchMock;
        render(<ApiKeySettingsModal open onClose={jest.fn()} />);

        await waitFor(() => {
            expect(screen.getByLabelText('Anthropic API key', { selector: 'input' })).toBeInTheDocument();
        });

        fireEvent.change(screen.getByLabelText('Anthropic API key', { selector: 'input' }), {
            target: { value: 'sk-ant-new-key' },
        });
        fireEvent.click(screen.getByText('Add an API key'));

        await waitFor(() => {
            expect(screen.getByText('API key saved.')).toBeInTheDocument();
        });
        const postCall = fetchMock.mock.calls.find(([, options]) => options?.method === 'POST');
        expect(JSON.parse(postCall[1].body)).toEqual({ api_key: 'sk-ant-new-key' });
    });

    it('shows the masked key and deletes it after confirmation', async () => {
        const fetchMock = mockFetch({ hasKey: true });
        global.fetch = fetchMock;
        render(<ApiKeySettingsModal open onClose={jest.fn()} />);

        await waitFor(() => {
            expect(screen.getByText('sk-ant-...abcd')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('Delete key'));
        expect(screen.getByText(/Deleting this key will disable/)).toBeInTheDocument();

        fireEvent.click(screen.getByText('Confirm delete'));

        await waitFor(() => {
            expect(screen.getByText('API key deleted.')).toBeInTheDocument();
        });
    });

    it('renders cost settings when available', async () => {
        global.fetch = mockFetch();
        render(<ApiKeySettingsModal open onClose={jest.fn()} />);

        await waitFor(() => {
            expect(screen.getByLabelText('Cost level (scans and answers)')).toHaveValue('standard');
        });
        expect(screen.getByLabelText('Reader questions per day')).toHaveValue(50);
    });
});
