from fastapi import FastAPI, File, UploadFile, Query
from fastapi.responses import StreamingResponse
from PIL import Image
import io
import concurrent.futures
import uvicorn
import asyncio

app = FastAPI()

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
        # Step 1: Resize to fill box, preserving aspect ratio, but possibly larger than target
        orig_width, orig_height = img.size
        if width is not None and height is not None:
            scale = max(width / orig_width, height / orig_height)
            resize_width = int(orig_width * scale)
            resize_height = int(orig_height * scale)
            img = img.resize((resize_width, resize_height), Image.LANCZOS)
            # Step 2: Center crop to exact dimensions
            left = (resize_width - width) // 2
            top = (resize_height - height) // 2
            right = left + width
            bottom = top + height
            img = img.crop((left, top, right, bottom))
        elif width is not None:
            scale = width / orig_width
            resize_width = width
            resize_height = int(orig_height * scale)
            img = img.resize((resize_width, resize_height), Image.LANCZOS)
        elif height is not None:
            scale = height / orig_height
            resize_height = height
            resize_width = int(orig_width * scale)
            img = img.resize((resize_width, resize_height), Image.LANCZOS)
        # Convert mode for JPEG
        if out_format.lower() in ["jpeg", "jpg"] and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        # Remove metadata
        img.info.pop("exif", None)
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

# if __name__ == "__main__":
#     uvicorn.run("image_api_server2:app", host="0.0.0.0", port=8001, reload=True)
