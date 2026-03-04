import io
import os
import sys

from flask import Flask, request, jsonify

# 确保可以从项目根目录导入 app.py
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import (
    extract_text_from_pdf,
    extract_basic_info,
    extract_job_info,
    extract_background_info,
    compute_match_score,
    make_cache_key,
    _CACHE,
)
from dataclasses import asdict


app = Flask(__name__)


@app.route("/analyze_with_cache", methods=["POST"])
def analyze_with_cache():
    """与主程序类似，但演示结果 JSON + 缓存能力。"""
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 file"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 简历文件"}), 400

    job_desc = request.form.get("job_desc", "")

    file_bytes = file.read()
    cache_key = make_cache_key(file_bytes, job_desc)
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        cached["from_cache"] = True
        return jsonify(cached)

    try:
        text = extract_text_from_pdf(io.BytesIO(file_bytes))
    except Exception as e:
        return jsonify({"error": f"PDF 解析失败: {e}"}), 500

    basic_info = extract_basic_info(text)
    job_info = extract_job_info(text)
    background_info = extract_background_info(text)
    match_result = compute_match_score(text, job_desc)

    result = {
        "raw_text": text,
        "basic_info": asdict(basic_info),
        "job_info": asdict(job_info),
        "background_info": asdict(background_info),
        "match": match_result,
        "from_cache": False,
    }

    _CACHE[cache_key] = result

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5104, debug=True)

