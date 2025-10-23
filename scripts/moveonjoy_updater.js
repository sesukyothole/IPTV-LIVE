const fs = require('fs');
const axios = require('axios');
const path = require('path');

const m3uFilePath = path.resolve(__dirname, '../PrimeVision/us.m3u');

function extractSubdomain(url) {
  const match = url.match(/http:\/\/(fl\d+)\.moveonjoy\.ml/i);
  return match ? match[1] : null;
}

function replaceSubdomain(url, newSub) {
  return url.replace(/fl\d+/, newSub);
}

async function isStreamOnline(url) {
  try {
    for (let i = 0; i < 3; i++) {
      const res = await axios.get(url, {
        timeout: 2000,
        responseType: 'arraybuffer',
      });

      if (res.status === 200) return true;
    }
  } catch {}

  return false;
}

async function findWorkingSubdomain(url) {
  const current = extractSubdomain(url);
  if (!current) return null;

  const currentNum = parseInt(current.replace('fl', ''), 10);

  for (let i = 1; i <= 3; i++) {
    const newNum = currentNum + i;
    const newSub = `fl${String(newNum).padStart(2, '0')}`;
    const newUrl = replaceSubdomain(url, newSub);

    console.log(`🔄 Testing fallback: ${newUrl}`);
    if (await isStreamOnline(newUrl)) {
      return newUrl;
    }
  }

  return null;
}

async function processPlaylist() {
  console.log(`📌 Loading playlist: ${m3uFilePath}`);

  let content = fs.readFileSync(m3uFilePath, 'utf8');
  const lines = content.split('\n');
  let updated = false;

  for (let i = 0; i < lines.length; i++) {
    let url = lines[i];

    if (!url.includes("moveonjoy.ml")) continue;

    const online = await isStreamOnline(url);
    if (!online) {
      console.log(`❌ Offline: ${url}`);

      const fallback = await findWorkingSubdomain(url);

      if (fallback && fallback !== url) {
        console.log(`✅ Replacing → ${fallback}`);
        lines[i] = fallback;
        updated = true;
      } else {
        console.log(`⚠ No change for: ${url}`);
      }
    } else {
      console.log(`✅ Still Online: ${url}`);
    }
  }

  if (updated) {
    fs.writeFileSync(m3uFilePath, lines.join('\n'), 'utf8');
    console.log("✅ ✅ ✅ M3U playlist UPDATED!");
  } else {
    console.log("ℹ️ No changes were needed (playlist unchanged).");
  }
}

processPlaylist();