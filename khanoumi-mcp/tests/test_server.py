import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class ServerTests(unittest.TestCase):
    def test_listing_maps_price_fields_and_encodes_query(self):
        fixture = {"isSuccess": True, "data": {"products": {"totalCount": 1, "items": [{
            "id": "42", "nameFa": "ریمل", "slug": "rimel-42", "basePrice": 200000,
            "effectivePrice": 150000, "discountPrice": 50000, "brand": {"nameFa": "آزمایش"},
            "hasStock": True}]}}}
        with patch.object(server, "fetch", return_value=json.dumps(fixture)) as fetch:
            result = server.listing(query="ریمل", limit=1)
        self.assertIn("query=%D8%B1%DB%8C%D9%85%D9%84", fetch.call_args.args[0])
        self.assertEqual(result["products"][0]["effective_price"], 150000)
        self.assertEqual(result["products"][0]["discount_amount"], 50000)
        self.assertEqual(result["products"][0]["url"], server.BASE + "/products/rimel-42")

    def test_id_is_validated_and_requires_previous_search(self):
        with self.assertRaises(ValueError):
            server.product("../../etc/passwd")
        server.SEEN.clear()
        with self.assertRaisesRegex(ValueError, "search for the product first"):
            server.product("42")

    def test_tool_errors_are_marked(self):
        result = server.dispatch({"method": "tools/call", "params": {"name": "browse_category", "arguments": {"cat_id": -2}}})
        self.assertTrue(result["isError"])

    def test_stdio_protocol(self):
        script = str(Path(server.__file__).resolve())
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        process = subprocess.run([sys.executable, script], input="\n".join(map(json.dumps, messages)) + "\n",
                                 capture_output=True, text=True, check=True)
        replies = [json.loads(x) for x in process.stdout.splitlines()]
        self.assertEqual([x["id"] for x in replies], [1, 2])
        self.assertEqual(len(replies[1]["result"]["tools"]), 4)


if __name__ == "__main__":
    unittest.main()
