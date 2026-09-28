import sqlite3
import numpy as np
import faiss

from sentence_transformers import SentenceTransformer


DB_PATH = "transit_ai.db"


# ============================================================
# EMBEDDING MODEL
# ============================================================

print("Loading embedding model...")

embedding_model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

print("Embedding model loaded!")


# ============================================================
# GET DATABASE CONNECTION
# ============================================================

def get_connection():
    return sqlite3.connect(DB_PATH)


# ============================================================
# BUILD KNOWLEDGE DOCUMENTS
# ============================================================

def build_documents():

    conn = get_connection()
    cursor = conn.cursor()

    documents = []

    # ========================================================
    # ROUTES
    # ========================================================

    cursor.execute("""
        SELECT
            route_id,
            route_type,
            system,
            origin,
            destination,
            stop_count,
            fare_rs,
            currency,
            operating_hours,
            headway_note,
            source_url
        FROM routes
    """)

    routes = cursor.fetchall()

    for route in routes:

        (
            route_id,
            route_type,
            system,
            origin,
            destination,
            stop_count,
            fare_rs,
            currency,
            operating_hours,
            headway,
            source
        ) = route

        # Get stops for this route
        cursor.execute("""
            SELECT stop_name
            FROM route_stops
            WHERE route_id = ?
            ORDER BY stop_sequence
        """, (route_id,))

        stop_rows = cursor.fetchall()

        stop_names = [
            row[0]
            for row in stop_rows
            if row[0]
        ]

        stops_text = " → ".join(stop_names)

        document = f"""
Lahore Public Transport Route

Route ID: {route_id}

Transport Type:
{route_type}

System:
{system}

Origin:
{origin}

Destination:
{destination}

Number of Stops:
{stop_count}

Fare:
Rs. {fare_rs} {currency}

Operating Hours:
{operating_hours}

Headway:
{headway}

Stops in order:
{stops_text}

Source:
{source}
"""

        documents.append({
            "text": document.strip(),
            "type": "route",
            "route_id": route_id,
            "source": source
        })


    # ========================================================
    # FARES
    # ========================================================

    cursor.execute("""
        SELECT
            service_type,
            fare_rule,
            fare_rs,
            currency,
            source_url
        FROM fares
    """)

    fares = cursor.fetchall()

    for fare in fares:

        (
            service_type,
            fare_rule,
            fare_rs,
            currency,
            source
        ) = fare

        document = f"""
Lahore Public Transport Fare Information

Service:
{service_type}

Fare Rule:
{fare_rule}

Fare:
Rs. {fare_rs} {currency}

Source:
{source}
"""

        documents.append({
            "text": document.strip(),
            "type": "fare",
            "source": source
        })


    # ========================================================
    # SERVICES
    # ========================================================

    cursor.execute("""
        SELECT
            service,
            origin,
            destination,
            operating_hours,
            headway,
            source_url
        FROM services
    """)

    services = cursor.fetchall()

    for service in services:

        (
            service_name,
            origin,
            destination,
            operating_hours,
            headway,
            source
        ) = service

        document = f"""
Lahore Public Transport Service Information

Service:
{service_name}

Origin:
{origin}

Destination:
{destination}

Operating Hours:
{operating_hours}

Headway:
{headway}

Source:
{source}
"""

        documents.append({
            "text": document.strip(),
            "type": "service",
            "source": source
        })


    # ========================================================
    # FAQ
    # ========================================================

    cursor.execute("""
        SELECT
            question,
            answer,
            source_url
        FROM transit_faq
    """)

    faqs = cursor.fetchall()

    for faq in faqs:

        question, answer, source = faq

        document = f"""
Lahore Public Transport FAQ

Question:
{question}

Answer:
{answer}

Source:
{source}
"""

        documents.append({
            "text": document.strip(),
            "type": "faq",
            "source": source
        })


    conn.close()

    return documents


# ============================================================
# CREATE DOCUMENTS
# ============================================================

documents = build_documents()

print(f"Knowledge documents created: {len(documents)}")


# ============================================================
# CREATE EMBEDDINGS
# ============================================================

texts = [
    document["text"]
    for document in documents
]

embeddings = embedding_model.encode(
    texts,
    batch_size=32,
    show_progress_bar=True,
    convert_to_numpy=True,
    normalize_embeddings=True
)

print("Embeddings created!")


# ============================================================
# CREATE FAISS INDEX
# ============================================================

dimension = embeddings.shape[1]

index = faiss.IndexFlatIP(dimension)

index.add(
    embeddings.astype("float32")
)

print("FAISS index created!")
print("Indexed documents:", index.ntotal)


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def search_transit_knowledge(query, top_k=5):

    query_embedding = embedding_model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype("float32")

    scores, indices = index.search(
        query_embedding,
        top_k
    )

    results = []

    for score, idx in zip(
        scores[0],
        indices[0]
    ):

        if idx == -1:
            continue

        result = documents[idx].copy()

        result["score"] = float(score)

        results.append(result)

    return results