import streamlit as st
import re
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components

# ------------------- CONFIG -------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "rootroot"
NEO4J_DB = "project"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# ------------------- UTILS -------------------
def clean_text(text: str, max_len=50):
    if not text:
        return "—"
    text = re.sub(r"[\n\r\t]+", " ", text)
    text = re.sub(r"[\"'`]", "", text)
    text = re.sub(r"[;]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[:max_len] + "…"

def clean_list(values):
    if not values:
        return []
    return sorted(set(clean_text(v) for v in values if v))

# ------------------- DATABASE FUNCTIONS -------------------
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
        coalesce(t.danceability, 0.0) AS danceability,
        coalesce(t.acousticness, 0.0) AS acousticness,
        coalesce(t.instrumentalness, 0.0) AS instrumentalness,
        coalesce(t.liveness, 0.0) AS liveness,
        coalesce(t.speechiness, 0.0) AS speechiness,
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
        coalesce(rec.popularity, 0) AS popularity,
        coalesce(rec.energy, 0.0) AS energy,
        coalesce(rec.valence, 0.0) AS valence,
        collect(DISTINCT a.artist_name) AS artists
    ORDER BY popularity DESC
    LIMIT 5
    """
    with driver.session(database=NEO4J_DB) as session:
        return list(session.run(query, name=track_name))

# ------------------- GRAPHE INTERACTIF -------------------
def render_interactive_graph(track_name):
    query = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    OPTIONAL MATCH (t)-[:SIMILAR_TO]->(s:Track)
    RETURN
        t.track_name AS track,
        collect(DISTINCT a.artist_name) AS artists,
        collect(DISTINCT g.genre_name) AS genres,
        collect(DISTINCT s.track_name) AS similars
    """
    with driver.session(database=NEO4J_DB) as session:
        r = session.run(query, name=track_name).single()

    if not r:
        st.info("Graphe introuvable.")
        return

    net = Network(height="400px", width="100%", bgcolor="#222222", font_color="white")

    # Track principal
    net.add_node(track_name, label=f"🎵 {track_name}", color="#2563eb", shape="circle")

    # Artists
    for a in r["artists"] or []:
        net.add_node(a, label=f"👤 {a}", color="#16a34a", shape="circle")
        net.add_edge(track_name, a, label="PERFORMED_BY")

    # Genres
    for g in r["genres"] or []:
        net.add_node(g, label=f"🎼 {g}", color="#9333ea", shape="circle")
        net.add_edge(track_name, g, label="IN_GENRE")

    # Similars
    for s in r["similars"] or []:
        net.add_node(s, label=f"🎵 {s}", color="#0ea5e9", shape="circle")
        net.add_edge(track_name, s, label="SIMILAR_TO")

    net.show_buttons(filter_=['physics'])
    net.save_graph("graph.html")
    HtmlFile = open("graph.html", "r", encoding="utf-8")
    components.html(HtmlFile.read(), height=450)

# ------------------- UI STYLE -------------------
st.set_page_config(page_title="Music Recommendation System", layout="wide")
st.markdown("""
<style>
.card { background: linear-gradient(135deg,#111827,#020617); padding: 20px; border-radius: 16px;
       box-shadow: 0 15px 30px rgba(0,0,0,0.4); margin-bottom: 20px; color: white; }
.sub { color: #9ca3af; }
.scroll-container { max-height: 400px; overflow-y: auto; }
</style>
""", unsafe_allow_html=True)

# ------------------- UI -------------------
st.title("🎵 Music Recommendation System")
st.caption("Neo4j • Graphe de similarité • UI moderne")

tracks = get_tracks()

selected_track = st.selectbox(
    "🔍 Rechercher une chanson",
    tracks,
    format_func=lambda x: clean_text(x),
    index=0
)

if selected_track:
    info = get_track_info(selected_track)

    if info:
        # ------------ HEADER CARD ------------
        st.markdown("## 🎶 Now Playing")
        st.markdown(f"""
        <div class="card">
            <h2>{clean_text(info['track'], 80)}</h2>
            <p class="sub">👤 Artistes : {', '.join(clean_list(info['artists']))}</p>
            <p class="sub">🎼 Genres : {', '.join(clean_list(info['genres']))}</p>
        </div>
        """, unsafe_allow_html=True)

        # ------------ METRICS ------------
        st.markdown("### 🎚️ Audio Features")
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("🔥 Popularité", int(info["popularity"]))
        with c2: st.metric("⚡ Énergie", round(float(info["energy"]), 2))
        with c3: st.metric("😊 Valence", round(float(info["valence"]), 2))

        st.markdown("### 🎵 Autres métriques")
        metrics = {
            "💃 Danceability": {"value": info["danceability"], "desc": "Facilité à danser"},
            "🎸 Acousticness": {"value": info["acousticness"], "desc": "Probabilité acoustique"},
            "🎹 Instrumentalness": {"value": info["instrumentalness"], "desc": "Instruments seuls"},
            "🎤 Liveness": {"value": info["liveness"], "desc": "Enregistrement live"},
            "🗣️ Speechiness": {"value": info["speechiness"], "desc": "Présence de paroles"}
        }
        cols = st.columns(5)
        for col, (name, meta) in zip(cols, metrics.items()):
            with col:
                st.markdown(f"**{name}**")
                st.caption(meta["desc"])
                st.progress(min(float(meta["value"]), 1.0))

        # ------------ RECOMMENDATIONS ------------
        st.markdown("## 🔁 Recommandations similaires")
        recs = get_recommendations(selected_track)
        if recs:
            with st.container():
                st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
                cols = st.columns(len(recs))
                for col, r in zip(cols, recs):
                    with col:
                        artists_str = ', '.join(clean_list(r['artists']))
                        st.markdown(f"""
                        <div class="card">
                            <strong>{clean_text(r['track'],35)}</strong><br>
                            👤 {artists_str}<br>
                            🔥 Popularité : {r['popularity']}<br>
                            ⚡ Énergie : {round(float(r['energy']),2)} | 😊 Valence : {round(float(r['valence']),2)}
                        </div>
                        """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Aucune recommandation disponible.")

        # ------------ INTERACTIVE GRAPH ------------
        st.markdown("## 🕸️ Graphe local (mini)")
        render_interactive_graph(selected_track)

    else:
        st.warning("Chanson introuvable dans la base Neo4j.")
