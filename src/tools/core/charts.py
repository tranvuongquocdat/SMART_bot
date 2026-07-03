"""render_chart — bot vẽ biểu đồ trong CHAT WEB của boss (user chốt 2026-07-03).

Cơ chế: chart-spec JSON (KHÔNG thực thi code — an toàn + tất định). Tool
validate spec rồi trả về chuỗi ``embed`` (fenced block ```chart```); responder
chèn NGUYÊN VĂN vào câu trả lời; FE web chat parse fence và render bằng bộ
chart của design system. Kênh ngoài web không render được → tool từ chối để
LLM trả lời bằng chữ (tương lai: render PNG gửi ảnh — hạng mục riêng).
"""

from __future__ import annotations

import json

from src.tools.base import ToolResult
from src.tools.registry import tool

CHART_TYPES = ("bar", "rank", "line", "pie")
MAX_POINTS = 30


@tool(
    name="render_chart",
    description=(
        "Vẽ biểu đồ trong chat web của sếp. Lấy SỐ LIỆU THẬT từ tool khác "
        "(workload_summary, search_knowledge...) trước, rồi gọi tool này. "
        "type: bar (so sánh), rank (xếp hạng ngang, cần sub/display rõ), "
        "line (xu hướng), pie (tỷ trọng). Kết quả trả về field `embed` — "
        "chèn NGUYÊN VĂN chuỗi đó vào câu trả lời tại vị trí muốn hiện biểu đồ."
    ),
    parameters={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": list(CHART_TYPES)},
            "title": {"type": "string", "description": "Tiêu đề ngắn của biểu đồ"},
            "labels": {
                "type": "array", "items": {"type": "string"},
                "description": "Nhãn từng điểm/cột/lát (vd tên người, tên nhóm, mốc thời gian)",
            },
            "series": {
                "type": "array",
                "description": "Các dãy số. bar/pie/rank: 1 dãy; line: 1-3 dãy.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "data": {"type": "array", "items": {"type": "number"}},
                    },
                    "required": ["data"],
                },
            },
        },
        "required": ["type", "labels", "series"],
    },
    available_to={"dm_responder"},
    parallel_safe=True,
)
async def render_chart(
    ctx, type: str, labels: list, series: list, title: str | None = None
) -> ToolResult:
    if getattr(ctx, "provider", None) != "web":
        return ToolResult(
            content=None,
            error="Kênh chat này không hiển thị được biểu đồ — hãy trả lời bằng chữ "
                  "(bảng/danh sách).",
        )
    if type not in CHART_TYPES:
        return ToolResult(content=None, error=f"type phải là một trong {CHART_TYPES}")
    labels = [str(x) for x in labels][:MAX_POINTS]
    if not labels:
        return ToolResult(content=None, error="labels rỗng")
    clean_series = []
    for s in series[:3]:
        data = [float(v) for v in (s.get("data") or [])][:MAX_POINTS]
        if len(data) != len(labels):
            return ToolResult(
                content=None,
                error=f"series '{s.get('name', '')}' có {len(data)} điểm nhưng "
                      f"labels có {len(labels)} — phải khớp nhau",
            )
        clean_series.append({"name": str(s.get("name") or ""), "data": data})
    if not clean_series:
        return ToolResult(content=None, error="series rỗng")

    spec = {"type": type, "title": title or "", "labels": labels, "series": clean_series}
    embed = "\n```chart\n" + json.dumps(spec, ensure_ascii=False) + "\n```\n"
    return ToolResult(content={
        "embed": embed,
        "instruction": "Chèn NGUYÊN VĂN chuỗi `embed` vào câu trả lời tại vị trí "
                       "muốn hiện biểu đồ, kèm 1-2 câu nhận xét số liệu.",
    })
