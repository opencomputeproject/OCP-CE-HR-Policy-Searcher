# Grid Cell 6.4: US States Grid Operators and Regulators

The eight US states with growing data center markets—Iowa, Indiana, Nevada, Utah, South Carolina, Tennessee, Montana, and Wisconsin—are served by a complex network of regional transmission organizations, investor-owned utilities, federal power agencies, and state regulatory commissions. **Indiana and Wisconsin have the most advanced data center-specific tariff policies**, with approved large load frameworks targeting 70+ MW customers. Tennessee's TVA operates the most established data center recruitment program, while South Carolina's Santee Cooper implemented an experimental data center rate schedule in April 2025 specifically for facilities exceeding 50 MW.

---

## Regional transmission organizations

### MISO (Midcontinent Independent System Operator)

| Field | Value |
|-------|-------|
| **Official Name** | Midcontinent Independent System Operator (MISO) |
| **Base URL** | https://www.misoenergy.org |
| **Category** | grid_operator |
| **JavaScript Required** | Yes |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/planning/resource-utilization/generator-interconnection/`
- `/planning/transmission-planning/mtep/`
- `/planning/long-range-transmission-planning/`
- `/planning/resource-utilization/GI_Queue/`
- `/engage/stakeholder-feedback/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| guidance | Large Load Interconnection Whitepaper | cdn.misoenergy.org/MISO Load Interconnection Whitepaper629693.pdf |
| report | Generator Interconnection Queue (interactive) | /planning/resource-utilization/GI_Queue/ |
| planning | MTEP Annual Transmission Planning | /planning/transmission-planning/mtep/ |
| planning | Long Range Transmission Planning (Tranche 1: $10.3B, Tranche 2.1: $21.8B) | /planning/long-range-transmission-planning/ |
| guidance | Expedited Project Review (EPR) for urgent large loads | Stakeholder process |

**Tags:** interconnection, capacity, planning, queue, large-load

**Notes:** MISO faces major data center growth challenges—the 2023 cycle received **123 GW of interconnection requests**. Implements queue cap of 50% of non-coincident peak load per study region. MTEP25 includes 435 projects supporting 11.6 GW spot load additions. Uses Expedited Project Review process for urgent large load additions outside standard MTEP cycle. Serves Iowa, Indiana (partial), Wisconsin, and parts of Montana.

---

### PJM Interconnection

| Field | Value |
|-------|-------|
| **Official Name** | PJM Interconnection, LLC |
| **Base URL** | https://www.pjm.com |
| **Category** | grid_operator |
| **JavaScript Required** | Yes |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/planning/service-requests/interconnection-process-reform`
- `/planning/service-requests/`
- `/planning/rtep-development/stakeholder-process/developers`
- `/planning/resource-adequacy-planning/`
- `/committees-and-groups/subcommittees/ips`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | Interconnection Process Reform (FERC-approved cycle approach) | /planning/service-requests/interconnection-process-reform |
| guidance | Reliability Resource Initiative (RRI) fast-track | 51 projects totaling 11,800 MW selected May 2025 |
| guidance | Large Load Additions Workshop | /committees-groups/workshops/llaw/ |
| tariff | Capacity Market (RPM) rules | Record-high $333.44/MW-day cap in 2027/28 auction |
| guidance | Manual 14G/14H - Interconnection procedures | PJM Manual Library |

**Tags:** interconnection, capacity, rates, planning, queue, data-center

**Notes:** PJM faces unprecedented data center demand—projecting **32 GW additional demand by 2028, 60 GW by 2030**. Data centers accounted for 40% of capacity costs in recent auction. Active Large Load Additions Workshop with ongoing stakeholder process on data center interconnection reforms. Serves parts of Indiana (border region with Indiana Michigan Power territory).

---

### Tennessee Valley Authority (TVA)

| Field | Value |
|-------|-------|
| **Official Name** | Tennessee Valley Authority (TVA) |
| **Base URL** | https://www.tva.com |
| **Alternative URLs** | https://tvasites.com (economic development), https://www.tva.gov |
| **Category** | grid_operator (federal power agency) |
| **JavaScript Required** | Yes (returns 403 on direct fetch; requires browser) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/about-tva/tva-rates`
- `/economic-development/`
- `/energy/our-power-system/`
- `/about-tva/reports/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Wholesale Rate Structure (seasonal time-of-use) | /about-tva/tva-rates |
| tariff | Direct Serve Program for loads >5,000 kW | 58 industrial customers served directly |
| guidance | Economic Development Rate Incentives (since 2008) | Board-approved data center incentives |
| report | Integrated Resource Plan | /about-tva/reports/ |
| guidance | Power Supply Flexibility Agreement | 102 LPCs signed as of Sept 2024 |

**Tags:** rates, economic-development, planning, capacity, wholesale, data-center-incentives

**Notes:** TVA is a **federally regulated power agency** (not subject to state PUC oversight) serving 10 million people across 7 states through 153 local power companies. Most established data center recruitment program with dedicated sites at tvasites.com. Has worked with Google ($600M), Facebook, Amazon. Operates xAI supercluster in Memphis (150 MW approved). Industrial rates lower than ~90% of top 100 US utilities. **99.999% reliability**. Active demand response program targeting 2,800 MW by 2030.

---

### CAISO (California Independent System Operator)

| Field | Value |
|-------|-------|
| **Official Name** | California Independent System Operator (California ISO) |
| **Base URL** | https://www.caiso.com |
| **Category** | grid_operator |
| **JavaScript Required** | No (most crawler-friendly site) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/generation-transmission/generation/generator-interconnection/`
- `/generation-transmission/generation/generator-interconnection/queue-management`
- `/legal-regulatory/tariff/`
- `/legal-regulatory/business-practice-manuals/`
- `/stakeholder/`
- `/library/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Generator Interconnection (GIDAP) - Appendix DD | /legal-regulatory/tariff/ |
| regulation | Resource Interconnection Standards (RIS) - Appendix KK | Cluster-based study approach |
| report | Queue Reports (Cluster 14, 15) | rimspub.caiso.com/rimsui/ |
| guidance | Business Practice Manuals | /legal-regulatory/business-practice-manuals/ |
| guidance | Western Energy Imbalance Market (WEIM) | westerneim.com |

**Tags:** interconnection, queue, deliverability, WEIM, tariff, western-markets

**Notes:** CAISO operates the Western Energy Imbalance Market extending to **11 western states including Nevada**, with $7.82B in cumulative benefits since 2014. Extended Day-Ahead Market (EDAM) launching 2026. Best-structured website for crawling—clean HTML, no JavaScript required. POI Heatmap provides interactive visualization of available interconnection capacity. Cluster-based interconnection process with defined phases.

---

## Major utilities serving target states

### NV Energy (Nevada)

| Field | Value |
|-------|-------|
| **Official Name** | NV Energy (Nevada Power Company / Sierra Pacific Power Company) |
| **Base URL** | https://www.nvenergy.com |
| **Category** | utility |
| **JavaScript Required** | Yes (Angular-based, Microsoft Azure) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/about-nvenergy/rates-regulatory`
- `/publish/content/dam/nvenergy/brochures_arch/about-nvenergy/rates-regulatory/electric-schedules-south/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Clean Transition Tariff (CTT) - pending approval | For 5 MW+ loads seeking clean generation |
| tariff | Rule 9 (Transmission cost allocation) | Direct allocation to large users |
| tariff | Rule 15 (Generation cost allocation) | Direct allocation to large users |
| tariff | Large General Service Schedules (LGS-X) | High-demand commercial rates |
| regulation | Take-or-Pay Programs | Letters of credit required |

**Tags:** interconnection, rates, capacity, planning, renewable, data-center-specific

**Notes:** Active data center market with Google facilities in Storey County. Clean Transition Tariff application filed for **Google's 115 MW Fervo geothermal project** (Docket 24-05023, 24-06014). Rule 9/Rule 15 framework isolates infrastructure costs to data center customers, protecting residential ratepayers. Nevada RPS requires 50% renewable by 2030, 100% carbon-free goal by 2050.

---

### Rocky Mountain Power / PacifiCorp (Utah)

| Field | Value |
|-------|-------|
| **Official Name** | Rocky Mountain Power (PacifiCorp subsidiary) |
| **Base URL** | https://www.rockymountainpower.net |
| **Category** | utility |
| **JavaScript Required** | Yes |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/about/rates-regulation/utah-rates-tariffs.html`
- `/savings-energy-choices/customer-generation/large-interconnections.html`
- `/savings-energy-choices/customer-generation/qualifying-facilities.html`
- `/working-with-us/large-service-requests.html`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Schedule 8 - Large General Service (1,000+ kW) | Distribution voltage |
| tariff | Schedule 9/9A - High Voltage / Energy Time of Day | Transmission voltage |
| tariff | Schedule 34 - Clean Energy Purchases (5,000+ kW) | Clean energy for qualified customers |
| tariff | Schedule 38 - Qualifying Facility Procedures | PURPA compliance |
| guidance | Large Interconnections (FERC Order 2003/2006 compliant) | Tier system: Level 1-3 based on kW |

**Tags:** interconnection, rates, capacity, planning, renewable, large-customer

**Notes:** Serves ~75% of Utah with 1+ million customers. **Utah SB132 (signed 2025)** creates new framework for large loads 100+ MW allowing RMP to contract individually with data centers requiring 50+ MW without affecting rates for existing customers. Utility has 90 days to evaluate large load impact. Third-party generators can serve large loads if RMP cannot. PSC implementing large load fee structure in Docket 25-R318-01.

---

### NorthWestern Energy (Montana)

| Field | Value |
|-------|-------|
| **Official Name** | NorthWestern Energy Group, Inc. |
| **Base URL** | https://www.northwesternenergy.com |
| **Category** | utility |
| **JavaScript Required** | Partial (Microsoft SQL Server, Sitefinity CMS) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/account-services/for-business/key-accounts`
- `/about-us/our-company`
- `/docs/default-source/default-document-library/billing-and-payment/rates-and-tariffs/montana/rules/electric/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| guidance | Key Account Services for large industrial | Load Interconnection Studies for 1+ MW |
| tariff | Montana Open Access Transmission Tariff (OATT) | FERC-compliant LGIP/SGIP |
| guidance | Rule 17 - Electric interconnection | Net-metered facilities |
| tariff | Large Load Tariff (pending) | Separate rate class for data centers |

**Tags:** interconnection, rates, capacity, planning, large-customer, data-center

**Notes:** Planning to serve at least three data centers scaling to **2,250 MW by 2030** (nearly twice current 1,300 MW peak). Announced deal with Quantica Infrastructure for 1,000 MW data center. Montana PSC ruled September 2025 that NorthWestern must inform potential customers with loads >5 MW about alternative supplier options. Black Hills Corp. merger planned for late 2026. OASIS system: oasis.oati.com/NWMT for interconnection queue.

---

### Duke Energy Carolinas / Progress (South Carolina)

| Field | Value |
|-------|-------|
| **Official Name** | Duke Energy Carolinas, LLC / Duke Energy Progress, LLC |
| **Base URL** | https://www.duke-energy.com |
| **Category** | utility |
| **JavaScript Required** | Yes |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/home/billing/rates`
- `/business/billing/rates`
- `/home/billing/dec-sc-rates`
- `/home/billing/de-progress-rates`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Business Rate Tiers | Multiple industrial options |
| guidance | Interconnection (Tiered: Tier 1-3 based on kW) | Solar/generation connection |
| tariff | Time-of-Use Rates (R-TOU-CPP, R-TOUD) | Demand management |
| regulation | SC Rate Cases (2025) | Docket 2025-250-E (DEC), 2025-154-E (DEP) |

**Tags:** rates, interconnection, economic-development, capacity, planning

**Notes:** DEC serves ~680,000 retail customers in upstate SC (Greenville, Spartanburg, Anderson); DEP serves ~177,000 in central/northeastern SC. Rate cases filed July 2025. Tariffs available at etariff.psc.sc.gov/Organization/Detail/407.

---

### Dominion Energy South Carolina

| Field | Value |
|-------|-------|
| **Official Name** | Dominion Energy South Carolina, Inc. |
| **Base URL** | https://www.dominionenergy.com/south-carolina |
| **Category** | utility |
| **JavaScript Required** | Yes |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/south-carolina/large-business-services`
- `/south-carolina/rates-and-tariffs`
- `/south-carolina/save-energy`
- `/economic-development`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | Rate Schedules 23/24 - Industrial | Large customer rates |
| tariff | Interruptible Service Program (1,000+ kW) | June-Sept curtailment |
| guidance | MV-WEB™ interval meter data service | Load profiling |
| guidance | Assigned Account Managers | Annual reviews for large customers |

**Tags:** rates, interconnection, economic-development, large-load, interruptible

**Notes:** Serves 3.6 million homes/businesses in VA, NC, SC. Acquired SCANA Corporation in 2019. Promotes: "Half of the United States' Internet traffic runs through our backyard." Large Business line: 866-913-9762. Tariffs at etariff.psc.sc.gov/Organization/Detail/411.

---

### Santee Cooper (South Carolina Public Service Authority)

| Field | Value |
|-------|-------|
| **Official Name** | South Carolina Public Service Authority (Santee Cooper) |
| **Base URL** | https://www.santeecooper.com |
| **Economic Development URL** | https://www.poweringsc.com |
| **Category** | utility (state-owned) |
| **JavaScript Required** | Yes (but content accessible) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/rates/`
- `/about/integrated-resource-plan/`
- `/rates/stakeholder-engagement/`
- `/policies-reference-materials/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | **Experimental Large Load Schedule (L-25-LL)** - DATA CENTER SPECIFIC | Mandatory for data centers >50 MW |
| tariff | Large Light & Power Schedule (L-25) | Customers contracting 1,000+ kW |
| tariff | Economic Development Service Rider (L-25-ED) | New incentive rider |
| tariff | Interruptible Rider (L-25-I) | Curtailable service |
| tariff | Economy Power Rider (L-25-EP) | Real-time pricing |

**Tags:** rates, economic-development, large-load, data-center, interconnection, planning

**Notes:** **Most significant data center policy development**: Implemented Experimental Large Load Schedule (L-25-LL) effective April 2025 specifically for data centers >50 MW and mobile loads >1,000 kW (including crypto mining). Requires **15-year contracts** with capacity payments regardless of usage. Expects 1,000+ MW of new large load demand by 2030. State-owned utility serving 2M+ people. Camp Hall Commerce Park (6,781 acres near Charleston) flagship industrial site. Companies attracted: Google, Volvo, Redwood Materials. Industrial rates 16-30% lower than peer utilities.

---

## State public utility commissions

### Iowa Utilities Commission (IUC)

| Field | Value |
|-------|-------|
| **Official Name** | Iowa Utilities Commission (IUC) |
| **Base URL** | https://iuc.iowa.gov |
| **Filing System** | https://efs.iowa.gov/efs/ |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/regulated-industries/electric`
- `/records-documents/utility-tariffs-filed-iuc`
- `/commission-activity/rulemaking-process-proposed-rules`
- `/records-documents/forms-applications`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | 199 IAC Chapter 15 - QF Interconnection | Qualifying facility rules |
| tariff | Rate 3 (≥75 kW), Rate 16 (≥300 kW) | Demand-based large power service |
| guidance | Energy Efficiency Programs | Iowa Code § 476.6 |
| report | Electric Service Territory Maps | ArcGIS interactive mapping |

**Tags:** interconnection, capacity, rates, planning, regulation, MISO

**Notes:** Renamed from Iowa Utilities Board (IUB) to Iowa Utilities Commission in July 2024. Iowa generates **62% of electricity from wind**. Major regulated utilities: MidAmerican Energy, Alliant Energy (Interstate Power & Light). Tariff search at efs.iowa.gov. IUB 24/7 Portal: https://iub247.iowa.gov for company information.

---

### Indiana Utility Regulatory Commission (IURC)

| Field | Value |
|-------|-------|
| **Official Name** | Indiana Utility Regulatory Commission (IURC) |
| **Base URL** | https://www.in.gov/iurc |
| **Filing System** | https://iurc.portal.in.gov |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/iurc/energy-division/electricity-industry/`
- `/iurc/docketed-cases/`
- `/iurc/laws-rules-and-regulations/`
- `/iurc/rulemakings/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | **Large Load Interconnection Tariff (Approved Feb 2025)** | I&M Settlement - 70+ MW / 150 MW aggregate |
| regulation | 170 IAC 4-4.2 - Net Metering | Customer-generator rules |
| regulation | 170 IAC 4-4.3 - Interconnection Standards | Customer-generator facilities |
| guidance | NIPSCO Generation Data Center Proposal | Settlement July 2025 |

**Tags:** interconnection, capacity, rates, planning, regulation, data-center, large-load, MISO, PJM, economic-development

**Notes:** **Indiana is at the forefront of data center interconnection policy.** The Indiana Michigan Power large load tariff (February 2025) is a model being watched nationally. Requires **minimum 12-year contracts with 5-year ramp-up** for facilities with 70+ MW contract capacity or 150+ MW aggregated. Settlement parties include AWS, Microsoft, Google, and Data Center Coalition. Major developments: AWS $11B campus near New Carlisle, Google $2B Fort Wayne, Microsoft $1B LaPorte. I&M expects peak load growth from 2,800 MW to **7,000+ MW by 2030**. State spans MISO/PJM border.

---

### Public Utilities Commission of Nevada (PUCN)

| Field | Value |
|-------|-------|
| **Official Name** | Public Utilities Commission of Nevada (PUCN) |
| **Base URL** | https://puc.nv.gov |
| **Docket System** | pucweb1.state.nv.us/puc2/Dktinfo.aspx?Util=Electric |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/About/Docs/Tariffs/`
- `/Dockets/Dockets/`
- `/Utilities/Electric/`
- `/About/Docs/Statutes_Regulations/`
- `/Renewable_Energy/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | Nevada Administrative Code 703.375-703.410 | Tariff requirements |
| regulation | Rate Case Process | Three times per year, public participation |
| regulation | Renewable Portfolio Standard Oversight | 50% renewable by 2030 |
| guidance | Consumer Advocate coordination | Data center cost allocation review |

**Tags:** tariffs, rate-cases, interconnection, renewable, planning

**Notes:** Regulates approximately 400 investor-owned utilities. Works with Consumer Advocate to ensure new data centers are not subsidized by residential/small business ratepayers. Recently approved demand charge and net metering changes for NV Energy (September 2025).

---

### Utah Public Service Commission

| Field | Value |
|-------|-------|
| **Official Name** | Public Service Commission of Utah |
| **Base URL** | https://psc.utah.gov |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/electric/dockets/all-electric-dockets/`
- `/psc-filing-requirements/`
- `/commissioners/`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | **Docket 25-R318-01 - Large Load Service (SB132)** | Implementing 100+ MW special process |
| regulation | Rule R746-312 - Grid interconnections | Fair and nondiscriminatory |
| regulation | Rule R746-313/314 - System reliability | Community renewable standards |
| guidance | STEP (Sustainable Transportation and Energy Plan) | Alternative rate-making for 5+ MW |

**Tags:** tariffs, rate-cases, interconnection, large-load, planning

**Notes:** Implementing Utah SB132 framework where large loads (100+ MW over 5 years) follow special evaluation process. Large load customers pay fees to cover PSC evaluation costs. Commission rejected/reduced three separate Rocky Mountain Power rate increase requests in 2025.

---

### South Carolina Public Service Commission

| Field | Value |
|-------|-------|
| **Official Name** | Public Service Commission of South Carolina |
| **Base URL** | https://www.psc.sc.gov |
| **Docket System** | https://dms.psc.sc.gov/Web/Dockets |
| **E-Tariff System** | https://etariff.psc.sc.gov |
| **Category** | regulatory |
| **JavaScript Required** | No (Drupal CMS) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/about-us`
- `/consumer-info`
- `/law-and-guidelines`
- `/forms`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | Rate Case Processing | Duke Energy, Dominion filings 2025 |
| regulation | SC Energy Freedom Act | Solar/renewable policies |
| report | Consumer Education | scutilityconsumer.sc.gov |

**Tags:** regulatory, rates, tariffs, planning, interconnection

**Notes:** Seven commissioners (one from each congressional district). Location: 101 Executive Center Dr., Suite 100, Columbia, SC 29210. Phone: 803-896-5100. Livestreams meetings via SCETV. Office of Regulatory Staff (ORS): https://ors.sc.gov is separate advocacy body.

---

### Tennessee Public Utility Commission (TPUC)

| Field | Value |
|-------|-------|
| **Official Name** | Tennessee Public Utility Commission (TPUC) |
| **Base URL** | https://www.tn.gov/tpuc |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/tpuc/agency/tra-history-and-leadership.html`
- `/tpuc/`

**Tags:** regulatory, rates, telecommunications

**Notes:** **LIMITED relevance for data center electric service** because TVA is federally regulated, bypassing state PUC jurisdiction. TPUC (renamed from TRA in 2017) regulates privately-owned telephone, natural gas, electric (non-TVA), and water utilities. Primary relevance is telecommunications regulation and wholesale interconnection rates. Five part-time commissioners.

---

### Montana Public Service Commission

| Field | Value |
|-------|-------|
| **Official Name** | Montana Public Service Commission (PSC) |
| **Base URL** | https://psc.mt.gov |
| **Filing System** | https://reddi.mt.gov (REDDI Portal) |
| **Category** | regulatory |
| **JavaScript Required** | No |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/Regulated-Utilities/Compliance-Materials`
- `/Documents-Proceedings/`
- `/rules/index`
- `/About-Us/What-We-Do`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| regulation | Investigation into Resource Adequacy/Data Centers | Active trending docket |
| regulation | Montana Administrative Rules Title 38, Chapter 2 | Utility regulatory procedures |
| regulation | Four-level Interconnection Review | Level 1 (≤50 kW) to Level 4 (complex) |
| guidance | Large Load Oversight | >5 MW customers must be informed of alternatives |

**Tags:** rate-cases, interconnection, planning, data-center, resource-adequacy

**Notes:** Five elected commissioners from regional districts. Active investigation on data center resource adequacy. PSC ruled September 2025 that NorthWestern must inform potential >5 MW customers about alternative supplier options. Currently investigating NWE's Colstrip transactions. PSC advocates support separate data center rate class with minimum load requirements, collateral, low-income support, and clean energy incentives.

---

### Public Service Commission of Wisconsin (PSCW)

| Field | Value |
|-------|-------|
| **Official Name** | Public Service Commission of Wisconsin (PSCW) |
| **Base URL** | https://psc.wi.gov |
| **Filing System** | https://apps.psc.wi.gov (CMS/ERF) |
| **Category** | regulatory |
| **JavaScript Required** | No (SharePoint) |
| **Language** | en |
| **Region** | us, us_states |

**Start Paths:**
- `/Pages/ServiceType/EnergyTopics.aspx`
- `/Pages/CommissionActions/CommissionActionsGuide.aspx`
- `/Pages/CommissionActions/HighlightedCases.aspx`
- `/Pages/ServiceType/OfficeEnergyInnovation.aspx`

**Data Center-Relevant Policies:**
| Policy Type | Description | Path/Resource |
|-------------|-------------|---------------|
| tariff | **Very Large Customer (VLC) Tariff (Filed March 2025)** | We Energies data center rate |
| tariff | Bespoke Resources Tariff | Dedicated generation for specific customers |
| tariff | Real Time Market Pricing (RTMP) | Incremental load tariff |
| tariff | New Load Market Pricing (NLMP) | WPSC and WPL |
| regulation | PSC 137 - Large commercial/industrial rules | Administrative framework |

**Tags:** interconnection, capacity, rates, planning, regulation, data-center, large-load, MISO, renewable-energy, economic-development

**Notes:** We Energies' Very Large Customer Tariff is Wisconsin's first attempt at data center-scale rates. Key features: customers pay for dedicated infrastructure, bespoke generation allowed, curtailment rights during grid stress, existing ratepayer protection. Seeking approval by December 31, 2025. Context: **Microsoft's $3.3 billion data center campus in Mount Pleasant** (online 2026). Proposed legislation (2025 SB 729) includes data center sustainability certification requirements.

---

## Sites evaluated but not recommended

| Organization | URL | Reason for Exclusion |
|--------------|-----|---------------------|
| Tennessee Public Utility Commission | tn.gov/tpuc | Limited jurisdiction—does not regulate TVA which serves most of Tennessee for electric; only relevant for telecommunications |
| Western Energy Imbalance Market | westerneim.com | Operates as part of CAISO; recommend crawling caiso.com instead which has comprehensive WEIM documentation |

---

## Summary comparison by data center policy maturity

| State | Primary Grid Operator | Key Utility | Regulator | Data Center Policy Status |
|-------|----------------------|-------------|-----------|---------------------------|
| **Indiana** | MISO/PJM | Indiana Michigan Power | IURC | **Most Advanced** - Large load tariff approved Feb 2025 (70+ MW threshold) |
| **Wisconsin** | MISO | We Energies | PSCW | **Advanced** - VLC Tariff pending approval (filed March 2025) |
| **South Carolina** | N/A (utility territories) | Santee Cooper | SC PSC | **Advanced** - L-25-LL data center tariff effective April 2025 (50+ MW) |
| **Tennessee** | TVA (federal) | TVA | TPUC (limited) | **Established** - Active recruitment program since 2008 |
| **Utah** | Western Interconnection | Rocky Mountain Power | Utah PSC | **Developing** - SB132 framework for 100+ MW implemented 2025 |
| **Nevada** | CAISO (WEIM) | NV Energy | PUCN | **Developing** - Clean Transition Tariff pending |
| **Montana** | MISO/Western | NorthWestern Energy | Montana PSC | **Emerging** - Large load tariff planned; 2,250 MW pipeline |
| **Iowa** | MISO | MidAmerican/Alliant | IUC | **Standard** - Standard industrial tariffs; no data center-specific policy |

---

## Technical crawling recommendations

**Sites requiring JavaScript rendering (Playwright recommended):**
- misoenergy.org
- pjm.com
- tva.com
- nvenergy.com
- rockymountainpower.net
- duke-energy.com
- dominionenergy.com
- santeecooper.com (partial)
- northwesternenergy.com (partial)

**Sites accessible without JavaScript:**
- caiso.com (most crawler-friendly)
- puc.nv.gov
- psc.utah.gov
- psc.sc.gov
- psc.mt.gov
- psc.wi.gov
- iuc.iowa.gov
- in.gov/iurc

**Filing/docket systems to index:**
- MISO: misoenergy.org GI_Queue
- PJM: pjm.com queue tools
- CAISO: rimspub.caiso.com/rimsui/
- NorthWestern: oasis.oati.com/NWMT
- Iowa: efs.iowa.gov
- Indiana: iurc.portal.in.gov
- Wisconsin: apps.psc.wi.gov
- South Carolina: dms.psc.sc.gov, etariff.psc.sc.gov
- Montana: reddi.mt.gov