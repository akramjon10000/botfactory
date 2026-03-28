// Live AI Call Implementation using WebSocket and AudioContext

let liveModal, liveStatusText, liveWaves, startLiveBtn, endLiveBtn, liveCallInitBtn;
let audioContext, mediaStream, sourceNode, processorNode;
let playContext, nextPlayTime;
let ws;

document.addEventListener('DOMContentLoaded', () => {
    liveModal = document.getElementById('liveCallModal');
    liveStatusText = document.getElementById('liveStatusText');
    liveWaves = document.getElementById('liveWaves');
    startLiveBtn = document.getElementById('startLiveCallBtn');
    endLiveBtn = document.getElementById('endLiveCallBtn');
    liveCallInitBtn = document.getElementById('liveCallInitBtn');
    const closeLiveBtn = document.getElementById('closeLiveCallModal');

    if(liveCallInitBtn) {
        liveCallInitBtn.addEventListener('click', () => {
            liveModal.classList.remove('hidden');
        });
    }

    if(closeLiveBtn) {
        closeLiveBtn.addEventListener('click', stopCallAndClose);
    }

    if(startLiveBtn) {
        startLiveBtn.addEventListener('click', startCall);
    }

    if(endLiveBtn) {
        endLiveBtn.addEventListener('click', stopCallAndClose);
    }
});

function stopCallAndClose() {
    stopLiveCall();
    liveModal.classList.add('hidden');
}

async function startCall() {
    startLiveBtn.classList.add('hidden');
    endLiveBtn.classList.remove('hidden');
    liveStatusText.innerText = "Ulanmoqda...";
    
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch(err) {
        liveStatusText.innerText = "Mikrofonga ruxsat olinmadi!";
        resetUI();
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const currentBotId = typeof botId !== 'undefined' && botId ? botId : (new URLSearchParams(window.location.search).get('bot_id') || '1');
    const wsUrl = `${protocol}//${window.location.host}/api/miniapp/live-stream/${currentBotId}`;
    
    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        liveStatusText.innerText = "Qo'ng'iroq ulandi! Gapirishingiz mumkin...";
        liveWaves.classList.add('active');
        startAudioCapture();
        startAudioPlayback();
    };

    ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
            playAudioChunk(event.data);
        } else if (typeof event.data === 'string') {
            console.log("WS text message: ", event.data);
            if(event.data.includes("Error")) {
                liveStatusText.innerText = event.data;
                stopLiveCall();
            }
        }
    };

    ws.onerror = (e) => {
        console.error("WS error: ", e);
        liveStatusText.innerText = "Xatolik yuz berdi.";
    };

    ws.onclose = () => {
        liveStatusText.innerText = "Qo'ng'iroq yakunlandi.";
        stopLiveCall();
    };
}

function startAudioCapture() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    processorNode = audioContext.createScriptProcessor(4096, 1, 1);

    sourceNode.connect(processorNode);
    processorNode.connect(audioContext.destination);

    processorNode.onaudioprocess = (e) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            const inputData = e.inputBuffer.getChannelData(0);
            
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                const s = Math.max(-1, Math.min(1, inputData[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            ws.send(pcmData.buffer);
        }
    };
}

function startAudioPlayback() {
    playContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    nextPlayTime = playContext.currentTime;
}

function playAudioChunk(arrayBuffer) {
    if(!playContext) return;
    
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
    }

    const audioBuffer = playContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = playContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(playContext.destination);

    const startTime = Math.max(playContext.currentTime, nextPlayTime);
    source.start(startTime);
    nextPlayTime = startTime + audioBuffer.duration;
}

function stopLiveCall() {
    if (ws) {
        ws.close();
        ws = null;
    }
    if (processorNode) {
        processorNode.disconnect();
        processorNode = null;
    }
    if (sourceNode) {
        sourceNode.disconnect();
        sourceNode = null;
    }
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
    }
    if (playContext && playContext.state !== 'closed') {
        playContext.close();
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }
    resetUI();
}

function resetUI() {
    startLiveBtn.classList.remove('hidden');
    endLiveBtn.classList.add('hidden');
    liveWaves.classList.remove('active');
    setTimeout(() => {
        if(liveStatusText.innerText === "Qo'ng'iroq yakunlandi." || liveStatusText.innerText.includes("Xatolik")) {
            liveStatusText.innerText = "Bog'lanish uchun pastdagi tugmani bosing";
        }
    }, 3000);
}
