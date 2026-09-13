import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_ORIGIN, kycAPI } from '../services/api.js';
import toast from 'react-hot-toast';

export default function Results() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [audit, setAudit] = useState([]);
  const [documents, setDocuments] = useState([]);

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    const id = localStorage.getItem('applicationId');
    if (!id) {
      nav('/');
      return;
    }

    try {
      const [results, trail, docs] = await Promise.all([
        kycAPI.getResults(id),
        kycAPI.getAuditTrail(id),
        kycAPI.listDocuments(id),
      ]);
      setData(results);
      setAudit(trail.audit_trail || []);
      setDocuments(docs.documents || []);
    } catch (e) {
      console.error(e);
      toast.error('Failed to load results');
    }
  };

  if (!data) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  const statusColor =
    data.status === 'approved'
      ? 'text-green-400'
      : data.status === 'rejected'
      ? 'text-red-400'
      : 'text-yellow-400';

  const extracted = data.extracted || {};

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-4xl space-y-4">
        <div className={'card text-center ' + statusColor}>
          <h2 className="text-2xl font-bold">{(data.status || '').toUpperCase()}</h2>
          <p className="text-[color:var(--muted)]">Application ID: {data.application_id}</p>
          <p className="mt-2">Risk score: {data.risk_score ?? 'N/A'}</p>
        </div>

        <div className="card">
          <h4 className="font-semibold mb-3">Extracted Details</h4>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><strong>Name:</strong> {extracted.name || 'N/A'}</div>
            <div><strong>Date of birth:</strong> {extracted.date_of_birth || 'N/A'}</div>
            <div><strong>Address:</strong> {extracted.address || 'N/A'}</div>
            <div><strong>ID number:</strong> {extracted.id_number || 'N/A'}</div>
          </div>
          {data.entity_mismatches?.mismatches?.length > 0 && (
            <div className="mt-3 text-sm text-red-400">
              {data.entity_mismatches.mismatches.map((m, i) => (
                <p key={i}>- {m}</p>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h4 className="font-semibold mb-3">Risk Factors (SHAP)</h4>

          {data?.explainability?.top_positive_factors?.length > 0 && (
            <div className="mb-4">
              <p className="text-sm text-green-400 mb-2">Positive factors</p>
              {data.explainability.top_positive_factors.map((f, i) => (
                <div key={i} className="flex items-center mb-2">
                  <span className="text-xs flex-1">{f.feature}</span>
                  <span className="text-xs">{(f.impact * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}

          {data?.explainability?.top_negative_factors?.length > 0 && (
            <div>
              <p className="text-sm text-red-400 mb-2">Negative factors</p>
              {data.explainability.top_negative_factors.map((f, i) => (
                <div key={i} className="flex items-center mb-2">
                  <span className="text-xs flex-1">{f.feature}</span>
                  <span className="text-xs">{(Math.abs(f.impact) * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}

          {data?.explainability?.explanation_text && (
            <pre className="text-xs mt-3 whitespace-pre-wrap text-[color:var(--muted)]">
              {data.explainability.explanation_text}
            </pre>
          )}
        </div>

        <div className="card">
          <h4 className="font-semibold mb-3">Audit Trail</h4>
          <div className="space-y-2">
            {audit.map((entry) => (
              <div key={entry.log_id} className="p-3 bg-black/20 rounded">
                <div className="text-xs text-[color:var(--muted)]">{entry.timestamp}</div>
                <div className="font-medium">{entry.action_type}</div>
              </div>
            ))}
          </div>
        </div>

        {documents.length > 0 && (
          <div className="card">
            <h4 className="font-semibold mb-3">Uploaded Documents</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {documents.map((doc) => (
                <div key={doc.document_id} className="border border-gray-700 rounded p-2">
                  <img
                    src={`${API_ORIGIN}${doc.view_url}`}
                    alt={doc.document_type}
                    className="w-full rounded"
                  />
                  <p className="text-xs mt-2 text-center">{doc.document_type}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button
            className="btn-primary flex-1"
            onClick={() => {
              localStorage.removeItem('applicationId');
              nav('/');
            }}
          >
            Start New
          </button>

          <button className="btn-secondary flex-1" onClick={() => nav('/reviewer')}>
            Reviewer
          </button>
        </div>
      </div>
    </div>
  );
}
