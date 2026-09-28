from rag import search_transit_knowledge


queries = [
    "What is the Metrobus fare?",
    "FRT09 ke stops kya hain?",
    "Metrobus kab chalti hai?",
    "Lahore feeder routes"
]


for query in queries:

    print("\n" + "=" * 60)
    print("QUERY:", query)
    print("=" * 60)

    results = search_transit_knowledge(
        query,
        top_k=3
    )

    for result in results:

        print(
            f"\nScore: {result['score']:.4f}"
        )

        print(
            f"Type: {result['type']}"
        )

        print(
            result["text"][:500]
        )