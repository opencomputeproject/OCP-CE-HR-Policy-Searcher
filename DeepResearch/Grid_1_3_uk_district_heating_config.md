# UK District Heating - Policy Tracker Configuration
## Grid Cell 1.3 | Generated: 2026-01-06

This configuration covers UK government bodies and programs for district heating and heat networks, including the Heat Networks Delivery Unit, heat network zoning authorities, and funding programs. Includes national UK programs and devolved initiatives in Scotland, Wales, and Northern Ireland.

---

## Summary

| Site | Category | JavaScript Required | Key Content |
|------|----------|---------------------|-------------|
| HNDU | National Funding | No | Heat Networks Delivery Unit - local authority support |
| GHNF | National Funding | No | Green Heat Network Fund - £288M+ capital grants |
| HN Zoning Maps | National Planning | No | Heat network zoning maps for 21 cities |
| HNPD | National Data | No | Heat Networks Planning Database |
| Ofgem Heat Networks | Regulatory | Yes | Heat network regulation from Jan 2026 |
| Heat Trust | Standards | No | Voluntary consumer protection scheme |
| Scotland SHNF | Devolved Funding | No | £300M Scotland's Heat Network Fund |
| Scotland HNSU | Devolved Support | No | Heat Network Support Unit |
| Wales Heat Strategy | Devolved Policy | No | Welsh Government heat decarbonisation |
| Welsh Gov Energy Service | Devolved Support | No | Energy project funding |
| GLA Heat Network | Regional | No | Greater London Authority heat maps |

---

## Key Policy Context

### Regulatory Timeline
- **Energy Act 2023** (26 Oct 2023): Appointed Ofgem as heat networks regulator, enabled heat network zoning in England
- **1 April 2025**: Citizens Advice, Consumer Scotland, Energy Ombudsman assumed statutory roles
- **27 January 2026**: Ofgem assumes regulatory powers; all heat networks deemed temporarily authorised
- **January 2027**: All heat networks must be registered with Ofgem

### Heat Network Zoning
First 6 designated zones (October 2024): Leeds, Plymouth, Bristol, Stockport, Sheffield, London (Old Oak & Park Royal)
- 14 additional areas identified for possible zoning
- Zone coordinators can require buildings to connect to heat networks

### Data Center Heat Projects
- **North Crawley Heat Network**: Gatwick Airport + data center (Digital Realty Manor Royal), 46GWh, construction 2026, operational 2027
- **Old Oak & Park Royal (London)**: Data center waste heat to 9,000+ homes, £36M GHNF grant, potential 25,000 homes

---

## YAML Configuration

```yaml
# UK - District Heating
# Generated: 2026-01-06
# Grid Cell: 1.3

# ============================================
# NATIONAL PROGRAMS - DESNZ
# ============================================

- name: Heat Networks Delivery Unit (HNDU)
  id: uk_hndu
  enabled: true
  base_url: https://www.gov.uk
  start_paths:
    - /guidance/heat-networks-delivery-unit
    - /government/publications/hndu-pipeline
    - /government/publications/heat-networks-delivery-unit-hndu-application-guidance
  allowed_path_patterns:
    - /guidance/heat-networks*
    - /government/publications/hndu*
    - /government/publications/heat-network*
  blocked_path_patterns:
    - /*/print
    - /government/uploads/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - incentives
    - planning
    - local_authority
  policy_types:
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Heat Networks Delivery Unit provides grant funding and guidance to local
    authorities in England and Wales for heat network development. Since 2013,
    has supported 200+ projects across 139+ local authorities. Round 15 open
    until 12 September 2025. Publishes quarterly pipeline documents showing
    all supported projects. Contact: hndu@energysecurity.gov.uk

- name: Green Heat Network Fund (GHNF)
  id: uk_ghnf
  enabled: true
  base_url: https://www.gov.uk
  start_paths:
    - /government/publications/green-heat-network-fund-ghnf
    - /government/collections/green-heat-network-fund
    - /guidance/green-heat-network-fund-ghnf-transition-scheme
  allowed_path_patterns:
    - /government/publications/green-heat-network*
    - /government/collections/green-heat-network*
    - /guidance/green-heat-network*
  blocked_path_patterns:
    - /*/print
    - /government/uploads/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - incentives
    - capital_funding
    - construction
  policy_types:
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Green Heat Network Fund provides commercialisation and capital grants for
    heat networks in England. Initially £288M, additional funding available
    through 2027/2028. Supports public, private, and third sectors. Key projects:
    North Crawley (data center + Gatwick Airport heat, 46GWh), Old Oak & Park
    Royal London (data center waste heat to 9,000+ homes). Transition Scheme
    provides early-stage support.

- name: Heat Network Zoning Maps and Guidance
  id: uk_hn_zoning
  enabled: true
  base_url: https://www.gov.uk
  start_paths:
    - /government/publications/heat-network-zoning
    - /government/publications/heat-network-zoning-maps
    - /government/consultations/proposals-for-heat-network-zoning
  allowed_path_patterns:
    - /government/publications/heat-network-zoning*
    - /government/consultations/*heat-network-zoning*
  blocked_path_patterns:
    - /*/print
    - /government/uploads/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - planning
    - mandates
    - zoning
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Heat Network Zoning enabled by Energy Act 2023. First 6 zones designated
    October 2024: Leeds, Plymouth, Bristol, Stockport, Sheffield, London
    (Old Oak & Park Royal). 14 additional areas identified. Zone coordinators
    can require new developments and large buildings to connect to heat networks.
    Maps published for 21 towns and cities showing areas where heat networks
    are expected to be lowest cost decarbonisation solution.

- name: DESNZ Heat Networks Planning Database (HNPD)
  id: uk_hnpd
  enabled: true
  base_url: https://www.data.gov.uk
  start_paths:
    - /dataset/065d267f-23bc-4d0e-9a56-52d388d5835c/desnz-heat-networks-planning-database
  allowed_path_patterns:
    - /dataset/*heat-network*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 1
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - research
    - planning
    - data
  policy_types:
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Heat Networks Planning Database tracks district and communal heat network
    deployment across UK. Tracks projects through inception, planning,
    construction, operation, and decommissioning stages. Data sourced from
    planning applications, updated quarterly. Previously under BEIS.

- name: DESNZ Heat Networks Overview
  id: uk_desnz_heat_networks
  enabled: true
  base_url: https://www.gov.uk
  start_paths:
    - /government/collections/heat-networks
    - /guidance/heat-networks-overview
    - /guidance/heat-networks-consumer-protection
    - /government/publications/heat-networks-market-framework-regulations
  allowed_path_patterns:
    - /government/collections/heat-network*
    - /guidance/heat-network*
    - /government/publications/heat-network*
  blocked_path_patterns:
    - /*/print
    - /government/uploads/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - mandates
    - reporting
    - efficiency
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Central DESNZ heat networks collection page with links to all guidance,
    regulations, and support schemes. Includes Heat Networks (Market Framework)
    (Great Britain) Regulations 2025, consumer protection measures, technical
    standards guidance, and metering/billing requirements. Key reference for
    heat network regulatory landscape.

# ============================================
# REGULATORY - OFGEM
# ============================================

- name: Ofgem Heat Networks Regulation
  id: uk_ofgem_heat_networks
  enabled: true
  base_url: https://www.ofgem.gov.uk
  start_paths:
    - /energy-policy-and-regulation/heat-networks
    - /publications/heat-networks-regulatory-framework
    - /consultations?topic=Heat+networks
  allowed_path_patterns:
    - /energy-policy-and-regulation/heat-network*
    - /publications/*heat-network*
    - /consultations/*heat*
  blocked_path_patterns:
    - /*/download/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: regulatory
  tags:
    - mandates
    - reporting
    - consumer_protection
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Ofgem becomes heat network regulator 27 January 2026 under Energy Act 2023.
    All heat network operators in GB must be authorised. Regulatory framework
    covers: pricing regulation, complaints/redress, metering/billing, debt
    management, vulnerable consumer protections, compensation, monitoring
    and enforcement. Beta site requires JavaScript for full functionality.

# ============================================
# VOLUNTARY STANDARDS
# ============================================

- name: Heat Trust Consumer Protection Scheme
  id: uk_heat_trust
  enabled: true
  base_url: https://www.heattrust.org
  start_paths:
    - /about-heat-networks
    - /coming-regulation
    - /the-scheme
    - /resources
  allowed_path_patterns:
    - /about*
    - /coming-regulation*
    - /the-scheme*
    - /resources*
  blocked_path_patterns:
    - /register/*
    - /members/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: standards
  tags:
    - consumer_protection
    - standards
  policy_types:
    - standard
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Voluntary consumer protection scheme for heat networks - much of forthcoming
    Ofgem regulation based on Heat Trust standards. Provides heat network
    deployment statistics (only 2-3% of UK heat from networks vs 50%+ in
    Denmark/Sweden). Excellent summary of regulatory timeline and upcoming
    requirements. Not government but referenced in DESNZ guidance.

# ============================================
# SCOTLAND - DEVOLVED
# ============================================

- name: Scottish Government Heat Networks Policy
  id: uk_scotland_heat_networks
  enabled: true
  base_url: https://www.gov.scot
  start_paths:
    - /policies/renewable-and-low-carbon-energy/heat-networks/
    - /publications/heat-network-fund-application-guidance/
    - /publications/heat-networks-scotland-act-2021-guidance/
    - /publications/first-national-assessment-potential-heat-network-zones/
  allowed_path_patterns:
    - /policies/renewable-and-low-carbon-energy/heat-network*
    - /publications/heat-network*
    - /publications/*heat-networks*
  blocked_path_patterns:
    - /binaries/*
    - /-/media/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - mandates
    - incentives
    - planning
    - zoning
  policy_types:
    - law
    - regulation
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Scotland has UK's most advanced heat network legislation. Heat Networks
    (Scotland) Act 2021 - first UK heat network law. Requires: building
    assessment reports for non-domestic public buildings, heat network zone
    designation by local councils. Targets: 2.6 TWh by 2027, 6 TWh by 2030.
    Only 1.5% of Scottish heat currently from networks. Heat Network Support
    Unit provides pre-capital development support.

- name: Scotland's Heat Network Fund (SHNF)
  id: uk_scotland_shnf
  enabled: true
  base_url: https://www.gov.scot
  start_paths:
    - /publications/heat-network-fund-application-guidance/
    - /publications/heat-network-fund-application-guidance/pages/overview/
    - /publications/heat-network-fund-supported-projects/
  allowed_path_patterns:
    - /publications/heat-network-fund*
  blocked_path_patterns:
    - /binaries/*
    - /-/media/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - incentives
    - capital_funding
    - construction
  policy_types:
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Scotland's Heat Network Fund provides £300M for zero emission heat networks
    across Scotland. Open to public and private sectors. Supports new networks,
    decarbonisation of existing networks, and network expansion. Up to 50%
    capital co-funding. Expression of interest open year-round. Projects must
    complete by March 2030. Contact: heatnetworkfund@gov.scot

- name: Scotland Heat Network Support Unit (HNSU)
  id: uk_scotland_hnsu
  enabled: true
  base_url: https://www.gov.scot
  start_paths:
    - /publications/heat-network-support-unit/
    - /publications/heat-network-support-unit-funding-guidance/
  allowed_path_patterns:
    - /publications/heat-network-support-unit*
  blocked_path_patterns:
    - /binaries/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - incentives
    - planning
    - pre_capital
  policy_types:
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Heat Network Support Unit provides grant funding and expert advice for
    pre-capital stages of heat network development in Scotland. Managed by
    Scottish Government with Scottish Futures Trust and Zero Waste Scotland
    as partners. Building pipeline of deliverable projects to meet Scotland's
    heat network targets. Contact: heatnetworksupport@gov.scot

- name: Scotland Heat Map
  id: uk_scotland_heat_map
  enabled: true
  base_url: https://heatmap.scotland.gov.uk
  start_paths:
    - /
  allowed_path_patterns:
    - /*
  blocked_path_patterns:
    - /api/*
  max_depth: 1
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: district_heating
  tags:
    - planning
    - data
    - mapping
  policy_types:
    - report
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Scotland's Heat Map identifies opportunities for heat networks by showing
    heat density and proximity to heat sources. Used by local authorities
    for heat network zoning decisions and building assessment reports.
    Interactive mapping tool. Requires JavaScript for full functionality.

# ============================================
# WALES - DEVOLVED
# ============================================

- name: Welsh Government Heat Strategy
  id: uk_wales_heat_strategy
  enabled: true
  base_url: https://www.gov.wales
  start_paths:
    - /heat-strategy-wales
    - /draft-heat-strategy-wales-html
    - /written-statement-consultation-heat-strategy-wales
  allowed_path_patterns:
    - /*heat-strategy*
    - /written-statement*heat*
  blocked_path_patterns:
    - /sites/default/files/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - planning
    - carbon
    - efficiency
  policy_types:
    - guidance
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Heat Strategy for Wales (published 2024) sets path to net zero heat by 2050.
    Heat accounts for 50% of Welsh energy demand, 75% from fossil fuels.
    Strategy supports heat pumps as primary mechanism, with role for heat
    networks in appropriate areas. Uses Local Area Energy Plans (LAEPs) for
    identifying heat network zones. Cardiff and Bridgend identified as
    priority areas.

- name: Welsh Government Energy Projects
  id: uk_wales_energy_service
  enabled: true
  base_url: https://www.gov.wales
  start_paths:
    - /kick-start-new-welsh-schemes-heat-homes-and-businesses-using-city-centre-heat-networks
    - /energy-service
  allowed_path_patterns:
    - /*heat-network*
    - /*energy-service*
    - /*district-heating*
  blocked_path_patterns:
    - /sites/default/files/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - incentives
    - planning
  policy_types:
    - incentive
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Welsh Government Energy Service supports heat network development.
    Cardiff Heat Network - first large-scale Welsh city heat network, £8.6M
    zero-interest loan, waste heat from Viridor Energy Recovery Facility
    to Cardiff Bay buildings. Bridgend Heat Network also supported.

# ============================================
# REGIONAL - GREATER LONDON
# ============================================

- name: Greater London Authority Heat Networks
  id: uk_gla_heat_networks
  enabled: true
  base_url: https://www.london.gov.uk
  start_paths:
    - /programmes-strategies/environment-and-climate-change/energy/district-heating
    - /publications/london-heat-map
    - /programmes-strategies/environment-and-climate-change/energy/zero-carbon-london
  allowed_path_patterns:
    - /programmes-strategies/environment-and-climate-change/energy/*
    - /publications/*heat*
  blocked_path_patterns:
    - /moderngov/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: district_heating
  tags:
    - planning
    - data
    - mapping
  policy_types:
    - guidance
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    London hosts 80% of UK data center capacity. GLA London Heat Map shows
    existing and planned district heat networks. GLA report shows 1.6 TWh
    heat recovery potential (could heat 500,000 homes). Old Oak & Park Royal
    received £36M GHNF for UK's first data center waste heat network
    (10,000+ homes by 2040). Created by Centre for Sustainable Energy.

- name: London Heat Map
  id: uk_london_heat_map
  enabled: true
  base_url: https://maps.london.gov.uk
  start_paths:
    - /heatmap/
  allowed_path_patterns:
    - /heatmap/*
  blocked_path_patterns:
    - /api/*
  max_depth: 1
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: district_heating
  tags:
    - planning
    - data
    - mapping
  policy_types:
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Interactive London Heat Map shows existing and planned district heat
    networks in Greater London. Updated regularly. Created by Centre for
    Sustainable Energy for GLA. Underlying datasets available for download.
    Requires JavaScript for full functionality.
```

---

## Sites Evaluated But Not Recommended

```yaml
# EVALUATED - NOT RECOMMENDED

- name: Association for Decentralised Energy (ADE)
  url: https://www.theade.co.uk
  region: UK
  topic: District Heating
  reason_excluded: |
    Trade association, not government body. Provides industry advocacy
    and best practices but not official policy source.
  checked_date: "2026-01-06"
  reconsider_if: "Government formally designates as standards body"

- name: Building Engineering Services Association (BESA)
  url: https://www.thebesa.com
  region: UK
  topic: District Heating
  reason_excluded: |
    Industry trade body. Produces technical guidance but not official
    government policy.
  checked_date: "2026-01-06"

- name: Heat Pump Association
  url: https://www.heatpumps.org.uk
  region: UK
  topic: District Heating
  reason_excluded: |
    Industry trade association. Not government policy source.
  checked_date: "2026-01-06"

- name: Northern Ireland Utility Regulator
  url: https://www.uregni.gov.uk
  region: UK
  topic: District Heating
  reason_excluded: |
    Northern Ireland electricity and gas regulator. Heat networks not
    currently regulated in NI (covered by GB Ofgem framework from 2026).
    Limited heat network specific content.
  checked_date: "2026-01-06"
  reconsider_if: "NI develops separate heat network regulations"

- name: BRE (Building Research Establishment)
  url: https://www.bregroup.com
  region: UK
  topic: District Heating
  reason_excluded: |
    Private research organisation (formerly government-owned). Produces
    BREEAM standards but not official policy maker.
  checked_date: "2026-01-06"
```

---

## Research Notes

### Key Patterns Discovered

1. **Funding Landscape**: UK has multiple overlapping funding streams:
   - HNDU (pre-capital development support)
   - GHNF (capital grants for construction)
   - Scotland: SHNF (£300M) + HNSU (pre-capital)
   - Wales: Energy Service loans

2. **Regulatory Timeline Critical**: 
   | Date | Milestone |
   |------|-----------|
   | Oct 2023 | Energy Act 2023 Royal Assent |
   | Oct 2024 | First 6 heat network zones designated |
   | Apr 2025 | Consumer advocacy bodies assume powers |
   | **Jan 2026** | Ofgem heat network regulation begins |
   | Jan 2027 | All networks must register with Ofgem |

3. **Devolution Complexity**: 
   - Scotland has separate, more advanced legislation (Heat Networks (Scotland) Act 2021)
   - Wales: Heat Strategy published 2024, uses LAEPs for zoning
   - Northern Ireland: Falls under GB Ofgem framework but no specific NI policy

4. **Data Center Heat Projects Emerging**:
   - North Crawley (Gatwick + Digital Realty data center) - 46GWh, 2027 target
   - Old Oak & Park Royal London (data center waste heat) - 9,000+ homes, £36M GHNF

5. **JavaScript Requirements**: Interactive maps (Scotland Heat Map, London Heat Map) require Playwright. Most policy pages are server-rendered.

### Key Legislation to Track

| Legislation | Reference | Relevance |
|-------------|-----------|-----------|
| Energy Act 2023 | ukpga/2023/52 | Heat network zoning, Ofgem regulation |
| Heat Networks (Market Framework) Regs 2025 | uksi/2025/269 | Ofgem authorisation requirements |
| Heat Networks (Scotland) Act 2021 | asp/2021/9 | Scottish zoning, permits, BAR duties |
| Heat Networks (Supply Targets) (Scotland) Regs 2023 | ssi/2023/297 | 2.6 TWh (2027), 6 TWh (2030) targets |
| Heat Network (Metering and Billing) Regs 2014 | uksi/2014/3120 | Consumer billing requirements |

### Data Center Heat Reuse Relevance

- **Zoning**: Zone coordinators can require buildings (including data centers) to connect to heat networks, but no mandatory waste heat utilization requirements
- **GHNF Priority**: Data center waste heat projects explicitly supported - North Crawley and Old Oak examples demonstrate government interest
- **Scotland Leadership**: Building Assessment Reports may identify data centers as potential heat sources in designated zones
- **Temperature Match**: UK policy increasingly recognizes low-temperature waste heat from data centers (typically 30-60°C) as viable heat source with heat pump augmentation

### Recommendation

Prioritize monitoring:
1. **uk_hn_zoning** - For new zone designations and connection requirements
2. **uk_ghnf** - For new data center heat projects receiving funding
3. **uk_ofgem_heat_networks** - For regulatory framework details (critical from Jan 2026)
4. **uk_scotland_heat_networks** - Scotland's more advanced framework may preview future UK policy
