document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const statusDiv = document.getElementById('status');
    const captureCalibBtn = document.getElementById('captureCalibBtn');
    const runCalibBtn = document.getElementById('runCalibBtn');
    const testUndistortBtn = document.getElementById('testUndistortBtn');
    const quickProcessBtn = document.getElementById('quickProcessBtn');
    const videoUploadInput = document.getElementById('videoUpload');
    const imageCountSpan = document.getElementById('imageCount');
    const calibOutputDiv = document.getElementById('calib-output');
    const testOutputDiv = document.getElementById('test-output');

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
    }

    function displayPreviewImage(url) {
        calibOutputDiv.innerHTML = '';
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime();
        img.alt = 'Calibration Preview';
        calibOutputDiv.appendChild(img);
    }

    function displayTestVideo(url) {
        testOutputDiv.innerHTML = '';
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime();
        video.controls = true;
        video.autoplay = true;
        video.muted = true;

        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.textContent = 'Download Processed Video';
        downloadLink.className = 'download-button';
        downloadLink.download = url.substring(url.lastIndexOf('/') + 1);

        testOutputDiv.appendChild(video);
        testOutputDiv.appendChild(downloadLink);
    }

    function displayDownloadLink(url) {
        testOutputDiv.innerHTML = '';
        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.textContent = 'Download Processed Video';
        downloadLink.className = 'download-button';
        downloadLink.download = url.substring(url.lastIndexOf('/') + 1);
        testOutputDiv.appendChild(downloadLink);
    }

    async function updateImageCount() {
        try {
            const response = await fetch('/get_calibration_status');
            const data = await response.json();
            imageCountSpan.textContent = data.image_count;
            if (data.is_ready) {
                runCalibBtn.disabled = false;
                imageCountSpan.style.color = '#198754';
            } else {
                runCalibBtn.disabled = true;
                imageCountSpan.style.color = '#0d6efd';
            }
        } catch (error) {
            console.error("Failed to get image count:", error);
        }
    }

    // --- Event Listeners ---
    captureCalibBtn.addEventListener('click', async () => {
        updateStatus('Capturing image and searching for checkerboard...');
        captureCalibBtn.disabled = true;
        try {
            const response = await fetch('/capture_for_calibration', { method: 'POST' });
            const result = await response.json();
            
            updateStatus(result.message, !result.success);
            if (result.preview_url) {
                displayPreviewImage(result.preview_url);
            }

            if (result.success) {
                await updateImageCount();
            }

        } catch (error) {
            updateStatus('A network error occurred during capture.', true);
        }
        captureCalibBtn.disabled = false;
    });

    runCalibBtn.addEventListener('click', async () => {
        updateStatus('Running calibration... This may take a minute.');
        runCalibBtn.disabled = true;
        captureCalibBtn.disabled = true;
        try {
            const response = await fetch('/run_calibration', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success); 
        } catch (error) {
            updateStatus('A network error occurred during calibration.', true);
        }
        captureCalibBtn.disabled = false; 
    });

    testUndistortBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to test.', true);
            return;
        }

        updateStatus('Performing full processing for web playback... Please wait.');
        testUndistortBtn.disabled = true;
        quickProcessBtn.disabled = true;

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/upload_and_undistort', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                displayTestVideo(result.video_url);
            }
        } catch (error) {
            updateStatus('A network error occurred during video processing.', true);
        }
        testUndistortBtn.disabled = false;
        quickProcessBtn.disabled = false;
    });

    quickProcessBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to test.', true);
            return;
        }

        updateStatus('Performing quick processing... Please wait.');
        quickProcessBtn.disabled = true;
        testUndistortBtn.disabled = true;

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/quick_undistort_and_download', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success && result.download_url) {
                displayDownloadLink(result.download_url);
            }
        } catch (error) {
            updateStatus('A network error occurred during quick processing.', true);
        }
        quickProcessBtn.disabled = false;
        testUndistortBtn.disabled = false;
    });

    // --- Initial State ---
    updateImageCount();
});