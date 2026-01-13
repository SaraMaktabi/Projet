import streamlit as st
import re
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components

# ================= CONFIG =================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "rootroot"
NEO4J_DB = "project"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# ================= UTILS =================
def clean_text(text, max_len=50):
    if not text:
        return "—"
    text = re.sub(r"[\n\r\t]+", " ", str(text))
    text = re.sub(r"[\"'`;]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[:max_len] + "…"

def clean_list(values):
    return sorted(set(clean_text(v) for v in values if v))

# ================= DATABASE =================
def get_tracks():
    q = """
    MATCH (t:Track)
    WHERE t.track_name IS NOT NULL
    RETURN DISTINCT t.track_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q)]

def get_track_info(track):
    q = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    RETURN
      t.track_name AS track,
      coalesce(t.popularity,0) AS popularity,
      coalesce(t.energy,0.0) AS energy,
      coalesce(t.valence,0.0) AS valence,
      coalesce(t.danceability,0.0) AS danceability,
      coalesce(t.acousticness,0.0) AS acousticness,
      coalesce(t.instrumentalness,0.0) AS instrumentalness,
      coalesce(t.liveness,0.0) AS liveness,
      coalesce(t.speechiness,0.0) AS speechiness,
      collect(DISTINCT a.artist_name) AS artists,
      collect(DISTINCT g.genre_name) AS genres
    """
    with driver.session(database=NEO4J_DB) as s:
        return s.run(q, name=track).single()

def get_recommendations(track):
    q = """
    MATCH (t:Track {track_name:$name})-[:SIMILAR_TO]->(r:Track)
    OPTIONAL MATCH (r)-[:PERFORMED_BY]->(a:Artist)
    RETURN r.track_name AS track,
           r.popularity AS popularity,
           r.energy AS energy,
           r.valence AS valence,
           collect(DISTINCT a.artist_name) AS artists
    ORDER BY popularity DESC
    LIMIT 5
    """
    with driver.session(database=NEO4J_DB) as s:
        return list(s.run(q, name=track))

# ================= GRAPH =================
def render_graph(track):
    q = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    OPTIONAL MATCH (t)-[:SIMILAR_TO]->(s:Track)
    RETURN
      collect(DISTINCT a.artist_name) AS artists,
      collect(DISTINCT g.genre_name) AS genres,
      collect(DISTINCT s.track_name) AS similars
    """
    with driver.session(database=NEO4J_DB) as s:
        r = s.run(q, name=track).single()

    net = Network(
        height="620px",
        width="100%",
        bgcolor="#020617",
        font_color="white",
        directed=True
    )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -26000,
          "springLength": 160
        }
      },
      "edges": {
        "arrows": { "to": { "enabled": true } },
        "font": { "size": 14 }
      },
      "interaction": {
        "zoomView": true,
        "dragView": true
      }
    }
    """)

    net.add_node(track, label="🎵 " + clean_text(track),
                 shape="star", size=42, color="#2563eb")

    for a in r["artists"]:
        net.add_node(a, label="👤 " + clean_text(a),
                     shape="circle", size=30, color="#22c55e")
        net.add_edge(track, a, label="PERFORMED_BY", width=2)

    for g in r["genres"]:
        net.add_node(g, label="🎼 " + clean_text(g),
                     shape="box", size=24, color="#a855f7")
        net.add_edge(track, g, label="IN_GENRE", width=2)

    for s in r["similars"]:
        net.add_node(s, label="🎵 " + clean_text(s),
                     shape="dot", size=26, color="#38bdf8")
        net.add_edge(track, s, label="SIMILAR_TO", width=3)

    net.save_graph("graph.html")
    with open("graph.html", "r", encoding="utf-8") as f:
        components.html(f.read(), height=650, scrolling=True)

# ================= UI =================
st.set_page_config("Music Recommendation System", layout="wide")

st.markdown("""
<style>
.card {
    background: linear-gradient(135deg,#111827,#020617);
    padding: 20px;
    border-radius: 18px;
    box-shadow: 0 18px 40px rgba(0,0,0,0.45);
    color: white;
    margin-bottom: 18px;
}
.sub { color:#9ca3af }
.scroll { max-height:380px; overflow-y:auto }
</style>
""", unsafe_allow_html=True)

st.title("🎵 Music Recommendation System")
st.caption("Neo4j • Graph Recommendation • Streamlit")

tracks = get_tracks()
selected = st.selectbox("🔍 Rechercher une chanson",
                         tracks,
                         format_func=lambda x: clean_text(x))

if selected:
    info = get_track_info(selected)

    st.markdown("## 🎶 Now Playing")
    st.markdown(f"""
    <div class="card">
      <h2>{clean_text(info['track'],80)}</h2>
      <p class="sub">👤 {', '.join(clean_list(info['artists']))}</p>
      <p class="sub">🎼 {', '.join(clean_list(info['genres']))}</p>
    </div>
    """, unsafe_allow_html=True)

    c1,c2,c3 = st.columns(3)
    c1.metric("🔥 Popularité", info["popularity"])
    c2.metric("⚡ Énergie", round(info["energy"],2))
    c3.metric("😊 Valence", round(info["valence"],2))

    st.markdown("### 🎛️ Audio Features")
    cols = st.columns(5)
    feats = ["danceability","acousticness",
             "instrumentalness","liveness","speechiness"]
    for col,f in zip(cols,feats):
        col.markdown(f"**{f.capitalize()}**")
        col.progress(min(float(info[f]),1.0))

    st.markdown("## 🔁 Recommandations")
    recs = get_recommendations(selected)
    if recs:
        st.markdown("<div class='scroll'>", unsafe_allow_html=True)
        for r in recs:
            st.markdown(f"""
            <div class="card">
              <b>{clean_text(r['track'])}</b><br>
              👤 {', '.join(clean_list(r['artists']))}<br>
              🔥 Popularité : {r['popularity']}
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("## 🗝️ Clé de lecture du graphe")
    st.markdown("""
- ⭐ Chanson sélectionnée  
- 🎵 Chanson similaire  
- 👤 Artiste  
- 🎼 Genre  
- ➝ Relation Neo4j  
    """)

    st.markdown("## 🕸️ Graphe local interactif")
    render_graph(selected)
