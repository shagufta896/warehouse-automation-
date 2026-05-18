import uvicorn
import webbrowser
import threading
import os

def open_browser():
    """Open the frontend after a short delay to let the server start."""
    import time
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000/app/")

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)