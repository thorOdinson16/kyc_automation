import React, { useCallback, useRef, useState } from 'react';
import Webcam from 'react-webcam';
import toast from 'react-hot-toast';

const LIVENESS_FRAMES = 10;
const LIVENESS_INTERVAL_MS = 220;

export default function CameraCapture({
  onCapture,
  onCancel,
  label = 'Capture Photo',
  mode = 'single',
}) {
  const webcamRef = useRef(null);
  const timerRef = useRef(null);
  const framesRef = useRef([]);

  const [frames, setFrames] = useState([]);
  const [cameraError, setCameraError] = useState(null);
  const [facingMode, setFacingMode] = useState('user');
  const [isReady, setIsReady] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const videoConstraints = {
    width: { ideal: 1280 },
    height: { ideal: 720 },
    facingMode,
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

  const snapshot = () => webcamRef.current?.getScreenshot();

  const captureSingle = useCallback(() => {
    const imageSrc = snapshot();
    if (!imageSrc) {
      toast.error('Failed to capture image');
      return;
    }
    setFrames([imageSrc]);
  }, []);

  const captureSequence = useCallback(() => {
    framesRef.current = [];
    setCapturing(true);

    timerRef.current = setInterval(() => {
      const imageSrc = snapshot();
      if (imageSrc) {
        framesRef.current.push(imageSrc);
        setFrames([...framesRef.current]);
      }

      if (framesRef.current.length >= LIVENESS_FRAMES) {
        clearInterval(timerRef.current);
        timerRef.current = null;
        setCapturing(false);
        if (framesRef.current.length < 2) {
          toast.error('Not enough frames captured. Try again.');
          setFrames([]);
        }
      }
    }, LIVENESS_INTERVAL_MS);
  }, []);

  const capture = mode === 'liveness' ? captureSequence : captureSingle;

  const retake = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    framesRef.current = [];
    setFrames([]);
    setCapturing(false);
  };

  const dataUrlToFile = (dataUrl, name) =>
    fetch(dataUrl)
      .then((res) => res.blob())
      .then(
        (blob) =>
          new File([blob], name, {
            type: 'image/jpeg',
          })
      );

  const confirm = async () => {
    if (frames.length === 0) return;

    try {
      if (mode === 'liveness') {
        const files = await Promise.all(
          frames.map((frame, index) =>
            dataUrlToFile(frame, `camera-capture-${Date.now()}-${index}.jpg`)
          )
        );
        onCapture(files);
      } else {
        const file = await dataUrlToFile(frames[0], `camera-capture-${Date.now()}.jpg`);
        onCapture(file);
      }
    } catch (err) {
      console.error('Error converting image:', err);
      toast.error('Failed to process captured image');
    }
  };

  const switchCamera = () => {
    setFacingMode((prev) => (prev === 'user' ? 'environment' : 'user'));
    setIsReady(false);
  };

  if (cameraError) {
    return (
      <div className="card text-center p-8">
        <h3 className="text-xl font-bold mb-2 text-red-400">Camera Access Error</h3>
        <p className="text-[color:var(--muted)] mb-6">{cameraError}</p>
        <button className="btn-secondary" onClick={onCancel}>
          Use File Upload Instead
        </button>
      </div>
    );
  }

  const hasFrame = frames.length > 0;
  const previewFrame = hasFrame ? frames[frames.length - 1] : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold">{label}</h3>
        {isReady && !hasFrame && (
          <span className="text-xs text-green-400 flex items-center">
            <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse" />
            Camera Ready
          </span>
        )}
      </div>

      {!hasFrame ? (
        <div className="space-y-4">
          <div className="relative rounded-lg overflow-hidden bg-black aspect-video">
            <Webcam
              ref={webcamRef}
              audio={false}
              screenshotFormat="image/jpeg"
              screenshotQuality={0.9}
              videoConstraints={videoConstraints}
              onUserMedia={handleUserMedia}
              onUserMediaError={handleUserMediaError}
              className="w-full h-full object-cover"
            />

            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="border-2 border-purple-500/50 rounded-lg w-3/4 h-3/4" />
            </div>

            {isReady && (
              <div className="absolute bottom-4 left-0 right-0 text-center">
                <p className="text-white text-sm bg-black/50 inline-block px-4 py-2 rounded-full">
                  {mode === 'liveness'
                    ? 'Look at the camera and blink slowly'
                    : `Position ${label.toLowerCase()} within the frame`}
                </p>
              </div>
            )}
          </div>

          {capturing && (
            <p className="text-center text-sm text-[color:var(--muted)]">
              Capturing {frames.length} / {LIVENESS_FRAMES} frames...
            </p>
          )}

          <div className="grid grid-cols-3 gap-3">
            <button className="btn-secondary py-3" onClick={switchCamera} disabled={!isReady}>
              Flip
            </button>
            <button className="btn-primary py-3" onClick={capture} disabled={!isReady || capturing}>
              {mode === 'liveness' ? 'Start Liveness' : 'Capture'}
            </button>
            <button className="btn-secondary py-3" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg overflow-hidden border-2 border-gray-700">
            <img src={previewFrame} alt="Captured" className="w-full" />
          </div>

          {mode === 'liveness' && (
            <p className="text-center text-sm text-[color:var(--muted)]">
              {frames.length} frames captured for liveness detection.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <button className="btn-secondary py-3" onClick={retake}>
              Retake
            </button>
            <button className="btn-primary py-3" onClick={confirm}>
              Use This {mode === 'liveness' ? 'Sequence' : 'Photo'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
