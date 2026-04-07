// --- API_BASE_URL auto-detection ---

const API_BASE_URL = (() => {
    const stored = localStorage.getItem("API_BASE_URL");
    if (stored) return stored;

    const host = window.location.hostname;
    const isLocal = host === "localhost" || host === "127.0.0.1";
    return isLocal ? "http://localhost:8000" : "https://govmatch-api.onrender.com";
})();

// Persist choice when user overrides via console / localStorage setter
window.addEventListener("DOMContentLoaded", () => {
    if (localStorage.getItem("API_BASE_URL")) {
        // already set — nothing to do
    }
});

const PER_PAGE = 20;
const MAX_PAGE_BUTTONS = 5;

let currentPage = 1;
let currentTotal = 0;
let currentQuery = "";

// DOM elements
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const predictCard = document.getElementById("predictCard");
const predictCompanyName = document.getElementById("predictCompanyName");
const predictWinRate = document.getElementById("predictWinRate");
const predictStats = document.getElementById("predictStats");
const errorMsg = document.getElementById("errorMsg");
const resultsSection = document.getElementById("resultsSection");
const resultsCount = document.getElementById("resultsCount");
const resultsBody = document.getElementById("resultsBody");
const pagination = document.getElementById("pagination");
const loadingOverlay = document.getElementById("loadingOverlay");

// --- Helpers ---

function setLoading(on) {
    loadingOverlay.classList.toggle("hidden", !on);
    searchBtn.disabled = on;
}

function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove("hidden");
}

function clearError() {
    errorMsg.classList.add("hidden");
}

function clearResults() {
    resultsSection.classList.add("hidden");
    predictCard.classList.add("hidden");
    clearError();
}

function formatAmount(val) {
    if (val === null || val === undefined) return "—";
    const num = parseFloat(val);
    return isNaN(num) ? val : num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(val) {
    if (!val || val === "null") return "—";
    try {
        const d = new Date(val);
        if (isNaN(d)) return val;
        return d.toISOString().slice(0, 10);
    } catch {
        return val;
    }
}

function escHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// --- Render helpers ---

function renderPredict(data) {
    predictCompanyName.textContent = data.recipient_name || currentQuery;

    const prob = data.predicted_win_probability; // 0–1
    const probPct = (prob * 100).toFixed(1);
    const barWidth = Math.round(prob * 100);    // 0–100 for progress bar

    predictWinRate.innerHTML = `
        <div class="win-rate-value">${probPct}%</div>
        <div class="win-rate-bar-track">
            <div class="win-rate-bar-fill" style="width:${barWidth}%"></div>
        </div>
    `;

    const confidenceColor =
        data.confidence === "High"
            ? "var(--success)"
            : data.confidence === "Medium"
            ? "var(--warning)"
            : "var(--text-muted)";

    predictStats.innerHTML = [
        { label: "Total Contracts", value: data.total_contracts },
        { label: "Total Amount", value: "$" + formatAmount(data.total_amount) },
        { label: "Avg Amount", value: "$" + formatAmount(data.avg_amount) },
        { label: "Recent Activity", value: data.recent_activity ? "Yes" : "No" },
        { label: "Win Rate Score", value: data.win_rate_score },
        { label: "Confidence", value: data.confidence, color: confidenceColor },
    ]
        .map(
            (s) => `
        <div class="stat-item">
            <div class="stat-label">${escHtml(s.label)}</div>
            <div class="stat-value" ${s.color ? `style="color:${s.color}"` : ""}>${escHtml(String(s.value))}</div>
        </div>`
        )
        .join("");

    predictCard.classList.remove("hidden");
}

function renderTable(rows) {
    if (!rows || rows.length === 0) {
        resultsBody.innerHTML =
            '<tr><td colspan="4" class="empty-cell">No contracts found</td></tr>';
        return;
    }

    resultsBody.innerHTML = rows
        .map((r) => {
            const id = escHtml(r.award_id || "—");
            const name = escHtml(r.recipient_name || "—");
            const amount = formatAmount(r.award_amount);
            const date = formatDate(r.start_date);

            return `<tr>
                <td><code class="award-id-badge">${id}</code></td>
                <td>${name}</td>
                <td class="amount-cell">${amount}</td>
                <td class="date-cell">${date}</td>
            </tr>`;
        })
        .join("");
}

function renderPagination() {
    const totalPages = Math.ceil(currentTotal / PER_PAGE) || 1;
    if (totalPages <= 1) {
        pagination.innerHTML = "";
        return;
    }

    const pages = getVisiblePages(currentPage, totalPages);

    let html = `
        <button class="page-btn" data-page="${currentPage - 1}" ${currentPage === 1 ? "disabled" : ""}>&lt;</button>`;

    for (const p of pages) {
        if (p === "...") {
            html += `<span class="page-btn page-ellipsis">…</span>`;
        } else {
            html += `<button class="page-btn ${p === currentPage ? "active" : ""}" data-page="${p}">${p}</button>`;
        }
    }

    html += `<button class="page-btn" data-page="${currentPage + 1}" ${currentPage === totalPages ? "disabled" : ""}>&gt;</button>`;

    pagination.innerHTML = html;
}

function getVisiblePages(cur, total) {
    if (total <= MAX_PAGE_BUTTONS) {
        return Array.from({ length: total }, (_, i) => i + 1);
    }

    const pages = [];
    const half = Math.floor(MAX_PAGE_BUTTONS / 2);
    let start = Math.max(1, cur - half);
    let end = Math.min(total, cur + half);

    if (end - start < MAX_PAGE_BUTTONS - 1) {
        if (start === 1) {
            start = Math.max(1, end - (MAX_PAGE_BUTTONS - 1));
        } else {
            end = Math.min(total, start + MAX_PAGE_BUTTONS - 1);
        }
    }

    if (start > 1) {
        pages.push(1);
        if (start > 2) pages.push("...");
    }

    for (let i = start; i <= end; i++) pages.push(i);

    if (end < total) {
        if (end < total - 1) pages.push("...");
        pages.push(total);
    }

    return pages;
}

// --- API calls ---

async function fetchPredict(recipientName) {
    const url = `${API_BASE_URL}/recipient/predict/${encodeURIComponent(recipientName)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Prediction API error (${resp.status})`);
    return await resp.json();
}

async function fetchContracts(recipientName, page) {
    const params = new URLSearchParams({
        recipient_name: recipientName,
        page,
        limit: PER_PAGE,
    });
    const url = `${API_BASE_URL}/contracts/search?${params}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Search API error (${resp.status})`);
    return await resp.json();
}

// --- Main search ---

async function doSearch(query, page = 1) {
    if (!query.trim()) {
        showError("Please enter a company name to search");
        return;
    }

    currentQuery = query.trim();
    currentPage = page;

    setLoading(true);
    clearResults();
    clearError();

    try {
        const [contracts, prediction] = await Promise.all([
            fetchContracts(currentQuery, currentPage).catch(() => ({ total: 0, results: [] })),
            fetchPredict(currentQuery).catch(() => null),
        ]);

        if (prediction) renderPredict(prediction);

        const results = Array.isArray(contracts) ? contracts : (contracts.results || []);
        currentTotal = contracts.total || results.length;

        // Empty results — always show the section with the empty message
        renderTable(results);
        renderPagination();

        const from = (currentPage - 1) * PER_PAGE + 1;
        const to = Math.min(currentPage * PER_PAGE, currentTotal);
        resultsCount.textContent = currentTotal === 0
            ? "No contracts found"
            : `Showing ${from}–${to} of ${currentTotal} result${currentTotal === 1 ? "" : "s"}`;

        resultsSection.classList.remove("hidden");
    } catch (err) {
        console.error(err);
        showError("Request failed — please check that the API service is running");
    } finally {
        setLoading(false);
    }
}

// --- Event listeners ---

searchBtn.addEventListener("click", () => doSearch(searchInput.value, 1));

searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch(searchInput.value, 1);
});

pagination.addEventListener("click", (e) => {
    const btn = e.target.closest(".page-btn");
    if (!btn || btn.disabled || btn.classList.contains("active")) return;
    const page = parseInt(btn.dataset.page, 10);
    if (!isNaN(page)) doSearch(currentQuery, page);
});

// Pre-fill demo value on load
searchInput.value = "SAFEWARE";