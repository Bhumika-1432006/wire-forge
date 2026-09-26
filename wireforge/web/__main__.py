import os

import uvicorn

uvicorn.run("wireforge.web.server:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
