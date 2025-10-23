const fs = require('fs');
const axios = require('axios');
const m3uFilePath = 'PrimeVision/us.m3u';

function extractSubdomain(url) {
  const match = url.match(/http:\/\/(fl\d+)\.moveonjoy\.ml/i);
  return match ? match[1] : null;
}

function replaceSubdomain(url, newSub) {
  return url.replace(/fl\d+/, newSub);
}

async function isStreamOnline(url) {
  try {
    const testPromises = Array.from({ length: 3 }, () =>
      axios.get(url, { timeout: 2000, responseType: 'arraybuffer' })
    );

    const results = await Promise.allSettled(testPromises);
    const successCount = results.filter(r => r.status === 'fulfilled').length;

    return successCount >= 2;
  } catch {
    return false;
  }
}

async function findWorkingSubdomain(url) {
  const currentSub = extractSubdomain(url);
  if (!currentSub) return null;

  const currentNum = parseInt(currentSub.replace('fl', ''), 10);

  for (let i = 1; i <= 3; i++) {
    const candidateSub = `fl${String(currentNum + i).padStart(2, '0')}`;
    const testUrl = replaceSubdomain(url, candidateSub);

    console.log(`🔄 Trying fallback: ${candidateSub} for ${url}`);
    const online = await isStreamOnline(testUrl);

    if (online) {
      console.log(`✅ Found working stream: ${testUrl}`);
      return testUrl;
    }
  }

  return null;
}

async function processPlaylist() {
  const data = fs.readFileSync(m3uFilePath, 'utf8');
  const lines = data.split('\n');

  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('http://')) {
      const url = lines[i];
      const online = await isStreamOnline(url);

      if (!online) {
        console.log(`❌ Offline: ${url}`);
        const workingUrl = await findWorkingSubdomain(url);
        if (workingUrl) {
          lines[i] = workingUrl;
        } else {
          console.warn(`⚠ No fallback found for: ${url}`);
        }
      } else {
        console.log(`✅ Online: ${url}`);
      }
    }
  }

  fs.writeFileSync(m3uFilePath, lines.join('\n'), 'utf8');
  console.log("✅ Playlist update complete!");
}

processPlaylist();