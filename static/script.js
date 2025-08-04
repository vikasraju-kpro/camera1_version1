document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const captureBtn = document.getElementById('captureBtn');
    const startRecordBtn = document.getElementById('startRecordBtn');
    const stopRecordBtn = document.getElementById('stopRecordBtn');
    const statusBtn = document.getElementById('statusBtn');
    const healthBtn = document.getElementById('healthBtn');
    const restartAppBtn = document.getElementById('restartAppBtn');
    const restartPiBtn = document.getElementById('restartPiBtn');
    const statusDiv = document.getElementById('status');
    const mediaOutputDiv = document.getElementById('media-output');

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
    }

    function clearMediaOutput() {
        mediaOutputDiv.innerHTML = '';
    }

    function displayImage(url) {
        clearMediaOutput();
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime();
        img.alt = 'Captured Image';

        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.textContent = 'Download Image';
        downloadLink.className = 'download-button';
        downloadLink.download = url.substring(url.lastIndexOf('/') + 1);

        mediaOutputDiv.appendChild(img);
        mediaOutputDiv.appendChild(downloadLink);
    }

    function displayVideo(url) {
        clearMediaOutput();
        const video = document.createElement('video');
        video.src = url + '?t=' + new Date().getTime();
        video.controls = true;
        video.muted = true;
        video.autoplay = true;
        video.playsinline = true;

        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.textContent = 'Download Video';
        downloadLink.className = 'download-button';
        downloadLink.download = url.substring(url.lastIndexOf('/') + 1);

        mediaOutputDiv.appendChild(video);
        mediaOutputDiv.appendChild(downloadLink);

        video.load();
        video.play().catch(error => {
            console.warn("Autoplay was prevented by the browser.", error);
        });
    }

    async function apiPost(endpoint) {
        try {
            const response = await fetch(endpoint, { method: 'POST' });
            return await response.json();
        } catch (error) {
            return { success: false, message: 'A network error occurred.' };
        }
    }

    // --- Event Listeners ---
    statusBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            updateStatus(data.message, false);
        } catch (error) {
            updateStatus('Failed to get status.', true);
        }
    });

    captureBtn.addEventListener('click', async () => {
        updateStatus('Capturing image...');
        const result = await apiPost('/capture_image');
        updateStatus(result.message, !result.success);
        if (result.success && result.image_url) {
            displayImage(result.image_url);
        }
    });

    startRecordBtn.addEventListener('click', async () => {
        updateStatus('Starting recording...');
        const result = await apiPost('/start_recording');
        updateStatus(result.message, !result.success);
        if (result.success) {
            startRecordBtn.disabled = true;
            stopRecordBtn.disabled = false;
            captureBtn.disabled = true;
        }
    });

    stopRecordBtn.addEventListener('click', async () => {
        updateStatus('Stopping recording...');
        const result = await apiPost('/stop_recording');
        updateStatus(result.message, !result.success);
        if (result.success) {
            startRecordBtn.disabled = false;
            stopRecordBtn.disabled = true;
            captureBtn.disabled = false;
            if (result.video_url) {
                displayVideo(result.video_url);
            }
        } else {
            startRecordBtn.disabled = false;
            stopRecordBtn.disabled = true;
            captureBtn.disabled = false;
        }
    });

    healthBtn.addEventListener('click', async () => {
        updateStatus('Fetching health report...');
        try {
            const response = await fetch('/health_report');
            const data = await response.json();
            if (data.error) {
                updateStatus(`Error: ${data.details}`, true);
            } else {
                const report = `CPU: ${data.cpu_usage_percent}% | Memory: ${data.memory_usage_percent}% | Disk: ${data.disk_usage_percent}%`;
                updateStatus(report, false);
            }
        } catch (error) {
            updateStatus('Failed to fetch health report.', true);
        }
    });

    restartAppBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to restart the application?')) {
            updateStatus('Restarting application...');
            await apiPost('/restart_app');
        }
    });

    restartPiBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to restart the Raspberry Pi? This will disconnect you.')) {
            updateStatus('Restarting Raspberry Pi...');
            apiPost('/restart_pi');
        }
    });
});