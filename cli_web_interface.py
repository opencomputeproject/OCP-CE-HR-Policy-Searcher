"""Simple web interface for the CLI agent using src.agent directly."""

import asyncio
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="CLI Agent Web Interface")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "CLI Agent Web Interface", "endpoint": "/ws"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            # Receive message from frontend
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "").strip()

            if not user_message:
                await websocket.send_text("Please provide a message.")
                continue

            # Run the CLI agent as a subprocess
            try:
                # Run the message like terminal input, e.g. --discover EU.
                cmd = [sys.executable, "-m", "src.agent", *shlex.split(user_message)]

                # Set environment to include the project root
                env = os.environ.copy()
                env["PYTHONPATH"] = str(project_root)
                env["PYTHONIOENCODING"] = "utf-8"

                # Run the command and capture output
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=project_root,
                    env=env
                )

                stdout, stderr = await process.communicate()

                # Send the output back to frontend
                if process.returncode == 0:
                    response = stdout.decode("utf-8", errors="replace").strip()
                    if response:
                        await websocket.send_text(response)
                    else:
                        await websocket.send_text("Agent completed successfully (no output)")
                else:
                    error_msg = stderr.decode("utf-8", errors="replace").strip()
                    await websocket.send_text(f"Error: {error_msg}")

            except Exception as e:
                await websocket.send_text(f"Failed to run agent: {str(e)}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    import uvicorn
    print("Starting CLI Agent Web Interface on http://localhost:8001")
    print("Connect your frontend to ws://localhost:8001/ws")
    uvicorn.run(app, host="0.0.0.0", port=8001)
