import React, { useEffect, useState } from 'react';
import { kycAPI } from '../services/api.js';

export default function DocumentPreview({ doc, className = '' }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  const isPdf = doc.mime_type === 'application/pdf';

  useEffect(() => {
    let objectUrl;
    let cancelled = false;

    kycAPI
      .fetchDocumentBlob(doc.document_id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.document_id]);

  if (failed) {
    return (
      <div className={`flex items-center justify-center h-40 bg-black/30 rounded text-xs text-red-400 ${className}`}>
        Preview unavailable
      </div>
    );
  }

  if (isPdf) {
    return (
      <a
        href={url || undefined}
        target="_blank"
        rel="noreferrer"
        className={`flex items-center justify-center h-40 bg-black/30 rounded text-sm text-purple-300 ${className}`}
      >
        {url ? 'PDF document - open' : 'Loading...'}
      </a>
    );
  }

  if (!url) {
    return (
      <div className={`flex items-center justify-center h-40 bg-black/30 rounded text-xs text-[color:var(--muted)] ${className}`}>
        Loading...
      </div>
    );
  }

  return <img src={url} alt={doc.document_type} className={`w-full rounded ${className}`} />;
}
