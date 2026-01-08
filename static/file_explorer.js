document.addEventListener('DOMContentLoaded', () => {
    const statusDiv = document.getElementById('status');
    // --- NEW: Modal Elements ---
    const pinModal = document.getElementById('pinModal');
    const pinInput = document.getElementById('pinInput');
    const pinCancelBtn = document.getElementById('pinCancelBtn');
    const pinConfirmBtn = document.getElementById('pinConfirmBtn');
    let filesToDelete = []; // To store which files are pending deletion

    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
    }

    // --- NEW: Modal Functions ---
    function showPinModal() {
        pinInput.value = '';
        pinModal.style.display = 'flex';
        pinInput.focus();
    }

    function hidePinModal() {
        pinModal.style.display = 'none';
    }

    function createFileRow(file) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><input type="checkbox" class="file-checkbox" value="${file.path}"></td>
            <td><a href="/${file.path}" target="_blank">${file.name}</a></td>
            <td>${file.size}</td>
            <td>${file.modified_date}</td>
        `;
        return row;
    }

    function setupSectionEventListeners(sectionId) {
        const section = document.getElementById(sectionId);
        const deleteSelectedBtn = section.querySelector('.delete-selected');
        // (other variables remain the same as before)
        const selectAllCheckbox = section.querySelector('.select-all');
        const fileListBody = section.querySelector('.file-list');
        const downloadSelectedBtn = section.querySelector('.download-selected');
        const downloadAllBtn = section.querySelector('.download-all');
        const fileType = sectionId.includes('image') ? 'images' : 'videos';

        function updateButtonState() {
            const selectedCount = section.querySelectorAll('.file-checkbox:checked').length;
            const hasSelection = selectedCount > 0;
            downloadSelectedBtn.disabled = !hasSelection;
            deleteSelectedBtn.disabled = !hasSelection;
        }

        selectAllCheckbox.addEventListener('change', () => {
            section.querySelectorAll('.file-checkbox').forEach(cb => cb.checked = selectAllCheckbox.checked);
            updateButtonState();
        });

        fileListBody.addEventListener('change', e => {
            if (e.target.classList.contains('file-checkbox')) {
                updateButtonState();
            }
        });

        downloadAllBtn.addEventListener('click', () => {
            updateStatus(`Zipping all ${fileType}...`);
            window.location.href = `/api/download_zip?type=all_${fileType}`;
        });

        downloadSelectedBtn.addEventListener('click', async () => {
            const selectedFiles = Array.from(section.querySelectorAll('.file-checkbox:checked')).map(cb => cb.value);
            if (selectedFiles.length === 0) return;
            updateStatus(`Zipping selected ${fileType}...`);
            
            const response = await fetch('/api/download_zip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: selectedFiles })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `${fileType}_selection.zip`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                updateStatus('Download started.');
            } else {
                updateStatus('Failed to create ZIP file.', true);
            }
        });

        // --- UPDATED: Delete Button Logic ---
        deleteSelectedBtn.addEventListener('click', () => {
            filesToDelete = Array.from(section.querySelectorAll('.file-checkbox:checked')).map(cb => cb.value);
            if (filesToDelete.length === 0) return;

            if (confirm(`You are about to delete ${filesToDelete.length} file(s). Continue?`)) {
                showPinModal(); // Show the modal instead of sending the request directly
            }
        });
    }

    // --- NEW: Event listeners for the modal buttons ---
    pinCancelBtn.addEventListener('click', hidePinModal);

    pinConfirmBtn.addEventListener('click', async () => {
        const pin = pinInput.value;
        if (!pin) {
            alert('Please enter a PIN.');
            return;
        }

        updateStatus('Verifying PIN and deleting files...');
        hidePinModal(); // Hide modal immediately

        try {
            const response = await fetch('/api/delete_files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    files: filesToDelete,
                    pin: pin // Send the PIN to the backend
                })
            });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                fetchAndDisplayFiles(); // Refresh the list on successful deletion
            }
        } catch (error) {
            updateStatus('A network error occurred during deletion.', true);
        }
    });

    async function fetchAndDisplayFiles() {
        // This function remains the same as before
        try {
            const response = await fetch('/api/files');
            const data = await response.json();

            const imageListBody = document.querySelector('#image-section .file-list');
            const videoListBody = document.querySelector('#video-section .file-list');
            
            imageListBody.innerHTML = '';
            videoListBody.innerHTML = '';

            data.images.forEach(file => imageListBody.appendChild(createFileRow(file)));
            data.videos.forEach(file => videoListBody.appendChild(createFileRow(file)));

            document.querySelector('#image-section .download-all').disabled = data.images.length === 0;
            document.querySelector('#video-section .download-all').disabled = data.videos.length === 0;

            const totalFiles = data.images.length + data.videos.length;
            updateStatus(totalFiles > 0 ? `Loaded ${totalFiles} files.` : 'No media files found.');

        } catch (error) {
            updateStatus('Failed to load file list.', true);
            console.error('Fetch error:', error);
        }
    }

    // --- Initial Load ---
    fetchAndDisplayFiles();
    setupSectionEventListeners('image-section');
    setupSectionEventListeners('video-section');
});