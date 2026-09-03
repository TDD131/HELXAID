// HELXAID Sync - Background Service Worker (Manifest V3)
// Automatically bridges YouTube Music session cookies to HELXAID with zero user intervention.

const HELXAID_SERVER = "http://127.0.0.1:8889";
let debounceTimer = null;
let lastSyncTimestamp = 0;

async function extractYouTubeCookies() {
  try {
    const musicCookies = await chrome.cookies.getAll({ url: "https://music.youtube.com" });
    const ytUrlCookies = await chrome.cookies.getAll({ url: "https://www.youtube.com" });
    const ytDomainCookies = await chrome.cookies.getAll({ domain: "youtube.com" });
    const gCookies = await chrome.cookies.getAll({ domain: "google.com" });

    const collected = {};
    for (const c of gCookies) collected[c.name] = c.value;
    for (const c of ytDomainCookies) collected[c.name] = c.value;
    for (const c of ytUrlCookies) collected[c.name] = c.value;
    for (const c of musicCookies) collected[c.name] = c.value;

    const hasCritical = Boolean(
      collected["SAPISID"] || 
      collected["LOGIN_INFO"] || 
      collected["__Secure-3PAPISID"] || 
      collected["__Secure-1PSID"] || 
      collected["SID"]
    );

    return hasCritical ? collected : null;
  } catch (err) {
    console.warn("[HELXAID Sync] Failed reading Chrome cookies:", err);
    return null;
  }
}

async function syncToHelxaid(force = false) {
  try {
    // 1. Health check to see if HELXAID desktop app is running
    const healthRes = await fetch(`${HELXAID_SERVER}/api/health`, { method: "GET" });
    if (!healthRes.ok) return false;

    const healthData = await healthRes.json();
    const isAppSynced = (healthData && healthData.youtube_synced === true);

    // If already synchronized and not forced, no need to spam the API
    if (isAppSynced && !force) {
      return true;
    }

    // 2. Extract cookies
    const cookies = await extractYouTubeCookies();
    if (!cookies) return false;

    // Rate-limit sync calls to at most once every 5 seconds unless forced
    const now = Date.now();
    if (!force && (now - lastSyncTimestamp < 5000)) {
      return true;
    }

    // 3. Transmit session payload
    const syncRes = await fetch(`${HELXAID_SERVER}/api/sync_cookies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "chrome_background_worker",
        browser: "Google Chrome",
        cookies: cookies,
        timestamp: now
      })
    });

    if (syncRes.ok) {
      lastSyncTimestamp = now;
      console.log("[HELXAID Sync] Successfully auto-pushed YouTube session to HELXAID!");
      return true;
    }
  } catch (err) {
    // HELXAID app is offline or network is busy
  }
  return false;
}

// Heartbeat Alarm: Check every 15-30s if HELXAID came online or needs session sync
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("helxaid_sync_alarm", { periodInMinutes: 0.25 }); // every 15s
  syncToHelxaid(true);
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("helxaid_sync_alarm", { periodInMinutes: 0.25 });
  syncToHelxaid(false);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "helxaid_sync_alarm") {
    syncToHelxaid(false);
  }
});

// Live Cookie Listener: Auto-push when user logs into YouTube or refreshes tokens
chrome.cookies.onChanged.addListener((changeInfo) => {
  const domain = changeInfo.cookie?.domain || "";
  if (domain.includes("youtube.com") || domain.includes("google.com")) {
    const name = changeInfo.cookie?.name || "";
    if (["SAPISID", "__Secure-3PAPISID", "SID", "LOGIN_INFO", "SSID", "HSID"].includes(name)) {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        syncToHelxaid(true);
      }, 1200);
    }
  }
});
