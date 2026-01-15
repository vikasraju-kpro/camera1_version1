document.addEventListener('DOMContentLoaded', () => {
    // --- Global Status ---
    const statusDiv = document.getElementById('status');
    
    // --- Recording & Replay Elements ---
    const startBtn = document.getElementById('startRecordBtn');
    const stopBtn = document.getElementById('stopRecordBtn');
    const replayBtn = document.getElementById('replayBtn');
    
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
    let currentMatchType = 'singles'; // Default

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.innerHTML = message;
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

    function getMatchDetails() {
        const type = document.querySelector('input[name="matchType"]:checked').value;
        let players = [];
        
        if (type === 'singles') {
            const p1 = document.getElementById('p1').value.trim();
            const p2 = document.getElementById('p2').value.trim();
            if (!p1 || !p2) return null; // Validation failed
            players = [p1, p2];
        } else {
            const dp1 = document.getElementById('dp1').value.trim();
            const dp2 = document.getElementById('dp2').value.trim();
            const dp3 = document.getElementById('dp3').value.trim();
            const dp4 = document.getElementById('dp4').value.trim();
            if (!dp1 || !dp2 || !dp3 || !dp4) return null;
            players = [dp1, dp2, dp3, dp4];
        }
        return { type, players };
    }

    // ==========================================
    // RECORDING & REPLAY LOGIC
    // ==========================================

    startBtn.addEventListener('click', async () => {
        // 1. Validate Input
        const details = getMatchDetails();
        if (!details) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Please enter all player names before starting.', true);
            return;
        }

        currentMatchType = details.type; // Store for stop logic

        updateStatus('<i class="fas fa-spinner fa-spin"></i> Starting match recording...');
        startBtn.disabled = true;
        stopBtn.disabled = true;
        manualHighlightBtn.disabled = true; 
        
        // Hide previous outputs
        matchOutputDiv.style.display = 'none';
        hideHighlightOutputs();

        try {
            // 2. Send Data to Backend
            const response = await fetch('/start_recording', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(details)
            });
            const result = await response.json();
            
            if (result.success) {
                updateStatus('<i class="fas fa-circle fa-beat" style="color: red;"></i> Match Recording in progress...', false);
                stopBtn.disabled = false;
                replayBtn.disabled = false;
            } else {
                updateStatus('<i class="fas fa-exclamation-triangle"></i> Error: ' + result.message, true);
                startBtn.disabled = false;
                manualHighlightBtn.disabled = false;
            }
        } catch (error) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Network error starting recording.', true);
            startBtn.disabled = false;
            manualHighlightBtn.disabled = false;
        }
    });

    stopBtn.addEventListener('click', async () => {
        updateStatus('<i class="fas fa-spinner fa-spin"></i> Stopping match... Finalizing video file.');
        stopBtn.disabled = true;
        replayBtn.disabled = true;

        try {
            const response = await fetch('/stop_recording', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                updateStatus('<i class="fas fa-check-circle"></i> Match saved!', false);
                startBtn.disabled = false;
                manualHighlightBtn.disabled = false;
                
                if (result.video_url) {
                    currentRecordedVideoUrl = result.video_url; 
                    
                    const url = result.video_url + '?t=' + new Date().getTime();
                    recordedVideo.src = url;
                    downloadLink.href = url;
                    downloadLink.download = url.split('/').pop();
                    
                    matchOutputDiv.style.display = 'flex';
                    
                    // --- CONDITIONAL HIGHLIGHTS ---
                    if (currentMatchType === 'singles') {
                        autoGenerateHighlights(result.video_url);
                    } else {
                        updateStatus('<i class="fas fa-check-circle"></i> Doubles Match saved! (AI Highlights skipped for Doubles)', false);
                    }
                }
            } else {
                updateStatus('<i class="fas fa-exclamation-triangle"></i> Error: ' + result.message, true);
                stopBtn.disabled = false;
                replayBtn.disabled = false;
            }
        } catch (error) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Network error stopping recording.', true);
            stopBtn.disabled = false;
        }
    });

    replayBtn.addEventListener('click', async () => {
        const originalText = replayBtn.innerHTML; 
        replayBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        replayBtn.disabled = true;

        try {
            const response = await fetch('/create_instant_replay', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                updateStatus('<i class="fas fa-check-circle"></i> Replay clip created!', false);
                
                if (result.video_url) {
                    const url = result.video_url + '?t=' + new Date().getTime();
                    replayVideo.src = url;
                    replayDownloadLink.href = url;
                    replayDownloadLink.download = url.split('/').pop();
                    replayOutputDiv.style.display = 'flex';
                    replayOutputDiv.scrollIntoView({ behavior: 'smooth' });
                }
            } else {
                updateStatus('<i class="fas fa-exclamation-triangle"></i> Replay Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Network error creating replay.', true);
        } finally {
            setTimeout(() => {
                replayBtn.innerHTML = originalText;
                replayBtn.disabled = false;
            }, 2000);
        }
    });

    // ==========================================
    // HIGHLIGHTS LOGIC
    // ==========================================

    async function autoGenerateHighlights(videoPath) {
        updateStatus('<i class="fas fa-check-circle"></i> Match saved! <i class="fas fa-magic"></i> Analyzing for highlights... This may take a few minutes.', false);
        hideHighlightOutputs();

        try {
            const response = await fetch('/api/process_highlights_from_path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_path: videoPath })
            });
            const result = await response.json();

            if (result.success) {
                updateStatus('<i class="fas fa-check-circle"></i> Highlights generated successfully!', false);
                setupHighlightCards(result);
            } else {
                updateStatus('<i class="fas fa-exclamation-triangle"></i> Highlight Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Network error generating highlights.', true);
        }
    }

    // 2. Manual Upload & Generate
    manualHighlightBtn.addEventListener('click', async () => {
        const file = manualHighlightUpload.files[0];
        if (!file) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Please select a video file to upload first.', true);
            return;
        }

        updateStatus('<i class="fas fa-spinner fa-spin"></i> Uploading video & generating highlights... This may take a few minutes.');
        manualHighlightBtn.disabled = true;
        startBtn.disabled = true; 

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
                updateStatus('<i class="fas fa-check-circle"></i> Highlights generated successfully from upload!', false);
                setupHighlightCards(result);
            } else {
                updateStatus('<i class="fas fa-exclamation-triangle"></i> Highlight Error: ' + result.message, true);
            }
        } catch (error) {
            updateStatus('<i class="fas fa-exclamation-circle"></i> Network error during upload/generation.', true);
        } finally {
            manualHighlightBtn.disabled = false;
            startBtn.disabled = false;
        }
    });
});