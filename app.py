import streamlit as st
import re
from neo4j import GraphDatabase

# -------------------
# CONFIG
# -------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"
NEO4J_DB = "music-recommendation"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# -------------------
# TEXT CLEANING (GLOBAL FIX)
# -------------------
def normalize_text(text: str, max_len=None):
    if not text:
        return ""

    text = text.replace('"', '')
    text = re.sub(r"[（(].*?[）)]", "", text)
    text = re.sub(r"[^a-zA-Z0-9À-ÿ\s\-&']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if max_len and len(text) > max_len:
        return text[:max_len] + "…"

    return text


def clean_list(values):
    if not values:
        return []
    return sorted({
        normalize_text(v) for v in values
        if normalize_text(v)
    })

# -------------------
# DATABASE FUNCTIONS
# -------------------
@st.cache_data(show_spinner=False)
def get_tracks():
    query = """
    MATCH (t:Track)
    WHERE t.track_name IS NOT NULL
    RETURN DISTINCT t.track_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as session:
        return [r["name"] for r in session.run(query)]


def get_track_info(track_name):
    query = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    RETURN
        t.track_name AS track,
        coalesce(t.popularity, 0) AS popularity,
        coalesce(t.energy, 0.0) AS energy,
        coalesce(t.valence, 0.0) AS valence,
        collect(DISTINCT a.artist_name) AS artists,
        collect(DISTINCT g.genre_name) AS genres
    """
    with driver.session(database=NEO4J_DB) as session:
        return session.run(query, name=track_name).single()


def get_recommendations(track_name):
    query = """
    MATCH (t:Track {track_name:$name})-[:SIMILAR_TO]->(rec:Track)
    OPTIONAL MATCH (rec)-[:PERFORMED_BY]->(a:Artist)
    RETURN
        rec.track_name AS track,
        collect(DISTINCT a.artist_name) AS artists,
        coalesce(rec.popularity, 0) AS popularity
    ORDER BY popularity DESC
    LIMIT 5
    """
    with driver.session(database=NEO4J_DB) as session:
        return list(session.run(query, name=track_name))

# -------------------
# PAGE SETUP
# -------------------
st.set_page_config(page_title="Music Recommendation System", layout="wide")

st.markdown("""
<style>
.card {
    background: linear-gradient(135deg,#020617,#020617);
    padding: 18px;
    border-radius: 16px;
    box-shadow: 0 10px 24px rgba(0,0,0,0.4);
    margin-bottom: 18px;
}
.sub {
    color: #9ca3af;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# -------------------
# UI
# -------------------
st.title("🎵 Music Recommendation System")
st.caption("Neo4j • Clean Data • Flashcard UX")

tracks = get_tracks()

search = st.text_input("🔍 Rechercher une chanson")

filtered = [
    t for t in tracks
    if search.lower() in t.lower()
][:50]

selected_track = None
if filtered:
    selected_track = st.selectbox(
        "Résultats",
        filtered,
        format_func=lambda x: normalize_text(x, 60),
        label_visibility="collapsed"
    )

# -------------------
# DISPLAY
# -------------------
if selected_track:
    info = get_track_info(selected_track)

    if info:
        st.markdown("## 🎶 Lecture en cours")

        st.markdown(f"""
        <div class="card">
            <h2>{normalize_text(info['track'], 80)}</h2>
            <p class="sub">👤 {", ".join(clean_list(info["artists"])) or "—"}</p>
            <p class="sub">🎼 {", ".join(clean_list(info["genres"])) or "—"}</p>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("🔥 Popularité", int(info["popularity"]))
        c2.metric("⚡ Énergie", round(float(info["energy"]), 2))
        c3.metric("😊 Valence", round(float(info["valence"]), 2))

        st.markdown("## 🔁 Recommandations similaires")

        recs = get_recommendations(selected_track)

        if recs:
            cols = st.columns(len(recs))
            for col, r in zip(cols, recs):
                with col:
                    st.markdown(f"""
                    <div class="card">
                        <strong>{normalize_text(r['track'], 40)}</strong>
                        <p class="sub">👤 {", ".join(clean_list(r["artists"])) or "—"}</p>
                        <p class="sub">🔥 Popularité : {r['popularity']}</p>
                    </div>
                    """, unsafe_allow_html=True)
