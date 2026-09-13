export async function validateImageQuality(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        
        const imageData = ctx.getImageData(0, 0, img.width, img.height);
        const data = imageData.data;
        
        // Blur detection (Laplacian variance)
        let variance = 0;
        for (let i = 0; i < data.length; i += 4) {
          const gray = 0.299 * data[i] + 0.587 * data[i+1] + 0.114 * data[i+2];
          variance += Math.pow(gray - 128, 2);
        }
        variance /= (data.length / 4);
        const isBlurry = variance < 100;
        
        // Brightness check
        let brightness = 0;
        for (let i = 0; i < data.length; i += 4) {
          brightness += (data[i] + data[i+1] + data[i+2]) / 3;
        }
        brightness /= (data.length / 4);
        const hasGlare = brightness > 200;
        const tooDark = brightness < 50;
        
        resolve({
          isValid: !isBlurry && !hasGlare && !tooDark,
          issues: [
            isBlurry && "Image is blurry - retake with steady hand",
            hasGlare && "Too much glare - avoid direct light",
            tooDark && "Image too dark - improve lighting"
          ].filter(Boolean)
        });
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}