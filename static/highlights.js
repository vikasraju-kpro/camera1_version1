document.addEventListener('DOMContentLoaded', () => {
    const statusDiv = document.getElementById('status');
    const generateBtn = document.getElementById('generateBtn');
    const videoInput = document.getElementById('videoUpload');
    const outputsDiv = document.getElementById('outputs');

    function updateStatus(msg, isError = false) {
        statusDiv.textContent = msg;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
        statusDiv.style.backgroundColor = isError ? '#f8d7da' : '#d1e7dd';
    }

    generateBtn.addEventListener('click', async () => {
        const file = videoInput.files[0];
        if (!file) {
            updateStatus("Please select a video file first.", true);
            return;
        }

        updateStatus("Processing... This involves AI tracking, composing, and web-encoding. Please be patient.");
        generateBtn.disabled = true;
        
        // Reset display
        outputsDiv.style.display = 'none';
        ['cardHighlights', 'cardLongest', 'cardShortest'].forEach(id => {
            document.getElementById(id).style.display = 'none';
        });

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/api/process_highlights', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success) {
                updateStatus("Processing complete!");
                outputsDiv.style.display = 'grid';
                
                // Helper to setup a video card
                const setupCard = (key, vidId, dlId, cardId) => {
                    if (result.files[key]) {
                        const vid = document.getElementById(vidId);
                        const dl = document.getElementById(dlId);
                        const url = result.files[key] + '?t=' + new Date().getTime(); // Prevent caching
                        
                        vid.src = url;
                        dl.href = url;
                        // Set nice filename for download
                        dl.download = result.files[key].split('/').pop();
                        
                        document.getElementById(cardId).style.display = 'flex';
                    }
                };

                setupCard('highlights', 'vidHighlights', 'dlHighlights', 'cardHighlights');
                setupCard('longest', 'vidLongest', 'dlLongest', 'cardLongest');
                setupCard('shortest', 'vidShortest', 'dlShortest', 'cardShortest');

            } else {
                updateStatus("Error: " + result.message, true);
            }
        } catch (error) {
            updateStatus("Network error occurred.", true);
            console.error(error);
        }
        generateBtn.disabled = false;
    });
});