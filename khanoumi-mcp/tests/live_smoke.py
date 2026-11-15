import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def main():
    results = server.listing(query="ریمل", limit=2)
    assert results["products"], "No results for a common search term"
    assert "ریمل" in results["products"][0]["name"], "Query did not filter products"
    print("Search OK:", [(p["id"], p["name"], p["effective_price"]) for p in results["products"]])
    results = server.listing(cat_id=27, limit=2)
    assert results["products"], "Category returned no products"
    print("Category OK:", results["total"], "products")
    sample = server.product(results["products"][0]["id"])
    print("Product lookup:", sample)


if __name__ == "__main__":
    main()
