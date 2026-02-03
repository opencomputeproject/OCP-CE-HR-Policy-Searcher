# UK Legislative Systems - Policy Tracker Configuration
## Grid Cell 1.2 | Generated: 2026-01-06

This configuration covers UK Parliament bill trackers, legislation databases, devolved legislature systems (Scotland, Wales, Northern Ireland), and the official gazette for tracking data center heat reuse and energy efficiency legislation.

---

## Summary

| Site | Category | JavaScript Required | Key Content |
|------|----------|---------------------|-------------|
| UK Parliament Bills | Westminster | Yes | Energy Act 2023, Great British Energy Act |
| Statutory Instruments | Westminster | Yes | Heat Networks Regulations 2025 |
| legislation.gov.uk | National Archives | No | All enacted UK legislation |
| Hansard | Westminster | Yes | Parliamentary debates |
| Scottish Parliament | Devolved | No | Heat Networks (Scotland) Act 2021 |
| Welsh Senedd | Devolved | No | Legislative Consent Memoranda |
| NI Assembly | Devolved | No | Climate Change Act (NI) 2022 |
| The Gazette | Official Record | No | Statutory notices |

---

## YAML Configuration

```yaml
# UK - Legislative Systems
# Generated: 2026-01-06
# Grid Cell: 1.2

# ============================================
# WESTMINSTER PARLIAMENT
# ============================================

- name: UK Parliament Bills Tracker
  id: uk_parliament_bills
  enabled: true
  base_url: https://bills.parliament.uk
  start_paths:
    - /bills
    - /bills?SearchTerm=energy
    - /bills?SearchTerm=heat
    - /bills?SearchTerm=climate
    - /bills?SearchTerm=data+centre
  allowed_path_patterns:
    - /bills/*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - bills
    - primary_legislation
    - parliamentary_progress
  policy_types:
    - law
    - regulation
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Official UK Parliament bill tracker showing progress of all bills through 
    Westminster. Key energy legislation tracked here includes Energy Act 2023
    (heat network zoning powers), Great British Energy Act 2025, and Climate
    Change Act amendments. Requires JavaScript for full functionality.
    Search for "energy", "heat", "climate", "data centre" (UK spelling).

- name: UK Parliament Statutory Instruments Tracker
  id: uk_parliament_si
  enabled: true
  base_url: https://statutoryinstruments.parliament.uk
  start_paths:
    - /
    - /instrument
    - /instruments?LayingBody=Department%20for%20Energy%20Security%20and%20Net%20Zero
  allowed_path_patterns:
    - /instrument/*
    - /instruments/*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - secondary_legislation
    - statutory_instruments
    - regulations
  policy_types:
    - regulation
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Tracks Statutory Instruments (secondary legislation) laid before Parliament.
    Critical for heat network regulations - Heat Networks (Market Framework)
    (Great Britain) Regulations 2025 published here. Filter by DESNZ as
    laying body for energy-related SIs. Requires JavaScript.

- name: UK Legislation Database (National Archives)
  id: uk_legislation
  enabled: true
  base_url: https://www.legislation.gov.uk
  start_paths:
    - /ukpga/2023/52  # Energy Act 2023
    - /ukpga/2008/27  # Climate Change Act 2008
    - /asp/2021/9     # Heat Networks (Scotland) Act 2021
    - /uksi/2014/3120 # Heat Network Metering Regulations
    - /uksi/2025/269  # Heat Networks Market Framework Regs 2025
    - /new/uk
    - /changes/affected/ukpga/2023/52
  allowed_path_patterns:
    - /ukpga/*
    - /uksi/*
    - /asp/*
    - /anaw/*
    - /nia/*
    - /ssi/*
    - /new/*
    - /changes/*
  blocked_path_patterns:
    - /*/data.xml
    - /*/data.rdf
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - enacted_legislation
    - primary_legislation
    - secondary_legislation
    - consolidated_law
  policy_types:
    - law
    - regulation
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Official repository of all UK legislation maintained by National Archives.
    Includes primary legislation (Acts of Parliament), secondary legislation
    (Statutory Instruments), and devolved legislation. Shows "as enacted"
    and "revised" versions with tracked changes. Key legislation:
    Energy Act 2023 (ukpga/2023/52), Climate Change Act 2008, Heat Networks
    (Scotland) Act 2021. Server-rendered HTML, no JavaScript required.
    API available for structured data access.

- name: UK Parliament Hansard
  id: uk_parliament_hansard
  enabled: true
  base_url: https://hansard.parliament.uk
  start_paths:
    - /search?searchTerm=heat+networks
    - /search?searchTerm=data+centre+energy
    - /search?searchTerm=waste+heat
    - /debates
  allowed_path_patterns:
    - /commons/*
    - /lords/*
    - /search*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - parliamentary_debates
    - hansard
    - ministerial_statements
  policy_types:
    - guidance
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Official record of Parliamentary debates (Commons and Lords). Useful for
    tracking ministerial statements on heat network policy, committee stage
    debates on energy bills, and questions to ministers. Heat Networks
    (Market Framework) Regulations 2025 debated 3 Feb 2025. Requires JavaScript.

# ============================================
# SCOTTISH PARLIAMENT
# ============================================

- name: Scottish Parliament Bills and Laws
  id: uk_scotland_parliament
  enabled: true
  base_url: https://www.parliament.scot
  start_paths:
    - /bills-and-laws/bills
    - /bills-and-laws/bills/heat-networks-scotland-bill
    - /chamber-and-committees/committees/current-and-previous-committees/session-6-net-zero-energy-and-transport-committee
    - /chamber-and-committees/official-report/search-what-was-said-in-parliament
  allowed_path_patterns:
    - /bills-and-laws/*
    - /chamber-and-committees/*
  blocked_path_patterns:
    - /-/media/*
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - scottish_legislation
    - devolved_powers
    - heat_networks
    - net_zero
  policy_types:
    - law
    - regulation
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Scottish Parliament has significant devolved powers over energy efficiency
    and heat networks. Key legislation: Heat Networks (Scotland) Act 2021
    (UK's first heat network law), upcoming Heat in Buildings Bill (announced
    2024). Net Zero, Energy and Transport Committee scrutinizes energy policy.
    Scotland targets net zero by 2045 (5 years ahead of UK). Server-rendered.

- name: Scottish Parliament Digital Publications
  id: uk_scotland_spice
  enabled: true
  base_url: https://digitalpublications.parliament.scot
  start_paths:
    - /ResearchBriefings
    - /ResearchBriefings?subject=Energy
    - /ResearchBriefings?subject=Climate+Change
  allowed_path_patterns:
    - /ResearchBriefings/*
  blocked_path_patterns:
    - /*/pdf/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - research_briefings
    - spice
    - policy_analysis
  policy_types:
    - report
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    SPICe (Scottish Parliament Information Centre) research briefings.
    Publishes detailed analysis of Scottish legislation including Heat
    Networks (Scotland) Bill briefing. Useful for understanding policy
    intent and implementation details.

# ============================================
# WELSH SENEDD
# ============================================

- name: Welsh Senedd Business
  id: uk_wales_senedd
  enabled: true
  base_url: https://business.senedd.wales
  start_paths:
    - /mgIssueHistoryHome.aspx?IId=41603  # Energy Bill LCM
    - /mgIssueHistoryHome.aspx?IId=44266  # Great British Energy Bill LCM
    - /mgListCommittees.aspx
  allowed_path_patterns:
    - /mgIssueHistoryHome.aspx*
    - /mgCommitteeDetails.aspx*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - welsh_legislation
    - legislative_consent
    - devolved_powers
  policy_types:
    - law
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Welsh Senedd business tracking including Legislative Consent Memoranda
    for UK bills affecting Wales. Climate Change, Environment and Infrastructure
    Committee handles energy legislation. Wales has devolved building regulations
    and some energy efficiency powers. Net zero target 2050 (statutory).
    Bilingual site (Welsh/English). Some pages require JavaScript.

- name: Senedd Research
  id: uk_wales_senedd_research
  enabled: true
  base_url: https://research.senedd.wales
  start_paths:
    - /research-articles
    - /research-articles/?topics=energy
    - /research-articles/?topics=climate-change
    - /research-articles/?topics=environment
  allowed_path_patterns:
    - /research-articles/*
  blocked_path_patterns:
    - /*/pdf/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - research_briefings
    - policy_analysis
    - wales
  policy_types:
    - report
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Research briefings from Senedd Research service. Covers Welsh Government
    legislative programme, energy policy analysis, and UK-EU TCA environment
    and energy implications. Good for tracking upcoming Welsh legislation.

# ============================================
# NORTHERN IRELAND ASSEMBLY
# ============================================

- name: Northern Ireland Assembly Legislation
  id: uk_ni_assembly
  enabled: true
  base_url: https://www.niassembly.gov.uk
  start_paths:
    - /assembly-business/legislation/
    - /assembly-business/legislation/2022-2027-mandate/primary-legislation-bills-22-27-mandate/
    - /assembly-business/committees/2022-2027-mandate/committee-for-the-economy/
  allowed_path_patterns:
    - /assembly-business/legislation/*
    - /assembly-business/committees/*
  blocked_path_patterns:
    - /globalassets/*
    - /*/pdf/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - northern_ireland_legislation
    - devolved_powers
    - energy_policy
  policy_types:
    - law
    - regulation
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Northern Ireland Assembly bill tracker. Committee for the Economy handles
    energy legislation. NI has Climate Change Act (Northern Ireland) 2022
    with 80% renewable electricity target by 2030 (statutory). Shares
    all-island Single Electricity Market with Republic of Ireland. Some EU
    energy regulations continue to apply under Windsor Framework. Drupal-based,
    server-rendered.

- name: Northern Ireland Assembly Archive
  id: uk_ni_assembly_archive
  enabled: true
  base_url: https://archive.niassembly.gov.uk
  start_paths:
    - /legislation/
    - /legislation/primary/
  allowed_path_patterns:
    - /legislation/*
  blocked_path_patterns:
    - /*/pdf/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - historical_legislation
    - northern_ireland
  policy_types:
    - law
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Archive of historical NI Assembly legislation. Energy Bill and related
    historical legislation available here. Useful for tracing policy evolution.

# ============================================
# OFFICIAL GAZETTE
# ============================================

- name: The Gazette (Official Public Record)
  id: uk_gazette
  enabled: true
  base_url: https://www.thegazette.co.uk
  start_paths:
    - /all-notices
    - /all-notices?noticetypes=Energy
    - /all-notices?noticetypes=Environment
    - /all-notices?text=heat+network
    - /all-notices?text=data+centre
  allowed_path_patterns:
    - /all-notices*
    - /notice/*
  blocked_path_patterns:
    - /place-notice/*
    - /my-gazette/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: legislative
  tags:
    - official_gazette
    - statutory_notices
    - public_record
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    UK's official public record since 1665. Combines London Gazette, Edinburgh
    Gazette, and Belfast Gazette. Publishes statutory notices required by law
    including energy infrastructure notices (Electricity Act 1989, s.36 consents),
    planning notices, and transport/highways notices. Over 450 notice types.
    Free to search. Notice codes 2103 (Electricity) relevant for energy projects.
    Server-rendered, no JavaScript required.
```

---

## Sites Evaluated But Not Recommended

```yaml
# EVALUATED - NOT RECOMMENDED

- name: House of Commons Library
  url: https://commonslibrary.parliament.uk
  region: UK
  topic: Legislative Systems
  reason_excluded: |
    Secondary analysis/research briefings, not primary legislation or policy.
    Useful for background research but duplicates information available from
    primary sources (bills.parliament.uk, legislation.gov.uk). Would add
    overhead without unique policy content.
  checked_date: "2026-01-06"
  reconsider_if: "Need policy analysis/explainers rather than raw legislation"

- name: House of Lords Library
  url: https://lordslibrary.parliament.uk
  region: UK
  topic: Legislative Systems
  reason_excluded: |
    Same as Commons Library - secondary analysis rather than primary legislation.
  checked_date: "2026-01-06"

- name: UK Parliament Publications
  url: https://publications.parliament.uk
  region: UK
  topic: Legislative Systems
  reason_excluded: |
    Older system being replaced by bills.parliament.uk. Still hosts some PDFs
    but bills tracker is more comprehensive and current.
  checked_date: "2026-01-06"

- name: Scottish Government Legislation Pages
  url: https://www.gov.scot/policies/legislation/
  region: UK
  topic: Legislative Systems
  reason_excluded: |
    Covered under Grid Cell 1.1 (Energy Ministries). parliament.scot is the
    primary source for Scottish legislation tracking.
  checked_date: "2026-01-06"

- name: UK Government Publications
  url: https://www.gov.uk/government/publications
  region: UK
  topic: Legislative Systems
  reason_excluded: |
    Covered under Grid Cell 1.1 (Energy Ministries). Would duplicate DESNZ
    entries.
  checked_date: "2026-01-06"
```

---

## Research Notes

### Key Patterns Discovered

1. **JavaScript Requirements**: Westminster Parliament sites (bills.parliament.uk, statutoryinstruments.parliament.uk, hansard.parliament.uk) require Playwright for full functionality. Devolved legislature sites are mostly server-rendered.

2. **Legislation Flow**: UK legislation follows this path:
   - Bill → Act (published on legislation.gov.uk) → Statutory Instruments (detailed regulations)
   - For heat networks: Energy Act 2023 → Heat Networks (Market Framework) Regulations 2025

3. **Devolved Differences**: 
   | Nation | Key Powers | Notable Legislation |
   |--------|-----------|---------------------|
   | Scotland | Heat networks, energy efficiency, building regs | Heat Networks (Scotland) Act 2021 |
   | Wales | Building regulations, some energy efficiency | Legislative Consent process for UK bills |
   | Northern Ireland | Energy policy (shared with Ireland) | Climate Change Act (NI) 2022 |

4. **Search Terms**: Use UK spelling **"data centre"** (not "data center") for all UK sites.

5. **The Gazette**: Often overlooked but contains statutory notices for energy infrastructure projects under Electricity Act 1989, Section 36 consents.

### Key Legislation to Track

| Legislation | Reference | Relevance |
|-------------|-----------|-----------|
| Energy Act 2023 | ukpga/2023/52 | Heat network zoning powers, Ofgem as regulator |
| Climate Change Act 2008 | ukpga/2008/27 | Net zero target framework |
| Heat Networks (Scotland) Act 2021 | asp/2021/9 | UK's first heat network law |
| Heat Networks (Market Framework) Regs 2025 | uksi/2025/269 | Ofgem authorization requirements |
| Climate Change Act (NI) 2022 | nia/2022/31 | 80% renewable electricity target |

### Recommendation

Prioritize **legislation.gov.uk** and **bills.parliament.uk** for primary legislation tracking, as they cover all UK jurisdictions with consolidated/tracked changes. The statutory instruments tracker is essential for secondary legislation (where detailed heat network regulations appear).
