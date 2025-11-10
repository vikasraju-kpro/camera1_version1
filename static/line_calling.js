document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const statusDiv = document.getElementById('status');
    const startRecordBtn = document.getElementById('startLineCallBtn');
    const stopRecordBtn = document.getElementById('stopLineCallBtn');
    const recordUploadInput = document.getElementById('recordUpload');
    const uploadAsRecordingBtn = document.getElementById('uploadAsRecordingBtn');
    const mediaOutputDiv = document.getElementById('media-output');
    const mediaOutputDiv2D = document.getElementById('media-output-2d');
    const mediaOutputDiv2DZoom = document.getElementById('media-output-2d-zoom');
    const mediaOutputReplay = document.getElementById('media-output-replay');
    
    // --- Inference Selectors ---
    const videoUploadInput = document.getElementById('videoUpload');
    const autoRunBtn = document.getElementById('autoRunBtn'); // <-- RENAMED
    const runOnLatestBtn = document.getElementById('runOnLatestBtn');

    // --- NEW: Semi-Auto Selectors ---
    const semiAutoUploadBtn = document.getElementById('semiAutoUploadBtn');
    const semiAutoControls = document.getElementById('semi-auto-controls');
    const semiAutoStatus = document.getElementById('semi-auto-status');
    const frameDisplayContainer = document.getElementById('frame-display-container');
    const frameImage = document.getElementById('frame-image');
    const frameCanvas = document.getElementById('frame-canvas');
    const prevFrameBtn = document.getElementById('prevFrameBtn');
    const nextFrameBtn = document.getElementById('nextFrameBtn');
    const currentFrameNumSpan = document.getElementById('currentFrameNum');
    const runSemiAutoBtn = document.getElementById('runSemiAutoBtn');

    // --- Global State ---
    let latestRecordedVideoPath = null;
    let statusInterval = null; 
    let semiAutoVideoPath = null; // Path to the uploaded video for marking
    let currentFrameNum = 0;
    let manualPoints = [];
    let canvasCtx = frameCanvas.getContext('2d');
    let naturalFrameWidth = 1;
    let naturalFrameHeight = 1;

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
        mediaOutputDiv.innerHTML = '<h3>Annotated Video</h3>'; 
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime(); 
        video.controls = true;
        video.autoplay = true;
        video.muted = true; 
        const downloadLink = createDownloadLink(url, 'Download Video');
        mediaOutputDiv.appendChild(video);
        mediaOutputDiv.appendChild(downloadLink);
    }
    
    function displayReplayVideo(url) {
        mediaOutputReplay.innerHTML = '<h3>Slow-Motion Replay</h3>';
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime(); 
        video.controls = true;
        video.autoplay = true;
        video.muted = true; 
        video.loop = true; 
        video.style.maxWidth = '400px'; 
        const downloadLink = createDownloadLink(url, 'Download Replay');
        mediaOutputReplay.appendChild(video);
        mediaOutputReplay.appendChild(downloadLink);
    }

    function display2dImage(url) {
        mediaOutputDiv2D.innerHTML = '<h3>2D Full Court</h3>';
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime();
        img.alt = '2D Court Illustration';
        mediaOutputDiv2D.appendChild(img);
    }

    function display2dZoomImage(url) {
        mediaOutputDiv2DZoom.innerHTML = '<h3>2D Zoom</h3>';
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime();
        img.alt = '2D Zoomed Illustration';
        mediaOutputDiv2DZoom.appendChild(img);
    }

    function setAllButtonsDisabled(disabled) {
        startRecordBtn.disabled = disabled;
        stopRecordBtn.disabled = disabled;
        if (uploadAsRecordingBtn) uploadAsRecordingBtn.disabled = disabled;
        autoRunBtn.disabled = disabled;
        semiAutoUploadBtn.disabled = disabled;
        runOnLatestBtn.disabled = disabled;
    }
    
    function clearMedia() {
        mediaOutputDiv.innerHTML = '';
        mediaOutputDiv2D.innerHTML = '';
        mediaOutputDiv2DZoom.innerHTML = '';
        mediaOutputReplay.innerHTML = ''; 
        runOnLatestBtn.style.display = 'none';
        latestRecordedVideoPath = null;
        // Also hide semi-auto controls
        semiAutoControls.style.display = 'none';
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
                displayVideo(result.video_url); 
                latestRecordedVideoPath = result.video_url; 
                runOnLatestBtn.style.display = 'inline-block'; 
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
            setAllButtonsDisabled(false);
        }
    });

    // --- NEW: Upload-as-Recording Event Listener ---
    if (uploadAsRecordingBtn) {
        uploadAsRecordingBtn.addEventListener('click', async () => {
            const file = recordUploadInput?.files?.[0];
            if (!file) {
                updateStatus('Please select a video file to upload as recording.', true);
                return;
            }
            updateStatus('Uploading video as recording...');
            setAllButtonsDisabled(true);
            clearMedia();
            const formData = new FormData();
            formData.append('video', file);
            try {
                const response = await fetch('/upload_line_call', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                updateStatus(result.message, !result.success);
                setAllButtonsDisabled(false);
                if (result.success && result.video_url) {
                    displayVideo(result.video_url);
                    latestRecordedVideoPath = result.video_url;
                    runOnLatestBtn.style.display = 'inline-block';
                }
            } catch (error) {
                updateStatus('A network error occurred during upload.', true);
                setAllButtonsDisabled(false);
            }
        });
    }


    // --- Inference Event Listeners & Functions ---

    runOnLatestBtn.addEventListener('click', () => {
        if (latestRecordedVideoPath) {
            startInferenceProcess(latestRecordedVideoPath, null); // null for manual_points
        } else {
            updateStatus('No recorded video found.', true);
        }
    });

    // --- MODIFIED: Auto-Run Button ---
    autoRunBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to upload.', true);
            return;
        }

        updateStatus('Uploading video for Auto-Run...');
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
                updateStatus('Upload complete. Starting auto-inference...', false);
                startInferenceProcess(result.input_path, null); // null for manual_points
            } else {
                updateStatus(result.message, true);
                setAllButtonsDisabled(false);
            }
        } catch (error) {
            updateStatus('A network error occurred during upload.', true);
            setAllButtonsDisabled(false);
        }
    });

    // --- NEW: Semi-Auto Upload Button ---
    semiAutoUploadBtn.addEventListener('click', async () => {
        const file = videoUploadInput.files[0];
        if (!file) {
            updateStatus('Please select a video file to upload.', true);
            return;
        }

        updateStatus('Uploading video for Semi-Auto...');
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
                semiAutoVideoPath = result.input_path;
                currentFrameNum = 0;
                manualPoints = [];
                semiAutoControls.style.display = 'block';
                runSemiAutoBtn.style.display = 'none';
                loadFrame(currentFrameNum);
                updateSemiAutoStatus();
            } else {
                updateStatus(result.message, true);
                setAllButtonsDisabled(false);
            }
        } catch (error) {
            updateStatus('A network error occurred during upload.', true);
            setAllButtonsDisabled(false);
        }
    });
    
    // --- NEW: Semi-Auto Frame Navigation ---
    prevFrameBtn.addEventListener('click', () => {
        if (currentFrameNum > 0) {
            loadFrame(currentFrameNum - 1);
        }
    });

    nextFrameBtn.addEventListener('click', () => {
        loadFrame(currentFrameNum + 1);
    });

    async function loadFrame(frameNum) {
        updateSemiAutoStatus('Loading frame...');
        try {
            const response = await fetch('/get_video_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: semiAutoVideoPath,
                    frame_number: frameNum
                })
            });
            const result = await response.json();
            
            if (result.success) {
                frameImage.src = result.image_url;
                currentFrameNum = frameNum;
                currentFrameNumSpan.textContent = frameNum;
                prevFrameBtn.disabled = (currentFrameNum === 0);
                
                // Store natural dimensions for click scaling
                naturalFrameWidth = result.width;
                naturalFrameHeight = result.height;
                
                // Resize canvas to match image display size
                frameImage.onload = () => {
                    resizeCanvas();
                    drawPoints(); // Redraw existing points
                    updateSemiAutoStatus(); // Update instructions
                }
            } else {
                updateStatus(result.message, true);
                nextFrameBtn.disabled = true; // Likely end of video
            }
        } catch (error) {
            updateStatus('Error fetching frame.', true);
        }
    }
    
    function resizeCanvas() {
        frameCanvas.width = frameImage.clientWidth;
        frameCanvas.height = frameImage.clientHeight;
        canvasCtx = frameCanvas.getContext('2d');
    }
    
    // Handle canvas clicks for point marking
    frameCanvas.addEventListener('click', (e) => {
        if (manualPoints.length >= 4) return;

        const rect = frameCanvas.getBoundingClientRect();
        
        // Get click position relative to canvas
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Scale click position to match video's *natural* dimensions
        const scaleX = naturalFrameWidth / frameCanvas.width;
        const scaleY = naturalFrameHeight / frameCanvas.height;
        
        const naturalX = x * scaleX;
        const naturalY = y * scaleY;
        
        manualPoints.push([naturalX, naturalY]);
        drawPoints();
        updateSemiAutoStatus();
    });
    
    function drawPoints() {
        canvasCtx.clearRect(0, 0, frameCanvas.width, frameCanvas.height);
        
        // Scale natural points back to canvas points
        const scaleX = frameCanvas.width / naturalFrameWidth;
        const scaleY = frameCanvas.height / naturalFrameHeight;
        
        canvasCtx.fillStyle = 'red';
        canvasCtx.strokeStyle = 'white';
        canvasCtx.lineWidth = 2;

        manualPoints.forEach((point, index) => {
            const x = point[0] * scaleX;
            const y = point[1] * scaleY;
            
            canvasCtx.beginPath();
            canvasCtx.arc(x, y, 5, 0, 2 * Math.PI);
            canvasCtx.fill();
            canvasCtx.stroke();
            
            canvasCtx.fillText((index + 1).toString(), x + 7, y + 7);
        });
    }

    function updateSemiAutoStatus() {
        const pointLabels = ["Top-Left (Baseline)", "Top-Right (Baseline)", "Bottom-Left (Service Line)", "Bottom-Right (Service Line)"];
        const nextPoint = manualPoints.length;

        if (nextPoint >= 4) {
            semiAutoStatus.textContent = "4 points selected. Ready to run.";
            runSemiAutoBtn.style.display = 'block';
        } else {
            semiAutoStatus.textContent = `Click Point ${nextPoint + 1}: ${pointLabels[nextPoint]}`;
            runSemiAutoBtn.style.display = 'none';
        }
    }
    
    // --- NEW: Run Semi-Auto Inference ---
    runSemiAutoBtn.addEventListener('click', () => {
        if (manualPoints.length < 4) {
            updateStatus("Please mark all 4 points.", true);
            return;
        }
        
        // The points are already in the correct (x, y) format
        startInferenceProcess(semiAutoVideoPath, manualPoints);
    });

    // --- MODIFIED: Main Inference Function ---
    async function startInferenceProcess(videoPath, manual_points = null) {
        let mode = manual_points ? "Semi-Auto" : "Auto";
        updateStatus(`Starting ${mode} 2-stage inference... This may take several minutes.`);
        setAllButtonsDisabled(true); 
        clearMedia(); 
        semiAutoControls.style.display = 'none'; // Hide marking UI

        try {
            // Build the request body
            let body = { 
                input_path: videoPath,
                manual_points: manual_points // Will be null for auto-mode
            };

            const response = await fetch('/run_inference', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
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

    // --- MODIFIED: Polling Function (no changes, but shown for context) ---
    async function checkInferenceStatus() {
        try {
            const response = await fetch('/check_inference_status');
            const result = await response.json();

            if (result.status === 'running') {
                updateStatus(result.message || 'Processing... please wait.');
            } else if (result.status === 'complete') {
                clearInterval(statusInterval); 
                updateStatus(result.message, false);
                
                displayVideo(result.output_url); 
                
                if (result.output_replay_url) {
                    displayReplayVideo(result.output_replay_url);
                }
                if (result.output_2d_url) {
                    display2dImage(result.output_2d_url);
                }
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