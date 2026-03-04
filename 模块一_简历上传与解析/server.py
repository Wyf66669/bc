import io
import os
import re
import sys

import pdfplumber
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)


INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>模块一：简历上传与解析</title>
</head>
<body>
  <h2>模块一：简历上传与解析 Demo</h2>
  <form action="/parse_html" method="post" enctype="multipart/form-data">
    <div>
      <label>选择 PDF 简历文件：</label>
      <input type="file" name="file" accept="application/pdf" required />
    </div>
    <button type="submit">上传并解析</button>
  </form>
  {% if text %}
    <h3>解析结果（清洗后文本）：</h3>
    <p>页数：{{ page_count }}，段落数：{{ paragraphs|length }}</p>
    <pre style="white-space: pre-wrap; border: 1px solid #ccc; padding: 8px;">{{ text }}</pre>
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    """提供一个简单页面，方便直接在浏览器测试。"""
    return render_template_string(INDEX_HTML)


def _extract_pdf_text_and_structure(file_stream: io.BytesIO):
    """解析 PDF，返回每页文本 + 清洗后的全文与分段结果。"""
    texts = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            texts.append(page_text)

    full_text = "\n".join(texts)

    # 清洗：去掉重复空白和部分不可见字符
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\u200b|\ufeff", "", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    cleaned = full_text.strip()

    # 合理分段：按空行分段
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]

    return texts, cleaned, paragraphs


@app.route("/parse_html", methods=["POST"])
def parse_html():
    """供浏览器直接使用的中文页面展示版本。"""
    if "file" not in request.files:
        return render_template_string(INDEX_HTML, text="", page_count=0, paragraphs=[])

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return render_template_string(
            INDEX_HTML + "<p style='color:red;'>仅支持 PDF 简历文件。</p>",
            text="",
            page_count=0,
            paragraphs=[],
        )

    pages, cleaned_text, paragraphs = _extract_pdf_text_and_structure(
        io.BytesIO(file.read())
    )

    return render_template_string(
        INDEX_HTML,
        text=cleaned_text,
        page_count=len(pages),
        paragraphs=paragraphs,
    )


@app.route("/parse", methods=["POST"])
def parse_pdf():
    """简历上传与解析模块 API：

    - 接收单个 PDF 文件（file）
    - 解析多页内容，输出每页文本
    - 对提取文本进行清洗和结构化分段
    """
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 file"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 简历文件"}), 400

    try:
        pages, cleaned_text, paragraphs = _extract_pdf_text_and_structure(
            io.BytesIO(file.read())
        )
    except Exception as e:  # pragma: no cover - 运行时错误简单透出
        return jsonify({"error": f"PDF 解析失败: {e}"}), 500

    return jsonify(
        {
            "file_name": file.filename,
            "page_count": len(pages),
            "pages": pages,
            "cleaned_text": cleaned_text,
            "paragraphs": paragraphs,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5101, debug=True)

