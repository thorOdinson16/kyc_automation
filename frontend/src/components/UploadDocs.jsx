import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';
import { validateImageQuality } from '../utils/imageValidation.js';
import toast from 'react-hot-toast';
import CameraCapture from './CameraCapture.jsx';

function DocumentUploader({ label, docType, onUploaded, icon, captureMode = 'single', allowPdf = false }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [showCamera, setShowCamera] = useState(false);

  const isLiveness = captureMode === 'liveness';

  const isPdfFile = (candidate) =>
    candidate?.type === 'application/pdf' || /\.pdf$/i.test(candidate?.name || '');

  const pickFile = () => inputRef.current?.click();

  const applicationId = () => localStorage.getItem('applicationId');

  const handleUpload = async (selectedFile) => {
    if (!selectedFile) return;

    if (selectedFile.size > 10 * 1024 * 1024) {
      toast.error('File size must be less than 10MB');
      return;
    }

    const validation = isPdfFile(selectedFile)
      ? { isValid: true, issues: [] }
      : await validateImageQuality(selectedFile);

    if (!validation.isValid) {
      validation.issues.forEach((issue) => toast.error(issue));
      const proceed = window.confirm(
        `Quality check flagged:\n- ${validation.issues.join('\n- ')}\n\nUpload anyway?`
      );
      if (!proceed) return;
    }

    const appId = applicationId();
    if (!appId) {
      toast.error('No application ID found. Please start over.');
      return;
    }

    setFile(selectedFile);
    setUploading(true);
    setProgress(0);

    try {
      const response = await kycAPI.uploadDocument(appId, docType, selectedFile, (progressEvent) => {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setProgress(percent);
      });

      setUploadComplete(true);
      onUploaded(response);
      toast.success(`${label} uploaded successfully!`);
    } catch (err) {
      console.error('Upload error:', err);
      setFile(null);
      setProgress(0);
      setUploadComplete(false);
    } finally {
      setUploading(false);
    }
  };

  const handleLivenessCapture = async (frames) => {
    setShowCamera(false);

    const appId = applicationId();
    if (!appId) {
      toast.error('No application ID found. Please start over.');
      return;
    }

    if (!Array.isArray(frames) || frames.length < 2) {
      toast.error('Liveness capture needs at least 2 frames. Please try again.');
      return;
    }

    const middleIndex = Math.floor(frames.length / 2);
    const selfie = frames[middleIndex];

    setFile(selfie);
    setUploading(true);
    setProgress(0);

    try {
      const response = await kycAPI.uploadDocument(appId, docType, selfie, (progressEvent) => {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setProgress(percent);
      });
      await kycAPI.uploadLivenessFrames(appId, frames);

      setUploadComplete(true);
      onUploaded(response);
      toast.success('Selfie and liveness frames uploaded!');
    } catch (err) {
      console.error('Liveness upload error:', err);
      setFile(null);
      setProgress(0);
      setUploadComplete(false);
    } finally {
      setUploading(false);
    }
  };

  const handleCameraCapture = (captured) => {
    if (captureMode === 'liveness' && Array.isArray(captured)) {
      handleLivenessCapture(captured);
      return;
    }
    setShowCamera(false);
    handleUpload(captured);
  };

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];
    if (selectedFile) handleUpload(selectedFile);
  };

  if (showCamera) {
    return (
      <div className="card">
        <CameraCapture
          label={`Capture ${label}`}
          mode={captureMode}
          onCapture={handleCameraCapture}
          onCancel={() => setShowCamera(false)}
        />
      </div>
    );
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <span className="text-2xl mr-3">{icon}</span>
          <div>
            <h4 className="font-semibold">{label}</h4>
            <p className="text-xs text-[color:var(--muted)]">Required</p>
          </div>
        </div>
        {uploadComplete && (
          <span className="text-green-400 text-xl">&#10003;</span>
        )}
      </div>

      {!file ? (
        <div className="space-y-3">
          {isLiveness ? (
            <p className="text-xs text-[color:var(--muted)]">
              Liveness requires the camera so we can verify you are physically present.
            </p>
          ) : (
            <>
              <div
                className="border-2 border-dashed border-gray-600 rounded-lg p-8 cursor-pointer hover:border-purple-500 transition-all text-center"
                onClick={pickFile}
              >
                <p className="text-sm font-medium mb-1">Click to upload from files</p>
                <p className="text-xs text-[color:var(--muted)]">
                  {allowPdf ? 'JPEG, PNG or PDF (max 10MB)' : 'JPEG, PNG or JPG (max 10MB)'}
                </p>
              </div>
              <input
                ref={inputRef}
                type="file"
                className="hidden"
                accept={
                  allowPdf
                    ? 'image/jpeg,image/png,image/jpg,application/pdf'
                    : 'image/jpeg,image/png,image/jpg'
                }
                onChange={handleFileChange}
              />
            </>
          )}

          <button
            className="w-full btn-secondary py-4"
            onClick={() => setShowCamera(true)}
          >
            {isLiveness ? 'Open Camera for Liveness' : 'Use Camera Instead'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg">
            <p className="text-sm font-medium truncate">{file.name}</p>
            {uploading && <span className="text-sm font-medium ml-3">{progress}%</span>}
          </div>

          {uploading && (
            <div className="w-full bg-gray-700 rounded-full h-2.5 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-purple-500 to-cyan-500 transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          {uploadComplete && (
            <div className="flex items-center justify-center p-3 bg-green-400/10 rounded-lg">
              <span className="text-sm text-green-400 font-medium">Upload complete!</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const REQUIRED_SLOTS = ['id_front', 'address_proof', 'utility_bill', 'selfie'];

const slotLabel = (slot) => (slot || '').replace(/_/g, ' ');

export default function UploadDocs() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [precheck, setPrecheck] = useState(null);
  const [processing, setProcessing] = useState(false);

  const applicationId = () => localStorage.getItem('applicationId');

  const refreshDocuments = async () => {
    const id = applicationId();
    if (!id) return;
    try {
      const data = await kycAPI.listDocuments(id);
      setDocuments((data.documents || []).filter((doc) => doc.document_type !== 'liveness'));
    } catch (err) {
      console.error('List documents error:', err);
    }
  };

  const runPrecheck = async () => {
    const id = applicationId();
    if (!id) return;
    try {
      const data = await kycAPI.precheck(id);
      setPrecheck(data);
    } catch (err) {
      console.error('Precheck error:', err);
    }
  };

  useEffect(() => {
    refreshDocuments();
  }, []);

  const presentSlots = new Set(documents.map((doc) => doc.document_type));
  const uploadedCount = REQUIRED_SLOTS.filter((slot) => presentSlots.has(slot)).length;
  const allDocsUploaded = uploadedCount === REQUIRED_SLOTS.length;

  useEffect(() => {
    if (allDocsUploaded) runPrecheck();
  }, [allDocsUploaded]);

  const handleUploaded = async () => {
    await refreshDocuments();
  };

  const moveDocument = async (documentId, suggestedRole) => {
    try {
      await kycAPI.reclassifyDocument(documentId, suggestedRole);
      toast.success(`Moved to ${slotLabel(suggestedRole)}`);
      await refreshDocuments();
      await runPrecheck();
    } catch (err) {
      console.error('Move document error:', err);
    }
  };

  const startProcessing = async () => {
    if (!allDocsUploaded) {
      toast.error('Please upload all required documents');
      return;
    }

    const id = applicationId();
    if (!id) {
      toast.error('No application ID found');
      navigate('/');
      return;
    }

    setProcessing(true);
    try {
      await kycAPI.startVerification(id);
      toast.success('Verification started!');
      navigate('/processing');
    } catch (err) {
      console.error('Start processing error:', err);
      setProcessing(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-4xl space-y-6">
        <div className="card text-center">
          <h2 className="text-3xl font-bold mb-2">Upload Documents</h2>
          <p className="text-[color:var(--muted)]">
            Please provide clear photos of your ID plus a short selfie liveness capture.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <DocumentUploader label="ID Document" docType="id_front" icon="&#129072;" allowPdf onUploaded={handleUploaded} />
          <DocumentUploader label="Address Proof" docType="address_proof" icon="&#128205;" allowPdf onUploaded={handleUploaded} />
          <DocumentUploader label="Utility Bill" docType="utility_bill" icon="&#128196;" allowPdf onUploaded={handleUploaded} />
          <DocumentUploader
            label="Selfie Liveness"
            docType="selfie"
            icon="&#129331;"
            captureMode="liveness"
            onUploaded={handleUploaded}
          />
        </div>

        {precheck && (
          <div className="card space-y-3">
            <h4 className="font-semibold">Document check</h4>
            {precheck.documents.map((doc) => {
              const detection = doc.detection || {};
              const looksLike =
                detection.id_type && detection.is_id
                  ? detection.id_type
                  : detection.is_bill
                  ? detection.bill_category
                  : detection.address_kind || 'unknown';
              return (
                <div
                  key={doc.document_id}
                  className="flex items-center justify-between text-sm gap-3"
                >
                  <span className="capitalize">{slotLabel(doc.document_type)}</span>
                  <span className="text-[color:var(--muted)] flex-1 text-center">
                    looks like: {looksLike}
                  </span>
                  {!doc.is_match && doc.suggested_role ? (
                    <button
                      className="btn-secondary py-1 px-3 text-xs"
                      onClick={() => moveDocument(doc.document_id, doc.suggested_role)}
                    >
                      Move to {slotLabel(doc.suggested_role)}
                    </button>
                  ) : (
                    <span className="text-green-400 text-xs">ok</span>
                  )}
                </div>
              );
            })}
            {precheck.missing_roles?.length > 0 && (
              <p className="text-xs text-yellow-400">
                Still missing a valid: {precheck.missing_roles.map(slotLabel).join(', ')}
              </p>
            )}
          </div>
        )}

        <div className="flex gap-4">
          <button
            className={`btn-primary flex-1 py-4 text-lg font-semibold ${
              !allDocsUploaded || processing ? 'opacity-50 cursor-not-allowed' : ''
            }`}
            onClick={startProcessing}
            disabled={!allDocsUploaded || processing}
          >
            {processing ? 'Processing...' : allDocsUploaded ? 'Start Verification' : 'Upload all documents to continue'}
          </button>

          <button
            className="btn-secondary px-8 py-4"
            onClick={() => {
              if (confirm('Are you sure you want to cancel? All progress will be lost.')) {
                localStorage.removeItem('applicationId');
                localStorage.removeItem('token');
                navigate('/');
              }
            }}
          >
            Cancel
          </button>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">Upload Progress</span>
            <span className="text-sm text-[color:var(--muted)]">{uploadedCount} / 4 documents</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-cyan-500 transition-all duration-500"
              style={{ width: `${(uploadedCount / 4) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
