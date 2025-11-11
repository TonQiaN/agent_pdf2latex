"""Image Extraction from PDF Utility

Extract images from PDF files based on bounding box coordinates.
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import List
from loguru import logger

from ..models.schemas import ImageInfo


def extract_images_from_pdf(
    pdf_path: str,
    images_info: List[ImageInfo],
    output_dir: Path,
    prefix: str = "image"
) -> List[ImageInfo]:
    """
    从 PDF 中截取图片
    
    Args:
        pdf_path: PDF 文件路径
        images_info: ImageInfo 列表（包含 page_number 和 bbox）
        output_dir: 输出目录
        prefix: 文件名前缀（如 "question_image" 或 "answer_image"）
    
    Returns:
        更新后的 ImageInfo 列表（填充了 image_path）
    """
    if not images_info:
        logger.debug(f"No images to extract from {pdf_path}")
        return images_info
    
    # Ensure output directory exists
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Extracting {len(images_info)} images from {pdf_path}")
    
    # Open PDF document
    doc = fitz.open(pdf_path)
    
    try:
        updated_images = []
        
        for idx, img_info in enumerate(images_info):
            try:
                # Get page (0-based indexing)
                page_num = img_info.page_number
                if page_num < 0 or page_num >= len(doc):
                    logger.warning(f"Page number {page_num} out of range (0-{len(doc)-1}), skipping image {idx}")
                    updated_images.append(img_info)
                    continue
                
                page = doc.load_page(page_num)
                
                # Extract bounding box coordinates
                bbox = img_info.bbox
                if len(bbox) != 4:
                    logger.warning(f"Invalid bbox format for image {idx}: {bbox}, expected [x1, y1, x2, y2]")
                    updated_images.append(img_info)
                    continue
                
                x1, y1, x2, y2 = bbox
                
                # Create rectangle for cropping
                # Note: fitz.Rect expects (x0, y0, x1, y1) where origin is top-left
                crop_rect = fitz.Rect(x1, y1, x2, y2)
                
                # Generate pixmap with specified DPI
                # Using 150 DPI for balance between quality and file size
                pix = page.get_pixmap(clip=crop_rect, dpi=150)
                
                # Generate output filename
                image_filename = f"{prefix}_{idx + 1}.png"
                image_path = output_dir / image_filename
                
                # Save image
                pix.save(str(image_path))
                logger.debug(f"Saved image: {image_path}")
                
                # Memory cleanup - critical to prevent memory leaks
                pix = None
                del pix
                
                # Update ImageInfo with relative path
                # Store relative path from output_dir for portability
                updated_img_info = img_info.model_copy()
                updated_img_info.image_path = image_filename
                updated_images.append(updated_img_info)
                
            except Exception as e:
                logger.error(f"Failed to extract image {idx} from page {img_info.page_number}: {e}")
                # Keep original ImageInfo if extraction fails
                updated_images.append(img_info)
                continue
        
        logger.info(f"✓ Successfully extracted {len(updated_images)} images to {output_dir}")
        return updated_images
        
    finally:
        # Always close the document to free resources
        doc.close()

