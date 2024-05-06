import json
import numpy as np
import soxr
import torch
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from infer import infer


hps = None  # init bert vits2
net_g = None
app = FastAPI()  # Cross-domain access should be allowed


def tts_streaming_fn(text, speaker, sdp_ratio, noise_scale, noise_scale_w, length_scale, sample_rate):
    with torch.no_grad():
        chunks = infer(text, sdp_ratio, noise_scale, noise_scale_w, length_scale, speaker, hps, net_g)
    if sample_rate != 44100:
        rs = soxr.ResampleStream(44100, sample_rate, 1, dtype=np.int16)
    for chunk in chunks:
        chunk = (chunk * 32767).astype(np.int16)
        if sample_rate != 44100:
            chunk = rs.resample_chunk(chunk)
        yield chunk.tobytes()


@app.get("/speakers")
def speakers():
    return list(hps.data.spk2id.keys())


@app.websocket("/tts")
async def tts(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        data = json.loads(data)
        text = data["text"]
        speaker = data.get("speaker", "baker")
        sdp_ratio = float(data.get("sdp_ratio", 0.7))
        noise_scale = float(data.get("noise_scale", 0.6))
        noise_scale_w = float(data.get("noise_scale_w", 0.9))
        length_scale = float(data.get("length_scale", 1.0))
        sample_rate = int(data.get("sample_rate", 44100))
        for chunk in tts_streaming_fn(text, speaker, sdp_ratio, noise_scale, noise_scale_w, length_scale, sample_rate):
            await websocket.send_bytes(chunk)
        await websocket.send_text(json.dumps({"is_done": True}))
        await websocket.close()
    except WebSocketDisconnect:
        await websocket.close()


if __name__ == "__main__":
    speaker = list(hps.data.spk2id.keys())[0]
    text = "为祖国健康工作五十年"
    list(tts_streaming_fn(text, speaker, 0.7, 0.6, 0.9, 1.0, 44100))
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
