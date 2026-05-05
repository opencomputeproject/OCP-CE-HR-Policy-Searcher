import React from 'react';
import SavedPolicy from './SavedPolicy';

// Example mock policy for testing
const mockPolicy = {
  url: "https://www.bmwk.de/Redaktion/EN/Artikel/Energy/data-centre-energy-efficiency-act.html",
  policy_name: "Energy Efficiency Act - Data Centre Waste Heat Reuse Requirements",
  jurisdiction: "Germany",
  policy_type: "law",
  summary: "Requires new and existing data centers to meet energy efficiency standards and examine opportunities for waste heat reuse. Operators must provide information about available waste heat to local heating networks where technically and economically feasible.",
  relevance_score: 10,
  effective_date: "2023-11-18",
  source_language: "English",
  bill_number: "EnEfG",
  key_requirements: "Data center operators must monitor energy performance, publish efficiency indicators, and assess waste heat reuse potential. New data centers must be designed so recovered heat can be supplied to district heating or other external users when feasible.",
  discovered_at: "2026-05-04T10:15:00Z",
  crawl_status: "success",
  error_details: null,
  review_status: "new",
  scan_id: "mock-scan-eu-2026-05-04",
  domain_id: "germany_bmwk",
  verification_flags: [],
  referenced_policies: [
    "Energy Efficiency Directive (EU) 2023/1791 Article 12",
    "German Energy Efficiency Act"
  ],
  referenced_urls: [
    "https://eur-lex.europa.eu/eli/dir/2023/1791/oj"
  ]
};

function SavedPolicyDemo() {
  return (
    <div>
      <h2 style={{ marginBottom: '16px' }}>Saved Policy Component</h2>
      <SavedPolicy policy={mockPolicy} />
    </div>
  );
}

export default SavedPolicyDemo;
