"""研究工具本地回归：使用合成资料，不联网、不保存真实联系人。"""

import copy
import importlib.util
import unittest
import tempfile
import json
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts/research/lead_research.py"
SPEC = importlib.util.spec_from_file_location("lead_research", MODULE)
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


def fixture():
    """返回最小合成来源/实体/价格样本；不包含任何真实业务联系方式。"""
    return {"as_of": "2026-09-30", "sources": [{"id": "S1", "url": "https://example.com/"}],
            "entities": [{"id": "C1"}],
            "facts": [{"entity_id": "C1", "field": "name", "value": "示例商户",
                       "evidence": [{"source_id": "S1", "quote": "示例商户"}]}],
            "products": [{"id": "P1", "source_id": "S1", "quotes": ["价格199元"],
                          "price": 199, "price_kind": "公开零售价", "price_quote": "价格199元"}]}


class ResearchTests(unittest.TestCase):
    """验证缺失数据、来源引用、日期与价格的严格边界。"""

    def test_valid_sample(self):
        self.assertEqual(research.validate(fixture())["entities"], 1)

    def test_unknown_not_zero(self):
        sample = fixture()
        sample["facts"].append({"entity_id": "C1", "field": "revenue", "value": None,
                                "missing_reason": "未找到本主体年度数据"})
        self.assertNotIn("revenue", research.validate(sample)["known_fields"])

    def test_unsourced_rejected(self):
        sample = fixture()
        sample["facts"][0]["evidence"] = []
        with self.assertRaisesRegex(ValueError, "Unsourced"):
            research.validate(sample)

    def test_duplicate_rejected(self):
        sample = fixture()
        sample["facts"].append(copy.deepcopy(sample["facts"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate fact"):
            research.validate(sample)

    def test_future_date_rejected(self):
        sample = fixture()
        sample["sources"][0]["published_on"] = "2026-10-01"
        with self.assertRaisesRegex(ValueError, "Future"):
            research.validate(sample)

    def test_group_metric_requires_scope(self):
        sample = fixture()
        sample["facts"].append({"entity_id": "C1", "field": "revenue", "value": 100,
                                "evidence": [{"source_id": "S1", "quote": "100"}]})
        with self.assertRaisesRegex(ValueError, "scope"):
            research.validate(sample)

    def test_price_not_in_quote_rejected(self):
        sample = fixture()
        sample["products"][0]["price"] = 298
        with self.assertRaisesRegex(ValueError, "Price not present"):
            research.validate(sample)

    def test_no_private_urls(self):
        for uri in ["file:///C:/secret", "http://localhost/a", "http://192.168.1.1/", "https://user:pwd@example.com"]:
            self.assertFalse(research.public_url(uri))

    def test_port_is_not_bypass(self):
        self.assertTrue(research.public_url("http://example.com:8080/public"))

    def test_changed_business_number_rejected(self):
        sample = fixture()
        sample["facts"] = [{"entity_id": "C1", "field": "phone", "value": "12345678",
                            "evidence": [{"source_id": "S1", "quote": "业务电话87654321"}]}]
        with self.assertRaisesRegex(ValueError, "Business phone"):
            research.validate(sample)

    def test_modified_archive_rejected(self):
        with tempfile.TemporaryDirectory(dir=research.ROOT / ".codex-tmp") as temp:
            directory = Path(temp)
            (directory / "S1.json").write_text('{"text":"改动后的原文"}', encoding="utf-8")
            (directory / "manifest.json").write_text(
                json.dumps({"records": [{"id": "S1", "sha256": "wrong"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                research.validate(fixture(), directory)


if __name__ == "__main__":
    unittest.main()
