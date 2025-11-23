import React, { useRef, useState, useCallback } from 'react';
import Webcam from 'react-webcam';
import toast from 'react-hot-toast';

export default function CameraCapture({ onCapture, onCancel, label = "Capture Photo" }) {
  const webcamRef = useRef(null);
  const [imgSrc, setImgSrc] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [facingMode, setFacingMode] = useState('user');
  const [isReady, setIsReady] = useState(false);

  const videoConstraints = {
    width: { ideal: 1280 },
    height: { ideal: 720 },
    facingMode: facingMode
  };

  const handleUserMedia = () => {
    setIsReady(true);
    toast.success('Camera ready!');
  };

  const handleUserMediaError = (error) => {
    console.error('Camera error:', error);
    setCameraError('Unable to access camera. Please check permissions.');
    toast.error('Camera access denied');
  };

  const capture = useCallback(() => {
    const imageSrc = webcamRef.current.getScreenshot();
    if (imageSrc) {
      setImgSrc(imageSrc);
    } else {
      toast.error('Failed to capture image');
    }
  }, [webcamRef]);

  const retake = () => {
    setImgSrc(null);
  };

  const confirm = () => {
    if (!imgSrc) return;

    // Convert base64 to blob
    fetch(imgSrc)
      .then(res => res.blob())
      .then(blob => {
        const file = new File([blob], `camera-capture-${Date.now()}.jpg`, { 
          type: "image/jpeg" 
        });
        onCapture(file);
      })
      .catch(err => {
        console.error('Error converting image:', err);
        toast.error('Failed to process captured image');
      });
  };

  const switchCamera = () => {
    setFacingMode(prevMode => prevMode === 'user' ? 'environment' : 'user');
    setIsReady(false);
  };

  if (cameraError) {
    return (
      <div className="card text-center p-8">
        <svg className="mx-auto h-16 w-16 text-red-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h3 className="text-xl font-bold mb-2 text-red-400">Camera Access Error</h3>
        <p className="text-[color:var(--muted)] mb-6">{cameraError}</p>
        <button className="btn-secondary" onClick={onCancel}>
          Use File Upload Instead
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold">{label}</h3>
        {isReady && !imgSrc && (
          <span className="text-xs text-green-400 flex items-center">
            <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse" />
            Camera Ready
          </span>
        )}
      </div>

      {!imgSrc ? (
        <div className="space-y-4">
          <div className="relative rounded-lg overflow-hidden bg-black aspect-video">
            <Webcam
              ref={webcamRef}
              audio={false}
              screenshotFormat="image/jpeg"
              screenshotQuality={0.95}
              videoConstraints={videoConstraints}
              onUserMedia={handleUserMedia}
              onUserMediaError={handleUserMediaError}
              className="w-full h-full object-cover"
            />
            
            {/* Camera overlay guide */}
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="border-2 border-purple-500/50 rounded-lg w-3/4 h-3/4" />
            </div>

            {/* Instructions overlay */}
            {isReady && (
              <div className="absolute bottom-4 left-0 right-0 text-center">
                <p className="text-white text-sm bg-black/50 inline-block px-4 py-2 rounded-full">
                  Position {label.toLowerCase()} within the frame
                </p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <button 
              className="btn-secondary py-3"
              onClick={switchCamera}
              disabled={!isReady}
            >
              <svg className="inline-block h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>

            <button 
              className="btn-primary py-3"
              onClick={capture}
              disabled={!isReady}
            >
              <svg className="inline-block h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>

            <button 
              className="btn-secondary py-3"
              onClick={onCancel}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg overflow-hidden border-2 border-gray-700">
            <img src={imgSrc} alt="Captured" className="w-full" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button className="btn-secondary py-3" onClick={retake}>
              <svg className="inline-block h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Retake
            </button>
            <button className="btn-primary py-3" onClick={confirm}>
              <svg className="inline-block h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Use This Photo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}