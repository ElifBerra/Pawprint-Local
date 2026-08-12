"""Quick check that the embedding model works and similarity behaves sanely.

Run:  python -m scripts.test_embeddings
"""

import numpy as np

from src import embeddings, foundry


def main():
    texts = [
        "Dogs need a rabies vaccination every year.",
        "Cats should be dewormed regularly as kittens.",
        "The capital of France is Paris.",
    ]

    print("Embedding 3 sentences...")
    vectors = embeddings.embed_texts(texts)
    print(f"Shape: {vectors.shape}  dtype: {vectors.dtype}")

    query = "How often does my dog need shots?"
    qvec = embeddings.embed_one(query)

    sims = embeddings.normalize(vectors) @ embeddings.normalize(qvec)

    print(f"\nQuery: {query}\n")
    for text, score in sorted(zip(texts, sims), key=lambda p: -p[1]):
        print(f"  {score:.3f}  {text}")

    print("\nExpected: the rabies sentence scores highest, Paris lowest.")
    foundry.unload_all()


if __name__ == "__main__":
    main()
