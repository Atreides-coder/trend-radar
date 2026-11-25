"""模型结构化输出的 JSON Schema（Codex 的 --output-schema 直接使用）。"""

_DIM = {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]}

FAST_FILTER_DIMENSIONS = [
    "change_signal", "ordinary_people", "story_potential", "trend_potential", "visual_potential",
]

REJECT_REASONS = [
    "none",                  # keep=true 时使用
    "not_a_change",          # 只是一件事，看不出任何变化
    "isolated_event",        # 孤立事件，不像更大趋势的信号
    "low_people_relevance",  # 和普通人没什么关系
    "low_story_potential",   # 没有冲突 / 反差 / 惊讶
    "minor_update",          # 小更新、例行发布
    "pure_technical",        # 纯技术 / 纯开发者内容
    "promotion",             # PR、营销稿、企业自我宣传
    "old_information",       # 旧闻、早已人尽皆知
]

FAST_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    **{d: _DIM for d in FAST_FILTER_DIMENSIONS},
                    "keep": {"type": "boolean"},
                    "reject_reason": {"type": "string", "enum": REJECT_REASONS},
                    "reason": {"type": "string"},
                    "possible_change": {"type": "string"},
                    "ordinary_people_connection": {"type": "string"},
                    "possible_story_angle": {"type": "string"},
                    "possible_bigger_trend": {"type": "string"},
                },
                "required": [
                    "item_id", *FAST_FILTER_DIMENSIONS, "keep", "reject_reason", "reason",
                    "possible_change", "ordinary_people_connection",
                    "possible_story_angle", "possible_bigger_trend",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- Phase 3

RELATIONSHIPS = ["primary", "duplicate_report", "supporting", "official_source", "commentary"]

EVENT_CLUSTERING_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_title": {"type": "string"},
                    "summary": {"type": "string"},
                    "core_change": {"type": "string"},
                    "reason": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_id": {"type": "integer"},
                                "relationship": {"type": "string", "enum": RELATIONSHIPS},
                                "independent": {"type": "boolean"},
                            },
                            "required": ["item_id", "relationship", "independent"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["canonical_title", "summary", "core_change", "reason", "items"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

EVENT_DIMENSIONS = [
    "audience_relevance", "change_magnitude", "story_potential",
    "trend_potential", "evidence_strength", "visual_potential",
]

EVENT_RANKING_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer"},
                    **{d: _DIM for d in EVENT_DIMENSIONS},
                    "rank": {"type": "integer"},
                    "why_it_matters": {"type": "string"},
                    "possible_bigger_trend": {"type": "string"},
                },
                "required": ["event_id", *EVENT_DIMENSIONS, "rank", "why_it_matters", "possible_bigger_trend"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

TREND_LINKING_SCHEMA = {
    "type": "object",
    "properties": {
        "trends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "trend_name": {"type": "string"},
                    "existing_trend_id": {"type": "integer"},   # 0 = 新趋势
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "event_ids": {"type": "array", "items": {"type": "integer"}},
                    "hypothesis": {"type": "string"},
                    "confidence": _DIM,
                },
                "required": ["trend_name", "existing_trend_id", "aliases", "event_ids", "hypothesis", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["trends"],
    "additionalProperties": False,
}
