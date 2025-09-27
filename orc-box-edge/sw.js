// sw.js - MV3 Service Worker
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
	if (msg && msg.type === "captureVisibleTab") {
	  const quality = Math.round((msg.quality ?? 0.92) * 100); // 0~100
	  chrome.tabs.captureVisibleTab(
		{ format: "jpeg", quality },
		(dataUrl) => {
		  if (chrome.runtime.lastError || !dataUrl) {
			sendResponse({
			  ok: false,
			  error: chrome.runtime.lastError?.message || "captureVisibleTab failed"
			});
		  } else {
			sendResponse({ ok: true, dataUrl });
		  }
		}
	  );
	  // 异步响应
	  return true;
	}
  });
  