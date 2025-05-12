# api/index.py
from fastapi import FastAPI, File, UploadFile, Query, Response
from fastapi.responses import StreamingResponse
from PIL import Image
import io
import concurrent.futures
# import uvicorn # Remove this line, not needed for Vercel
import asyncio

app = FastAPI()

# ProcessPoolExecutor for parallel processing
# !! CAUTION !!: This may not be optimal for Vercel's serverless environment.
# Consider alternative platforms like Google Cloud Run or AWS Fargate for production
# image processing at scale, as they offer better control over resources for CPU-bound tasks.
executor = concurrent.futures.ProcessPoolExecutor(max_workers=8)

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
            img = img.resize((new_width, new_height), Image.LANCZOS)
        # Convert mode for JPEG
        if out_format.lower() in ["jpeg", "jpg"] and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        # Save to buffer
        buf = io.BytesIO()
        save_kwargs = {"quality": quality}
        if out_format.lower() == "webp":
            save_kwargs["method"] = method
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
    import time
    start = time.perf_counter()
    file_bytes = await file.read()
    # Run in thread pool for concurrency
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

@app.get("/")
def root():
    return {"message": "Image conversion API. POST /convert with image file."}

# The following block is for local testing only and should be removed or commented out for Vercel deployment.
# if __name__ == "__main__":
#     uvicorn.run("image_api_server:app", host="0.0.0.0", port=8000, reload=True)
