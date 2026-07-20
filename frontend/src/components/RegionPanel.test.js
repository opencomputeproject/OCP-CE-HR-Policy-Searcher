import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import RegionPanel from './RegionPanel';

const UNIT_WITH_POLICIES = {
  id: 'BE-BRU', slug: 'belgium-bru', name: 'Brussels', sources: 1, policies: 3,
  topPolicyNames: ['Brussels Heat Directive'], isFederal: false,
};

const FEDERAL_WITH_POLICIES = {
  id: 'federal', slug: 'belgium', name: 'Belgium', sources: 6, policies: 2,
  topPolicyNames: ['Federal Heat Reuse Act'], isFederal: true,
};

const UNIT_NO_POLICIES = {
  id: 'BE-VLG', slug: 'belgium-vlg', name: 'Flanders', sources: 1, policies: 0,
  topPolicyNames: [], isFederal: false,
};

describe('RegionPanel', () => {
  it('leads with "View {n} found policies" for a unit with policies, calling onViewPlacePolicies with slug+name', () => {
    const onViewPlacePolicies = jest.fn();
    render(
      <RegionPanel
        selection={UNIT_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={onViewPlacePolicies}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'View 3 found policies' }));
    expect(onViewPlacePolicies).toHaveBeenCalledWith({ slug: 'belgium-bru', name: 'Brussels' });
  });

  it('the federal selection views policies under the country slug, not a child slug', () => {
    const onViewPlacePolicies = jest.fn();
    render(
      <RegionPanel
        selection={FEDERAL_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={onViewPlacePolicies}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'View 2 found policies' }));
    expect(onViewPlacePolicies).toHaveBeenCalledWith({ slug: 'belgium', name: 'Belgium' });
  });

  it('does not render the view-policies CTA when the unit has zero policies', () => {
    render(
      <RegionPanel
        selection={UNIT_NO_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={jest.fn()}
        onViewPlacePolicies={jest.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /View \d+ found/ })).not.toBeInTheDocument();
  });

  it('the scan action is demoted (link style) and hidden entirely when showScanAction is false', () => {
    const onSearchPlace = jest.fn();
    const { rerender } = render(
      <RegionPanel
        selection={UNIT_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={onSearchPlace}
        onViewPlacePolicies={jest.fn()}
      />,
    );

    const scanButton = screen.getByRole('button', { name: 'Scan Brussels for new policies' });
    expect(scanButton).toHaveClass('wm-panel-cta-link');
    fireEvent.click(scanButton);
    expect(onSearchPlace).toHaveBeenCalledWith('Brussels');

    rerender(
      <RegionPanel
        selection={UNIT_WITH_POLICIES}
        onClose={jest.fn()}
        onSearchPlace={onSearchPlace}
        onViewPlacePolicies={jest.fn()}
        showScanAction={false}
      />,
    );
    expect(screen.queryByRole('button', { name: /Scan/ })).not.toBeInTheDocument();
  });
});
