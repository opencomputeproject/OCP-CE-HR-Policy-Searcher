# EU Data Center Energy Policy: Government Website Configuration Guide

The **EU Energy Efficiency Directive 2023/1791** mandates all member states transpose data center reporting requirements by October 11, 2025. Research across Spain, Italy, Poland, Portugal, and Czech Republic reveals significant variation in implementation progress, agency structures, and website accessibility. All five countries host relevant policy content through dedicated energy ministries and agencies, though JavaScript requirements and content organization vary substantially.

Spain leads with a **draft Royal Decree specifically targeting data centers** (public consultation completed September 2025), while Italy has developed **ENEA data center design guidelines** and robust White Certificate incentives. Poland's extensive district heating network (Europe's second largest) creates unique waste heat recovery opportunities. Portugal shows "serious gaps" in EED transposition despite hosting Europe's first gigascale renewable data campus, while Czech Republic relies primarily on EU-level requirements without additional national measures.

---

## Spain: Most advanced data center regulations

Spain's regulatory framework stands out for its **dedicated data center provisions**. MITECO hosts a specific data center section at `/es/energia/eficiencia/centros-de-datos.html` containing the draft Royal Decree implementing Article 12 of EED 2023/1791. Key requirements include mandatory annual reporting by May 15 for facilities ≥500kW IT load, waste heat reuse obligations for facilities ≥1MW (with cost-benefit analysis), and grid access conditionality tied to compliance.

IDAE complements MITECO as Spain's operational energy efficiency agency, managing the Heat Map of Spain tool useful for identifying waste heat recovery opportunities and participating in the **ODYSSEE-MURE** monitoring project. Both sites render without JavaScript and offer multilingual content including English.

```yaml
# ============================================
# SPAIN - ENERGY MINISTRY AND AGENCIES
# ============================================

- name: "MITECO - Ministry for Ecological Transition"
  name_local: "Ministerio para la Transición Ecológica y el Reto Demográfico"
  id: eu_spain_miteco
  enabled: true
  base_url: "https://www.miteco.gob.es"
  start_paths:
    - "/es/energia/eficiencia/centros-de-datos.html"
    - "/es/energia/eficiencia/"
    - "/es/energia/participacion/"
    - "/es/cambio-climatico/temas.html"
    - "/es/energia/estrategia-normativa/"
    - "/en/energia/"
  allowed_path_patterns:
    - "/*/energia/eficiencia/*"
    - "/*/energia/participacion/*"
    - "/*/cambio-climatico/*"
    - "/*/energia/estrategia-normativa/*"
  blocked_path_patterns:
    - "/*/ministerio/empleo-publico/*"
    - "/*/cartografia-y-sig/*"
    - "/*/costas/*"
    - "/*/biodiversidad/*"
  max_depth: 4
  language: "es"
  language_alternatives: ["en", "ca", "gl", "eu"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "energy_ministry"
  tags:
    - mandates
    - reporting
    - efficiency
    - heat_reuse
    - carbon
    - planning
    - data_centers
  policy_types:
    - regulation
    - directive
    - guidance
    - consultation
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Primary authority for data center energy policy. Hosts dedicated data center section 
    with draft Royal Decree (consultation closed Sep 2025). Key contact: bzn-cd-sgeae@miteco.es.
    Site uses Adobe Experience Manager CMS, renders without JavaScript.
    Draft Royal Decree requires: PUE/WUE/ERF reporting for ≥500kW, waste heat CBA for ≥1MW,
    EU Code of Conduct compliance for ≥1MW, top 15% performance for >100MW facilities.

- name: "IDAE - Institute for Energy Diversification and Saving"
  name_local: "Instituto para la Diversificación y Ahorro de la Energía"
  id: eu_spain_idae
  enabled: true
  base_url: "https://www.idae.es"
  start_paths:
    - "/en/technologies/energy-efficiency/"
    - "/en/information-and-notifications/"
    - "/en/support-and-funding/"
    - "/en/technologies/energy-efficiency/conversion-energy/heatmap-spain"
    - "/en/information-and-notifications/national-integrated-energy-and-climate-plan-pniec-2021-2030"
  allowed_path_patterns:
    - "/*/technologies/energy-efficiency/*"
    - "/*/information-and-notifications/*"
    - "/*/support-and-funding/*"
  blocked_path_patterns:
    - "/perfil-de-contratante*"
    - "/*/human-resources/*"
    - "/sede-electronica/*"
  max_depth: 4
  language: "es"
  language_alternatives: ["en", "ca", "eu", "gl"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "energy_efficiency_agency"
  tags:
    - incentives
    - efficiency
    - guidance
    - funding
    - statistics
    - heat_networks
    - research
  policy_types:
    - guidance
    - incentive
    - report
    - technical_resource
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Operational energy efficiency agency under MITECO. Manages Heat Map of Spain tool
    (Article 14 EED implementation) for waste heat planning. Participates in ODYSSEE-MURE
    monitoring project. Drupal CMS, no JavaScript required. Supports PNIEC 2023-2030
    implementation (81% renewable electricity target by 2030).
```

---

## Italy: Rich incentive ecosystem requiring JavaScript

Italy's three-agency structure covers policy (MASE), technical guidance (ENEA), and incentives (GSE). ENEA has developed **specific data center design guidelines** in collaboration with FIRE, covering PUE monitoring, efficient cooling, and automatic control systems. GSE manages the **Certificati Bianchi (White Certificates)** program—Italy's primary efficiency incentive since 2005—which data centers can leverage for cooling, lighting, and cogeneration improvements.

All three Italian sites require JavaScript/Playwright due to heavy frontend frameworks and bot protection (403 errors on direct fetch). Italy has active waste heat projects: Retelit Avalon 3 in Milan (operational early 2026, 1,250 households) and A2A/Qarnot in Brescia (Italy's first liquid-cooled DC connected to district heating).

```yaml
# ============================================
# ITALY - ENERGY MINISTRY AND AGENCIES
# ============================================

- name: "MASE - Ministry of Environment and Energy Security"
  name_local: "Ministero dell'Ambiente e della Sicurezza Energetica"
  id: eu_italy_mase
  enabled: true
  base_url: "https://www.mase.gov.it"
  start_paths:
    - "/pagina/"
    - "/portale/"
    - "/en/"
    - "/energia/"
  allowed_path_patterns:
    - "/pagina/*"
    - "/portale/*"
    - "/energia/*"
    - "/en/*"
    - "/documenti/*"
  blocked_path_patterns:
    - "/login/"
    - "/admin/"
    - "/media/"
  max_depth: 4
  language: "it"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: true
  rate_limit_seconds: 3
  category: "energy_ministry"
  tags:
    - mandates
    - reporting
    - carbon
    - planning
    - climate
    - strategy
  policy_types:
    - law
    - regulation
    - directive
    - strategy
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Primary ministry for energy and environment policy. Returns 403 on direct fetch - 
    requires Playwright/browser automation. Legacy domains mite.gov.it and mise.gov.it 
    may still host some content. Responsible for EED 2023/1791 transposition 
    (deadline Oct 2025). Collaborates with ENEA on data center guidelines.

- name: "ENEA - National Agency for New Technologies, Energy and Sustainable Economic Development"
  name_local: "Agenzia Nazionale per le Nuove Tecnologie, l'Energia e lo Sviluppo Economico Sostenibile"
  id: eu_italy_enea
  enabled: true
  base_url: "https://www.enea.it"
  secondary_urls:
    - "https://www.efficienzaenergetica.enea.it"
    - "https://audit102.enea.it"
  start_paths:
    - "/en/"
    - "/servizi-per/imprese/diagnosi-energetiche/"
    - "/servizi-per/imprese/diagnosi-energetiche/linee-guida-settoriali.html"
    - "/servizi-per/pubblica-amministrazione/"
    - "/pubblicazioni/"
  allowed_path_patterns:
    - "/en/*"
    - "/servizi-per/*"
    - "/archivio/*"
    - "/pubblicazioni/*"
  blocked_path_patterns:
    - "/login/"
    - "/reserved/"
    - "/intranet/"
  max_depth: 4
  language: "it"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: true
  rate_limit_seconds: 3
  category: "research_agency"
  tags:
    - efficiency
    - guidelines
    - mandates
    - reporting
    - audits
    - research
    - data_centers
  policy_types:
    - guideline
    - regulation
    - report
    - technical_standard
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    National Agency for Energy Efficiency under D.Lgs. 115/2008. CRITICAL: Hosts data center
    design guidelines ("Linee guida per la progettazione di datacenter ad alta efficienza")
    developed with FIRE. Manages Audit102 portal for mandatory energy audits. Operates
    LEAPto11 EU project. Mandatory audits for enterprises >250 employees or >€50M turnover.
    SSL/fetch issues - requires Playwright.

- name: "GSE - Energy Services Manager"
  name_local: "Gestore dei Servizi Energetici S.p.A."
  id: eu_italy_gse
  enabled: true
  base_url: "https://www.gse.it"
  start_paths:
    - "/en/"
    - "/servizi-per-te/efficienza-energetica/"
    - "/servizi-per-te/efficienza-energetica/certificati-bianchi/"
    - "/servizi-per-te/efficienza-energetica/conto-termico/"
    - "/dati-e-scenari/rapporti/"
    - "/dati-e-scenari/open-data/"
    - "/servizi-per-te/attuazione-misure-pnrr/"
  allowed_path_patterns:
    - "/en/*"
    - "/servizi-per-te/*"
    - "/dati-e-scenari/*"
    - "/documenti_site/*"
  blocked_path_patterns:
    - "/Area-Clienti/"
    - "*.service-now.com/*"
  max_depth: 4
  language: "it"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: true
  rate_limit_seconds: 3
  category: "regulatory"
  tags:
    - incentives
    - efficiency
    - reporting
    - certificates
    - cogeneration
    - carbon
  policy_types:
    - incentive
    - regulation
    - guidance
    - report
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    100% owned by Ministry of Economy. Manages Certificati Bianchi (White Certificates/TEE)
    since DM 11/01/2017 - Italy's primary efficiency incentive (28+ Mtoe cumulative savings).
    Data centers eligible for WCs on cooling, lighting, motors, CHP improvements.
    Also manages Conto Termico 2.0 (€900M/year thermal efficiency incentives, 40-65% rates).
    Heavy JavaScript framework - returns 403 on direct fetch.
```

---

## Poland: Extensive district heating creates unique opportunities

Poland hosts Eastern Europe's largest data center market centered on Warsaw, with **1,200MW of grid capacity** allocated for data centers through 2034. The gov.pl platform provides excellent accessibility (no JavaScript required) for both the Ministry of Climate and Environment and NFOŚiGW. Poland's **second-largest district heating network in Europe** creates substantial waste heat recovery potential—the Beyond.pl + Veolia project in Poznań targets 30 MWt capacity.

The **White Certificates system (Białe Certyfikaty)** allows data centers to earn tradeable certificates for efficiency improvements exceeding 10 toe (~116.3 MWh) annual savings. NFOŚiGW administers substantial funding: PLN 4.15 billion for energy storage and PLN 3 billion for cogeneration projects.

```yaml
# ============================================
# POLAND - ENERGY MINISTRY AND AGENCIES
# ============================================

- name: "Ministry of Climate and Environment"
  name_local: "Ministerstwo Klimatu i Środowiska"
  id: eu_poland_climate_ministry
  enabled: true
  base_url: "https://www.gov.pl/web/klimat"
  base_url_en: "https://www.gov.pl/web/climate"
  start_paths:
    - "/web/klimat/efektywnosc-energetyczna"
    - "/web/klimat/krajowy-plan-na-rzecz-energii-i-klimatu"
    - "/web/climate/energy-policy-of-poland-until-2040-epp2040"
    - "/web/climate/national-energy-and-climate-plan"
    - "/web/klimat/cieplo-przyszlosci---tanio-czysto-bezpiecznie2"
  allowed_path_patterns:
    - "/web/klimat/*"
    - "/web/climate/*"
    - "/attachment/*"
  blocked_path_patterns:
    - "/web/klimat/aktualnosci"
    - "/photo/*"
  max_depth: 4
  language: "pl"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "energy_ministry"
  tags:
    - mandates
    - reporting
    - efficiency
    - planning
    - carbon
    - district_heating
    - waste_heat
  policy_types:
    - law
    - regulation
    - strategy
    - guidance
    - incentive
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Primary authority for EED transposition and energy efficiency. Governs White Certificates
    system (Ustawa o efektywności energetycznej, May 2016). Manages CROEF registry (energy
    savings tracking since Jan 2021). District Heating Strategy 2040 explicitly includes
    waste heat recovery. PEP2040 targets 85% efficient district heating by 2040.
    Gov.pl platform renders without JavaScript. Key laws: Dz.U.2016.831.

- name: "NFOŚiGW - National Fund for Environmental Protection"
  name_local: "Narodowy Fundusz Ochrony Środowiska i Gospodarki Wodnej"
  id: eu_poland_nfosigw
  enabled: true
  base_url: "https://www.gov.pl/web/nfosigw"
  base_url_en: "https://www.gov.pl/web/nfosigw-en"
  start_paths:
    - "/web/nfosigw/oferta-finansowania"
    - "/web/nfosigw/energia-plus"
    - "/web/nfosigw-en/priority-programmes"
    - "/web/modernisation-fund"
    - "/web/nfosigw/kogeneracja-dla-cieplownictwa-czesc-1---ii-nabor"
  allowed_path_patterns:
    - "/web/nfosigw/*"
    - "/web/nfosigw-en/*"
    - "/web/modernisation-fund/*"
  blocked_path_patterns:
    - "/web/nfosigw/aktualnosci"
  max_depth: 4
  language: "pl"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "funding"
  tags:
    - incentives
    - funding
    - grants
    - loans
    - efficiency
    - cogeneration
    - district_heating
    - storage
  policy_types:
    - incentive
    - grant_program
    - loan_program
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Main funding body for energy efficiency investments. Key programs: Energy storage
    (PLN 4.15B, 172 projects, 14.5 GWh), Cogeneration for Heating (PLN 3B 2022-2030),
    District heating infrastructure (€1.183B via EU FENX), Energia Plus (industrial efficiency).
    Co-financing 45-65% of eligible costs. English version limited but key programs described.
    Contact: fundusz@nfosigw.gov.pl, energiadlawsi@nfosigw.gov.pl.
```

---

## Portugal: Implementation gaps despite renewable leadership

Despite generating **87.4% renewable electricity** (2024) and hosting the Start Campus SINES gigascale development (€8.5B, PUE 1.1), Portugal shows "serious gaps" in EED 2023 transposition according to Energy Cities tracking. DGEG serves as the primary energy policy authority, hosting district heating potential assessments and the PNEC 2030. ADENE manages **SGCIE**—the intensive energy consumption system covering facilities ≥500 toe/year (~5.8 GWh)—which captures large data centers through mandatory audits and 4-6% efficiency improvement requirements.

Portugal's limited district heating infrastructure (only Parque das Nações in Lisbon operates large-scale DHC) constrains immediate waste heat recovery opportunities, though ADENE participates in the **EMB3Rs** EU waste heat matching project.

```yaml
# ============================================
# PORTUGAL - ENERGY MINISTRY AND AGENCIES
# ============================================

- name: "DGEG - Directorate-General for Energy and Geology"
  name_local: "Direção-Geral de Energia e Geologia"
  id: eu_portugal_dgeg
  enabled: true
  base_url: "https://www.dgeg.gov.pt"
  start_paths:
    - "/en/vertical-areas/energy/energy-efficiency/"
    - "/en/vertical-areas/energy/energy-planning-and-security-of-supply/"
    - "/en/vertical-areas/energy/energy-sustainability-division/"
    - "/en/transversal-areas/research-and-innovation/publications-reports-studies/"
    - "/en/statistics/energy-statistics/"
  allowed_path_patterns:
    - "/*/energy/*"
    - "/*/energy-efficiency/*"
    - "/*/statistics/*"
    - "/*/research-and-innovation/*"
    - "/*/climate/*"
  blocked_path_patterns:
    - "/*/geology/*"
    - "/*/mines/*"
    - "/*/petroleum/*"
  max_depth: 4
  language: "pt"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "energy_ministry"
  tags:
    - efficiency
    - planning
    - reporting
    - mandates
    - statistics
    - district_heating
  policy_types:
    - law
    - directive
    - report
    - national_plan
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Primary energy policy authority; 69.66% shareholder in ADENE. EED transposition via
    Decree-Law 68-A/2015 (original directive). Has published "Assessment of District Heating
    and Cooling Potential in Portugal" and "Waste Heat in Portugal" studies. Portugal shows
    "serious gaps" in EED 2023 transposition (Energy Cities Oct 2025 tracker).
    Site well-structured with good English coverage.

- name: "ADENE - Portuguese Energy Agency"
  name_local: "ADENE - Agência para a Energia"
  id: eu_portugal_adene
  enabled: true
  base_url: "https://www.adene.pt"
  start_paths:
    - "/sgcie/"
    - "/eficiencia-energetica/"
    - "/certificacao/"
    - "/sce/"
    - "/observatorio/"
  allowed_path_patterns:
    - "/sgcie/*"
    - "/eficiencia*"
    - "/certificacao/*"
    - "/sce/*"
    - "/formacao/*"
  blocked_path_patterns:
    - "/agua/*"
  max_depth: 4
  language: "pt"
  language_alternatives: []
  region:
    - "eu"
  requires_playwright: true
  rate_limit_seconds: 3
  category: "energy_agency"
  tags:
    - efficiency
    - reporting
    - mandates
    - certification
    - audits
    - training
  policy_types:
    - regulation
    - certification
    - guidance
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Manages SGCIE (Intensive Energy Consumption Management System) under Decree-Law 71/2008.
    CRITICAL: 500 toe threshold (~5.8 GWh) captures large data centers. Mandatory 8-year
    audits, 4-6% energy intensity reduction required. SGCIE being updated for EED 2023
    Article 11 (new thresholds: monitoring ≥100 toe, audits ≥240 toe, 4-year audit period).
    Participates in EMB3Rs waste heat matching project. Site likely requires JavaScript.

- name: "APA - Portuguese Environment Agency"
  name_local: "Agência Portuguesa do Ambiente"
  id: eu_portugal_apa
  enabled: true
  base_url: "https://apambiente.pt"
  start_paths:
    - "/clima/"
    - "/en/clima/"
    - "/avaliacoes-ambientais/"
    - "/sites/default/files/_Clima/"
  allowed_path_patterns:
    - "/clima/*"
    - "/en/clima/*"
    - "/avaliacoes-ambientais/*"
    - "/economia-circular/*"
    - "/sites/default/files/*"
  blocked_path_patterns:
    - "/agua/*"
    - "/residuos/*"
  max_depth: 4
  language: "pt"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "environmental_agency"
  tags:
    - carbon
    - climate
    - planning
    - reporting
    - environmental_assessment
  policy_types:
    - national_plan
    - regulation
    - report
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Hosts PNEC 2030 official document. EU ETS competent authority. Climate neutrality
    target advanced to 2045 (from 2050). RNC 2050 roadmap via Council of Ministers
    Resolution 107/2019. Environmental licensing may apply to large data centers.
    800+ employees, National Focal Point for EEA EIONET network.
```

---

## Czech Republic: Funding-rich but policy-light

Czech Republic relies primarily on EU-level EED requirements without additional national data center measures. The **State Environmental Fund (SFŽP)** offers the most accessible content with substantial funding through the **Modernisation Fund** (minimum 300 billion CZK) and **New Green Savings** program (117 billion CZK paid to 500,000 beneficiaries 2009-2024). MPO manages EED transposition through Act 406/2000 on Energy Management.

MZP requires Playwright due to **418 bot protection errors**, though PDF documents at `/system/files/` may be directly accessible. Czech Republic's strong district heating tradition (41% of households, 600+ licensed entities) and EU-approved **€401 million green district heating scheme** create waste heat recovery opportunities despite the absence of data center-specific mandates.

```yaml
# ============================================
# CZECH REPUBLIC - ENERGY MINISTRY AND AGENCIES
# ============================================

- name: "MPO - Ministry of Industry and Trade"
  name_local: "Ministerstvo průmyslu a obchodu České republiky"
  id: eu_czechia_mpo
  enabled: true
  base_url: "https://mpo.gov.cz"
  start_paths:
    - "/en/energy/"
    - "/en/energy/energy-efficiency/"
    - "/en/energy/strategic-and-conceptual-documents/"
    - "/en/energy/statistics/"
    - "/en/energy/energy-efficiency/strategic-documents/"
  allowed_path_patterns:
    - "/en/energy/*"
    - "/en/industry/*"
    - "/assets/en/energy/*"
  blocked_path_patterns:
    - "/cz/"
  max_depth: 4
  language: "cs"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "energy_ministry"
  tags:
    - efficiency
    - reporting
    - mandates
    - planning
    - buildings
    - industry
  policy_types:
    - law
    - regulation
    - strategy
    - national_plan
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    Primary authority for EED implementation via Act 406/2000 on Energy Management.
    Manages NECP (updated 2023) and NEEAP. No Czech-specific data center threshold
    below EU 500kW identified. Works with MZP and Ministry of Regional Development
    on EED implementation. robots.txt restricts some /en/energy/ direct fetching.
    State Energy Policy (SEP 2015) under revision for 2040+ horizon.

- name: "MZP - Ministry of the Environment"
  name_local: "Ministerstvo životního prostředí České republiky"
  id: eu_czechia_mzp
  enabled: true
  base_url: "https://www.mzp.cz"
  start_paths:
    - "/en/ministry"
    - "/en/climate"
    - "/cz/zmena_klimatu/"
    - "/system/files/"
  allowed_path_patterns:
    - "/en/*"
    - "/cz/zmena_klimatu/*"
    - "/system/files/*"
  blocked_path_patterns:
    - "/cz/sluzby/*"
    - "/cz/urad/*"
  max_depth: 4
  language: "cs"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: true
  rate_limit_seconds: 3
  category: "environmental_agency"
  tags:
    - climate
    - carbon
    - environmental_policy
    - reporting
    - adaptation
  policy_types:
    - policy
    - strategy
    - guidance
    - report
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    CRITICAL: Site has bot protection returning 418 errors - REQUIRES PLAYWRIGHT.
    PDFs at /system/files/ may be directly accessible. Climate Protection Policy
    updated 2021 (37.1% GHG reduction vs 1990 by 2023). NEP 2030 includes energy
    efficiency targets. Coordinates environmental aspects of EED with SFŽP.
    Less direct data center involvement than MPO.

- name: "SFŽP - State Environmental Fund of the Czech Republic"
  name_local: "Státní fond životního prostředí České republiky"
  id: eu_czechia_sfzp
  enabled: true
  base_url: "https://www.sfzp.cz"
  alternate_url: "https://sfzp.gov.cz"
  start_paths:
    - "/en/administered-programmes/"
    - "/en/about-the-modernisation-fund/"
    - "/en/administered-programmes/new-green-savings-programme/"
    - "/en/administered-programmes/operational-programme-environment/"
    - "/en/administered-programmes/national-programme-environment/"
    - "/en/about-us/what-we-do/"
  allowed_path_patterns:
    - "/en/*"
    - "/en/administered-programmes/*"
    - "/en/about-the-modernisation-fund/*"
  blocked_path_patterns:
    - "/wp-content/themes/*"
    - "/wp-content/plugins/*"
  max_depth: 4
  language: "cs"
  language_alternatives: ["en"]
  region:
    - "eu"
  requires_playwright: false
  rate_limit_seconds: 2
  category: "funding"
  tags:
    - incentives
    - funding
    - subsidies
    - efficiency
    - renewables
    - modernisation_fund
    - green_savings
    - buildings
  policy_types:
    - incentive
    - funding
    - guidance
  verified_by: "automated_research"
  verified_date: "2026-01-06"
  notes: |
    BEST ACCESSIBLE Czech agency - clean WordPress site, excellent English content.
    Key programs: New Green Savings (117B CZK paid, 500K beneficiaries 2009-2024),
    Modernisation Fund (min 300B CZK - includes ENERG for EU ETS industrial efficiency),
    OP Environment 2021-2027 (€2.4B). 2025 budget: 45.5B CZK. Most relevant for
    data center operators seeking efficiency funding. Receives EU ETS allowance revenues.
```

---

## Sites evaluated but not recommended

| Agency | Country | URL | Reason for Exclusion |
|--------|---------|-----|---------------------|
| URE (Energy Regulatory Office) | Poland | ure.gov.pl | Regulatory/licensing focus, limited policy content for tracking purposes |
| Ministry of Digital Affairs | Poland | gov.pl/web/cyfryzacja | Digitalization strategy relevant but not primary for energy efficiency |
| Climaespaço | Portugal | climaespaco.pt | Commercial district heating operator, not government policy source |
| GME (Energy Markets Manager) | Italy | mercatoelettrico.org | Market platform for certificate trading, not policy content |
| ARERA | Italy | arera.it | Regulatory authority focused on tariffs, less relevant for policy tracking |

---

## Implementation comparison and key metrics

Spain's draft Royal Decree represents the **most comprehensive national data center framework**, with requirements exceeding EU minimums (grid access conditionality, socioeconomic reporting). Italy's mature White Certificate market and ENEA guidelines provide actionable efficiency pathways. Poland's combination of white certificates, substantial NFOŚiGW funding, and extensive district heating creates a uniquely favorable environment for waste heat projects.

| Country | DC-Specific Law | Waste Heat Mandate | Key Threshold | JS Required |
|---------|-----------------|-------------------|---------------|-------------|
| Spain | Draft Royal Decree (2025) | ≥1MW (CBA required) | ≥500kW reporting | No |
| Italy | Via EED transposition | EED Article 12 | ≥500kW reporting | Yes (all 3) |
| Poland | Via EED transposition | EED Article 12 | ≥500kW reporting | No |
| Portugal | Gaps identified | No national mandate | SGCIE ≥500 toe | Partial |
| Czech Rep. | Via EED transposition | EED Article 12 | ≥500kW reporting | Partial |

Active waste heat projects demonstrate feasibility: Milan's **Retelit Avalon 3** (2.5MW, 1,250 households), Brescia's **A2A/Qarnot** (3,500 tCO2/year avoided), and Poznań's **Beyond.pl + Veolia** (30 MWt planned). These projects validate the technical and economic viability of data center heat recovery that the EED 2023 recast now mandates member states to facilitate.