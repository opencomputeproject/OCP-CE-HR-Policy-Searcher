import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminSignInDialog from './AdminSignInDialog';
import { getAdminToken, setAdminToken } from '../utils/adminAuth';

afterEach(() => {
    window.sessionStorage.clear();
});

describe('AdminSignInDialog', () => {
    it('renders nothing when closed', () => {
        const { container } = render(<AdminSignInDialog open={false} onClose={jest.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('renders the passphrase field and explanatory sentence, with no sign-out button', () => {
        render(<AdminSignInDialog open onClose={jest.fn()} />);

        expect(screen.getByText('Admin sign-in')).toBeInTheDocument();
        expect(screen.getByLabelText('Admin passphrase')).toBeInTheDocument();
        expect(screen.getByText(
            /Set by the server operator via the ADMIN_TOKEN environment variable/,
        )).toBeInTheDocument();
        expect(screen.getByText('Save')).toBeInTheDocument();
        expect(screen.getByText('Cancel')).toBeInTheDocument();
        expect(screen.queryByText('Sign out')).not.toBeInTheDocument();
    });

    it('saves the entered passphrase, notifies the caller, and closes', () => {
        const onAdminTokenChange = jest.fn();
        const onClose = jest.fn();
        render(<AdminSignInDialog open onClose={onClose} onAdminTokenChange={onAdminTokenChange} />);

        fireEvent.change(screen.getByLabelText('Admin passphrase'), {
            target: { value: 'secret-passphrase' },
        });
        fireEvent.click(screen.getByText('Save'));

        expect(getAdminToken()).toBe('secret-passphrase');
        expect(onAdminTokenChange).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('discards the typed value on cancel without storing a token', () => {
        const onClose = jest.fn();
        render(<AdminSignInDialog open onClose={onClose} />);

        fireEvent.change(screen.getByLabelText('Admin passphrase'), {
            target: { value: 'not-saved' },
        });
        fireEvent.click(screen.getByText('Cancel'));

        expect(getAdminToken()).toBe('');
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('offers sign-out when a token is already stored, and clears it', () => {
        setAdminToken('existing-token');
        const onAdminTokenChange = jest.fn();
        render(<AdminSignInDialog open onClose={jest.fn()} onAdminTokenChange={onAdminTokenChange} />);

        expect(screen.getByLabelText('Admin passphrase')).toHaveValue('existing-token');
        const signOutButton = screen.getByText('Sign out');

        fireEvent.click(signOutButton);

        expect(getAdminToken()).toBe('');
        expect(onAdminTokenChange).toHaveBeenCalledTimes(1);
        expect(screen.queryByText('Sign out')).not.toBeInTheDocument();
    });
});
