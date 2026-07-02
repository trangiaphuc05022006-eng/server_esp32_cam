document.addEventListener('DOMContentLoaded', () => {
    const historyBody = document.getElementById('historyBody');
    const refreshBtn = document.getElementById('refreshBtn');
    
    // Modal elements
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImg');
    const modalCaption = document.getElementById('modalCaption');
    const closeBtn = document.querySelector('.close-btn');

    // Fetch history from API
    const fetchHistory = async () => {
        try {
            refreshBtn.style.opacity = '0.5';
            const response = await fetch('/api/history');
            const data = await response.json();
            
            renderHistory(data);
        } catch (error) {
            console.error("Error fetching history:", error);
            historyBody.innerHTML = `<tr><td colspan="6" class="text-center loading-text error">Failed to load data. Ensure server is running.</td></tr>`;
        } finally {
            refreshBtn.style.opacity = '1';
        }
    };

    // Render history table
    const renderHistory = (data) => {
        if (data.length === 0) {
            historyBody.innerHTML = `<tr><td colspan="6" class="text-center loading-text">No scans recorded yet. Trigger the ESP32-CAM to see logs.</td></tr>`;
            return;
        }

        historyBody.innerHTML = '';
        data.forEach(item => {
            const tr = document.createElement('tr');
            
            // Format confidence
            const confidenceStr = item.confidence > 0 ? `${item.confidence.toFixed(1)}%` : '-';
            
            // Badge class
            let badgeClass = 'error';
            if (item.status === 'success') badgeClass = 'success';
            if (item.status === 'failed') badgeClass = 'failed';

            tr.innerHTML = `
                <td>#${item.id}</td>
                <td>${item.timestamp}</td>
                <td>
                    <img src="${item.image_path}" class="thumb" alt="Scan" 
                         onclick="openModal('${item.image_path}', '${item.message} - Confidence: ${confidenceStr}')">
                </td>
                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                <td>${confidenceStr}</td>
                <td>${item.message}</td>
            `;
            historyBody.appendChild(tr);
        });
    };

    // Modal Logic
    window.openModal = (imgSrc, caption) => {
        modalImg.src = imgSrc;
        modalCaption.textContent = caption;
        modal.classList.add('show');
    };

    const closeModal = () => {
        modal.classList.remove('show');
        setTimeout(() => { modalImg.src = ''; }, 300); // Clear after animation
    };

    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    // Initial fetch
    fetchHistory();

    // Event listeners
    refreshBtn.addEventListener('click', fetchHistory);

    // Auto refresh every 5 seconds
    setInterval(fetchHistory, 5000);
});
