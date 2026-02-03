# UK Grid Operators - Policy Tracker Configuration
## Grid Cell 1.4 | Generated: 2026-01-06

This configuration covers UK electricity grid operators, system operators, and regulators including the National Energy System Operator (NESO, formerly National Grid ESO), distribution network operators (DNOs), and bodies involved in grid planning for large electricity consumers like data centers.

---

## Summary

| Site | Category | JavaScript Required | Key Content |
|------|----------|---------------------|-------------|
| NESO | System Operator | Yes | National Energy System Operator - grid balancing, FES |
| NESO Data Portal | Data | No | Grid data, carbon intensity, connections |
| Ofgem Connections | Regulatory | Yes | Grid connection reforms, data center guidance |
| Ofgem RIIO | Regulatory | Yes | Price controls, network investment |
| Distribution Code | Standards | No | Technical standards for DNO connections |
| UK Power Networks DSO | DNO | Yes | London/SE distribution, data center connections |
| Scottish Power Energy Networks | DNO | No | Scotland/NW England distribution |
| SSEN | DNO | No | N. Scotland/S. England distribution |
| Northern Powergrid | DNO | No | NE England/Yorkshire distribution |
| National Grid ED | DNO | No | Midlands/SW/Wales distribution |
| Electricity North West | DNO | No | NW England distribution |

---

## Critical Policy Context

### Major Structural Change (October 2024)
- **National Grid ESO** became **National Energy System Operator (NESO)**
- Publicly owned (£630M acquisition from National Grid plc)
- Expanded role: electricity system operation + strategic energy planning
- Chair: Dr Paul Golby; CEO: Fintan Slye

### Grid Connection Queue Crisis
| Metric | Value |
|--------|-------|
| Total queue (Feb 2025) | 756 GW |
| Transmission queue | 587 GW |
| Distribution queue | 178 GW |
| Wait times | Up to 15 years |
| Data center share | "Significant" (per Ofgem) |

### Connection Reforms (TM04+) - April 2025
- **Gate 1**: Indicative connection offer
- **Gate 2**: Confirmed connection date, point, queue position
- Requires: Strategic Alignment + Readiness criteria
- Data centers classified as "critical national infrastructure" (Sept 2024)
- 500MW availability per AI Growth Zone announced

### Key Timeline
| Date | Milestone |
|------|-----------|
| Sept 2024 | Data centers classified as Critical National Infrastructure |
| Oct 2024 | NESO launched (publicly owned) |
| April 2025 | Ofgem approved TM04+ connection reforms |
| May 2025 | Distribution customer evidence window opened |
| July 2025 | Transmission customer evidence window opened |
| Sept 2025 | Gate 2 outcomes announced |
| Autumn 2025 | Revised connection offers issued |
| Dec 2025 | NESO announced queue reforms - 2/3 reduction |
| Dec 2025 | Ofgem end-to-end connections review consultation |
| Feb 2026 | Consultation closes |
| Autumn 2027 | Strategic Spatial Energy Plan (SSEP) due |
| 2028 | Centralised Strategic Network Plan (CSNP) due |

---

## YAML Configuration

```yaml
# UK - Grid Operators
# Generated: 2026-01-06
# Grid Cell: 1.4

# ============================================
# NATIONAL ENERGY SYSTEM OPERATOR (NESO)
# ============================================

- name: National Energy System Operator (NESO)
  id: uk_neso
  enabled: true
  base_url: https://www.neso.energy
  start_paths:
    - /
    - /what-we-do/connections
    - /future-energy/future-energy-scenarios
    - /industry-information/connections
  allowed_path_patterns:
    - /what-we-do/*
    - /future-energy/*
    - /industry-information/*
    - /news/*
  blocked_path_patterns:
    - /document/*/download
    - /cdn-cgi/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: grid_operator
  tags:
    - planning
    - research
    - carbon
  policy_types:
    - report
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    National Energy System Operator (formerly National Grid ESO) launched
    Oct 2024 as publicly-owned body. Balances GB electricity system in
    real time. Publishes Future Energy Scenarios (FES) annually - key
    forecasts for data center demand. Manages connections reform (TM04+).
    Clean Power 2030 analysis. Critical for tracking grid connection policy.

- name: NESO Data Portal
  id: uk_neso_data
  enabled: true
  base_url: https://www.neso.energy
  start_paths:
    - /data-portal
  allowed_path_patterns:
    - /data-portal/*
  blocked_path_patterns:
    - /api/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - research
    - data
    - carbon
  policy_types:
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Centralised repository for NESO published data. Includes: carbon
    intensity forecasts, connection registers, constraint management,
    demand forecasts, generation data, network charges. APIs available.
    Key for tracking grid capacity and data center electricity demand.

- name: NESO Connections Information
  id: uk_neso_connections
  enabled: true
  base_url: https://www.neso.energy
  start_paths:
    - /industry-information/connections
    - /industry-information/connections/connections-reform
  allowed_path_patterns:
    - /industry-information/connections/*
  blocked_path_patterns:
    - /document/*/download
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: grid_operator
  tags:
    - planning
    - mandates
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    NESO connections reform hub. TM04+ implementation details, Gate 1/Gate 2
    process, queue management. Demand Queue Call for Input launched Nov 2025
    due to "surge in demand connection applications" from data centers.
    Critical for tracking data center grid access policy.

# ============================================
# OFGEM - ENERGY REGULATOR
# ============================================

- name: Ofgem Grid Connections
  id: uk_ofgem_connections
  enabled: true
  base_url: https://www.ofgem.gov.uk
  start_paths:
    - /energy-policy-and-regulation/policy-and-regulatory-programmes/connections
    - /publications?topic=Connections
    - /consultations?topic=Connections
  allowed_path_patterns:
    - /energy-policy-and-regulation/*connections*
    - /publications/*connection*
    - /consultations/*connection*
    - /blog/*connection*
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
    - planning
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Ofgem connections policy and reform. Approved TM04+ reforms April 2025.
    Published Demand Connections Update Nov 2025 specifically addressing
    data center queue growth. End-to-end connections review consultation
    Dec 2025 - Feb 2026. Connections Delivery Board oversight. Critical
    for data center grid access regulation.

- name: Ofgem Network Price Controls (RIIO)
  id: uk_ofgem_riio
  enabled: true
  base_url: https://www.ofgem.gov.uk
  start_paths:
    - /energy-policy-and-regulation/policy-and-regulatory-programmes/network-price-controls
    - /publications?topic=Network+price+controls
  allowed_path_patterns:
    - /energy-policy-and-regulation/*network*
    - /energy-policy-and-regulation/*riio*
    - /publications/*riio*
    - /publications/*network*
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
    - planning
    - incentives
  policy_types:
    - regulation
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    RIIO price controls set framework for network investment. RIIO-3
    settlement Dec 2025 aims to unlock £90bn transmission investment.
    RIIO-ED2 (distribution) allows £22.2bn investment with agile funding
    for EV/heat pump uptake. Affects network capacity for data centers.

- name: Ofgem Connections Action Plan
  id: uk_ofgem_cap
  enabled: true
  base_url: https://www.gov.uk
  start_paths:
    - /government/publications/connections-action-plan
    - /government/news/clean-energy-projects-prioritised-for-grid-connections
  allowed_path_patterns:
    - /government/publications/*connections*
    - /government/news/*connection*
    - /government/news/*grid*
  blocked_path_patterns:
    - /*/print
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: regulatory
  tags:
    - planning
    - mandates
  policy_types:
    - guidance
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Joint DESNZ/Ofgem Connections Action Plan published Dec 2023. Sets
    target to reduce average connection delay from 5 years to 6 months.
    Data centers explicitly mentioned as benefiting from "fast-track
    approach" alongside AI sector. £40bn annual clean energy investment
    target.

# ============================================
# DISTRIBUTION CODE
# ============================================

- name: GB Distribution Code
  id: uk_distribution_code
  enabled: true
  base_url: https://dcode.org.uk
  start_paths:
    - /
    - /distribution-code
  allowed_path_patterns:
    - /*
  blocked_path_patterns:
    - /downloads/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: standards
  tags:
    - mandates
    - standards
  policy_types:
    - standard
    - regulation
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Technical standards for connection to distribution networks. All DNOs
    maintain same version under Ofgem Licence Condition 21. Distribution
    Code Review Panel oversees modifications. Key for understanding
    technical requirements for data center distribution connections.
    Issue 58 current version.

# ============================================
# DISTRIBUTION NETWORK OPERATORS (DNOs)
# ============================================

- name: UK Power Networks Distribution System Operator
  id: uk_ukpn_dso
  enabled: true
  base_url: https://dso.ukpowernetworks.co.uk
  start_paths:
    - /
    - /flexibility
    - /local-net-zero
  allowed_path_patterns:
    - /*
  blocked_path_patterns:
    - /api/*
    - /login/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: grid_operator
  tags:
    - planning
    - data
    - flexibility
  policy_types:
    - guidance
    - report
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    UK Power Networks DSO covers London, South East, East of England -
    80% of UK data center capacity. First DNO to partner with Data Centre
    Alliance (Nov 2025). "Introduction to Connections" guide for data
    centers. Distribution Future Energy Scenarios (DFES) forecasts.
    Flexibility Hub for demand response. Local Net Zero planning tools.

- name: UK Power Networks Connections
  id: uk_ukpn_connections
  enabled: true
  base_url: https://www.ukpowernetworks.co.uk
  start_paths:
    - /electricity/new-connection
    - /electricity/new-connection/demand-connections
  allowed_path_patterns:
    - /electricity/new-connection/*
    - /electricity/*connection*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Main UKPN connections portal. Covers London area where most UK data
    centers located. Connection options include: non-curtailable (24/7),
    flexible capacity, self-supply arrangements. Key for understanding
    distribution-level data center connection options.

- name: Scottish Power Energy Networks
  id: uk_spen
  enabled: true
  base_url: https://www.spenergynetworks.co.uk
  start_paths:
    - /
    - /our-services/connections
    - /the-future
  allowed_path_patterns:
    - /our-services/*
    - /the-future/*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    SP Energy Networks covers Central and Southern Scotland, Merseyside,
    North Wales. Part of Scottish Power (Iberdrola). Relevant for Scottish
    data center developments. Distribution Future Energy Scenarios
    available.

- name: Scottish and Southern Electricity Networks (SSEN)
  id: uk_ssen
  enabled: true
  base_url: https://www.ssen.co.uk
  start_paths:
    - /
    - /connections
    - /our-services/connections
  allowed_path_patterns:
    - /connections/*
    - /our-services/*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    SSEN covers Northern Scotland and Central Southern England (Hampshire,
    Berkshire, Oxfordshire area). Two separate licence areas. SSE also
    operates transmission in Scotland. Relevant for data centers outside
    London seeking cooler climate locations.

- name: Northern Powergrid
  id: uk_northern_powergrid
  enabled: true
  base_url: https://www.northernpowergrid.com
  start_paths:
    - /
    - /get-connected
    - /our-network
  allowed_path_patterns:
    - /get-connected/*
    - /our-network/*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Northern Powergrid covers North East England, Yorkshire, Northern
    Lincolnshire. Growing data center interest in Yorkshire due to
    lower costs than London. Distribution Future Energy Scenarios
    available.

- name: National Grid Electricity Distribution
  id: uk_nged
  enabled: true
  base_url: https://www.nationalgrid.co.uk
  start_paths:
    - /electricity-distribution
    - /electricity-distribution/getting-connected
  allowed_path_patterns:
    - /electricity-distribution/*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    National Grid Electricity Distribution (formerly Western Power
    Distribution) covers Midlands, South West England, South Wales.
    Part of National Grid plc (separate from NESO). Bristol/Cardiff
    data center corridor relevant.

- name: Electricity North West
  id: uk_enwl
  enabled: true
  base_url: https://www.enwl.co.uk
  start_paths:
    - /
    - /get-connected
  allowed_path_patterns:
    - /get-connected/*
    - /our-future-network/*
  blocked_path_patterns:
    - /login/*
    - /my-account/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: grid_operator
  tags:
    - planning
  policy_types:
    - guidance
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Electricity North West covers Greater Manchester, Lancashire,
    Cumbria. Manchester emerging as secondary UK data center market.

# ============================================
# ENERGY NETWORKS ASSOCIATION
# ============================================

- name: Energy Networks Association
  id: uk_ena
  enabled: true
  base_url: https://www.energynetworks.org
  start_paths:
    - /
    - /creating-tomorrows-networks
    - /info
  allowed_path_patterns:
    - /creating-tomorrows-networks/*
    - /info/*
  blocked_path_patterns:
    - /members-only/*
  max_depth: 2
  language: en
  region:
    - "uk"
  requires_playwright: false
  rate_limit_seconds: 2.0
  category: standards
  tags:
    - planning
    - standards
  policy_types:
    - guidance
    - standard
  verified_by: Deep Research
  verified_date: "2026-01-06"
  notes: |
    Trade body representing UK/Ireland gas and electricity networks.
    Coordinates DNO activities, publishes Smarter Networks Portal,
    Strategic Innovation Fund. Industry Hub with connection resources.
    "Find my network operator" tool. Note: trade body not government,
    but coordinates regulatory compliance.
```

---

## Sites Evaluated But Not Recommended

```yaml
# EVALUATED - NOT RECOMMENDED

- name: National Grid plc
  url: https://www.nationalgrid.com
  region: UK
  topic: Grid Operators
  reason_excluded: |
    Corporate parent company site. Transmission Owner (separate from
    System Operator since Oct 2024). Use NESO for system operation
    and National Grid ED for distribution.
  checked_date: "2026-01-06"

- name: Data Centre Alliance
  url: https://www.datacentrealliance.org
  region: UK
  topic: Grid Operators
  reason_excluded: |
    Industry trade association. Strategic partner of UK Power Networks
    but not government/regulatory body. Membership portal access.
  checked_date: "2026-01-06"
  reconsider_if: "Government formally designates as advisory body"

- name: NIE Networks (Northern Ireland)
  url: https://www.nienetworks.co.uk
  region: UK
  topic: Grid Operators
  reason_excluded: |
    Northern Ireland distribution network. Separate regulatory framework
    (Utility Regulator NI). Limited data center market in NI. Could add
    if NI data center activity increases.
  checked_date: "2026-01-06"
  reconsider_if: "Significant NI data center developments"

- name: ESO Data Portal (legacy)
  url: https://data.nationalgrideso.com
  region: UK
  topic: Grid Operators
  reason_excluded: |
    Legacy domain - redirects to neso.energy/data-portal. Included
    NESO Data Portal instead.
  checked_date: "2026-01-06"

- name: Competition and Markets Authority
  url: https://www.gov.uk/government/organisations/competition-and-markets-authority
  region: UK
  topic: Grid Operators
  reason_excluded: |
    Appeals body for some Ofgem decisions. Not primary policy source.
    May hear appeals on connection reforms but unlikely to publish
    data center specific guidance.
  checked_date: "2026-01-06"
```

---

## Research Notes

### Key Findings: Data Center Grid Policy

1. **Data Centers Classified as Critical National Infrastructure (Sept 2024)**
   - Enables fast-track grid connections
   - AI Growth Zones promised 500MW availability each
   - Special treatment in connections reform

2. **Grid Connection Crisis Affecting Data Centers**
   - 125 GW total demand queue as of June 2025
   - Data centers "significant share" of growth (Ofgem)
   - Wait times up to 15 years before reforms
   - Ofgem concerned about "less viable" projects crowding queue

3. **TM04+ Reforms Impact on Data Centers**
   - Potential disadvantage: Data centers typically acquire land rights later than generators
   - May struggle to meet "readiness" criteria
   - Ofgem acknowledged concern but considers "acceptable outcome"
   - Special demand queue review launched Nov 2025

4. **NESO/Ofgem Three Pillars for Demand Connections**
   - **Curate**: Stronger entry/progression requirements
   - **Plan**: Government strategic plan for data centers
   - **Connect**: New solutions including self-build transmission assets

5. **DNO-Level Innovation**
   - UK Power Networks first DNO to partner with Data Centre Alliance
   - Published "Introduction to Connections" guide specifically for data centers
   - Flexible connection options: non-curtailable, flexible capacity, self-supply

### Technical Patterns

| Site Type | JavaScript Required | Rate Limit |
|-----------|---------------------|------------|
| NESO | Yes | 3.0s |
| Ofgem | Yes | 3.0s |
| DNO main sites | Mostly no | 2.0s |
| DSO portals | Yes | 3.0s |
| Distribution Code | No | 2.0s |

### Key Documents to Track

| Document | Publisher | Frequency | Relevance |
|----------|-----------|-----------|-----------|
| Future Energy Scenarios (FES) | NESO | Annual | Data center demand forecasts |
| Distribution Future Energy Scenarios (DFES) | Each DNO | Annual | Regional capacity planning |
| Connections Queue Data | NESO | Ongoing | Queue position tracking |
| Connections Action Plan Updates | DESNZ/Ofgem | Periodic | Policy changes |
| RIIO Price Control | Ofgem | 5-year cycles | Network investment |
| Clean Power 2030 Action Plan | DESNZ | Updates | Strategic direction |
| Strategic Spatial Energy Plan (SSEP) | NESO | Autumn 2027 | Long-term planning |

### Data Center-Specific Grid Statistics

| Metric | Source | Value |
|--------|--------|-------|
| Current UK electricity demand from data centers | National Grid | 2.5-3% |
| Projected UK electricity demand from data centers (2025) | National Grid | Up to 9% |
| Data center projects in transmission queue | Ofgem | "Significant share" of 125 GW |
| UK commercial data centers | NESO FES | 400-600 known |
| London data center market share (Europe) | NESO FES | Largest hub |

### Regulatory Complexity Note

The UK grid regulatory landscape is complex with multiple overlapping bodies:
- **DESNZ**: Policy direction, legislation
- **Ofgem**: Regulation, price controls, connection rules
- **NESO**: System operation, connections management, planning
- **DNOs**: Distribution networks, local connections
- **Transmission Owners**: Network infrastructure (National Grid, SSEN, SPT)

For policy tracking, prioritize:
1. **NESO Connections** - operational connection policy
2. **Ofgem Connections** - regulatory framework
3. **DESNZ gov.uk** - strategic policy direction
4. **UK Power Networks DSO** - London/SE specific (80% of UK data centers)

---

## Heat Reuse Relevance

While Grid Cell 1.4 focuses on electricity grid operators, connections to heat reuse policy include:

1. **Demand Flexibility**: Data centers participating in demand response could integrate heat storage
2. **Connection Conditions**: Future connection agreements may include waste heat utilization requirements
3. **Heat Network Zoning**: Grid connection planning should align with heat network zone designations
4. **Strategic Planning**: SSEP/CSNP may eventually integrate heat infrastructure planning

Cross-reference with:
- Grid Cell 1.3 (UK District Heating) - Heat network infrastructure
- Grid Cell 1.1 (UK Energy Ministries) - DESNZ policy direction
- Grid Cell 1.2 (UK Legislative) - Energy Act 2023 provisions
