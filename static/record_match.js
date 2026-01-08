document.addEventListener('DOMContentLoaded', () => {
    // --- Global Status ---
    const statusDiv = document.getElementById('status');
    
    // --- Recording & Replay Elements ---
    const startBtn = document.getElementById('startRecordBtn');
    const stopBtn = document.getElementById('stopRecordBtn');
    const replayBtn = document.getElementById('replayBtn');
    const genHighlightsBtn = document.getElementById('generateHighlightsBtn');
    
    const matchOutputDiv = document.getElementById('match-output');
    const recordedVideo = document.getElementById('recordedVideo');
    const downloadLink = document.getElementById('downloadLink');

    const replayOutputDiv = document.getElementById('replay-output');
    const replayVideo = document.getElementById('replayVideo');
    const replayDownloadLink = document.getElementById('replayDownloadLink');

    const highlightsOutputDiv = document.getElementById('highlights-output');

    // --- Manual Highlight Elements ---
    const manualHighlightUpload = document.getElementById('manualHighlightUpload');
    const manualHighlightBtn = document.getElementById('manualHighlightBtn');

    // --- State Variables ---
    let currentRecordedVideoUrl = null;

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
        statusDiv.style.backgroundColor = isError ? '#f8d7da' : '#d1e7dd';
    }

    function setupHighlightCards(result) {
        highlightsOutputDiv.style.display = 'grid';
        
        const setupCard = (key, vidId, dlId, cardId) => {
            if (result.files[key]) {
                const vid = document.getElementById(vidId);
                const dl = document.getElementById(dlId);
                const url = result.files[key] + '?t=' + new Date().getTime();
                vid.src = url;
                dl.href = url;
                dl.download = result.files[key].split('/').pop();
                document.getElementById(cardId).style.display = 'flex';
            }
        };
        setupCard('highlights', 'vidHighlights', 'dlHighlights', 'cardHighlights');
        setupCard('longest', 'vidLongest', 'dlLongest', 'cardLongest');
        setupCard('shortest', 'vidShortest', 'dlShortest', 'cardShortest');
        
        highlightsOutputDiv.scrollIntoView({ behavior: 'smooth' });
    }

    function hideHighlightOutputs() {
        ['cardHighlights', 'cardLongest', 'cardShortest'].forEach(id => {
            document.getElementById(id).style.display = 'none';
        });
        highlightsOutputDiv.style.display = 'none';
    }

    // ==========================================
    // RECORDING & REPLAY LOGIC
    // ==========================================

    startBtn.addEventListener('click', async () => {
        updateStatus('Starting match recording...');
        startBtn.disabled = true;
        stopBtn.disabled = true;
        genHighlightsBtn.disabled = true;
        
        // Hide previous outputs
        matchOutputDiv.style.display = 'none';
        hideHighlightOutputs();

        try {
            const response = await fetch('/start_recording', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                updateStatus('🔴 Match Recording in progress...', false);
                stopBtn.disabled = false;
                replayBtn.disabled = false;
            } else {
                updateStatus('Error: ' + result.message, true);
                startBtn.disabled = false;
            }
        } catch (error) {
            updateStatus('Network error starting recording.', true);
            startBtn.disabled = false;
        }
    });

    stopBtn.addEventListener('click', async () => {
        updateStatus('Stopping match... Finalizing video file.');
        stopBtn.disabled = true;
        replayBtn.disabled = true;

        try {
            const response = await fetch('/stop_recording', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                updateStatus('✅ Match saved!', false);
                startBtn.disabled = false;
                
                if (result.video_url) {
                    currentRecordedVideoUrl = result.video_url; // Store for highlights
                    
                    const url = result.video_url + '?t=' + new Date().getTime();
                    recordedVideo.src = url;
                    downloadLink.href = url;
                    downloadLink.download = url.split('/').pop();
                    
                    matchOutputDiv.style.display = 'flex';
                    genHighlightsBtn.disabled = false;
                }
            } else {
                updateStatus('Error: ' + result.message, true);
                stopBtn.disabled = false;
                replayBtn.disabled = false;
            }
        } catch (error) {
            updateStatus('Network error stopping recording.', true);
            stopBtn.disabled = false;
        }
    });

    replayBtn.addEventListener('click', async () => {
        const originalText = replayBtn.innerText;
        replayBtn.innerText = "⏳ Saving...";
        replayBtn.disabled = true;

        try {
            const response = await fetch('/create_instant_replay', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                updateStatus('✅ Replay clip created!', false);
                
                if (result.video_url) {
                    const url = result.video_url + '?t=' + new Date().getTime();
                    replayVideo.src = url;
                    replayDownloadLink.href = url;
                    replayDownloadLink.download = url.split('/').pop();
                    replayOutputDiv.style.display = 'flex';
                    replayOutputDiv.scrollIntoView({ behavior: 'smooth' });
                }
            } else {
                updateStatus('Replay Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('Network error creating replay.', true);
        } finally {
            setTimeout(() => {
                replayBtn.innerText = originalText;
                replayBtn.disabled = false;
            }, 2000);
        }
    });

    // ==========================================
    // HIGHLIGHTS LOGIC
    // ==========================================

    // 1. Generate from Recorded Match
    genHighlightsBtn.addEventListener('click', async () => {
        if (!currentRecordedVideoUrl) {
            updateStatus('No recorded video found.', true);
            return;
        }

        updateStatus('✨ Analyzing recorded match for highlights... This may take a few minutes.');
        genHighlightsBtn.disabled = true;
        manualHighlightBtn.disabled = true;
        
        hideHighlightOutputs();

        try {
            const response = await fetch('/api/process_highlights_from_path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_path: currentRecordedVideoUrl })
            });
            const result = await response.json();

            if (result.success) {
                updateStatus('✅ Highlights generated successfully!', false);
                setupHighlightCards(result);
            } else {
                updateStatus('Highlight Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('Network error generating highlights.', true);
        } finally {
            genHighlightsBtn.disabled = false;
            manualHighlightBtn.disabled = false;
        }
    });

    // 2. Manual Upload & Generate
    manualHighlightBtn.addEventListener('click', async () => {
        const file = manualHighlightUpload.files[0];
        if (!file) {
            updateStatus('Please select a video file to upload first.', true);
            return;
        }

        updateStatus('Uploading video & generating highlights... This may take a few minutes.');
        manualHighlightBtn.disabled = true;
        genHighlightsBtn.disabled = true;

        hideHighlightOutputs();

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/api/process_highlights', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success) {
                updateStatus('✅ Highlights generated successfully from upload!', false);
                setupHighlightCards(result);
            } else {
                updateStatus('Highlight Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('Network error during upload/generation.', true);
        } finally {
            manualHighlightBtn.disabled = false;
            genHighlightsBtn.disabled = false;
        }
    });
});