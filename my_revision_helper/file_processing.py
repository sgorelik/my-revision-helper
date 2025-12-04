"""
File processing utilities for My Revision Helper.

This module handles:
- Image compression for OpenAI Vision API
- Text extraction from images (OCR via OpenAI)
- Text extraction from PDFs
- Text extraction from PowerPoint presentations
- File processing orchestration
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from PIL import Image

# Set up logging
logger = logging.getLogger(__name__)

# Maximum file size for upload: 50MB (we'll compress/process as needed)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

# Maximum size for OpenAI Vision API (after base64 encoding, ~20MB raw = ~27MB base64)
# We'll compress images to stay under this limit
MAX_OPENAI_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB raw image (before base64)


def compress_image(image_bytes: bytes, max_size: int = MAX_OPENAI_IMAGE_SIZE, quality: int = 85) -> bytes:
    """
    Compress an image to fit within size limits while preserving quality.
    
    Args:
        image_bytes: Original image bytes
        max_size: Maximum size in bytes (default: MAX_OPENAI_IMAGE_SIZE)
        quality: JPEG quality (1-100, default: 85)
        
    Returns:
        Compressed image bytes (JPEG format)
    """
    try:
        # Open image
        img = Image.open(BytesIO(image_bytes))
        
        # Convert RGBA to RGB if needed (for JPEG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # If already small enough, return as-is
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        compressed = output.getvalue()
        
        if len(compressed) <= max_size:
            return compressed
        
        # Need to resize - calculate scale factor
        original_size = len(image_bytes)
        scale_factor = (max_size / original_size) ** 0.5  # Square root for 2D scaling
        
        # Resize image
        new_width = int(img.width * scale_factor)
        new_height = int(img.height * scale_factor)
        
        # Ensure minimum dimensions for readability
        new_width = max(new_width, 800)
        new_height = max(new_height, 600)
        
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Try different quality levels
        for q in range(quality, 50, -10):
            output = BytesIO()
            img_resized.save(output, format='JPEG', quality=q, optimize=True)
            compressed = output.getvalue()
            if len(compressed) <= max_size:
                logger.info(f"Compressed image: {len(image_bytes) / (1024*1024):.1f}MB -> {len(compressed) / (1024*1024):.1f}MB (quality={q})")
                return compressed
        
        # If still too large, use minimum quality
        output = BytesIO()
        img_resized.save(output, format='JPEG', quality=50, optimize=True)
        compressed = output.getvalue()
        logger.info(f"Compressed image to minimum: {len(image_bytes) / (1024*1024):.1f}MB -> {len(compressed) / (1024*1024):.1f}MB")
        return compressed
        
    except Exception as e:
        logger.error(f"Failed to compress image: {e}", exc_info=True)
        # Return original if compression fails
        return image_bytes


async def extract_text_from_pdf(file: UploadFile) -> Optional[str]:
    """
    Extract text from a PDF file.
    
    Args:
        file: Uploaded PDF file
        
    Returns:
        Extracted text, or None if extraction fails
    """
    try:
        import pdfplumber
        
        # Read file content
        contents = await file.read()
        
        # Check file size - PDFs can be large, but we process them locally
        if len(contents) > MAX_FILE_SIZE:
            logger.warning(f"PDF {file.filename} is large ({len(contents) / (1024*1024):.1f}MB), processing in chunks...")
        
        # Use pdfplumber to extract text (processes all pages)
        with pdfplumber.open(BytesIO(contents)) as pdf:
            text_parts = []
            total_pages = len(pdf.pages)
            logger.info(f"Processing PDF {file.filename} with {total_pages} pages")
            
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- Page {page_num} ---\n{page_text}")
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num} of {file.filename}: {e}")
                    continue
            
            extracted_text = "\n\n".join(text_parts)
            logger.info(f"Extracted {len(extracted_text)} characters from PDF {file.filename} ({total_pages} pages)")
            return extracted_text if extracted_text else None
            
    except ImportError:
        logger.error("pdfplumber not installed - cannot extract text from PDFs")
        return None
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {file.filename}: {e}", exc_info=True)
        return None


async def extract_text_from_pptx(file: UploadFile) -> Optional[str]:
    """
    Extract text from a PowerPoint presentation file.
    
    Args:
        file: Uploaded PPTX file
        
    Returns:
        Extracted text, or None if extraction fails
    """
    try:
        from pptx import Presentation
        
        # Read file content
        contents = await file.read()
        
        # Check file size - PPTX can be large, but we process them locally
        if len(contents) > MAX_FILE_SIZE:
            logger.warning(f"PPTX {file.filename} is large ({len(contents) / (1024*1024):.1f}MB), processing all slides...")
        
        # Use python-pptx to extract text (processes all slides)
        prs = Presentation(BytesIO(contents))
        text_parts = []
        total_slides = len(prs.slides)
        logger.info(f"Processing PPTX {file.filename} with {total_slides} slides")
        
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    slide_texts.append(shape.text)
            
            if slide_texts:
                slide_text = f"--- Slide {slide_num} ---\n" + "\n".join(slide_texts)
                text_parts.append(slide_text)
        
        extracted_text = "\n\n".join(text_parts)
        logger.info(f"Extracted {len(extracted_text)} characters from PPTX {file.filename} ({total_slides} slides)")
        return extracted_text if extracted_text else None
        
    except ImportError:
        logger.error("python-pptx not installed - cannot extract text from PowerPoint files")
        return None
    except Exception as e:
        logger.error(f"Failed to extract text from PPTX {file.filename}: {e}", exc_info=True)
        return None


async def extract_text_from_image(file: UploadFile, client: Any) -> Optional[str]:
    """
    Extract text from an uploaded image using OpenAI Vision API.
    
    Args:
        file: Uploaded file (should be an image)
        client: OpenAI client instance
        
    Returns:
        Extracted text, or None if extraction fails
    """
    try:
        # Read file content
        contents = await file.read()
        original_size = len(contents)
        
        # Check file size - compress if too large for OpenAI
        if original_size > MAX_OPENAI_IMAGE_SIZE:
            logger.info(f"Image {file.filename} is large ({original_size / (1024*1024):.1f}MB), compressing...")
            try:
                contents = compress_image(contents, max_size=MAX_OPENAI_IMAGE_SIZE)
                logger.info(f"Compressed {file.filename}: {original_size / (1024*1024):.1f}MB -> {len(contents) / (1024*1024):.1f}MB")
            except ImportError:
                logger.warning("Pillow not available - cannot compress image. Install Pillow for large image support.")
                if original_size > MAX_OPENAI_IMAGE_SIZE:
                    logger.error(f"Image {file.filename} too large ({original_size / (1024*1024):.1f}MB) and compression unavailable")
                    return None
            except Exception as e:
                logger.error(f"Failed to compress image {file.filename}: {e}", exc_info=True)
                if original_size > MAX_OPENAI_IMAGE_SIZE:
                    return None
        
        # Encode to base64 for OpenAI Vision API
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # After compression, images are always JPEG
        # (compression converts all formats to JPEG for consistency and size)
        image_format = "image/jpeg"
        
        # Use OpenAI Vision API to extract text
        response = client.chat.completions.create(
            model="gpt-4o",  # gpt-4o has vision capabilities
            messages=[
                {
                    "role": "system",
                    "content": "You are a text extraction assistant. Extract all text from the image accurately, preserving formatting and structure. Return only the extracted text, no explanations.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this image. Preserve the structure and formatting as much as possible.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_format};base64,{base64_image}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=2000,
        )
        
        extracted_text = response.choices[0].message.content
        logger.info(f"Extracted {len(extracted_text)} characters from image {file.filename}")
        return extracted_text
        
    except Exception as e:
        logger.error(f"Failed to extract text from image {file.filename}: {e}", exc_info=True)
        return None


async def process_uploaded_files(files: List[UploadFile], openai_client: Any) -> Dict[str, str]:
    """
    Process uploaded files and extract text from images, PDFs, and PowerPoint files.
    
    Args:
        files: List of uploaded files
        openai_client: OpenAI client instance (for image OCR)
        
    Returns:
        Dictionary mapping filename to extracted text
    """
    if not files:
        return {}
    
    extracted_texts = {}
    skipped_files = []
    
    for file in files:
        content_type = file.content_type or ""
        filename = file.filename or "unknown"
        filename_lower = filename.lower()
        
        # Reset file pointer (in case it was read before)
        await file.seek(0)
        
        try:
            # Handle PDF files
            if "pdf" in content_type or filename_lower.endswith('.pdf'):
                logger.info(f"Processing PDF file: {filename}")
                text = await extract_text_from_pdf(file)
                if text:
                    extracted_texts[filename] = text
                else:
                    skipped_files.append(f"{filename} (PDF extraction failed or file too large)")
            
            # Handle PowerPoint files
            elif ("presentation" in content_type or "powerpoint" in content_type or 
                  filename_lower.endswith(('.pptx', '.ppt'))):
                logger.info(f"Processing PowerPoint file: {filename}")
                text = await extract_text_from_pptx(file)
                if text:
                    extracted_texts[filename] = text
                else:
                    skipped_files.append(f"{filename} (PowerPoint extraction failed or file too large)")
            
            # Handle image files (requires OpenAI client)
            elif any(img_type in content_type for img_type in ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]):
                if not openai_client:
                    skipped_files.append(f"{filename} (OpenAI client not available for image OCR)")
                    logger.warning(f"OpenAI client not available - cannot extract text from image {filename}")
                else:
                    logger.info(f"Processing image file: {filename}")
                    text = await extract_text_from_image(file, openai_client)
                    if text:
                        extracted_texts[filename] = text
                    else:
                        skipped_files.append(f"{filename} (image extraction failed or file too large)")
            
            else:
                skipped_files.append(f"{filename} (unsupported file type: {content_type})")
                logger.warning(f"Skipping unsupported file: {filename} (type: {content_type})")
        
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}", exc_info=True)
            skipped_files.append(f"{filename} (processing error: {str(e)[:50]})")
    
    if skipped_files:
        logger.info(f"Skipped {len(skipped_files)} file(s): {', '.join(skipped_files)}")
    
    if extracted_texts:
        logger.info(f"Successfully extracted text from {len(extracted_texts)} file(s)")
    
    return extracted_texts

