import React, { useState } from 'react';
import './SavedPolicy.css';

function SavedPolicy({ policy }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!policy) {
    return <div className="saved-policy-empty">No policy data available</div>;
  }

  const getReviewStatusBadge = (status) => {
    const statusMap = {
      new: 'badge-new',
      needs_review: 'badge-review',
      verified: 'badge-verified',
      archived: 'badge-archived',
    };
    return statusMap[status] || 'badge-default';
  };

  const getPolicyTypeBadge = (type) => {
    const typeMap = {
      law: 'type-law',
      directive: 'type-directive',
      regulation: 'type-regulation',
      incentive: 'type-incentive',
    };
    return typeMap[type] || 'type-default';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div className="saved-policy-card">
      <div className="saved-policy-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="saved-policy-title-section">
          <h3 className="saved-policy-name">{policy.policy_name}</h3>
          <div className="saved-policy-meta">
            <span className="saved-policy-jurisdiction">{policy.jurisdiction}</span>
            <span className={`saved-policy-badge ${getPolicyTypeBadge(policy.policy_type)}`}>
              {policy.policy_type}
            </span>
            <span className={`saved-policy-badge ${getReviewStatusBadge(policy.review_status)}`}>
              {policy.review_status}
            </span>
          </div>
        </div>
        <div className="saved-policy-score">
          <div className="relevance-score">{policy.relevance_score}</div>
          <span className="score-label">relevance</span>
        </div>
        <button className="expand-button" aria-label="Toggle details">
          {isExpanded ? '−' : '+'}
        </button>
      </div>

      <div className="saved-policy-summary">
        <p>{policy.summary}</p>
      </div>

      {isExpanded && (
        <div className="saved-policy-details">
          <div className="detail-section" id="key-requirements">
            
          {policy.key_requirements && (
            <div className="detail-section">
              <h4>Key Requirements</h4>
              <p className="requirements-text">{policy.key_requirements}</p>
            </div>
          )}

            <h4>Key Information</h4>
            <dl className="detail-list">
              {policy.bill_number && (
                <>
                  <dt>Bill Number:</dt>
                  <dd>{policy.bill_number}</dd>
                </>
              )}
              {policy.effective_date && (
                <>
                  <dt>Effective Date:</dt>
                  <dd>{formatDate(policy.effective_date)}</dd>
                </>
              )}
              {policy.source_language && (
                <>
                  <dt>Source Language:</dt>
                  <dd>{policy.source_language}</dd>
                </>
              )}
              {policy.discovered_at && (
                <>
                  <dt>Discovered:</dt>
                  <dd>{formatDate(policy.discovered_at)}</dd>
                </>
              )}
            </dl>
          </div>

          {policy.referenced_policies && policy.referenced_policies.length > 0 && (
            <div className="detail-section" id="referenced-policies">
              <h4>Referenced Policies</h4> 
              <ul className="referenced-list">
                {policy.referenced_policies.map((ref, index) => (
                  <li key={index}>{ref}</li>
                ))}
              </ul>
            </div>
          )}

          {policy.referenced_urls && policy.referenced_urls.length > 0 && (
            <div className="detail-section" id="referenced-urls">
              <h4>Referenced URLs</h4>
              <ul className="referenced-urls-list">
                {policy.referenced_urls.map((url, index) => (
                  <li key={index}>
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {policy.verification_flags && policy.verification_flags.length > 0 && (
            <div className="detail-section verification-flags">
              <h4>Verification Flags</h4>
              <div className="flags-container">
                {policy.verification_flags.map((flag, index) => (
                  <span key={index} className="flag-badge">
                    {flag}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="detail-section meta-info">
            <dl className="detail-list">
              <dt>Scan ID:</dt>
              <dd className="monospace">{policy.scan_id}</dd>
              <dt>Domain ID:</dt>
              <dd className="monospace">{policy.domain_id}</dd>
              <dt>Crawl Status:</dt>
              <dd>{policy.crawl_status}</dd>
              {policy.error_details && (
                <>
                  <dt>Error Details:</dt>
                  <dd>{policy.error_details}</dd>
                </>
              )}
            </dl>
          </div>

          <div className="detail-section actions">
            <a
              href={policy.url}
              target="_blank"
              rel="noopener noreferrer"
              className="action-link primary"
            >
              View Full Policy
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

export default SavedPolicy;
