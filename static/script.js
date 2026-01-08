document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors for Main Page ---
    const statusDiv = document.getElementById('status');
    const captureBtn = document.getElementById('captureBtn');
    const startRecordBtn = document.getElementById('startRecordBtn');
    const stopRecordBtn = document.getElementById('stopRecordBtn');
    const statusBtn = document.getElementById('statusBtn');
    const healthBtn = document.getElementById('healthBtn');
    const restartAppBtn = document.getElementById('restartAppBtn');
    const restartSystemBtn = document.getElementById('restartSystemBtn');
    const mediaOutputDiv = document.getElementById('media-output');

    // --- Helper Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
        statusDiv.style.backgroundColor = isError ? '#f8d7da' : '#d1e7dd';
    }

    function displayImage(url) {
        mediaOutputDiv.innerHTML = ''; // Clear previous output
        const img = document.createElement('img');
        img.src = url + '?t=' + new Date().getTime(); // Bust cache
        img.alt = 'Captured Image';
        
        const downloadLink = createDownloadLink(url, 'Download Image');
        mediaOutputDiv.appendChild(img);
        mediaOutputDiv.appendChild(downloadLink);
    }

    function displayVideo(url) {
        mediaOutputDiv.innerHTML = ''; // Clear previous output
        const video = document.createElement('video');
        video.src = url;
        video.controls = true;
        video.autoplay = true;
        video.muted = true; // Autoplay often requires video to be muted

        const downloadLink = createDownloadLink(url, 'Download Video');
        mediaOutputDiv.appendChild(video);
        mediaOutputDiv.appendChild(downloadLink);
    }
    
    function createDownloadLink(url, text) {
        const a = document.createElement('a');
        a.href = url;
        a.textContent = text;
        a.className = 'download-button';
        a.download = url.substring(url.lastIndexOf('/') + 1);
        return a;
    }

    // --- Event Listeners for Main Page ---
    captureBtn.addEventListener('click', async () => {
        updateStatus('Capturing image...');
        try {
            const response = await fetch('/capture_image', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success && result.image_url) {
                displayImage(result.image_url);
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
        }
    });

    startRecordBtn.addEventListener('click', async () => {
        updateStatus('Starting recording...');
        try {
            const response = await fetch('/start_recording', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                startRecordBtn.disabled = true;
                stopRecordBtn.disabled = false;
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
        }
    });

    stopRecordBtn.addEventListener('click', async () => {
        updateStatus('Stopping recording and processing video...');
        try {
            const response = await fetch('/stop_recording', { method: 'POST' });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                startRecordBtn.disabled = false;
                stopRecordBtn.disabled = true;
                if (result.video_url) {
                    displayVideo(result.video_url);
                }
            }
        } catch (error) {
            updateStatus('A network error occurred.', true);
        }
    });

    statusBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/device_status');
            const data = await response.json();
            const statusMessage = `Device: ${data.name} (ID: ${data.device_id}) - Status: ${data.message}`;
            updateStatus(statusMessage);
        } catch (error) {
            updateStatus('Failed to get device status.', true);
        }
    });

    healthBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/health_report');
            const data = await response.json();
            
            if (data.error) {
                updateStatus(`Error: ${data.details}`, true);
            } else {
                // Build the health report string
                let report = `Device ID: ${data.device_id} | CPU: ${data.cpu_usage_percent}% | Memory: ${data.memory_usage_percent}% | Disk: ${data.disk_usage_percent}%`;
                // Add temperature if it exists in the response
                if (data.cpu_temperature_c !== null) {
                    report += ` | Temp: ${data.cpu_temperature_c}°C`;
                }
                updateStatus(report, false);
            }
        } catch (error) {
            updateStatus('Failed to get health report.', true);
        }
    });

    restartAppBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to restart the application?')) {
            updateStatus('Restarting application...');
            await fetch('/restart_app', { method: 'POST' });
        }
    });

    restartSystemBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to RESTART THE ENTIRE SYSTEM?')) {
            updateStatus('Restarting system...');
            await fetch('/restart_system', { method: 'POST' });
        }
    });
});