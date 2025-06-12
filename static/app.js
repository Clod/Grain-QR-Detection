class ImageViewer {
    constructor() {
        this.currentIndex = 0;
        this.totalImages = 0;
        this.images = [];
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;
        
        this.initializeElements();
        this.bindEvents();
        this.initializeState(); // Call new method
    }

    initializeState() {
        // Check global JS variables set by the template
        if (typeof isDriveModeActive !== 'undefined' && isDriveModeActive &&
            typeof initialDriveImageCount !== 'undefined' && initialDriveImageCount > 0) {

            this.totalImages = initialDriveImageCount;
            this.currentIndex = 0; // Assuming Drive mode always starts at index 0 if images exist
            this.showImageSections();
            this.updateStatus(`Google Drive folder selected. Found ${this.totalImages} images. Loading first image...`);
            this.loadImage(0); // Load the first image from Drive
            console.log("ImageViewer initialized in Drive Mode.");
        } else if (typeof isDriveModeActive !== 'undefined' && !isDriveModeActive) {
            // Standard local file mode, or no files selected yet
            // Optional: Hide image sections if no local files are loaded initially.
            // this.imageSection.style.display = 'none';
            // this.controlsSection.style.display = 'none';
            this.updateStatus('Please select images or a Google Drive folder.');
            console.log("ImageViewer initialized in Local File Mode or awaiting selection.");
        } else {
            // Fallback or initial state before any selection
            this.updateStatus('Please select images to begin.');
            console.log("ImageViewer initialized, awaiting user action.");
        }
    }
    
    initializeElements() {
        this.fileInput = document.getElementById('fileInput');
        this.uploadBtn = document.getElementById('uploadBtn');
        this.uploadStatus = document.getElementById('uploadStatus');
        this.imageSection = document.getElementById('imageSection');
        this.controlsSection = document.getElementById('controlsSection');
        this.originalImage = document.getElementById('originalImage');
        this.processedImage = document.getElementById('processedImage');
        this.imageContainer = document.getElementById('imageContainer');
        this.charucoStatus = document.getElementById('charucoStatus');
        this.qrData = document.getElementById('qrData');
        this.statusBar = document.getElementById('statusBar');
        this.imageInfo = document.getElementById('imageInfo');
        this.prevBtn = document.getElementById('prevBtn');
        this.nextBtn = document.getElementById('nextBtn');
        this.resetZoomBtn = document.getElementById('resetZoomBtn');
        this.zoomInBtn = document.getElementById('zoomInBtn');
        this.zoomOutBtn = document.getElementById('zoomOutBtn');
    }
    
    bindEvents() {
        this.uploadBtn.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
        
        // Navigation
        this.prevBtn.addEventListener('click', () => this.navigate('prev'));
        this.nextBtn.addEventListener('click', () => this.navigate('next'));
        
        // Zoom controls
        this.resetZoomBtn.addEventListener('click', () => this.resetZoom());
        this.zoomInBtn.addEventListener('click', () => this.adjustZoom(1.2));
        this.zoomOutBtn.addEventListener('click', () => this.adjustZoom(0.8));
        
        // Mouse events for zoom and pan
        this.imageContainer.addEventListener('wheel', (e) => this.handleWheel(e));
        this.processedImage.addEventListener('mousedown', (e) => this.startDrag(e));
        document.addEventListener('mousemove', (e) => this.drag(e));
        document.addEventListener('mouseup', () => this.stopDrag());
        
        // Prevent context menu on image
        this.processedImage.addEventListener('contextmenu', (e) => e.preventDefault());
    }
    
    /**
     * Handles the file upload process.
     * When files are selected by the user, this function constructs a FormData object,
     * sends the files to the '/upload' endpoint via a POST request,
     * and then processes the JSON response to update the image viewer.
     *
     * @param {Event} event - The file input change event.
     *                        It contains the files selected by the user.
     * @returns {Promise<void>} A promise that resolves when the file upload and
     *                          UI update process is complete or an error is handled.
     */
    async handleFileUpload(event) {
        const files = event.target.files;
        if (files.length === 0) return;
        
        const formData = new FormData();
        for (let file of files) {
            formData.append('files[]', file);
        }
        
        this.updateStatus('Uploading images...');
        
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();

            // Explicitly set isDriveModeActive to false for JS context
            if (typeof isDriveModeActive !== 'undefined') {
                isDriveModeActive = false;
                console.log("Switched to Local File Mode due to file upload.");
            }
            
            if (result.success) {
                this.images = result.images; // This might be less relevant if only relying on server state
                this.totalImages = result.image_count;
                this.currentIndex = 0;
                
                this.updateStatus(`Loaded ${this.totalImages} images.`);
                this.showImageSections();
                this.loadImage(0);
            } else {
                this.updateStatus('Error uploading images: ' + result.error);
            }
        } catch (error) {
            this.updateStatus('Upload failed: ' + error.message);
        }
    }
    
    async loadImage(index) {
        // For local mode, this check is useful. For Drive mode, server handles index validity.
        // However, with totalImages now being updated from server response, this check can be more robust.
        if (!isDriveModeActive && (index < 0 || index >= this.totalImages && this.totalImages > 0)) {
            console.warn(`Local mode: loadImage called with invalid index ${index} for ${this.totalImages} images. Aborting.`);
            return;
        }
        // If isDriveModeActive, we rely on the server to validate the index for Drive files.
        // If totalImages is 0 (e.g. empty Drive folder), this will also prevent client-side errors.
        if (this.totalImages === 0 && index === 0) { // Special case for empty folder, don't try to load index 0
            this.updateStatus("No images to display.");
            this.updateNavigation(false, false); // No next/prev
            return;
        }


        this.updateStatus(`Processing image ${index + 1} of ${this.totalImages > 0 ? this.totalImages : '...'}...`);
        
        try {
            const response = await fetch(`/process/${index}`);
            // It's important to check response.ok before trying to parse as JSON
            if (!response.ok) {
                // Attempt to parse error response if server sends JSON for errors
                try {
                    const errorResult = await response.json();
                    this.updateStatus(`Error: ${errorResult.error || response.statusText}`);
                    if (errorResult.is_api_error) {
                        this.currentIndex = errorResult.current_index !== undefined ? errorResult.current_index : this.currentIndex;
                        this.totalImages = errorResult.total_images !== undefined ? errorResult.total_images : this.totalImages;
                        this.updateNavigation(this.currentIndex > 0, this.currentIndex < this.totalImages - 1);
                        this.imageInfo.textContent = `Image ${this.currentIndex + 1} of ${this.totalImages}: ${errorResult.filename || 'N/A'} (Error loading)`;
                    }
                } catch (e) {
                    // If error response is not JSON, use statusText
                    this.updateStatus(`Error: ${response.statusText}`);
                }
                return; // Stop processing on error
            }

            const result = await response.json(); // Now safe to parse as JSON
            
            // Check for logical error within a 2xx response, if applicable by server design (already done by !response.ok for HTTP errors)
            // This 'if (result.error)' might be redundant if all errors result in non-ok HTTP status.
            // However, if server sends 200 OK with an error field in JSON:
            if (result.error) {
                this.updateStatus('Error: ' + result.error);
                if (result.is_api_error) { // Handle API error details if present
                    this.currentIndex = result.current_index !== undefined ? result.current_index : this.currentIndex;
                    this.totalImages = result.total_images !== undefined ? result.total_images : this.totalImages;
                    this.updateNavigation(this.currentIndex > 0, this.currentIndex < this.totalImages - 1);
                    this.imageInfo.textContent = `Image ${this.currentIndex + 1} of ${this.totalImages}: ${result.filename || 'N/A'} (Error loading)`;
                }
                return;
            }
            
            // Update images
            this.originalImage.src = result.original_image;
            this.processedImage.src = result.processed_image;
            
            // Update totalImages from server response to keep client in sync
            if (typeof result.total_images !== 'undefined') {
                this.totalImages = result.total_images;
            }

            // Update info panel
            this.updateCharucoStatus(result.charuco_detected);
            this.updateQRData(result.qr_codes, result.qr_codes_json);
            console.log("QR Codes:", result.qr_codes); // Log the raw QR codes
            console.log("QR Codes Decoded:", result.qr_codes_json); // Log the decoded QR codes
            
            // Update navigation
            this.currentIndex = result.current_index;
            this.updateNavigation(result.has_prev, result.has_next);
            
            // Reset zoom and pan
            this.resetZoom();
            
            // Update status and info
            this.updateStatus(`Displaying: ${result.filename} (Processed)`);
            this.imageInfo.textContent = `Image ${result.current_index + 1} of ${result.total_images}: ${result.filename}`;
            
        } catch (error) {
            this.updateStatus('Error loading image: ' + error.message);
        }
    }
    
    navigate(direction) {
        // Navigation now primarily relies on server-side redirects via fetch
        // The client-side currentIndex and totalImages are updated by loadImage
        // This function can simplify to just fetching the navigation URL
        this.updateStatus(`Navigating ${direction}...`);
        console.log(`Calling /navigate/${direction}`); // Added for debugging
        fetch(`/navigate/${direction}`)
            .then(response => {
                if (response.ok) {
                    return response.json().then(data => {
                        console.log("Received data from /navigate:", data); // Added for debugging
                        if(data.error) {
                             this.updateStatus(`Navigation error: ${data.error}`);
                        } else if (typeof data.current_index !== 'undefined') {
                            // The backend now returns the full image data, similar to /process/<index>
                            // We can directly use this data to update the UI, or call loadImage
                            // For consistency and to ensure all UI updates happen, let's call loadImage.
                            this.loadImage(data.current_index);
                        }
                    });
                } else {
                    response.json().then(data => {
                        console.error("Navigation failed, server response:", data); // Added for debugging
                        this.updateStatus(`Navigation failed: ${data.error || response.statusText}`);
                    });
                }
            })
            .catch(error => {
                console.error('Navigation fetch error:', error);
                this.updateStatus(`Navigation error: ${error.message}`);
            });
    }
    
    updateCharucoStatus(detected) {
        const { classList } = this.charucoStatus;

        // Remove any previous status-specific classes to ensure a clean state
        classList.remove('detected', 'not-detected', 'unknown');

        // Ensure base classes are present.
        // If these are guaranteed by the HTML, this explicit add might be redundant
        // but ensures they are there if managed dynamically.
        classList.add('status-indicator', 'mx-auto');

        let statusMessage; // Will hold "Detected", "Not Detected", or "Unknown"
        if (detected === true) {
            classList.add('detected');
            statusMessage = "Detected";
        } else if (detected === false) {
            classList.add('not-detected');
            statusMessage = "Not Detected";
        } else {
            // This handles cases where 'detected' is not strictly true/false (e.g., null, undefined).
            // If 'detected' could be a string ("true") or number (1) meaning true,
            // the conditional logic above would need to be adjusted.
            classList.add('unknown');
            statusMessage = "Unknown";
        }
        // Set only the dynamic part of the status. "ChArUco Status: " should be static HTML.
        this.charucoStatus.textContent = statusMessage;
    }
    
    updateQRData(qrCodes, qrCodesDecoded) {
        console.log("updateQRData called. qrCodesDecoded:", qrCodesDecoded); // Log the entire decoded array
        if (qrCodes && qrCodes.length > 0) {
            let qrHtml = qrCodes.map((code, index) => {
                // Escape HTML special characters from the code data
                const escapedCode = String(code)
                                    .replace(/&/g, "&amp;")
                                    .replace(/</g, "&lt;")
                                    .replace(/>/g, "&gt;");
                let decodedDataHtml = '';
                // Log individual decoded item
                console.log(`Processing QR #${index + 1}. Decoded data:`, qrCodesDecoded ? qrCodesDecoded[index] : 'qrCodesDecoded is undefined/null');
                
                if (qrCodesDecoded && typeof qrCodesDecoded[index] !== 'undefined') {
                    decodedDataHtml = `Decoded: <pre>${JSON.stringify(qrCodesDecoded[index], null, 2)}</pre>`;
                }
                return `<div><strong>QR #${index + 1}:</strong> ${escapedCode}<br>${decodedDataHtml}</div><hr>`;
            }).join('');
            this.qrData.innerHTML = qrHtml;
        } else {
            this.qrData.innerHTML = 'No QR codes found or decoded.';
        }
    }
    
    updateNavigation(hasPrev, hasNext) {
        this.prevBtn.disabled = !hasPrev;
        this.nextBtn.disabled = !hasNext;
    }
    
    showImageSections() {
        this.imageSection.style.display = '';
        this.controlsSection.style.display = 'block';
    }
    
    updateStatus(message) {
        this.statusBar.textContent = message;
    }
    
    // Zoom and Pan functionality
    handleWheel(event) {
        event.preventDefault();
        const zoomFactor = event.deltaY > 0 ? 0.9 : 1.1;
        this.adjustZoom(zoomFactor, event.offsetX, event.offsetY);
    }
    
    adjustZoom(factor, centerX = null, centerY = null) {
        const containerRect = this.imageContainer.getBoundingClientRect();
        const imgRect = this.processedImage.getBoundingClientRect();
        
        if (centerX === null) centerX = containerRect.width / 2;
        if (centerY === null) centerY = containerRect.height / 2;
        
        const oldZoom = this.zoom;
        this.zoom = Math.max(0.1, Math.min(5, this.zoom * factor));
        
        if (this.zoom !== oldZoom) {
            // Adjust pan to zoom toward the center point
            const zoomRatio = this.zoom / oldZoom;
            this.panX = centerX - (centerX - this.panX) * zoomRatio;
            this.panY = centerY - (centerY - this.panY) * zoomRatio;
            
            this.updateImageTransform();
        }
    }
    
    resetZoom() {
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateImageTransform();
    }
    
    startDrag(event) {
        this.isDragging = true;
        this.lastMouseX = event.clientX;
        this.lastMouseY = event.clientY;
        this.processedImage.style.cursor = 'grabbing';
        event.preventDefault();
    }
    
    drag(event) {
        if (!this.isDragging) return;
        
        const deltaX = event.clientX - this.lastMouseX;
        const deltaY = event.clientY - this.lastMouseY;
        
        this.panX += deltaX;
        this.panY += deltaY;
        
        this.lastMouseX = event.clientX;
        this.lastMouseY = event.clientY;
        
        this.updateImageTransform();
    }
    
    stopDrag() {
        this.isDragging = false;
        this.processedImage.style.cursor = 'grab';
    }
    
    updateImageTransform() {
        this.processedImage.style.transform = 
            `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ImageViewer();
});
