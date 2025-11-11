"""PDF rendering and preprocessing"""

import fitz  # PyMuPDF
import base64
from typing import Dict, List
from pathlib import Path
from loguru import logger

from ..config.settings import settings


class PDFRenderer:
    """Render PDF pages as images (similar to import_v3)"""
    
    QUALITY_SCALES = {
        "low": 1.0,
        "medium": 1.5,
        "high": 2.0
    }
    
    def __init__(self, quality: str = None):
        self.quality = quality or settings.pdf_render_quality
        self.scale = self.QUALITY_SCALES.get(self.quality, 1.5)
    
    def render_page(self, pdf_path: str, page_num: int) -> Dict:
        """
        Render a single page as base64 image
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-based)
        
        Returns:
            Dict with image_base64, estimated_tokens, etc.
        """
        doc = fitz.open(pdf_path)
        
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise ValueError(f"Invalid page number {page_num}. PDF has {len(doc)} pages.")
        
        page = doc[page_num - 1]
        
        # Render with scaling
        mat = fitz.Matrix(self.scale, self.scale)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to base64
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        # Estimate vision tokens
        estimated_tokens = self._estimate_vision_tokens(pix.width, pix.height)
        
        result = {
            "page_number": page_num,
            "image_base64": img_base64,
            "estimated_tokens": estimated_tokens,
            "file_size_kb": len(img_bytes) / 1024,
            "width": pix.width,
            "height": pix.height
        }
        
        doc.close()
        return result
    
    @staticmethod
    def _estimate_vision_tokens(width: int, height: int) -> int:
        """
        Estimate Vision API token consumption
        Based on OpenAI's vision token calculation
        """
        # Scale to fit within 2048px
        scale = min(2048 / max(width, height), 1)
        scaled_w = int(width * scale)
        scaled_h = int(height * scale)
        
        # Calculate tiles (512x512)
        tiles_w = (scaled_w + 511) // 512
        tiles_h = (scaled_h + 511) // 512
        total_tiles = tiles_w * tiles_h
        
        # Base tokens + tile tokens
        base_tokens = 85
        tokens_per_tile = 170
        
        return base_tokens + (total_tiles * tokens_per_tile)


async def preprocess_for_classification(paper_pdf_path: str) -> Dict:
    """
    轻量级预处理：渲染指定页面用于分类
    
    策略（与 import_v3 一致）：
    - 优先使用倒数第 2、4、6 页
    - 如果页数不足，使用最后 N 页
    - 使用可配置的缩放比例（默认 medium = 1.5x）
    
    Args:
        paper_pdf_path: Paper PDF路径
    
    Returns:
        {
            "selected_pages": [page1_data, page2_data, ...],
            "paper_pdf_path": str,
            "total_pages": int
        }
    """
    logger.info(f"📄 Preprocessing for classification...")
    logger.info(f"   Render quality: {settings.pdf_render_quality}")
    
    # 获取总页数
    doc = fitz.open(paper_pdf_path)
    total_pages = len(doc)
    doc.close()
    
    logger.info(f"   Total pages: {total_pages}")
    
    # 选择页面：优先使用倒数第 2、4、6 页
    target_indices = []
    for offset in [2, 4, 6]:
        idx = total_pages - offset
        if idx >= 0:
            target_indices.append(idx)
    
    # 如果页数不足，使用最后 N 页
    if len(target_indices) < settings.classification_sample_pages:
        target_indices = list(range(
            max(0, total_pages - settings.classification_sample_pages), 
            total_pages
        ))
    
    # 排序以保持页面顺序
    target_indices.sort()
    
    # 页码（1-based）
    page_numbers = [idx + 1 for idx in target_indices]
    logger.info(f"   Selected pages for classification: {page_numbers}")
    
    # 使用 PDFRenderer 渲染选中的页面
    renderer = PDFRenderer()
    selected_pages = []
    total_tokens = 0
    
    for page_num in page_numbers:
        logger.info(f"   Rendering page {page_num}...")
        page_data = renderer.render_page(paper_pdf_path, page_num)
        selected_pages.append(page_data)
        total_tokens += page_data['estimated_tokens']
        
        logger.debug(
            f"      Size: {page_data['file_size_kb']:.1f}KB, "
            f"Dims: {page_data['width']}x{page_data['height']}, "
            f"Tokens: ~{page_data['estimated_tokens']}"
        )
    
    logger.info(f"✓ Preprocessed {len(selected_pages)} pages for classification")
    logger.info(f"   Total estimated tokens: ~{total_tokens}")
    
    return {
        "selected_pages": selected_pages,
        "paper_pdf_path": paper_pdf_path,
        "total_pages": total_pages,
        "estimated_tokens": total_tokens
    }


def add_page_markers_to_pdf(input_pdf_path: str, output_pdf_path: str, zero_based: bool = True) -> str:
    """
    Add visible page index markers to PDF (0-based or 1-based).
    
    Args:
        input_pdf_path: Path to input PDF
        output_pdf_path: Path to output PDF with markers
        zero_based: If True, use 0-based indexing (0, 1, 2...); otherwise 1-based
    
    Returns:
        Path to output PDF
    """
    import tempfile
    
    logger.info(f"Adding page markers to PDF: {input_pdf_path}")
    logger.info(f"  Using {'0-based' if zero_based else '1-based'} indexing")
    
    doc = fitz.open(input_pdf_path)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_width = page.rect.width
            page_height = page.rect.height
            
            # Generate marker image
            marker_image_path = Path(temp_dir) / f"marker_{page_num}.png"
            page_index = page_num if zero_based else page_num + 1
            _generate_page_marker_image(page_index, marker_image_path)
            
            # Position at top-right corner
            marker_width_pt = page_width * 0.15
            marker_height_pt = page_height * 0.03
            margin_pt = page_width * 0.01
            
            marker_rect = fitz.Rect(
                page_width - margin_pt - marker_width_pt,
                margin_pt,
                page_width - margin_pt,
                margin_pt + marker_height_pt
            )
            
            page.insert_image(marker_rect, filename=str(marker_image_path))
            logger.debug(f"Added marker to page {page_index}")
        
        doc.save(output_pdf_path)
        doc.close()
        logger.info(f"PDF with page markers saved to: {output_pdf_path}")
    
    return output_pdf_path


def _generate_page_marker_image(page_index: int, output_path: Path):
    """Generate a page marker image with page index."""
    from PIL import Image, ImageDraw, ImageFont
    
    img_width = 800
    img_height = 150
    img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    marker_text = f"PAGE_INDEX_{page_index}"
    
    try:
        font_size = 80
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), marker_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (img_width - text_width) // 2
    y = (img_height - text_height) // 2
    
    bg_padding = 10
    draw.rectangle(
        [x - bg_padding, y - bg_padding, 
         x + text_width + bg_padding, y + text_height + bg_padding],
        fill='yellow',
        outline='red',
        width=5
    )
    
    draw.text((x, y), marker_text, fill='red', font=font)
    img.save(str(output_path), 'PNG')

