document.addEventListener('DOMContentLoaded', () => {
    const statusDiv = document.getElementById('status');
    
    // --- NEW: Tab Elements ---
    const btnShowVideos = document.getElementById('btn-show-videos');
    const btnShowImages = document.getElementById('btn-show-images');
    const sectionVideos = document.getElementById('video-section');
    const sectionImages = document.getElementById('image-section');

    // --- Modal Elements ---
    const pinModal = document.getElementById('pinModal');
    const pinInput = document.getElementById('pinInput');
    const pinCancelBtn = document.getElementById('pinCancelBtn');
    const pinConfirmBtn = document.getElementById('pinConfirmBtn');
    let filesToDelete = []; 

    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? '#dc3545' : '#198754';
    }

    // --- NEW: Tab Switching Logic ---
    btnShowVideos.addEventListener('click', () => {
        sectionVideos.style.display = 'block';
        sectionImages.style.display = 'none';
        btnShowVideos.classList.add('active');
        btnShowImages.classList.remove('active');
    });

    btnShowImages.addEventListener('click', () => {
        sectionVideos.style.display = 'none';
        sectionImages.style.display = 'block';
        btnShowVideos.classList.remove('active');
        btnShowImages.classList.add('active');
    });

    // --- Modal Functions ---
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
            <td><a href="/${file.path}" target="_blank" style="text-decoration:none; color:#0d6efd; font-weight:500;">${file.name}</a></td>
            <td>${file.size} MB</td>
            <td>${file.modified_date}</td>
        `;
        return row;
    }

    function setupSectionEventListeners(sectionId) {
        const section = document.getElementById(sectionId);
        const deleteSelectedBtn = section.querySelector('.delete-selected');
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

        deleteSelectedBtn.addEventListener('click', () => {
            filesToDelete = Array.from(section.querySelectorAll('.file-checkbox:checked')).map(cb => cb.value);
            if (filesToDelete.length === 0) return;

            if (confirm(`You are about to delete ${filesToDelete.length} file(s). Continue?`)) {
                showPinModal();
            }
        });
    }

    pinCancelBtn.addEventListener('click', hidePinModal);

    pinConfirmBtn.addEventListener('click', async () => {
        const pin = pinInput.value;
        if (!pin) {
            alert('Please enter a PIN.');
            return;
        }

        updateStatus('Verifying PIN and deleting files...');
        hidePinModal();

        try {
            const response = await fetch('/api/delete_files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    files: filesToDelete,
                    pin: pin 
                })
            });
            const result = await response.json();
            updateStatus(result.message, !result.success);
            if (result.success) {
                fetchAndDisplayFiles(); 
            }
        } catch (error) {
            updateStatus('A network error occurred during deletion.', true);
        }
    });

    async function fetchAndDisplayFiles() {
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