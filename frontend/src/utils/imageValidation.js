const MAX_DIMENSION = 512;
const BLUR_VARIANCE_THRESHOLD = 80;
const GLARE_FRACTION_THRESHOLD = 0.05;
const GLARE_PIXEL_MIN_CHANNEL = 250;
const DARK_LUMINANCE_THRESHOLD = 40;

export async function validateImageQuality(file) {
  // PDFs are not decodable via canvas; format checks happen server-side.
  if (file && (file.type === 'application/pdf' || /\.pdf$/i.test(file.name || ''))) {
    return { isValid: true, issues: [], metrics: {} };
  }

  return new Promise((resolve) => {
    const done = (result) => resolve(result);
    const passes = () => done({ isValid: true, issues: [], metrics: {} });

    const reader = new FileReader();
    reader.onerror = passes;

    reader.onload = (event) => {
      const img = new Image();
      img.onerror = passes;

      img.onload = () => {
        const scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height));
        const width = Math.max(1, Math.round(img.width * scale));
        const height = Math.max(1, Math.round(img.height * scale));

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        const { data } = ctx.getImageData(0, 0, width, height);

        const pixels = width * height;
        const gray = new Float32Array(pixels);

        let luminanceSum = 0;
        let glarePixels = 0;

        for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
          const r = data[i];
          const g = data[i + 1];
          const b = data[i + 2];
          const luminance = 0.299 * r + 0.587 * g + 0.114 * b;

          gray[p] = luminance;
          luminanceSum += luminance;

          // Real glare is a specular, near-saturated patch: all channels blown out.
          if (Math.min(r, g, b) >= GLARE_PIXEL_MIN_CHANNEL) {
            glarePixels += 1;
          }
        }

        const meanLuminance = luminanceSum / pixels;
        const glareFraction = glarePixels / pixels;

        // Variance of the Laplacian is a standard focus/blur metric.
        let lapSum = 0;
        let lapSumSq = 0;
        let count = 0;
        for (let y = 1; y < height - 1; y += 1) {
          for (let x = 1; x < width - 1; x += 1) {
            const i = y * width + x;
            const lap =
              -4 * gray[i] + gray[i - 1] + gray[i + 1] + gray[i - width] + gray[i + width];
            lapSum += lap;
            lapSumSq += lap * lap;
            count += 1;
          }
        }

        const lapMean = count ? lapSum / count : 0;
        const laplacianVariance = count ? lapSumSq / count - lapMean * lapMean : 0;

        const isBlurry = laplacianVariance < BLUR_VARIANCE_THRESHOLD;
        const hasGlare = glareFraction > GLARE_FRACTION_THRESHOLD;
        const tooDark = meanLuminance < DARK_LUMINANCE_THRESHOLD;

        done({
          isValid: !isBlurry && !hasGlare && !tooDark,
          issues: [
            isBlurry && 'Image looks blurry - hold steady and retake',
            hasGlare && 'Strong glare detected - avoid direct light or flash',
            tooDark && 'Image too dark - move to better lighting',
          ].filter(Boolean),
          metrics: {
            laplacianVariance: Number(laplacianVariance.toFixed(1)),
            glareFraction: Number(glareFraction.toFixed(4)),
            meanLuminance: Number(meanLuminance.toFixed(1)),
          },
        });
      };

      img.src = event.target.result;
    };

    reader.readAsDataURL(file);
  });
}
