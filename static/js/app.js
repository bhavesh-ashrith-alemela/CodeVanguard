// CodeVanguard Client Script

document.addEventListener("DOMContentLoaded", () => {
    initDragAndDrop();
});

// Drag and Drop Zone handler
function initDragAndDrop() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const uploadForm = document.getElementById("upload-form");
    
    if (!dropZone || !fileInput) return;
    
    // Highlight drop zone on drag over
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("drag-zone-active");
        }, false);
    });
    
    // Remove highlight on drag leave
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("drag-zone-active");
        }, false);
    });
    
    // Handle dropped files
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelection(files[0]);
        }
    }, false);
    
    // Handle file click/selection
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });
}

function handleFileSelection(file) {
    const fileInfo = document.getElementById("file-info");
    const fileDetails = document.getElementById("file-details");
    const submitBtn = document.getElementById("submit-scan-btn");
    
    const fileInput = document.getElementById("file-input");
    
    if (!fileInfo || !fileDetails) return;
    
    // Max 10MB limit validation
    const maxBytes = 10 * 1024 * 1024;
    if (file.size > maxBytes) {
        showToast("File exceeds maximum limit of 10MB.", "error");
        fileInput.value = ""; // clear selection
        fileDetails.classList.add("hidden");
        if (submitBtn) submitBtn.disabled = true;
        return;
    }
    
    // Show selected file info
    const sizeKB = (file.size / 1024).toFixed(1);
    fileInfo.innerHTML = `
        <div class="flex items-center gap-3 bg-base-900/40 p-3 rounded-lg border border-white/5">
            <span class="p-2 bg-primary/20 rounded-md text-primary">
                <i data-lucide="${file.name.endsWith('.zip') ? 'folder-archive' : 'file-code'}" class="w-5 h-5"></i>
            </span>
            <div class="text-left">
                <p class="font-semibold text-white truncate max-w-[200px] sm:max-w-xs">${file.name}</p>
                <p class="text-xs text-base-content/60">${sizeKB} KB</p>
            </div>
        </div>
    `;
    fileDetails.classList.remove("hidden");
    if (submitBtn) submitBtn.disabled = false;
    
    // Trigger Lucide refresh to show file icons
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

// Global Toast notification utility
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `alert shadow-lg pointer-events-auto border border-white/5 animate-slide-up `;
    
    let icon = "info";
    if (type === "success") {
        toast.classList.add("alert-success");
        icon = "check-circle";
    } else if (type === "error") {
        toast.classList.add("alert-error");
        icon = "alert-triangle";
    } else {
        toast.classList.add("alert-info");
        icon = "info";
    }
    
    toast.innerHTML = `
        <div class="flex items-center gap-2">
            <i data-lucide="${icon}" class="w-5 h-5"></i>
            <span>${message}</span>
        </div>
    `;
    
    container.appendChild(toast);
    
    if (window.lucide) {
        window.lucide.createIcons();
    }
    
    // Remove toast after 4 seconds
    setTimeout(() => {
        toast.classList.add("opacity-0");
        toast.style.transition = "opacity 0.5s ease";
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}
