"""Streamlit interface for Pawprint-Local.

Run:  streamlit run src/app.py

This is a thin shell over rag.answer_stream. No retrieval or prompting logic
lives here — whatever the CLI does, this does, so a demo cannot diverge from
what was measured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# streamlit runs this file as a script, so the project root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, db, foundry, rag  # noqa: E402

st.set_page_config(page_title="Pawprint-Local", page_icon="*", layout="centered")


@st.cache_resource(show_spinner="Loading local models...")
def load_models():
    """Load once per session.

    FoundryLocalManager is a process-wide singleton and Streamlit re-runs this
    script on every interaction, so without the cache the second interaction
    would fail.
    """
    foundry.get_chat_client()
    foundry.get_embedding_client()
    return True


@st.cache_data(show_spinner=False)
def corpus_stats():
    return db.stats()


def capture(generator, holder):
    """Adapter for st.write_stream, which wants a plain iterator.

    answer_stream returns the finished Answer through StopIteration, which
    write_stream discards. `yield from` gives it back so the sources and
    latency survive.
    """
    holder["answer"] = yield from generator


def main() -> None:
    st.title("Pawprint-Local")
    st.caption("Offline pet health assistant. Runs entirely on this machine.")

    if not config.DB_PATH.exists() or db.count() == 0:
        st.error("No knowledge base found. Run `python -m src.ingest` first.")
        st.stop()

    stats = corpus_stats()

    with st.sidebar:
        st.subheader("Knowledge base")
        left, right = st.columns(2)
        left.metric("Chunks", stats["chunks"])
        right.metric("Documents", stats["sources"])

        st.subheader("Retrieval")
        top_k = st.slider(
            "Chunks retrieved", 1, 6, config.TOP_K,
            help="More context can help, but every chunk costs generation time.",
        )
        threshold = st.slider(
            "Relevance threshold", 0.0, 1.0, config.SIM_THRESHOLD, 0.01,
            help=(
                "Below this the question is treated as out of scope and the "
                "model is never called. Measured separation: answerable "
                "questions score 0.548-0.785, unanswerable ones 0.165-0.427."
            ),
        )

        st.subheader("Models")
        st.caption(f"Chat: `{config.CHAT_MODEL_ALIAS}`")
        st.caption(f"Embedding: `{config.EMBEDDING_MODEL_ALIAS}`")

        st.divider()
        st.caption(
            "Not veterinary advice. Contact a vet for anything urgent."
        )

    load_models()

    if "history" not in st.session_state:
        st.session_state.history = []

    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            st.write(entry["answer"].text)
            render_footer(entry["answer"])

    question = st.chat_input("Ask about vaccines, symptoms, feeding, parasites...")
    if not question:
        render_examples()
        return

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        holder: dict = {}
        st.write_stream(
            capture(rag.answer_stream(question, k=top_k, threshold=threshold), holder)
        )
        result = holder.get("answer")
        if result is not None:
            render_footer(result)
            st.session_state.history.append({"question": question, "answer": result})


def render_footer(result) -> None:
    """Sources, timing, and the retrieved passages behind the answer."""
    if result.sources:
        st.caption("Sources: " + ", ".join(f"`{s}`" for s in result.sources))
    st.caption(f"{result.latency_s:.1f}s")

    if not result.retrieved:
        return

    label = (
        "Retrieved passages (below threshold — model not called)"
        if result.used_fallback
        else "Retrieved passages"
    )
    with st.expander(label):
        for item in result.retrieved:
            st.markdown(
                f"**{item.chunk.source}** · chunk {item.chunk.chunk_index} · "
                f"score {item.score:.3f}"
            )
            st.text(item.chunk.content)
            st.divider()


def render_examples() -> None:
    st.markdown("#### Try one of these")
    st.markdown(
        "- How many DHPP doses does a puppy need before sixteen weeks?\n"
        "- My cat is straining in the litter box, is that urgent?\n"
        "- Can I use my dog's flea treatment on my cat?\n"
        "- How do I train my puppy to sit? *(not in the documents)*"
    )


if __name__ == "__main__":
    main()
