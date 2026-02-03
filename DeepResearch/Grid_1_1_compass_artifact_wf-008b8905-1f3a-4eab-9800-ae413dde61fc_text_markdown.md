# UK Government Websites for Data Center Energy Policy Tracking

The UK's data center energy policy landscape spans **central government**, **three devolved administrations**, and **specialized regulators**, with Ofgem becoming the heat networks regulator in January 2026. Scotland leads with dedicated heat network legislation; England's heat network zoning framework is emerging under the Energy Act 2023. Unlike the EU, the UK has **no mandatory PUE limits or waste heat quotas** for data centers, but funding schemes incentivize voluntary heat reuse.

---

## YAML Configuration Entries

### Central UK Government Bodies

```yaml
- name: Department for Energy Security and Net Zero (DESNZ)
  id: uk_desnz
  base_url: https://www.gov.uk
  start_paths:
    - /government/organisations/department-for-energy-security-and-net-zero
    - /government/collections/heat-networks
    - /search/policy-papers-and-consultations?organisations[]=department-for-energy-security-and-net-zero
    - /search/guidance-and-regulation?organisations[]=department-for-energy-security-and-net-zero
    - /government/publications/green-heat-network-fund-ghnf
    - /government/publications/heat-network-efficiency-scheme-hnes
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: central_government
  tags:
    - heat_networks
    - energy_efficiency
    - net_zero
    - climate_change_agreements
    - funding_schemes
  policy_types:
    - Heat network zoning regulations
    - Green Heat Network Fund grants
    - Heat Network Efficiency Scheme
    - Climate Change Agreements (data center sector)
    - Energy Savings Opportunity Scheme (ESOS)
    - Streamlined Energy and Carbon Reporting (SECR)
    - Clean Power 2030 strategy
  notes: >
    Primary UK government department for energy policy. Created February 2023.
    Publishes Heat Network Zoning consultations, administers GHNF (£180m+ awarded)
    and HNES (£77m budget). Data centers participate in Climate Change Agreements
    via techUK with 19% efficiency target. GOV.UK is server-rendered HTML with
    no JavaScript required. Critical for tracking heat network mandates and
    funding for data center heat reuse projects.

- name: Office of Gas and Electricity Markets (Ofgem)
  id: uk_ofgem
  base_url: https://www.ofgem.gov.uk
  start_paths:
    - /energy-policy-and-regulation/policy-and-regulatory-programmes/heat-networks
    - /consultations
    - /publications
    - /news-and-insight
    - /environmental-and-social-schemes
  language: en
  region:
    - "uk"
  requires_playwright: true
  category: regulator
  tags:
    - heat_networks_regulation
    - consumer_protection
    - grid_connections
    - energy_market
  policy_types:
    - Heat network operator authorization requirements
    - Heat network consumer protection standards
    - Registration and licensing guidance
    - Grid connection reform (relevant to data centers)
    - Network price controls
  notes: >
    Independent energy regulator. Becomes heat network regulator for Great Britain
    on 27 January 2026 under Energy Act 2023. Will set rules on heat network
    prices and potentially mandate waste heat disclosure. Site displays
    "Please enable JavaScript" warning - Playwright recommended for full
    functionality. Beta site. Essential for tracking upcoming heat network
    operator requirements that could affect data centers supplying heat.

- name: Climate Change Committee (CCC)
  id: uk_ccc
  base_url: https://www.theccc.org.uk
  start_paths:
    - /publications/
    - /news/
    - /news/calls-for-evidence/
    - /publicationtype/report/progress-reports-net-zero/
    - /publicationtype/report/carbon-budget/
    - /publicationtype/report/letters/
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: advisory_body
  tags:
    - carbon_budgets
    - net_zero_monitoring
    - climate_risk
    - policy_recommendations
  policy_types:
    - Carbon budget recommendations
    - Annual progress reports to Parliament
    - UK climate risk assessments
    - Sector-specific decarbonization advice
    - Net zero pathway analysis
  notes: >
    Independent statutory body established under Climate Change Act 2008.
    WordPress-based site, server-rendered, no JS required. Publishes annual
    progress reports (2025 report noted UK missing 72% of emissions cuts).
    Provides independent scrutiny of government energy efficiency policies.
    Indirect but important for understanding overall emissions trajectory
    and policy adequacy assessments affecting data center sector.

- name: Environment Agency
  id: uk_environment_agency
  base_url: https://www.gov.uk
  start_paths:
    - /government/organisations/environment-agency
    - /search/policy-papers-and-consultations?organisations[]=environment-agency
    - /guidance/check-if-you-need-an-environmental-permit
    - /government/publications/climate-change-agreements-cca-biennial-report
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: regulator
  tags:
    - environmental_permits
    - climate_change_agreements
    - water_abstraction
    - emissions_regulation
  policy_types:
    - Environmental permits for backup generators
    - Water abstraction licensing (cooling systems)
    - Climate Change Agreement biennial reports
    - Medium Combustion Plant Directive implementation
  notes: >
    Executive non-departmental body sponsored by Defra. Administers Climate
    Change Agreement scheme and publishes biennial CCA performance reports.
    Relevant for data center environmental permits (backup diesel generators,
    water cooling). Server-rendered GOV.UK content, no JS required.
    Consultation platform at consult.environment-agency.gov.uk may need JS.
```

### Devolved Government Bodies

```yaml
- name: Scottish Government Energy and Climate Change Directorate
  id: uk_scotland_energy
  base_url: https://www.gov.scot
  start_paths:
    - /energy/
    - /policies/renewable-and-low-carbon-energy/
    - /policies/energy-efficiency/
    - /policies/energy-infrastructure/
    - /policies/climate-change/
    - /publications/?cat=filter&topic=energy
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: devolved_government
  tags:
    - heat_networks_scotland
    - net_zero_2045
    - building_regulations
    - heat_networks_fund
  policy_types:
    - Heat Networks (Scotland) Act 2021 implementation
    - Heat Network Delivery Plan
    - Scotland's Heat Network Fund (£300M)
    - Non-domestic building energy standards
    - Draft Energy Strategy and Just Transition Plan
    - NPF4 data center planning support
  notes: >
    Scotland has UK's most advanced heat network legislation. Heat Networks
    (Scotland) Act 2021 was first of its kind, establishes licensing and
    requires waste heat source assessments including data centers. Targets:
    2.6 TWh heat network output by 2027, 6 TWh by 2030. Net zero target 2045
    (5 years ahead of UK). NPF4 lists 20 data center sites. Building
    regulations are devolved. Server-rendered, no JS required. Essential for
    tracking Scotland-specific heat reuse mandates.

- name: Welsh Government Climate Change
  id: uk_wales_climate
  base_url: https://www.gov.wales
  start_paths:
    - /climate-change
    - /environment-climate-change
    - /topics/environment-countryside/energy/
    - /prosperity-all-low-carbon-wales
    - /net-zero-wales-carbon-budget-2
    - /heat-strategy-wales
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: devolved_government
  tags:
    - net_zero_wales
    - heat_strategy
    - building_regulations
    - bilingual
  policy_types:
    - Net Zero Wales carbon budgets
    - Heat Strategy for Wales
    - Low Carbon Heat Grants
    - Welsh Government Energy Service
    - Building regulations guidance
  notes: >
    Wales declared first climate emergency (April 2019). Net zero by 2050
    (statutory), public sector net zero by 2030. Heat networks less
    developed than Scotland. Cardiff emerging as data center hub (M4 corridor,
    Vantage campus). Bilingual requirement - Welsh versions at llyw.cymru.
    Standard Drupal CMS, server-rendered, no JS required. Useful for Wales-
    specific building regulations and regional heat strategy.

- name: Northern Ireland Department for the Economy
  id: uk_ni_economy
  base_url: https://www.economy-ni.gov.uk
  start_paths:
    - /topics/energy
    - /topics/energy-strategy
    - /topics/energy-efficiency
    - /topics/renewables
    - /topics/heat
    - /articles/northern-ireland-energy-strategy-path-net-zero-energy
    - /articles/mid-term-review-energy-strategy-path-net-zero-energy
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: devolved_government
  tags:
    - energy_strategy_ni
    - single_electricity_market
    - renewable_heat
  policy_types:
    - Energy Strategy Path to Net Zero Energy
    - Energy efficiency programs
    - Renewable Heat Incentive (closing)
    - Public sector energy management
  notes: >
    Energy policy is extensively devolved to NI. Unique situation: shares
    all-island Single Electricity Market (SEM) with Republic of Ireland,
    regulated jointly by NI Utility Regulator and Ireland's CRU. Some EU
    energy regulations continue to apply under Protocol. 80% renewable
    electricity target by 2030 (statutory). Heat networks and data center
    policies less developed. Drupal-based, server-rendered, no JS required.
    Important for cross-border energy considerations.
```

### Legislative and Specialized Bodies

```yaml
- name: UK Legislation
  id: uk_legislation
  base_url: https://www.legislation.gov.uk
  start_paths:
    - /ukpga/2023/52  # Energy Act 2023
    - /asp/2021/9     # Heat Networks (Scotland) Act 2021
    - /uksi/2014/3120 # Heat Network Metering Regulations
    - /ssi/2023/123   # Heat Network Zones Scotland Regs
    - /new/uk
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: legislation
  tags:
    - primary_legislation
    - secondary_legislation
    - statutory_instruments
  policy_types:
    - Energy Act 2023 (heat network zoning powers)
    - Heat Networks (Scotland) Act 2021
    - Heat Network (Metering and Billing) Regulations 2014
    - Climate Change Act 2008
    - Environment (Wales) Act 2016
    - Climate Change (Northern Ireland) Act 2022
  notes: >
    Official UK legislation repository. Essential for tracking enacted
    laws vs consultations/guidance. Energy Act 2023 provides heat network
    zoning and regulation powers. Heat Networks (Scotland) Act 2021 is
    primary Scottish heat network law. Server-rendered, no JS required.
    XML and PDF formats available for all legislation.

- name: National Wealth Fund
  id: uk_national_wealth_fund
  base_url: https://www.nationalwealthfund.org.uk
  start_paths:
    - /
    - /our-investments/
    - /sectors/
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: investment_body
  tags:
    - infrastructure_investment
    - clean_energy_finance
    - heat_networks_funding
    - local_authority_lending
  policy_types:
    - Infrastructure investment priorities
    - Heat network project financing
    - Clean energy sector investments
    - Local authority lending programs
  notes: >
    Renamed from UK Infrastructure Bank in October 2024. £27.8 billion
    capital. Heat networks listed as priority investment sector. Provides
    local authority lending for infrastructure. Example: £9.6M for Solihull
    heating improvements. Also invested in data center cooling technology
    via British Patient Capital. Important for tracking government
    investment in heat network infrastructure.

- name: Greater London Authority
  id: uk_gla
  base_url: https://www.london.gov.uk
  start_paths:
    - /programmes-strategies/environment-and-climate-change/energy
    - /what-we-do/environment/energy
    - /who-we-are/city-halls-partners/old-oak-and-park-royal-development-corporation-opdc
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: local_government
  tags:
    - london_plan
    - heat_networks_london
    - data_center_heat_reuse
    - local_energy_accelerator
  policy_types:
    - London Plan energy policies
    - Data center heat reuse guidance
    - Local Energy Accelerator funding
    - Green Finance Programme
    - Cooling hierarchy requirements
  notes: >
    London hosts 80% of UK data center capacity. GLA commissioned
    "Optimising Data Centres in London: Heat Reuse" report (2025) showing
    up to 1.6 TWh heat recovery potential annually (could heat 500,000
    homes). OPDC received £36M GHNF for UK's first data center waste heat
    network (10,000+ homes by 2040). London Plan encourages data center
    heat supply. Critical for tracking London-specific policies affecting
    largest UK data center market.

- name: Office for Product Safety and Standards (OPSS)
  id: uk_opss
  base_url: https://www.gov.uk
  start_paths:
    - /government/organisations/office-for-product-safety-and-standards
    - /government/publications/opss-enforcement-enforcement-actions/heat-network-regulations
    - /guidance/heat-networks
  language: en
  region:
    - "uk"
  requires_playwright: false
  category: regulator
  tags:
    - heat_network_enforcement
    - metering_regulations
    - compliance
  policy_types:
    - Heat Network Metering and Billing Regulations enforcement
    - Compliance notices and penalties
    - Heat network database management
  notes: >
    Enforces Heat Network (Metering and Billing) Regulations 2014.
    Maintains UK's first heat network database. Issues compliance notices
    and penalties for non-compliant operators. GOV.UK content, server-
    rendered. Important for understanding current enforcement regime before
    Ofgem takes over broader heat network regulation in January 2026.
```

---

## Sites Evaluated But Not Recommended

### News and Trade Media (Excluded)
| Site | Reason for Exclusion |
|------|---------------------|
| Data Center Dynamics (datacenterdynamics.com) | Industry news site, not official government source |
| Heating and Ventilation News (hvnplus.co.uk) | Trade press |
| Construction Enquirer | Industry news |

### Industry Associations (Excluded)
| Site | Reason for Exclusion |
|------|---------------------|
| techUK (techuk.org) | Trade body; administers CCA for data centers but not government |
| Energy UK (energy-uk.org.uk) | Energy industry trade body |
| Association for Decentralised Energy | Heat network trade body |
| Heat Networks Industry Council (heatnic.uk) | Government-industry advisory body, not primary policy source |
| European Data Centre Association | EU-level industry body |

### Academic/Research (Excluded)
| Site | Reason for Exclusion |
|------|---------------------|
| House of Commons Library (parliament.uk/research) | Secondary analysis/briefings, not primary policy |
| University research sites | Academic, not official policy repository |

### Consultancies and Think Tanks (Excluded)
| Site | Reason for Exclusion |
|------|---------------------|
| AECOM | Infrastructure consultancy (authored GLA report) |
| Institute for Government | Think tank |
| Gemserv | HNES delivery partner but not government body |

### Login-Required (Excluded)
| Site | Reason for Exclusion |
|------|---------------------|
| HNES Application Portal | Requires Expression of Interest registration |
| EPR.ofgem.gov.uk (parts) | Some sections require registration |

---

## Key Policy Context for Grid Cell 1.1

**Current UK Position on Data Center Heat Reuse:**

1. **No mandatory PUE limits** - Unlike Germany (requires PUE 1.3 for new data centers) or EU Energy Efficiency Directive requirements, UK has no statutory PUE caps

2. **No mandatory waste heat quotas** - Unlike Germany (10-20% waste heat utilization from July 2026), UK relies on voluntary participation via Climate Change Agreements and funding incentives

3. **Heat Network Zoning** - Energy Act 2023 enables zoning in England; data centers classified as "low temperature, near constant, recoverable heat sources" - encouraged but NOT mandated to connect

4. **Ofgem regulation effective 27 January 2026** - All heat network operators/suppliers must be authorized; potential future mandates for waste heat disclosure

5. **Scotland ahead** - Heat Networks (Scotland) Act 2021 requires waste heat source assessments and sets supply targets (6 TWh by 2030)

6. **Funding available** - GHNF (£180M+ awarded), HNES (£77M), Scotland's Heat Network Fund (£300M)

7. **First data center heat project** - Old Oak and Park Royal (London) £36M GHNF grant for UK's first data center waste heat network, 10,000+ homes by 2040

**JavaScript Rendering Summary:**
- Only **Ofgem** requires Playwright (beta site with JS-dependent navigation)
- All other sites are server-rendered HTML with no JavaScript required