/**
 * app.js - Frontend Logic for the Granos Image Processor
 *
 * This script defines the ImageViewer class, which manages the entire user interface
 * and interaction logic for the web application. It communicates with the Flask
 * backend via asynchronous Fetch API calls to handle image uploads, Google Drive
 * integration, image processing, and navigation.
 *
 * Core Features Handled by this Script:
 * - **State Management:** Keeps track of the current image index, total number of images,
 *   and the current mode (local files vs. Google Drive).
 * - **Event Handling:** Binds event listeners to UI elements for actions like file uploads,
 *   button clicks (navigation, zoom), and Google Drive link submissions.
 * - **Dynamic UI Updates:** Renders images, processing results (ChArUco status, QR data),
 *   and status messages without requiring a full page reload.
 * - **Image Interaction:** Implements zoom (via mouse wheel and buttons) and pan
 *   (via drag-and-drop) functionality for the processed image view.
 * - **API Communication:** Encapsulates all `fetch` calls to the backend API endpoints.
 */
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
        this.isDriveMode = false; // Internal state
        this.isServerMode = false; // Internal state
        this.lastMouseY = 0;
        
        this.initializeElements();
        this.bindEvents();
        this.initializeState(); // Call new method
    }

    /**
     * Initializes the viewer's state based on global variables set by the Flask template.
     * This allows the frontend to know if it should start in "Google Drive mode"
     * or "Local file mode" when the page loads, and immediately fetch the first
     * image if a Drive folder was already selected in a previous session.
     * @returns {void}
     */
    initializeState() {
        // Check global JS variables set by the template
        if (isDriveModeActive && initialDriveImageCount > 0) {
            this.isDriveMode = true;
            this.totalImages = initialDriveImageCount;
            this.currentIndex = 0; // Assuming Drive mode always starts at index 0 if images exist
            this.showImageSections();
            this.updateStatus(`Google Drive folder selected. Found ${this.totalImages} images. Loading first image...`);
            this.loadImage(0); // Load the first image from Drive
            console.log("ImageViewer initialized in Drive Mode.");
        } else if (isServerModeActive && initialServerImageCount > 0) { // New Server Mode
            this.isServerMode = true;
            this.totalImages = initialServerImageCount;
            this.currentIndex = 0;
            this.showImageSections();
            this.updateStatus(`Server images selected. Found ${this.totalImages} images. Loading first image...`);
            this.loadImage(0); // Load the first image from Server
            console.log("ImageViewer initialized in Server Mode.");
        }
        else if (!isDriveModeActive && !isServerModeActive) {
            // Standard local file mode, or no files selected yet
            // This branch is for when neither Drive nor Server mode is active.
            this.updateStatus('Please select images or a Google Drive folder.');
            console.log("ImageViewer initialized in Local File Mode or awaiting selection.");
        } else {
            // Fallback or initial state before any selection
            this.updateStatus('Please select images to begin.');
            console.log("ImageViewer initialized, awaiting user action.");
        }
    }
    
    /**
     * Caches references to all necessary DOM elements for performance and easy access.
     * This avoids repeated `document.getElementById` calls throughout the code.
     * @returns {void}
     */
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
        this.driveLinkInput = document.getElementById('driveLinkInput'); 
        this.submitDriveLinkBtn = document.getElementById('submitDriveLinkBtn'); 
        this.zoomInBtn = document.getElementById('zoomInBtn');
        this.zoomOutBtn = document.getElementById('zoomOutBtn');
        this.selectServerImagesBtn = document.getElementById('selectServerImagesBtn'); // New
        this.saveProcessedBtn = document.getElementById('saveProcessedBtn');
    }
    
    /**
     * Binds all necessary event listeners to the DOM elements.
     * This includes handling clicks for file uploads, navigation, zoom controls,
     * and Drive link submission, as well as mouse events for interactive pan and zoom.
     * @returns {void}
     */
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

        // Handle Drive link submission
        if (this.submitDriveLinkBtn) { 
            this.submitDriveLinkBtn.addEventListener('click', () => this.handleDriveLinkSubmit());
        }
        // Handle Server Images selection
        if (this.selectServerImagesBtn) {
            this.selectServerImagesBtn.addEventListener('click', () => this.handleSelectServerImages());
        }

        // Handle Save Processed Image
        if (this.saveProcessedBtn) {
            this.saveProcessedBtn.addEventListener('click', () => this.handleSaveProcessedImage());
        }
    }

    async handleSaveProcessedImage() {
        this.updateStatus('Saving processed image...');

        try {
            const response = await fetch('/save_processed_image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            const result = await response.json();

            if (result.success) {
                this.updateStatus(result.message);
            } else {
                this.updateStatus('Error saving image: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            this.updateStatus('Failed to save image: ' + error.message);
            console.error('Full error details:', error);
        }
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

            // Update internal state
            this.isDriveMode = false;
            this.isServerMode = false;
            // Update global var for consistency on potential page reloads
            isDriveModeActive = false;
            
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
    
    /**
     * Handles the submission of a Google Drive folder link.
     * It takes the URL from the input field, sends it to the backend for validation
     * and processing, and then updates the UI to reflect the new set of images
     * from the Drive folder.
     * @returns {Promise<void>} A promise that resolves when the link has been processed
     *                          and the UI is updated, or an error is handled.
     */
    async handleDriveLinkSubmit() {
        if (!this.driveLinkInput) {
            console.error("Drive link input element not found.");
            this.updateStatus("Error: UI element for Drive link missing.");
            return;
        }
        const driveLink = this.driveLinkInput.value.trim();
        if (!driveLink) {
            this.updateStatus('Please enter a Google Drive folder link.');
            return;
        }

        this.updateStatus('Processing Google Drive link...');

        try {
            const response = await fetch('/process_drive_link', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ drive_link: driveLink }),
            });

            if (!response.ok) {
                // Try to get more details from the response body if it's not JSON
                const errorText = await response.text();
                throw new Error(`Server responded with ${response.status}: ${errorText}`);
            }

            const result = await response.json(); // Now, this is safer

            if (result.success && result.image_count !== undefined) {
                // Update internal state
                this.isDriveMode = true;
                this.isServerMode = false;
                // Update global var for consistency on potential page reloads
                isDriveModeActive = true;
                this.totalImages = result.image_count;
                this.currentIndex = 0; 
                this.updateStatus(`Google Drive folder processed. Found ${this.totalImages} images. ${this.totalImages > 0 ? 'Loading first image...' : ''}`);
                this.showImageSections();
                this.loadImage(0); 
            } else {
                // If server sent success:false in JSON
                this.updateStatus('Error processing Drive link: ' + (result.error || 'Unknown error from server.'));
            }
        } catch (error) {
            console.error('Full error details:', error); // Log the full error object
            this.updateStatus('Failed to process Drive link: ' + error.message);
        }
    }

    /**
     * Handles the selection of images from a pre-configured server directory.
     * It sends a request to the backend to list available images in the server's
     * shared volume, then updates the UI to display the first image.
     * @returns {Promise<void>} A promise that resolves when the server images
     *                          are loaded and the UI is updated, or an error is handled.
     */
    async handleSelectServerImages() {
        this.updateStatus('Loading images from server...');

        try {
            const response = await fetch('/select_server_images', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json', // Even if body is empty, good practice
                },
                body: JSON.stringify({}) // Send an empty JSON object
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server responded with ${response.status}: ${errorText}`);
            }

            const result = await response.json();

            if (result.success && result.image_count !== undefined) {
                // Update internal state
                this.isDriveMode = false;
                this.isServerMode = true;
                this.totalImages = result.image_count;
                this.currentIndex = 0;
                this.updateStatus(`Server images loaded. Found ${this.totalImages} images. ${this.totalImages > 0 ? 'Loading first image...' : ''}`);
                this.showImageSections();
                this.loadImage(0);
            } else {
                this.updateStatus('Error loading server images: ' + (result.error || 'Unknown error from server.'));
            }
        } catch (error) {
            this.updateStatus('Failed to load server images: ' + error.message);
            console.error('Full error details:', error);
        }
    }

    /**
     * Fetches and displays the image and its processing data for a given index.
     * This is a core function that communicates with the `/process/<index>` backend endpoint.
     * It handles both success and error responses, updating the image displays,
     * information panels (ChArUco, QR), navigation state, and status bar.
     * It works transparently for both local files and Google Drive images.
     *
     * @param {number} index - The zero-based index of the image to load.
     * @returns {Promise<void>} A promise that resolves when the image data is loaded
     *                          and the UI is updated, or an error is handled.
     */
    async loadImage(index) {
        // For local mode, this check is useful. For Drive/Server modes, server handles index validity.
        // However, with totalImages now being updated from server response, this check can be more robust.
        if (!this.isDriveMode && !this.isServerMode && (index < 0 || index >= this.totalImages && this.totalImages > 0)) {
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
    
    /**
     * Handles navigation to the next or previous image.
     * It calls the `/navigate/<direction>` endpoint on the backend. The backend
     * determines the new image index and returns the complete data for that image.
     * This function then calls `loadImage` with the new index to update the UI.
     *
     * @param {string} direction - The direction to navigate, either 'prev' or 'next'.
     * @returns {void}
     */
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
    
    /**
     * Updates the ChArUco status indicator in the UI.
     * It changes the text and CSS class of the status element to reflect
     * whether a ChArUco board was detected in the current image.
     * @param {boolean} detected - True if a board was detected, false otherwise.
     * @returns {void}
     */
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
    
    /**
     * Updates the QR code information panel with data from the current image.
     * It formats the raw QR data and any decoded JSON objects into readable HTML
     * and displays it. It handles cases with single or multiple QR codes.
     *
     * @param {string[]} qrCodes - An array of raw string data from detected QR codes.
     * @param {Object[]} qrCodesDecoded - An array of objects resulting from JSON-parsing the qrCodes.
     * @returns {void}
     */
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
    
    /**
     * Enables or disables the 'Previous' and 'Next' navigation buttons.
     * This is based on flags received from the server, ensuring users cannot
     * navigate beyond the bounds of the image list.
     * @param {boolean} hasPrev - True if there is a previous image.
     * @param {boolean} hasNext - True if there is a next image.
     * @returns {void}
     */
    updateNavigation(hasPrev, hasNext) {
        this.prevBtn.disabled = !hasPrev;
        this.nextBtn.disabled = !hasNext;
    }
    
    /**
     * Makes the main image display and control sections visible.
     * This is typically called after the first set of images (either local or Drive)
     * has been successfully loaded.
     * @returns {void}
     */
    showImageSections() {
        this.imageSection.style.display = '';
        this.controlsSection.style.display = 'block';
    }
    
    /**
     * Updates the text content of the main status bar at the bottom of the screen.
     * This provides users with feedback about the application's current state
     * (e.g., "Uploading...", "Processing image...", "Error...").
     * @param {string} message - The message to display.
     * @returns {void}
     */
    updateStatus(message) {
        this.statusBar.textContent = message;
    }
    
    // Zoom and Pan functionality
    /**
     * Handles the mouse wheel event for zooming.
     * It calculates a zoom factor based on the scroll direction and calls
     * `adjustZoom` to apply the new zoom level, centered on the mouse cursor.
     * @param {WheelEvent} event - The mouse wheel event.
     * @returns {void}
     */
    handleWheel(event) {
        event.preventDefault();
        const zoomFactor = event.deltaY > 0 ? 0.9 : 1.1;
        this.adjustZoom(zoomFactor, event.offsetX, event.offsetY);
    }
    
    adjustZoom(factor, centerX = null, centerY = null) {
    /**
     * Applies a zoom factor to the image and adjusts the pan to keep the view centered.
     * @param {number} factor - The zoom multiplier (e.g., 1.1 for zoom in, 0.9 for zoom out).
     * @param {?number} [centerX=null] - The x-coordinate to zoom towards. Defaults to the container center.
     * @param {?number} [centerY=null] - The y-coordinate to zoom towards. Defaults to the container center.
     * @returns {void}
     */
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
    
    /**
     * Resets the image zoom and pan to their default state (100% scale, no offset).
     * @returns {void}
     */
    resetZoom() {
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateImageTransform();
    }
    
    /**
     * Initiates the drag-to-pan functionality.
     * Called on `mousedown`, it sets the dragging state and records the initial mouse position.
     * @param {MouseEvent} event - The mousedown event.
     * @returns {void}
     */
    startDrag(event) {
        this.isDragging = true;
        this.lastMouseX = event.clientX;
        this.lastMouseY = event.clientY;
        this.processedImage.style.cursor = 'grabbing';
        event.preventDefault();
    }
    
    /**
     * Handles the image panning while the mouse is being dragged.
     * Called on `mousemove`, it calculates the change in mouse position and updates the pan coordinates.
     * @param {MouseEvent} event - The mousemove event.
     * @returns {void}
     */
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
    
    /**
     * Stops the drag-to-pan functionality.
     * Called on `mouseup`, it resets the dragging state.
     * @returns {void}
     */
    stopDrag() {
        this.isDragging = false;
        this.processedImage.style.cursor = 'grab';
    }
    
    /**
     * Applies the current zoom and pan values to the image element's CSS transform property.
     * @returns {void}
     */
    updateImageTransform() {
        this.processedImage.style.transform = 
            `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ImageViewer();
});
