import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_ORIGIN, kycAPI } from '../services/api.js';

export default function ReviewerPanel() {
  const nav = useNavigate();
  const [applications, setApplications] = useState([]);
  const [selected, setSelected] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [audit, setAudit] = useState([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    if (!localStorage.getItem('token')) {
      toast.error('Please sign in as staff');
      nav('/login');
      return;
    }
    loadApplications();
  }, [filter]);

  const loadApplications = async () => {
    try {
      const data = await kycAPI.listApplications(filter);
      setApplications(data);
    } catch (err) {
      console.error('Load applications error:', err);
    }
  };

  const loadApplication = async (id) => {
    try {
      const [results, docs, logs] = await Promise.all([
        kycAPI.getResults(id),
        kycAPI.listDocuments(id),
        kycAPI.getAuditTrail(id),
      ]);
      setSelected(results);
      setDocuments(docs.documents || []);
      setAudit(logs.audit_trail || []);
    } catch (err) {
      console.error('Load application error:', err);
    }
  };

  const overrideDecision = async (decision, reason) => {
    try {
      await kycAPI.overrideDecision(selected.application_id, decision, reason);
      toast.success(`Application ${decision}`);
      loadApplications();
      loadApplication(selected.application_id);
    } catch (err) {
      console.error('Override error:', err);
    }
  };

  return (
    <div className="min-h-screen p-6">
      <div className="grid grid-cols-4 gap-6">
        <div className="col-span-1 card">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold">Applications</h4>
            <button className="text-xs text-[color:var(--muted)]" onClick={() => nav('/')}>Home</button>
          </div>
          <div className="space-y-2 mb-4">
            {['all', 'pending', 'processing', 'review_required', 'approved', 'rejected'].map((f) => (
              <button
                key={f}
                className={`btn-secondary w-full text-left ${filter === f ? 'bg-purple-600' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="space-y-2 max-h-96 overflow-auto">
            {applications.map((application) => (
              <div
                key={application.application_id}
                className="p-3 bg-black/20 rounded cursor-pointer hover:bg-purple-900/20"
                onClick={() => loadApplication(application.application_id)}
              >
                <p className="text-sm font-medium">{application.application_id.slice(0, 8)}</p>
                <p className="text-xs text-[color:var(--muted)]">{application.status}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="col-span-3 space-y-4">
          {selected && (
            <>
              <div className="card">
                <h4 className="font-semibold mb-2">Application Summary</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div><strong>Status:</strong> {selected.status}</div>
                  <div><strong>Risk Score:</strong> {selected.risk_score ?? 'N/A'}</div>
                  <div><strong>Name:</strong> {selected.extracted?.name || 'N/A'}</div>
                  <div><strong>DOB:</strong> {selected.extracted?.date_of_birth || 'N/A'}</div>
                  <div><strong>ID number:</strong> {selected.extracted?.id_number || 'N/A'}</div>
                  <div><strong>Mismatches:</strong> {selected.entity_mismatches?.mismatches?.length || 0}</div>
                </div>
              </div>

              <div className="card">
                <h4 className="font-semibold mb-3">Documents</h4>
                <div className="grid grid-cols-4 gap-4">
                  {documents.map((doc) => (
                    <div key={doc.document_id}>
                      {doc.mime_type === 'application/pdf' ? (
                        <a
                          href={`${API_ORIGIN}${doc.view_url}`}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center justify-center h-40 bg-black/30 rounded border border-gray-700 text-xs text-purple-300"
                        >
                          PDF - open
                        </a>
                      ) : (
                        <img
                          src={`${API_ORIGIN}${doc.view_url}`}
                          alt={doc.document_type}
                          className="w-full rounded border border-gray-700"
                        />
                      )}
                      <p className="text-xs mt-1 text-center">{doc.document_type}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card">
                <h4 className="font-semibold mb-3">Reviewer Actions</h4>
                <div className="flex gap-3">
                  <button
                    className="btn-primary flex-1"
                    onClick={() => {
                      const reason = prompt('Approval reason:');
                      if (reason) overrideDecision('approved', reason);
                    }}
                  >
                    Approve
                  </button>
                  <button
                    className="btn-secondary flex-1 bg-red-600"
                    onClick={() => {
                      const reason = prompt('Rejection reason:');
                      if (reason) overrideDecision('rejected', reason);
                    }}
                  >
                    Reject
                  </button>
                </div>
              </div>

              <div className="card">
                <h4 className="font-semibold mb-3">Audit Trail</h4>
                <div className="space-y-2 max-h-64 overflow-auto">
                  {audit.map((entry) => (
                    <div key={entry.log_id} className="p-3 bg-black/20 rounded">
                      <div className="flex justify-between text-xs">
                        <span>{entry.action_type}</span>
                        <span className="text-[color:var(--muted)]">{entry.timestamp}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
