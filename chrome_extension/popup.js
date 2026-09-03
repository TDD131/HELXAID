const HELXAID_SERVER = "http://127.0.0.1:8889";

const SVG_SYNC = `<svg class="ext-btn-svg" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>`;
const SVG_SPIN = `<svg class="ext-btn-svg ext-spin" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8z"/></svg>`;
const SVG_CHECK = `<svg class="ext-btn-svg" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>`;

function setBadge(id, text, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = "ext-status-badge " + (type === "active" ? "status-active" : type === "error" ? "status-error" : "status-checking");
}

document.addEventListener("DOMContentLoaded", async () => {
  const syncBtn = document.getElementById("syncBtn");
  const msgBox = document.getElementById("msgBox");

  let helxaidOnline = false;
  let hasYouTubeCookies = false;
  let collectedCookies = {};
  let isCurrentlySynced = localStorage.getItem("helxaid_is_synced") === "true";

  // If local storage already marked as synced, render synced state immediately
  if (isCurrentlySynced) {
    syncBtn.disabled = false;
    syncBtn.innerHTML = `${SVG_CHECK} <span>SYNCED</span>`;
    syncBtn.style.background = "#059669";
    msgBox.textContent = "YouTube session is linked to HELXAID.";
    msgBox.style.color = "#00E599";
  }

  // Mouse hover feedback for re-syncing
  syncBtn.addEventListener("mouseenter", () => {
    if (isCurrentlySynced && !syncBtn.disabled) {
      syncBtn.innerHTML = `${SVG_SYNC} <span>RE-SYNC</span>`;
    }
  });

  syncBtn.addEventListener("mouseleave", () => {
    if (isCurrentlySynced && !syncBtn.disabled) {
      syncBtn.innerHTML = `${SVG_CHECK} <span>SYNCED</span>`;
    }
  });

  // 1. Check HELXAID App Health & Live Sync State
  try {
    const res = await fetch(`${HELXAID_SERVER}/api/health`, { method: "GET" });
    if (res.ok) {
      const data = await res.json();
      helxaidOnline = true;
      setBadge("appStatus", "ONLINE", "active");

      // Verify authentic sync state directly from HELXAID
      if (data && data.youtube_synced === true) {
        isCurrentlySynced = true;
        localStorage.setItem("helxaid_is_synced", "true");
        syncBtn.disabled = false;
        syncBtn.innerHTML = `${SVG_CHECK} <span>SYNCED</span>`;
        syncBtn.style.background = "#059669";
        msgBox.textContent = "YouTube session is linked to HELXAID.";
        msgBox.style.color = "#00E599";
      } else {
        isCurrentlySynced = false;
        localStorage.removeItem("helxaid_is_synced");
        syncBtn.innerHTML = `${SVG_SYNC} <span>SYNC TO HELXAID</span>`;
        syncBtn.style.background = "#FF5B06";
      }
    } else {
      throw new Error("Bad response");
    }
  } catch (err) {
    setBadge("appStatus", "OFFLINE", "error");
    msgBox.textContent = "Start HELXAID desktop app to enable sync.";
    msgBox.style.color = "#FF4B4B";
    syncBtn.disabled = true;
  }

  // 2. Fetch YouTube Session Cookies from Chrome
  try {
    const musicCookies = await chrome.cookies.getAll({ url: "https://music.youtube.com" });
    const ytUrlCookies = await chrome.cookies.getAll({ url: "https://www.youtube.com" });
    const ytDomainCookies = await chrome.cookies.getAll({ domain: "youtube.com" });
    const gCookies = await chrome.cookies.getAll({ domain: "google.com" });

    for (const c of gCookies) collectedCookies[c.name] = c.value;
    for (const c of ytDomainCookies) collectedCookies[c.name] = c.value;
    for (const c of ytUrlCookies) collectedCookies[c.name] = c.value;
    for (const c of musicCookies) collectedCookies[c.name] = c.value;

    if (
      collectedCookies["SAPISID"] || 
      collectedCookies["LOGIN_INFO"] || 
      collectedCookies["__Secure-3PAPISID"] || 
      collectedCookies["__Secure-1PSID"] ||
      collectedCookies["SID"]
    ) {
      hasYouTubeCookies = true;
      setBadge("ytStatus", "LOGGED IN", "active");
    } else {
      setBadge("ytStatus", "NOT LOGGED IN", "checking");
      msgBox.textContent = "Log in to music.youtube.com in Chrome first.";
      msgBox.style.color = "#FFA726";
      syncBtn.disabled = true;
    }
  } catch (err) {
    setBadge("ytStatus", "COOKIE ERROR", "error");
    msgBox.textContent = "Unable to read Chrome cookies.";
    msgBox.style.color = "#FF4B4B";
    syncBtn.disabled = true;
  }

  // Enable sync if both are ready and not already synced
  if (helxaidOnline && hasYouTubeCookies && !isCurrentlySynced) {
    syncBtn.disabled = false;
    msgBox.textContent = "Ready to sync active session to HELXAID.";
    msgBox.style.color = "#8C92A4";
  }

  // 3. Sync Action
  syncBtn.addEventListener("click", async () => {
    syncBtn.disabled = true;
    syncBtn.innerHTML = `${SVG_SPIN} <span>SYNCING...</span>`;
    msgBox.textContent = "Transmitting session tokens to HELXAID...";
    msgBox.style.color = "#FFA726";

    try {
      const res = await fetch(`${HELXAID_SERVER}/api/sync_cookies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "chrome_extension",
          browser: "Google Chrome",
          cookies: collectedCookies,
          timestamp: Date.now()
        })
      });

      const data = await res.json();
      if (data.success) {
        isCurrentlySynced = true;
        localStorage.setItem("helxaid_is_synced", "true");
        syncBtn.disabled = false;
        syncBtn.innerHTML = `${SVG_CHECK} <span>SYNCED</span>`;
        syncBtn.style.background = "#059669";
        msgBox.textContent = "YouTube Music session linked to HELXAID.";
        msgBox.style.color = "#00E599";
      } else {
        throw new Error(data.message || "Failed to sync");
      }
    } catch (err) {
      syncBtn.disabled = false;
      syncBtn.innerHTML = `${SVG_SYNC} <span>RETRY SYNC</span>`;
      syncBtn.style.background = "#FF5B06";
      msgBox.textContent = `Sync failed: ${err.message}`;
      msgBox.style.color = "#FF4B4B";
    }
  });
});
