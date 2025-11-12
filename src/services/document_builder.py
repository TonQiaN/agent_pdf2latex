"""
Document Builder Service
Handles PDF image extraction and LaTeX document generation
Combines image extraction and LaTeX generation into a unified workflow
"""

import os
import subprocess
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF


class DocumentBuilder:
    """
    Unified document builder that handles both image extraction and LaTeX generation
    Provides end-to-end document building workflow from PDF to compiled LaTeX
    """
    
    def __init__(
        self,
        output_dir: str = "./output",
        images_dir: Optional[str] = None
    ):
        """
        Initialize DocumentBuilder
        
        Args:
            output_dir: Base directory for output files
            images_dir: Directory for extracted images (default: {output_dir}/images)
        """
        self.output_dir = output_dir
        self.images_dir = images_dir or os.path.join(output_dir, "images")
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
    
    # ============= Image Extraction Methods =============
    
    def extract_images_from_pdf(
        self,
        pdf_path: str,
        result: dict,
        scale_factor: float = 2.0,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        根据结果中的图片信息，从 PDF 中提取图片
        
        Args:
            pdf_path: PDF 文件路径
            result: workflow 生成的结果（包含 latex_results）
            scale_factor: 图片缩放比例（用于提高分辨率）
            verbose: 是否打印详细信息
        
        Returns:
            List[Dict]: 提取的图片信息列表
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        # 打开 PDF
        doc = fitz.open(pdf_path)
        
        extracted_images = []
        total_images = 0
        
        if verbose:
            print("=" * 70)
            print("📷 提取图片中...")
            print("=" * 70)
        
        # 遍历每道题的 LaTeX 结果
        for q_idx, latex_result in enumerate(result.get('latex_results', []), 1):
            question_images = latex_result.get('question_images', [])
            
            if not question_images:
                continue
            
            # 提取该题的所有图片
            for img_idx, img_info in enumerate(question_images):
                total_images += 1
                
                page_num = img_info['page_number']
                bbox = img_info['bbox']  # [x0, y0, x1, y1]
                description = img_info.get('description', '')
                
                # 检查页码是否有效
                if page_num < 0 or page_num >= len(doc):
                    if verbose:
                        print(f"⚠️ Q{q_idx} 图片 {img_idx+1}: 页码 {page_num} 超出范围，跳过")
                    continue
                
                # 读取页面
                page = doc[page_num]
                
                # 提取区域的像素图（bbox 格式: x0, y0, x1, y1）
                rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                
                # 设置缩放矩阵（提高分辨率）
                mat = fitz.Matrix(scale_factor, scale_factor)
                
                try:
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    
                    # 生成文件名
                    img_filename = f"q{q_idx}_img{img_idx+1}_p{page_num}.png"
                    img_path = os.path.join(self.images_dir, img_filename)
                    
                    # 保存图片
                    pix.save(img_path)
                    
                    extracted_images.append({
                        'question': q_idx,
                        'image_index': img_idx + 1,
                        'page': page_num,
                        'filename': img_filename,
                        'path': img_path,
                        'bbox': bbox,
                        'description': description,
                        'width': pix.width,
                        'height': pix.height,
                    })
                    
                    if verbose:
                        print(f"✅ Q{q_idx} 图片 {img_idx+1}: {img_filename} (Page {page_num}, {pix.width}x{pix.height})")
                
                except Exception as e:
                    if verbose:
                        print(f"❌ Q{q_idx} 图片 {img_idx+1}: 提取失败 - {e}")
        
        doc.close()
        
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"✅ 提取完成！共 {len(extracted_images)}/{total_images} 张图片")
            print(f"📁 保存位置: {self.images_dir}")
            print("=" * 70)
        
        return extracted_images
    
    def extract_single_image(
        self,
        pdf_path: str,
        page_num: int,
        bbox: List[float],
        output_filename: str,
        scale_factor: float = 2.0
    ) -> Optional[str]:
        """
        从 PDF 中提取单张图片
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（0-based）
            bbox: 边界框 [x0, y0, x1, y1]
            output_filename: 输出文件名
            scale_factor: 缩放比例
        
        Returns:
            str: 图片保存路径，失败返回 None
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
            
            if page_num < 0 or page_num >= len(doc):
                print(f"⚠️ 页码 {page_num} 超出范围 (0-{len(doc)-1})")
                doc.close()
                return None
            
            page = doc[page_num]
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
            mat = fitz.Matrix(scale_factor, scale_factor)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            
            output_path = os.path.join(self.images_dir, output_filename)
            pix.save(output_path)
            
            doc.close()
            
            print(f"✅ 图片已保存: {output_path}")
            return output_path
        
        except Exception as e:
            print(f"❌ 提取图片失败: {e}")
            return None
    
    def get_page_dimensions(self, pdf_path: str, page_num: int = 0) -> Optional[Dict[str, float]]:
        """
        获取 PDF 页面尺寸
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（0-based）
        
        Returns:
            dict: 包含 width 和 height 的字典
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
            
            if page_num < 0 or page_num >= len(doc):
                print(f"⚠️ 页码 {page_num} 超出范围")
                doc.close()
                return None
            
            page = doc[page_num]
            rect = page.rect
            
            dimensions = {
                'width': rect.width,
                'height': rect.height,
                'x0': rect.x0,
                'y0': rect.y0,
                'x1': rect.x1,
                'y1': rect.y1,
            }
            
            doc.close()
            return dimensions
        
        except Exception as e:
            print(f"❌ 获取页面尺寸失败: {e}")
            return None
    
    def render_page_as_image(
        self,
        pdf_path: str,
        page_num: int,
        output_filename: str,
        scale_factor: float = 2.0
    ) -> Optional[str]:
        """
        将整个 PDF 页面渲染为图片
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（0-based）
            output_filename: 输出文件名
            scale_factor: 缩放比例
        
        Returns:
            str: 图片保存路径，失败返回 None
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
            
            if page_num < 0 or page_num >= len(doc):
                print(f"⚠️ 页码 {page_num} 超出范围")
                doc.close()
                return None
            
            page = doc[page_num]
            mat = fitz.Matrix(scale_factor, scale_factor)
            pix = page.get_pixmap(matrix=mat)
            
            output_path = os.path.join(self.images_dir, output_filename)
            pix.save(output_path)
            
            doc.close()
            
            print(f"✅ 页面已渲染: {output_path} ({pix.width}x{pix.height})")
            return output_path
        
        except Exception as e:
            print(f"❌ 渲染页面失败: {e}")
            return None
    
    # ============= LaTeX Generation Methods =============
    
    def generate_latex_preview(
        self,
        result: dict,
        output_filename: Optional[str] = None,
        include_answers: bool = False,
        document_class: str = "article",
        custom_preamble: Optional[str] = None
    ) -> str:
        """
        生成 LaTeX 预览文件
        
        Args:
            result: workflow 生成的结果
            output_filename: 输出文件名（None 则自动生成）
            include_answers: 是否包含答案
            document_class: LaTeX 文档类型
            custom_preamble: 自定义导言区
        
        Returns:
            str: 生成的 LaTeX 文件路径
        """
        # 生成文件名
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            exam_id = result.get('exam_id', 'exam')
            output_filename = f"{exam_id}_{timestamp}.tex"
        
        latex_file = os.path.join(self.output_dir, output_filename)
        
        with open(latex_file, 'w', encoding='utf-8') as f:
            # 文档类和导言区
            f.write(f"\\documentclass{{{document_class}}}\n")
            f.write("\\usepackage{amsmath}\n")
            f.write("\\usepackage{amssymb}\n")
            f.write("\\usepackage{graphicx}\n")
            f.write("\\usepackage{enumitem}\n")
            f.write("\\usepackage[margin=1in]{geometry}\n")
            
            if custom_preamble:
                f.write("\n% Custom preamble\n")
                f.write(custom_preamble)
                f.write("\n")
            
            f.write("\n\\begin{document}\n\n")
            
            # 标题
            exam_id = result.get('exam_id', 'Exam')
            exam_type = result.get('exam_type', 'Unknown')
            total_questions = result.get('total_questions', 0)
            
            f.write(f"\\section*{{{exam_id}}}\n")
            f.write(f"\\textbf{{Type:}} {exam_type} \\quad ")
            f.write(f"\\textbf{{Total Questions:}} {total_questions}\n\n")
            f.write("\\hrule\n\\vspace{1em}\n\n")
            
            # 题目列表
            f.write("\\begin{enumerate}\n\n")
            
            for i, latex_result in enumerate(result.get('latex_results', []), 1):
                # 题目
                question_latex = latex_result.get('question_latex', '')
                f.write(f"% Question {i}\n")
                f.write(question_latex)
                f.write("\n\n")
                
                # 答案（如果启用）
                if include_answers and latex_result.get('answer_latex'):
                    answer_latex = latex_result.get('answer_latex', '')
                    marks = latex_result.get('marks')
                    
                    f.write("\\vspace{0.5em}\n")
                    f.write("\\textbf{Solution:")
                    if marks:
                        f.write(f" [{marks} marks]")
                    f.write("}\n\n")
                    f.write(answer_latex)
                    f.write("\n\n")
                
                # 分隔线
                if i < len(result.get('latex_results', [])):
                    f.write("\\vspace{1em}\n")
            
            f.write("\\end{enumerate}\n\n")
            f.write("\\end{document}\n")
        
        print(f"✅ LaTeX 预览已保存到: {latex_file}")
        print(f"\n💡 编译命令:")
        print(f"   cd {self.output_dir} && pdflatex {os.path.basename(latex_file)}")
        
        return latex_file
    
    def update_latex_with_images(
        self,
        result: dict,
        images_info: List[Dict[str, Any]],
        output_filename: Optional[str] = None,
        images_relative_path: str = "images",
        include_answers: bool = False
    ) -> str:
        """
        更新 LaTeX 文件，将 PLACEHOLDER 替换为实际的图片路径
        
        Args:
            result: workflow 生成的结果
            images_info: 图片信息列表（来自 extract_images_from_pdf）
            output_filename: 输出文件名
            images_relative_path: 图片相对路径（相对于 LaTeX 文件）
            include_answers: 是否包含答案
        
        Returns:
            str: 生成的 LaTeX 文件路径
        """
        # 生成文件名
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            exam_id = result.get('exam_id', 'exam')
            output_filename = f"{exam_id}_with_images_{timestamp}.tex"
        
        latex_file = os.path.join(self.output_dir, output_filename)
        
        with open(latex_file, 'w', encoding='utf-8') as f:
            # 文档类和导言区
            f.write("\\documentclass{article}\n")
            f.write("\\usepackage{amsmath}\n")
            f.write("\\usepackage{amssymb}\n")
            f.write("\\usepackage{graphicx}\n")
            f.write("\\usepackage{enumitem}\n")
            f.write("\\usepackage[margin=1in]{geometry}\n")
            f.write("\n\\begin{document}\n\n")
            
            # 标题
            exam_id = result.get('exam_id', 'Exam')
            exam_type = result.get('exam_type', 'Unknown')
            total_questions = result.get('total_questions', 0)
            
            f.write(f"\\section*{{{exam_id}}}\n")
            f.write(f"\\textbf{{Type:}} {exam_type} \\quad ")
            f.write(f"\\textbf{{Total Questions:}} {total_questions}\n\n")
            f.write("\\hrule\n\\vspace{1em}\n\n")
            
            # 题目列表
            f.write("\\begin{enumerate}\n\n")
            
            for q_idx, latex_result in enumerate(result.get('latex_results', []), 1):
                # 获取题目 LaTeX
                question_latex = latex_result.get('question_latex', '')
                
                # 替换 PLACEHOLDER 为实际图片路径
                if latex_result.get('question_images'):
                    for img_idx, img_info in enumerate(latex_result['question_images']):
                        placeholder = f"idPLACEHOLDER{q_idx}_{img_idx+1}"
                        
                        # 找到对应的实际图片文件名
                        actual_img = next(
                            (img for img in images_info 
                             if img['question'] == q_idx and img['image_index'] == img_idx + 1),
                            None
                        )
                        
                        if actual_img:
                            actual_filename = f"{images_relative_path}/{actual_img['filename']}"
                            question_latex = question_latex.replace(
                                f"Figures/{placeholder}.png",
                                actual_filename
                            )
                        else:
                            # 如果找不到实际图片，保持占位符或给出警告
                            print(f"⚠️ Q{q_idx} 图片 {img_idx+1}: 未找到对应的提取图片")
                
                f.write(f"% Question {q_idx}\n")
                f.write(question_latex)
                f.write("\n\n")
                
                # 答案（如果启用）
                if include_answers and latex_result.get('answer_latex'):
                    answer_latex = latex_result.get('answer_latex', '')
                    marks = latex_result.get('marks')
                    
                    # 替换答案中的图片占位符
                    if latex_result.get('answer_images'):
                        for img_idx, img_info in enumerate(latex_result['answer_images']):
                            placeholder = f"idPLACEHOLDER{q_idx}_sol_{img_idx+1}"
                            
                            # 找到对应的实际图片（答案图片可能需要单独提取）
                            actual_filename = f"{images_relative_path}/q{q_idx}_ans_img{img_idx+1}_p{img_info['page_number']}.png"
                            answer_latex = answer_latex.replace(
                                f"Figures/{placeholder}.png",
                                actual_filename
                            )
                    
                    f.write("\\vspace{0.5em}\n")
                    f.write("\\textbf{Solution:")
                    if marks:
                        f.write(f" [{marks} marks]")
                    f.write("}\n\n")
                    f.write(answer_latex)
                    f.write("\n\n")
                
                # 分隔线
                if q_idx < len(result.get('latex_results', [])):
                    f.write("\\vspace{1em}\n")
            
            f.write("\\end{enumerate}\n\n")
            f.write("\\end{document}\n")
        
        print(f"✅ 更新的 LaTeX 已保存到: {latex_file}")
        print(f"\n💡 编译命令:")
        print(f"   cd {self.output_dir} && pdflatex {os.path.basename(latex_file)}")
        
        return latex_file
    
    def generate_question_only(
        self,
        result: dict,
        output_filename: Optional[str] = None
    ) -> str:
        """
        生成只包含题目的 LaTeX 文件（用于学生作答）
        
        Args:
            result: workflow 生成的结果
            output_filename: 输出文件名
        
        Returns:
            str: 生成的 LaTeX 文件路径
        """
        return self.generate_latex_preview(
            result=result,
            output_filename=output_filename,
            include_answers=False
        )
    
    def generate_with_solutions(
        self,
        result: dict,
        output_filename: Optional[str] = None
    ) -> str:
        """
        生成包含答案的 LaTeX 文件（用于教师参考）
        
        Args:
            result: workflow 生成的结果
            output_filename: 输出文件名
        
        Returns:
            str: 生成的 LaTeX 文件路径
        """
        return self.generate_latex_preview(
            result=result,
            output_filename=output_filename,
            include_answers=True
        )
    
    def compile_latex(self, latex_file: str, compiler: str = "pdflatex") -> bool:
        """
        编译 LaTeX 文件为 PDF
        
        Args:
            latex_file: LaTeX 文件路径
            compiler: LaTeX 编译器（pdflatex, xelatex, lualatex）
        
        Returns:
            bool: 编译是否成功
        """
        if not os.path.exists(latex_file):
            print(f"❌ LaTeX 文件不存在: {latex_file}")
            return False
        
        # 切换到 LaTeX 文件所在目录
        latex_dir = os.path.dirname(os.path.abspath(latex_file))
        latex_filename = os.path.basename(latex_file)
        
        try:
            print(f"🔨 正在编译: {latex_file}")
            
            # 运行两次以确保交叉引用正确
            for i in range(2):
                result = subprocess.run(
                    [compiler, "-interaction=nonstopmode", latex_filename],
                    cwd=latex_dir,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"❌ 编译失败 (第 {i+1} 次):")
                    print(result.stdout)
                    return False
            
            pdf_file = latex_file.replace('.tex', '.pdf')
            print(f"✅ 编译成功: {pdf_file}")
            return True
        
        except FileNotFoundError:
            print(f"❌ 找不到编译器: {compiler}")
            print("   请确保已安装 TeX 发行版 (TeX Live, MiKTeX, MacTeX)")
            return False
        
        except Exception as e:
            print(f"❌ 编译出错: {e}")
            return False
    
    # ============= Unified Workflow Methods =============
    
    def build_document(
        self,
        pdf_path: str,
        result: dict,
        output_filename: Optional[str] = None,
        include_answers: bool = False,
        auto_compile: bool = False,
        scale_factor: float = 2.0,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        完整的文档构建流程：提取图片 → 生成 LaTeX → (可选)编译 PDF
        
        Args:
            pdf_path: 原始 PDF 路径
            result: workflow 生成的结果
            output_filename: LaTeX 输出文件名
            include_answers: 是否包含答案
            auto_compile: 是否自动编译为 PDF
            scale_factor: 图片缩放比例
            verbose: 是否打印详细信息
        
        Returns:
            dict: 包含生成文件路径的字典
        """
        output_info = {}
        
        # Step 1: 提取图片
        if verbose:
            print("\n" + "=" * 70)
            print("🚀 Step 1: 提取图片")
            print("=" * 70)
        
        images_info = self.extract_images_from_pdf(
            pdf_path=pdf_path,
            result=result,
            scale_factor=scale_factor,
            verbose=verbose
        )
        output_info['images'] = images_info
        output_info['images_dir'] = self.images_dir
        
        # Step 2: 生成 LaTeX
        if verbose:
            print("\n" + "=" * 70)
            print("🚀 Step 2: 生成 LaTeX 文档")
            print("=" * 70)
        
        if images_info:
            latex_file = self.update_latex_with_images(
                result=result,
                images_info=images_info,
                output_filename=output_filename,
                include_answers=include_answers
            )
        else:
            latex_file = self.generate_latex_preview(
                result=result,
                output_filename=output_filename,
                include_answers=include_answers
            )
        
        output_info['latex_file'] = latex_file
        
        # Step 3: (可选) 编译 PDF
        if auto_compile:
            if verbose:
                print("\n" + "=" * 70)
                print("🚀 Step 3: 编译 LaTeX 为 PDF")
                print("=" * 70)
            
            success = self.compile_latex(latex_file)
            output_info['pdf_compiled'] = success
            
            if success:
                output_info['pdf_file'] = latex_file.replace('.tex', '.pdf')
        
        if verbose:
            print("\n" + "=" * 70)
            print("✅ 文档构建完成！")
            print("=" * 70)
            print(f"📁 输出目录: {self.output_dir}")
            print(f"📷 图片数量: {len(images_info)}")
            print(f"📄 LaTeX 文件: {latex_file}")
            if output_info.get('pdf_compiled'):
                print(f"📕 PDF 文件: {output_info['pdf_file']}")
        
        return output_info


# ============= 便捷函数 =============

_default_builder: Optional[DocumentBuilder] = None


def _get_default_builder() -> DocumentBuilder:
    """Get or create default DocumentBuilder instance"""
    global _default_builder
    if _default_builder is None:
        _default_builder = DocumentBuilder()
    return _default_builder


def extract_images_from_pdf(
    pdf_path: str,
    result: dict,
    output_dir: str = "./output/images",
    scale_factor: float = 2.0,
    verbose: bool = True
) -> List[Dict[str, Any]]:
    """从 PDF 提取图片（便捷函数）"""
    builder = DocumentBuilder(images_dir=output_dir)
    return builder.extract_images_from_pdf(pdf_path, result, scale_factor, verbose)


def generate_latex_preview(
    result: dict,
    output_dir: str = "./output",
    output_filename: Optional[str] = None,
    include_answers: bool = False
) -> str:
    """生成 LaTeX 预览文件（便捷函数）"""
    builder = DocumentBuilder(output_dir=output_dir)
    return builder.generate_latex_preview(result, output_filename, include_answers)


def update_latex_with_images(
    result: dict,
    images_info: List[Dict[str, Any]],
    output_dir: str = "./output",
    output_filename: Optional[str] = None,
    include_answers: bool = False
) -> str:
    """更新 LaTeX 文件图片路径（便捷函数）"""
    builder = DocumentBuilder(output_dir=output_dir)
    return builder.update_latex_with_images(
        result, images_info, output_filename, include_answers=include_answers
    )


def build_document(
    pdf_path: str,
    result: dict,
    output_dir: str = "./output",
    output_filename: Optional[str] = None,
    include_answers: bool = False,
    auto_compile: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """完整文档构建流程（便捷函数）"""
    builder = DocumentBuilder(output_dir=output_dir)
    return builder.build_document(
        pdf_path, result, output_filename, include_answers, auto_compile, verbose=verbose
    )


def compile_latex(latex_file: str, compiler: str = "pdflatex") -> bool:
    """编译 LaTeX 文件（便捷函数）"""
    return _get_default_builder().compile_latex(latex_file, compiler)

