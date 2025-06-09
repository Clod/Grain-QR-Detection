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
            
            if (result.success) {
                this.images = result.images;
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
        if (index < 0 || index >= this.totalImages) return;
        
        this.updateStatus(`Processing image ${index + 1} of ${this.totalImages}...`);
        
        try {
            const response = await fetch(`/process/${index}`);
            const result = await response.json();
            
            if (result.error) {
                this.updateStatus('Error: ' + result.error);
                return;
            }
            
            // Update images
            this.originalImage.src = result.original_image;
            this.processedImage.src = result.processed_image;
            
            // Update info panel
            this.updateCharucoStatus(result.charuco_detected);
            this.updateQRData(result.qr_codes);
            
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
        const newIndex = direction === 'next' ? this.currentIndex + 1 : this.currentIndex - 1;
        if (newIndex >= 0 && newIndex < this.totalImages) {
            this.loadImage(newIndex);
        }
    }
    
    updateCharucoStatus(detected) {
        this.charucoStatus.className = 'status-indicator mx-auto ';
        if (detected === true) {
            this.charucoStatus.classList.add('detected');
        } else if (detected === false) {
            this.charucoStatus.classList.add('not-detected');
        } else {
            this.charucoStatus.classList.add('unknown');
        }
    }
    
    updateQRData(qrCodes) {
        if (qrCodes && qrCodes.length > 0) {
            const qrHtml = qrCodes.map((code, index) => {
                // Escape HTML special characters from the code data
                const escapedCode = String(code)
                                    .replace(/&/g, "&amp;")
                                    .replace(/</g, "&lt;")
                                    .replace(/>/g, "&gt;");
                return `QR #${index + 1}: ${escapedCode}<br>---<br>`;
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
        this.imageSection.style.display = 'block';
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
