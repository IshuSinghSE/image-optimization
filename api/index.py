# api/index.py (or your main FastAPI file)
from fastapi import FastAPI, File, UploadFile, Query, Response
from fastapi.responses import StreamingResponse, HTMLResponse # Import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # Import StaticFiles
from PIL import Image
import io
import concurrent.futures
# import uvicorn # Remove this line if you haven't already
import asyncio
import time # Ensure time is imported

app = FastAPI()

# Add CORS middleware to allow requests from all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# ProcessPoolExecutor for parallel processing
# !! IMPORTANT CAUTION !!: This setup might not be optimal for Google Cloud Functions or Vercel Serverless.
# Consider Cloud Run or similar for production image processing at scale.
# If you are still on Vercel and getting multiprocessing errors, you might need ThreadPoolExecutor instead.
executor = concurrent.futures.ProcessPoolExecutor(max_workers=8) # Adjust max_workers if needed

SUPPORTED_FORMATS = ["png", "webp", "jpeg", "jpg"]

def process_image(
    file_bytes: bytes,
    out_format: str = "webp",
    width: int = None,
    height: int = None,
    quality: int = 80,
    method: int = 6
):
    with Image.open(io.BytesIO(file_bytes)) as img:
        # Resize if needed
        if width or height:
            orig_width, orig_height = img.size
            new_width = width or orig_width
            new_height = height or orig_height
            # Use LANCZOS filter for resizing
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS) # Use Image.Resampling.LANCZOS

        # Convert mode for JPEG if image has alpha channel
        if out_format.lower() in ["jpeg", "jpg"] and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        # Save to buffer
        buf = io.BytesIO()
        save_kwargs = {"quality": quality}
        if out_format.lower() == "webp":
            save_kwargs["method"] = method # WebP encoding method
            # Add lossless option for WebP if quality is 100
            if quality == 100:
                 save_kwargs["lossless"] = True
        img.save(buf, out_format.upper(), **save_kwargs)
        buf.seek(0)
        return buf

@app.post("/convert")
async def convert_image(
    file: UploadFile = File(...),
    out_format: str = Query("webp", enum=SUPPORTED_FORMATS, description="Output format (default: webp)"),
    width: int = Query(None, description="Resize width (px), default: original width"),
    height: int = Query(None, description="Resize height (px), default: original height"),
    quality: int = Query(80, ge=1, le=100, description="Compression quality (1-100), default: 80"),
    method: int = Query(6, ge=0, le=6, description="WebP encoding method (0-6), default: 6")
):
    start = time.perf_counter()
    file_bytes = await file.read()

    # Run the blocking image processing in the executor
    loop = asyncio.get_running_loop()
    buf = await loop.run_in_executor(
        executor,
        process_image,
        file_bytes,
        out_format,
        width,
        height,
        quality,
        method
    )

    elapsed = (time.perf_counter() - start) * 1000  # ms
    print(f"Processed {file.filename} in {elapsed:.2f} ms")

    media_type = f"image/{'jpeg' if out_format.lower() == 'jpg' else out_format.lower()}"
    return StreamingResponse(buf, media_type=media_type)

# Mount a directory named 'static' to serve static files (like index.html, favicon.ico, etc.)
# The directory path is relative to where your 'api' folder is located.
# '..' goes up one level from 'api/' to the project root, then 'static' refers to the 'static' folder.
app.mount("/static", StaticFiles(directory="../static"), name="static")

# Route to serve the index.html file at the root path "/"
@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    # Construct the path to your index.html file.
    # Assumes index.html is directly inside the 'static' directory.
    html_file_path = "../static/index.html"
    try:
        with open(html_file_path, "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: index.html not found!</h1>", status_code=404)


# The following block is for local testing only and should be removed or commented out for Vercel deployment.
# if __name__ == "__main__":
#     uvicorn.run("image_api_server:app", host="0.0.0.0", port=8000, reload=True)

