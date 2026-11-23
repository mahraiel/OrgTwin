import threading, webbrowser, uvicorn
threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8001")).start()
uvicorn.run("orgtwin.api:app", host="127.0.0.1", port=8001)
