import io
import os
import sys
import re
from dataclasses import asdict

from flask import Flask, request, jsonify, render_template_string

# 确保可以从项目根目录导入 app.py
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import (  # noqa: E402
    extract_text_from_pdf,
    extract_basic_info,
    extract_job_info,
    extract_background_info,
)


app = Flask(__name__)


INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>模块二：关键信息提取</title>
</head>
<body>
  <h2>模块二：关键信息提取 Demo</h2>
  <p>上传 PDF 简历，抽取姓名、电话、邮箱、地址、求职意向、期望薪资、工作年限、学历等关键信息。</p>
  <form action="/extract_html" method="post" enctype="multipart/form-data">
    <div>
      <label>选择 PDF 简历文件：</label>
      <input type="file" name="file" accept="application/pdf" required />
    </div>
    <button type="submit">上传并抽取信息</button>
  </form>
  {% if info %}
    <h3>抽取结果：</h3>
    <pre style="white-space: pre-wrap; border: 1px solid #ccc; padding: 8px;">{{ info }}</pre>
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML, info="")


@app.route("/extract", methods=["POST"])
def extract():
    """上传 PDF，仅做关键信息结构化提取，不做匹配评分。"""
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 file"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 简历文件"}), 400

    try:
        text = extract_text_from_pdf(io.BytesIO(file.read()))
    except Exception as e:
        return jsonify({"error": f"PDF 解析失败: {e}"}), 500

    basic_info = extract_basic_info(text)
    job_info = extract_job_info(text)
    background_info = extract_background_info(text)

    return jsonify(
        {
            "raw_text": text,
            "basic_info": asdict(basic_info),
            "job_info": asdict(job_info),
            "background_info": asdict(background_info),
        }
    )


@app.route("/extract_html", methods=["POST"])
def extract_html():
    """浏览器直接使用的关键信息提取展示页面。"""
    if "file" not in request.files:
        return render_template_string(INDEX_HTML, info="未选择文件。")

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return render_template_string(INDEX_HTML, info="仅支持 PDF 简历文件。")

    text = extract_text_from_pdf(io.BytesIO(file.read()))
    basic_info = extract_basic_info(text)
    job_info = extract_job_info(text)
    background_info = extract_background_info(text)

    # 地址兜底：在原始文本中额外再扫一遍“地址/籍贯/户籍”等关键词，避免上游规则漏掉（支持“地 址/籍 贯”）
    addr_fallback = None
    for line in text.splitlines():
        norm = re.sub(r"\s+", "", line)
        if any(k in norm for k in ["地址", "住址", "现居", "现居地", "居住地", "籍贯", "户籍", "户口所在地"]):
            m_addr = re.search(
                r"(?:地\s*址|地址|住址|现居地|现居|所在城市|居住地|家庭住址|籍\s*贯|户籍|户口所在地)\s*[:：]?\s*([^\s，,。;；]+)",
                line,
            )
            addr_fallback = (m_addr.group(1).strip() if m_addr else line.strip())
            break

    # 只展示题目要求的 8 个核心字段
    # 地址优先使用 BasicInfo 中的真实地址，其次使用籍贯/户籍，再次使用 fallback 行
    address_value = (
        basic_info.address
        or getattr(basic_info, "native_place", None)
        or addr_fallback
        or "未识别/未提供"
    )

    lines = [
        "【关键信息提取结果】",
        f"姓名：{basic_info.name or '未识别'}",
        f"电话：{basic_info.phone or '未识别'}",
        f"邮箱：{basic_info.email or '未识别'}",
        f"地址：{address_value}",
        f"求职意向：{job_info.intention or '未识别'}",
        f"期望薪资：{job_info.expected_salary or '未识别'}",
        f"工作年限：{background_info.years_of_experience or '未识别'}",
        f"学历：{getattr(background_info, 'highest_degree', None) or '未识别'}",
        f"学校：{getattr(background_info, 'school', None) or '未识别'}",
        f"专业：{getattr(background_info, 'major', None) or '未识别'}",
    ]

    info = "\n".join(lines)

    return render_template_string(INDEX_HTML, info=info)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5102, debug=True)

