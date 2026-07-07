import { buildTreeData, formatLabel, isHiddenGroup } from './RegionSelector';

describe('isHiddenGroup', () => {
  it('hides internal QA groups', () => {
    for (const id of ['test', 'test_new', 'test_eu_expansion', 'sample_nordic', 'sample_apac']) {
      expect(isHiddenGroup(id)).toBe(true);
    }
  });

  it('keeps real groups, including names containing but not starting with test', () => {
    for (const id of ['all', 'eu', 'nordic', 'us_states', 'contest', 'latest_laws']) {
      expect(isHiddenGroup(id)).toBe(false);
    }
  });
});

describe('formatLabel', () => {
  it('uses overrides for known abbreviations', () => {
    expect(formatLabel('eu')).toBe('EU');
    expect(formatLabel('us')).toBe('United States');
  });

  it('title-cases snake_case ids', () => {
    expect(formatLabel('pending_legislation')).toBe('Pending Legislation');
  });
});

describe('buildTreeData', () => {
  const groups = {
    nordic: 'Nordic countries',
    test_new: 'internal',
    all: 'Everything',
    eu: 'European Union',
    sample_apac: 'internal',
  };
  const groupDomains = {
    nordic: [{ region: ['sweden'] }, { region: ['sweden', 'nordic'] }],
    all: [],
    eu: [],
  };

  it('excludes hidden groups from the tree', () => {
    const tree = buildTreeData({ groups, groupDomains, regions: {} });
    const ids = tree.map((item) => item.id);
    expect(ids).not.toContain('group:test_new');
    expect(ids).not.toContain('group:sample_apac');
    expect(ids).toHaveLength(3);
  });

  it('pins the all group first, remaining groups alphabetical', () => {
    const tree = buildTreeData({ groups, groupDomains, regions: {} });
    expect(tree.map((item) => item.id)).toEqual(['group:all', 'group:eu', 'group:nordic']);
  });

  it('sorts region children and includes domain counts', () => {
    const tree = buildTreeData({ groups, groupDomains, regions: {} });
    const nordic = tree.find((item) => item.id === 'group:nordic');
    expect(nordic.children.map((c) => c.label)).toEqual(['Nordic (1)', 'Sweden (2)']);
  });
});
