import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';
import toast from 'react-hot-toast';
import CameraCapture from './CameraCapture.jsx';

function DocumentUploader({ label, docType, onUploaded, icon }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [uploadMethod, setUploadMethod] = useState(null); // null, 'file', 'camera'

  const pickFile = () => inputRef.current?.click();

  const handleUpload = async (f) => {
    if (!f) return;
    
    if (f.size > 10 * 1024 * 1024) {
      toast.error('File size must be less than 10MB');
      return;
    }
    
    setFile(f);
    setUploading(true);
    setProgress(0);

    const applicationId = localStorage.getItem('applicationId');
    
    if (!applicationId) {
      toast.error('No application ID found. Please start over.');
      return;
    }
    
    try {
      const response = await kycAPI.uploadDocument(
        applicationId, 
        docType, 
        f, 
        (progressEvent) => {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setProgress(percent);
        }
      );
      
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

  const handleCameraCapture = (capturedFile) => {
    setShowCamera(false);
    setUploadMethod('camera');
    handleUpload(capturedFile);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setUploadMethod('file');
      handleUpload(selectedFile);
    }
  };

  if (showCamera) {
    return (
      <div className="card">
        <CameraCapture
          label={`Capture ${label}`}
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
          <svg className="h-8 w-8 text-green-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )}
      </div>
      
      {!file ? (
        <div className="space-y-3">
          {/* File Upload */}
          <div
            className="border-2 border-dashed border-gray-600 rounded-lg p-8 cursor-pointer hover:border-purple-500 transition-all text-center"
            onClick={pickFile}
          >
            <svg className="mx-auto h-12 w-12 text-[color:var(--muted)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm font-medium mb-1">Click to upload from files</p>
            <p className="text-xs text-[color:var(--muted)]">JPEG, PNG or JPG (max 10MB)</p>
          </div>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept="image/jpeg,image/png,image/jpg"
            onChange={handleFileChange}
          />

          {/* Camera Button */}
          <button 
            className="w-full btn-secondary py-4 flex items-center justify-center"
            onClick={() => setShowCamera(true)}
          >
            <svg className="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Use Camera Instead
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg">
            <div className="flex items-center flex-1 min-w-0">
              <svg className="h-8 w-8 text-green-400 flex-shrink-0 mr-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clipRule="evenodd" />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{file.name}</p>
                <p className="text-xs text-[color:var(--muted)]">
                  {uploadMethod === 'camera' ? 'Captured from camera' : 'Uploaded from files'}
                </p>
              </div>
            </div>
            {uploading && (
              <span className="text-sm font-medium ml-3">{progress}%</span>
            )}
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
              <svg className="h-5 w-5 text-green-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-green-400 font-medium">Upload complete!</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function UploadDocs() {
  const navigate = useNavigate();
  const [uploaded, setUploaded] = useState({});
  const [processing, setProcessing] = useState(false);

  const handleUploaded = (response) => {
    console.log('Document uploaded:', response);
    setUploaded((prev) => ({
      ...prev,
      [response.document_type]: true,
    }));
  };

  const allDocsUploaded = uploaded.id_front && uploaded.selfie;

  const startProcessing = async () => {
    if (!allDocsUploaded) {
      toast.error('Please upload all required documents');
      return;
    }

    const applicationId = localStorage.getItem('applicationId');
    if (!applicationId) {
      toast.error('No application ID found');
      navigate('/');
      return;
    }

    setProcessing(true);
    
    try {
      await kycAPI.startVerification(applicationId);
      toast.success('Verification started!');
      navigate('/processing');
    } catch (err) {
      console.error('Start processing error:', err);
      toast.error('Failed to start verification. Please try again.');
      setProcessing(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-4xl space-y-6">
        {/* Header */}
        <div className="card text-center">
          <h2 className="text-3xl font-bold mb-2">Upload Documents</h2>
          <p className="text-[color:var(--muted)]">
            Please provide clear photos of your ID and a selfie for verification
          </p>
        </div>

        {/* Upload Cards */}
        <div className="grid md:grid-cols-2 gap-6">
          <DocumentUploader
            label="ID Document"
            docType="id_front"
            icon="🪪"
            onUploaded={handleUploaded}
          />

          <DocumentUploader
            label="Selfie Photo"
            docType="selfie"
            icon="🤳"
            onUploaded={handleUploaded}
          />
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <button
            className={`btn-primary flex-1 py-4 text-lg font-semibold ${
              !allDocsUploaded || processing ? 'opacity-50 cursor-not-allowed' : ''
            }`}
            onClick={startProcessing}
            disabled={!allDocsUploaded || processing}
          >
            {processing ? (
              <>
                <svg className="animate-spin h-5 w-5 mr-2 inline-block" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
                </svg>
                Processing...
              </>
            ) : (
              <>
                {allDocsUploaded ? (
                  <>
                    <svg className="inline-block h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Start Verification
                  </>
                ) : (
                  'Upload all documents to continue'
                )}
              </>
            )}
          </button>

          <button
            className="btn-secondary px-8 py-4"
            onClick={() => {
              if (confirm('Are you sure you want to cancel? All progress will be lost.')) {
                localStorage.removeItem('applicationId');
                navigate('/');
              }
            }}
          >
            Cancel
          </button>
        </div>

        {/* Progress Indicator */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">Upload Progress</span>
            <span className="text-sm text-[color:var(--muted)]">
              {Object.keys(uploaded).length} / 2 documents
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-purple-500 to-cyan-500 transition-all duration-500"
              style={{ width: `${(Object.keys(uploaded).length / 2) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}