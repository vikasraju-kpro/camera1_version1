document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const statusDiv = document.getElementById('status');
    const startRecordBtn = document.getElementById('startLineCallBtn');
    const stopRecordBtn = document.getElementById('stopLineCallBtn');
    const mediaOutputDiv = document.getElementById('media-output');
    
    // --- NEW: Inference Selectors ---
    const videoUploadInput = document.getElementById('videoUpload');
    const uploadAndRunBtn = document.getElementById('uploadAndRunBtn');
    const runOnLatestBtn = document.getElementById('runOnLatestBtn');

    // --- Global State ---
    let latestRecordedVideoPath = null;
    let statusInterval = null; // To store the interval ID for polling

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
        statusDiv.style.backgroundColor = isError ? '#f8d7da' : '#d1e7dd';
    }
    
    function createDownloadLink(url, text) {
        const a = document.createElement('a');
        a.href = url;
        a.textContent = text;
        a.className = 'download-button';
        a.download = url.substring(url.lastIndexOf('/') + 1);
        return a;
    }

    function displayVideo(url) {
        mediaOutputDiv.innerHTML = ''; // Clear previous output
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime(); // Cache bust
        video.controls = true;
        video.autoplay = true;
        video.muted = true; 

        const downloadLink = createDownloadLink(url, 'Download Video');
        mediaOutputDiv.appendChild(video);
        mediaOutputDiv.appendChild(downloadLink);
    }

    function setAllButtonsDisabled(disabled) {
        startRecordBtn.disabled = disabled;
        stopRecordBtn.disabled = disabled;
        uploadAndRunBtn.disabled = disabled;
        runOnLatestBtn.disabled = disabled;
    }

    // --- Recording Event Listeners ---
    startRecordBtn.addEventListener('click', async () => {
        updateStatus('Starting line call recording...');
        setAllButtonsDisabled(true); // Disable all buttons
        try {
            const response = await fetch('/start_line_calling', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                stopRecordBtn.disabled = false; // Only enable stop
                runOnLatestBtn.style.display = 'none'; // Hide inference btn
            } else {
                setAllButtonsDisabled(false); // Re-enable if failed
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    });

    stopRecordBtn.addEventListener('click', async () => {
        updateStatus('Stopping recording and processing video...');
        try {
            const response = await fetch('/stop_line_calling', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            setAllButtonsDisabled(false); // Re-enable all buttons
            
            if (result.success && result.video_url) {
                displayVideo(result.video_url);
                latestRecordedVideoPath = result.video_url; // Save the path
                runOnLatestBtn.style.display = 'inline-block'; // Show "Run Inference" btn
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    });


    // --- NEW: Inference Event Listeners & Functions ---

    // 1. Click listener for the "Run Inference on This Video" button
    runOnLatestBtn.addEventListener('click', () => {
        if (latestRecordedVideoPath) {
            startInferenceProcess(latestRecordedVideoPath);
        } else {
            updateStatus('No recorded video found.', true);
        }
    });

    // 2. Click listener for the "Upload & Run Inference" button
    uploadAndRunBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to upload.', true);
            return;
        }

        updateStatus('Uploading video...');
        setAllButtonsDisabled(true);

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/upload_for_inference', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            
            if (result.success) {
                updateStatus('Upload complete. Starting inference...', false);
                // Call the function to start the background job
                startInferenceProcess(result.input_path); 
            } else {
                updateStatus(result.message, true);
                setAllButtonsDisabled(false);
            }
        } catch (error) {
            updateStatus('A network error occurred during upload.', true);
            setAllButtonsDisabled(false);
        }
    });

    // 3. Function to start the background inference job
    async function startInferenceProcess(videoPath) {
        updateStatus('Starting inference... This may take several minutes.');
        setAllButtonsDisabled(true); // Disable all controls
        runOnLatestBtn.style.display = 'none'; // Hide button

        try {
            const response = await fetch('/run_inference', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_path: videoPath })
            });
            const result = await response.json();

            if (result.success) {
                // Start polling
                statusInterval = setInterval(checkInferenceStatus, 2000);
            } else {
                updateStatus(result.message, true);
                setAllButtonsDisabled(false);
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    }

    // 4. Function to poll for the job status
    async function checkInferenceStatus() {
        try {
            const response = await fetch('/check_inference_status');
            const result = await response.json();

            if (result.status === 'running') {
                updateStatus(result.message || 'Processing... please wait.');
            } else if (result.status === 'complete') {
                clearInterval(statusInterval); // Stop polling
                updateStatus(result.message, false);
                displayVideo(result.output_url); // Display the new video
                setAllButtonsDisabled(false); // Re-enable controls
                latestRecordedVideoPath = null; // Clear the "latest" video
            } else if (result.status === 'error') {
                clearInterval(statusInterval); // Stop polling
                updateStatus(result.message, true);
                setAllButtonsDisabled(false); // Re-enable controls
                latestRecordedVideoPath = null; // Clear the "latest" video
            }
        } catch (error) {
            clearInterval(statusInterval); // Stop polling on error
            updateStatus('Error checking status. Please reload.', true);
            setAllButtonsDisabled(false);
        }
    }
});