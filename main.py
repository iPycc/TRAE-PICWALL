from pathlib import Path
import os

import uvicorn


BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)


if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=1309,
        reload=False,
    )
