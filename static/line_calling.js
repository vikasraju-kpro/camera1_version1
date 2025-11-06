document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const statusDiv = document.getElementById('status');
    const startRecordBtn = document.getElementById('startLineCallBtn');
    const stopRecordBtn = document.getElementById('stopLineCallBtn');
    const mediaOutputDiv = document.getElementById('media-output');
    const mediaOutputDiv2D = document.getElementById('media-output-2d');
    const mediaOutputDiv2DZoom = document.getElementById('media-output-2d-zoom');
    const mediaOutputReplay = document.getElementById('media-output-replay'); // <-- NEW
    
    // --- Inference Selectors ---
    const videoUploadInput = document.getElementById('videoUpload');
    const uploadAndRunBtn = document.getElementById('uploadAndRunBtn');
    const runOnLatestBtn = document.getElementById('runOnLatestBtn');

    // --- Global State ---
    let latestRecordedVideoPath = null;
    let statusInterval = null; 

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
        mediaOutputDiv.innerHTML = '<h3>Annotated Video</h3>'; // Clear previous output
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime(); // Cache bust
        video.controls = true;
        video.autoplay = true;
        video.muted = true; 

        const downloadLink = createDownloadLink(url, 'Download Video');
        mediaOutputDiv.appendChild(video);
        mediaOutputDiv.appendChild(downloadLink);
    }
    
    // --- NEW: Function to display replay video ---
    function displayReplayVideo(url) {
        mediaOutputReplay.innerHTML = '<h3>Slow-Motion Replay</h3>'; // Clear previous
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime(); // Cache bust
        video.controls = true;
        video.autoplay = true;
        video.muted = true; 
        video.loop = true; // Loop the replay
        video.style.maxWidth = '400px'; // Match image size

        const downloadLink = createDownloadLink(url, 'Download Replay');
        mediaOutputReplay.appendChild(video);
        mediaOutputReplay.appendChild(downloadLink);
    }

    function display2dImage(url) {
        mediaOutputDiv2D.innerHTML = '<h3>2D Full Court</h3>'; // Clear previous
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime(); // Cache bust
        img.alt = '2D Court Illustration';
        mediaOutputDiv2D.appendChild(img);
    }

    function display2dZoomImage(url) {
        mediaOutputDiv2DZoom.innerHTML = '<h3>2D Zoom</h3>'; // Clear previous
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime(); // Cache bust
        img.alt = '2D Zoomed Illustration';
        mediaOutputDiv2DZoom.appendChild(img);
    }

    function setAllButtonsDisabled(disabled) {
        startRecordBtn.disabled = disabled;
        stopRecordBtn.disabled = disabled;
        uploadAndRunBtn.disabled = disabled;
        runOnLatestBtn.disabled = disabled;
    }
    
    function clearMedia() {
        mediaOutputDiv.innerHTML = '';
        mediaOutputDiv2D.innerHTML = '';
        mediaOutputDiv2DZoom.innerHTML = '';
        mediaOutputReplay.innerHTML = ''; // <-- NEW
        runOnLatestBtn.style.display = 'none';
        latestRecordedVideoPath = null;
    }

    // --- Recording Event Listeners ---
    startRecordBtn.addEventListener('click', async () => {
        updateStatus('Starting line call recording...');
        setAllButtonsDisabled(true); 
        clearMedia(); 
        try {
            const response = await fetch('/start_line_calling', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                stopRecordBtn.disabled = false;
            } else {
                setAllButtonsDisabled(false); 
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    });

    stopRecordBtn.addEventListener('click', async () => {
        updateStatus('Stopping recording and processing video...');
        clearMedia(); 
        try {
            const response = await fetch('/stop_line_calling', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            setAllButtonsDisabled(false); 
            
            if (result.success && result.video_url) {
                displayVideo(result.video_url); // Display original recorded video
                latestRecordedVideoPath = result.video_url; 
                runOnLatestBtn.style.display = 'inline-block'; 
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    });


    // --- Inference Event Listeners & Functions ---

    runOnLatestBtn.addEventListener('click', () => {
        if (latestRecordedVideoPath) {
            startInferenceProcess(latestRecordedVideoPath);
        } else {
            updateStatus('No recorded video found.', true);
        }
    });

    uploadAndRunBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to upload.', true);
            return;
        }

        updateStatus('Uploading video...');
        setAllButtonsDisabled(true);
        clearMedia(); 

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

    async function startInferenceProcess(videoPath) {
        updateStatus('Starting 2-stage inference... This may take several minutes.');
        setAllButtonsDisabled(true); 
        clearMedia(); 

        try {
            const response = await fetch('/run_inference', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_path: videoPath })
            });
            const result = await response.json();

            if (result.success) {
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

    async function checkInferenceStatus() {
        try {
            const response = await fetch('/check_inference_status');
            const result = await response.json();

            if (result.status === 'running') {
                updateStatus(result.message || 'Processing... please wait.');
            } else if (result.status === 'complete') {
                clearInterval(statusInterval); 
                updateStatus(result.message, false);
                
                // Display annotated video
                displayVideo(result.output_url); 
                
                // --- NEW: Display the replay video ---
                if (result.output_replay_url) {
                    displayReplayVideo(result.output_replay_url);
                }

                // Display the full 2D image
                if (result.output_2d_url) {
                    display2dImage(result.output_2d_url);
                }
                
                // Display the 2D zoom image
                if (result.output_2d_zoom_url) {
                    display2dZoomImage(result.output_2d_zoom_url);
                }

                setAllButtonsDisabled(false); 
                latestRecordedVideoPath = null; 
            } else if (result.status === 'error') {
                clearInterval(statusInterval); 
                updateStatus(result.message, true);
                setAllButtonsDisabled(false); 
                latestRecordedVideoPath = null; 
            }
        } catch (error) {
            clearInterval(statusInterval); 
            updateStatus('Error checking status. Please reload.', true);
            setAllButtonsDisabled(false);
        }
    }
});