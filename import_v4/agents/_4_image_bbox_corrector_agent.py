"""Image Bbox Corrector Agent

Verifies and corrects image bounding box coordinates to ensure proper image extraction.
"""

import json
import base64
from pathlib import Path
from typing import List, Tuple, Dict
from loguru import logger
import fitz  # PyMuPDF
from PIL import Image

from ..models.schemas import BboxCorrectionOutput, ImageInfo
from ..clients.client_manager import ClientManager
from ..clients.base import LLMMessage, MessageContent, MessageRole, ContentType
from ..preprocessing.pdf_renderer import PDFRenderer
from agents import Usage


def get_bbox_corrector_prompt(
    question_label: str,
    current_bbox: List[float],
    expected_description: str,
    image_type: str,
    pdf_page_size: Tuple[float, float],
    rendered_page_size: Tuple[int, int],
    cropped_image_size: Tuple[int, int]
) -> str:
    """生成 bbox 修正提示词"""
    
    pdf_width, pdf_height = pdf_page_size
    rendered_width, rendered_height = rendered_page_size
    cropped_width, cropped_height = cropped_image_size
    
    # Calculate scale factor
    scale_x = rendered_width / pdf_width
    scale_y = rendered_height / pdf_height
    
    # Calculate bbox in rendered image coordinates
    x1, y1, x2, y2 = current_bbox
    bbox_rendered_x1 = x1 * scale_x
    bbox_rendered_y1 = y1 * scale_y
    bbox_rendered_x2 = x2 * scale_x
    bbox_rendered_y2 = y2 * scale_y
    
    return f"""You are an expert at validating image crops from PDF documents.

=== Your Task ===
Verify if the cropped image correctly captures the {image_type} content for {question_label}.

=== Current Crop Info ===
- Question Label: {question_label}
- Current BBox (PDF points): {current_bbox} (format: [x1, y1, x2, y2])
- Current BBox (rendered pixels): [{bbox_rendered_x1:.1f}, {bbox_rendered_y1:.1f}, {bbox_rendered_x2:.1f}, {bbox_rendered_y2:.1f}]
- Expected Content: {expected_description}
- Image Type: {image_type}

=== Dimension Information ===
- PDF Page Size: {pdf_width:.1f} x {pdf_height:.1f} points (PDF coordinate system)
- Rendered Page Size: {rendered_width} x {rendered_height} pixels
- Cropped Image Size: {cropped_width} x {cropped_height} pixels
- Scale Factor: {scale_x:.3f} (X), {scale_y:.3f} (Y) pixels per PDF point

=== Important Context ===
The expected description may include:
- **For multiple choice questions**: The description may indicate which option the image belongs to (e.g., "Image for option A", "Diagram for choice B")
- **For sub-parts**: The description may indicate which sub-part the image belongs to (e.g., "Image for part (i)", "Diagram for part (ii)")
- **General descriptions**: The description may describe the image content (e.g., "Graph showing quadratic function", "Triangle diagram")

When validating, pay special attention to:
- If the description mentions an option (A, B, C, D), verify the crop includes ONLY that option's image
- If the description mentions a sub-part (i, ii, iii), verify the crop includes ONLY that sub-part's image
- Ensure the crop matches the specific context mentioned in the description

=== Evaluation Criteria ===
1. **Completeness**: Is all relevant content included?
2. **Accuracy**: Is the content correctly identified and matches the expected description?
3. **Context Match**: Does the crop match the specific context (option, sub-part, etc.) mentioned in the description?
4. **Boundaries**: Are the boundaries appropriate (not too tight/loose)?
5. **No Extra Content**: Is there minimal irrelevant content? For option-specific images, ensure no other options are included.

=== Instructions ===
1. Compare the cropped image with the rendered PDF page image
2. Check if the crop matches the expected description, paying special attention to context (option, sub-part, etc.)
3. Verify the crop includes only the relevant content mentioned in the description
4. If incorrect, provide corrected coordinates in PDF points (not pixels)
5. PDF coordinate system: origin at top-left, x increases right, y increases down
6. Coordinate conversion: PDF points × scale_factor = rendered pixels
7. The rendered page image shows the full PDF page, use it as reference to identify the correct crop area

=== Common Issues to Check ===
- Coordinates might be scaled incorrectly (e.g., pixel coordinates vs PDF points)
- Crop might be too small or too large
- Crop might be offset from the actual content
- Content might span a larger area than the current bbox

=== Output Format ===
Return ONLY valid JSON:
{{
    "is_correct": true/false,
    "confidence": 0.95,
    "issue_description": "Crop is too narrow, missing right side of diagram" or null,
    "corrected_bbox": [x1, y1, x2, y2] or null,
    "reasoning": "Detailed explanation of your decision..."
}}

If crop is correct, set corrected_bbox to null.
If crop needs correction, provide the corrected coordinates in PDF points.

Now analyze the cropped image and the PDF page.
"""


async def correct_image_bbox(
    question_label: str,
    original_bbox: List[float],
    cropped_image_path: str,
    pdf_path: str,
    page_number: int,
    expected_description: str,
    image_type: str = "question",
    max_iterations: int = 4
) -> Tuple[List[float], bool, Usage, List[str]]:
    """
    验证并修正图片截取坐标
    
    Args:
        question_label: 题目标签
        original_bbox: 原始 bbox 坐标
        cropped_image_path: 截取的图片路径
        pdf_path: PDF 文件路径（用于重新截取和渲染页面）
        page_number: 页码（0-based）
        expected_description: 期望的图片内容描述
        image_type: 图片类型（"question" 或 "answer"）
        max_iterations: 最大迭代次数（默认 4）
    
    Returns:
        Tuple[List[float], bool, Usage, List[str]]: (最终bbox, 是否成功, 使用统计, 所有截取的图片路径)
    """
    logger.info(f"🔍 Verifying {image_type} image bbox for {question_label}")
    logger.info(f"   Initial bbox: {original_bbox}")
    
    current_bbox = original_bbox
    total_usage = Usage()
    all_image_paths = [cropped_image_path]
    
    # Get PDF page dimensions (PDF points)
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number]  # 0-based
        pdf_page_rect = page.rect
        pdf_page_width = pdf_page_rect.width
        pdf_page_height = pdf_page_rect.height
    finally:
        doc.close()
    
    # Get cropped image dimensions
    with Image.open(cropped_image_path) as img:
        cropped_image_width, cropped_image_height = img.size
    
    # Use gpt-5 for better accuracy
    client = ClientManager.create_agent_client(model="gpt-5")
    
    # Initialize PDF renderer
    pdf_renderer = PDFRenderer(quality="medium")
    
    # Render PDF page as image once (outside loop for consistency)
    logger.debug(f"  Rendering PDF page {page_number + 1} (1-based)...")
    rendered_page_data = pdf_renderer.render_page(pdf_path, page_number + 1)  # render_page uses 1-based
    rendered_page_b64 = rendered_page_data['image_base64']
    rendered_page_width = rendered_page_data['width']
    rendered_page_height = rendered_page_data['height']
    
    # Save rendered page image to temporary file for cropping
    output_dir = Path(cropped_image_path).parent
    rendered_page_path = output_dir / f"{image_type}_rendered_page_{page_number}.png"
    rendered_page_bytes = base64.b64decode(rendered_page_b64)
    with open(rendered_page_path, 'wb') as f:
        f.write(rendered_page_bytes)
    logger.debug(f"  Saved rendered page image: {rendered_page_path}")
    
    # Calculate scale factors for coordinate conversion
    scale_x = rendered_page_width / pdf_page_width
    scale_y = rendered_page_height / pdf_page_height
    
    for iteration in range(max_iterations):
        logger.info(f"  Iteration {iteration + 1}/{max_iterations}")
        
        try:
            
            # Read and encode current cropped image as base64
            current_img_path = all_image_paths[-1]
            logger.debug(f"  Reading cropped image: {current_img_path}")
            
            with open(current_img_path, 'rb') as f:
                cropped_image_data = f.read()
                cropped_image_b64 = base64.b64encode(cropped_image_data).decode('utf-8')
            
            # Get current cropped image dimensions (may have changed after re-extraction)
            with Image.open(current_img_path) as img:
                current_cropped_width, current_cropped_height = img.size
            
            # Prepare prompt with dimension information
            system_prompt = get_bbox_corrector_prompt(
                question_label=question_label,
                current_bbox=current_bbox,
                expected_description=expected_description,
                image_type=image_type,
                pdf_page_size=(pdf_page_width, pdf_page_height),
                rendered_page_size=(rendered_page_width, rendered_page_height),
                cropped_image_size=(current_cropped_width, current_cropped_height)
            )
            
            # Prepare message content with rendered PDF page and cropped image
            user_content = [
                MessageContent(
                    type=ContentType.TEXT,
                    text=f"Here is the rendered PDF page image and the cropped image. "
                         f"The crop was taken from page {page_number} (0-based) using bbox {current_bbox} (PDF points). "
                         f"Please verify if the crop is correct and provide corrected coordinates in PDF points if needed."
                ),
                MessageContent(
                    type=ContentType.IMAGE,
                    image_base64=rendered_page_b64
                ),
                MessageContent(
                    type=ContentType.IMAGE,
                    image_base64=cropped_image_b64
                )
            ]
            
            messages = [
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(role=MessageRole.USER, content=user_content)
            ]
            
            # Call LLM
            response = await client.aquery(
                messages=messages,
                temperature=0.0,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            if not response.content or not response.content.strip():
                logger.error(f"Empty response from bbox corrector API")
                break
            
            response_data = json.loads(response.content)
            correction_result = BboxCorrectionOutput(**response_data)
            
            # Track usage
            if response.usage:
                iter_usage = Usage()
                iter_usage.requests = 1
                iter_usage.input_tokens = response.usage.get("prompt_tokens", 0)
                iter_usage.output_tokens = response.usage.get("completion_tokens", 0)
                iter_usage.total_tokens = response.usage.get("total_tokens", 0)
                total_usage.add(iter_usage)
            
            logger.info(f"  Correction result: is_correct={correction_result.is_correct}, confidence={correction_result.confidence}")
            logger.info(f"  Reasoning: {correction_result.reasoning}")
            
            if correction_result.is_correct:
                logger.info(f"  ✓ Bbox verified as correct")
                return current_bbox, True, total_usage, all_image_paths
            
            # Need correction
            if correction_result.corrected_bbox is None:
                logger.warning(f"  LLM says crop is incorrect but provided no corrected bbox")
                break
            
            logger.info(f"  Issue: {correction_result.issue_description}")
            logger.info(f"  Suggested bbox: {correction_result.corrected_bbox}")
            
            # Update bbox and re-extract from rendered page image
            current_bbox = correction_result.corrected_bbox
            
            # Convert PDF points to pixel coordinates
            x1, y1, x2, y2 = current_bbox
            pixel_x1 = int(x1 * scale_x)
            pixel_y1 = int(y1 * scale_y)
            pixel_x2 = int(x2 * scale_x)
            pixel_y2 = int(y2 * scale_y)
            
            # Ensure coordinates are within bounds
            pixel_x1 = max(0, min(pixel_x1, rendered_page_width - 1))
            pixel_y1 = max(0, min(pixel_y1, rendered_page_height - 1))
            pixel_x2 = max(pixel_x1 + 1, min(pixel_x2, rendered_page_width))
            pixel_y2 = max(pixel_y1 + 1, min(pixel_y2, rendered_page_height))
            
            # Crop from rendered page image
            with Image.open(rendered_page_path) as rendered_img:
                cropped_img = rendered_img.crop((pixel_x1, pixel_y1, pixel_x2, pixel_y2))
                
                # Save cropped image
                prefix = f"{image_type}_image_corrected_iter{iteration + 1}"
                new_img_filename = f"{prefix}_1.png"
                new_img_path = output_dir / new_img_filename
                cropped_img.save(str(new_img_path))
                
            all_image_paths.append(str(new_img_path))
            logger.info(f"  Re-extracted image from rendered page with new bbox: {new_img_path}")
            logger.info(f"    PDF bbox: {current_bbox} -> Pixel bbox: [{pixel_x1}, {pixel_y1}, {pixel_x2}, {pixel_y2}]")
            
        except Exception as e:
            logger.error(f"  Error in bbox correction iteration {iteration + 1}: {e}")
            break
    
    # Reached max iterations or error
    logger.warning(f"  ⚠ Bbox correction completed with {len(all_image_paths)} attempts")
    logger.warning(f"  Final bbox: {current_bbox}")
    
    return current_bbox, False, total_usage, all_image_paths

