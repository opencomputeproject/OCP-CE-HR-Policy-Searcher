import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import CountryPanel from './CountryPanel';

const TRACKED_WITH_POLICIES = {
  id: '840', slug: 'us', name: 'United States', sources: 162, policies: 23,
  topPolicyNames: ['Heat Reuse Act'],
};

const TRACKED_NO_POLICIES = {
  id: '702', slug: 'singapore', name: 'Singapore', sources: 2, policies: 0, topPolicyNames: [],
};

const UNTRACKED = {
  id: '276', slug: 'germany', name: 'Germany', sources: 0, policies: 0, topPolicyNames: [],
};

describe('CountryPanel', () => {
  it('leads with "View {n} found policies" when the place has policies, calling onViewPlacePolicies with slug+name', () => {
    const onViewPlacePolicies = jest.fn();
    render(
      <CountryPanel
        selection={TRACKED_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={onViewPlacePolicies}
      />,
    );

    const viewButton = screen.getByRole('button', { name: 'View 23 found policies' });
    fireEvent.click(viewButton);
    expect(onViewPlacePolicies).toHaveBeenCalledWith({ slug: 'us', name: 'United States' });
  });

  it('does not render the view-policies CTA when the place has zero policies', () => {
    render(
      <CountryPanel
        selection={TRACKED_NO_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={jest.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /View \d+ found/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scan Singapore for new policies' })).toBeInTheDocument();
  });

  it('the scan action is demoted (secondary/link style) and calls onSearchPlace with the place name', () => {
    const onSearchPlace = jest.fn();
    render(
      <CountryPanel
        selection={TRACKED_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={onSearchPlace}
        onViewPlacePolicies={jest.fn()}
      />,
    );

    const scanButton = screen.getByRole('button', { name: 'Scan United States for new policies' });
    expect(scanButton).toHaveClass('wm-panel-cta-link');
    fireEvent.click(scanButton);
    expect(onSearchPlace).toHaveBeenCalledWith('United States');
  });

  it('hides the scan action entirely when showScanAction is false', () => {
    render(
      <CountryPanel
        selection={TRACKED_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={jest.fn()}
        showScanAction={false}
      />,
    );

    expect(screen.getByRole('button', { name: 'View 23 found policies' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Scan/ })).not.toBeInTheDocument();
  });

  it('an untracked place hides the view CTA and, when shown, offers only the scan action', () => {
    render(
      <CountryPanel
        selection={UNTRACKED}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={jest.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /View \d+ found/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scan Germany for new policies' })).toBeInTheDocument();
  });

  it('an untracked place with showScanAction false renders no action button at all', () => {
    render(
      <CountryPanel
        selection={UNTRACKED}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={jest.fn()}
        showScanAction={false}
      />,
    );

    expect(screen.queryByRole('button', { name: /View|Scan/ })).not.toBeInTheDocument();
  });
});
