import streamlit as st
import re
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components

# ================= CONFIG =================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"
NEO4J_DB = "music-recommendation"

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
def get_all_artists():
    q = """
    MATCH (a:Artist)
    WHERE a.artist_name IS NOT NULL
    RETURN DISTINCT a.artist_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q)]

def get_all_genres():
    q = """
    MATCH (g:Genre)
    WHERE g.genre_name IS NOT NULL
    RETURN DISTINCT g.genre_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q)]

def get_tracks(artist_filter=None, genre_filter=None, min_popularity=0, max_popularity=100):
    conditions = ["t.track_name IS NOT NULL"]
    
    if min_popularity > 0 or max_popularity < 100:
        conditions.append(f"t.popularity >= {min_popularity} AND t.popularity <= {max_popularity}")
    
    optional_match = []
    where_clauses = []
    
    if artist_filter and artist_filter != "Tous les artistes":
        optional_match.append("OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)")
        where_clauses.append("a.artist_name = $artist")
    
    if genre_filter and genre_filter != "Tous les genres":
        optional_match.append("OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)")
        where_clauses.append("g.genre_name = $genre")
    
    where_str = " AND ".join(conditions + where_clauses) if (conditions or where_clauses) else ""
    
    q = f"""
    MATCH (t:Track)
    {' '.join(optional_match)}
    WHERE {where_str}
    RETURN DISTINCT t.track_name AS name
    ORDER BY name
    """
    
    params = {}
    if artist_filter and artist_filter != "Tous les artistes":
        params["artist"] = artist_filter
    if genre_filter and genre_filter != "Tous les genres":
        params["genre"] = genre_filter
    
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q, **params)]

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

    net.add_node(track, label="♪ " + clean_text(track),
                 shape="star", size=42, color="#2563eb", title="Chanson sélectionnée")

    for a in r["artists"]:
        net.add_node(a, label="♫ " + clean_text(a),
                     shape="circle", size=30, color="#22c55e", title="Artiste")
        net.add_edge(track, a, label="PERFORMED_BY", width=2)

    for g in r["genres"]:
        net.add_node(g, label="♬ " + clean_text(g),
                     shape="box", size=24, color="#a855f7", title="Genre")
        net.add_edge(track, g, label="IN_GENRE", width=2)

    for s in r["similars"]:
        net.add_node(s, label="♪ " + clean_text(s),
                     shape="dot", size=26, color="#38bdf8", title="Chanson similaire")
        net.add_edge(track, s, label="SIMILAR_TO", width=3)

    net.save_graph("graph.html")
    with open("graph.html", "r", encoding="utf-8") as f:
        components.html(f.read(), height=650, scrolling=True)

# ================= UI =================
st.set_page_config("Music Recommendation System", layout="wide")

st.markdown("""
<style>
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

body {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
}

.main {
    background: transparent;
}

.stApp {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
}

.card {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    padding: 24px;
    border-radius: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08), 0 0 1px rgba(0,0,0,0.05);
    color: #1e293b;
    margin-bottom: 20px;
    border: 1px solid rgba(59,130,246,0.1);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(59,130,246,0.15), 0 0 2px rgba(59,130,246,0.2);
}

.filter-card {
    background: linear-gradient(135deg, #dbeafe, #e0f2fe);
    padding: 24px;
    border-radius: 16px;
    box-shadow: 0 4px 20px rgba(59,130,246,0.1);
    margin-bottom: 24px;
    border: 1px solid rgba(59,130,246,0.2);
}

.title-header {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 3em;
    font-weight: 800;
    text-align: center;
    margin-bottom: 10px;
}

.subtitle {
    text-align: center;
    color: #64748b;
    font-size: 1.1em;
    margin-bottom: 30px;
}

.sub { 
    color: #64748b;
    font-size: 0.95em;
}

.scroll { 
    max-height: 380px; 
    overflow-y: auto;
    padding-right: 10px;
}

.scroll::-webkit-scrollbar {
    width: 8px;
}

.scroll::-webkit-scrollbar-track {
    background: rgba(226,232,240,0.5);
    border-radius: 10px;
}

.scroll::-webkit-scrollbar-thumb {
    background: rgba(59,130,246,0.4);
    border-radius: 10px;
}

.scroll::-webkit-scrollbar-thumb:hover {
    background: rgba(59,130,246,0.6);
}

.icon-title {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    color: #1e293b;
}

.icon-title i {
    color: #3b82f6;
}

.metric-card {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    padding: 20px;
    border-radius: 16px;
    border: 2px solid rgba(59,130,246,0.2);
    box-shadow: 0 4px 15px rgba(59,130,246,0.1);
    transition: all 0.3s ease;
    text-align: center;
}

.metric-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 25px rgba(59,130,246,0.2);
    border-color: rgba(59,130,246,0.4);
}

.metric-icon {
    font-size: 2.5em;
    margin-bottom: 12px;
    display: block;
}

.metric-label {
    font-size: 0.9em;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
}

.metric-value {
    font-size: 2.2em;
    font-weight: 800;
    color: #1e293b;
    line-height: 1;
}

.feature-bar {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 8px;
    border: 1px solid rgba(59,130,246,0.15);
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    transition: all 0.3s ease;
}

.feature-bar:hover {
    transform: scale(1.02);
    box-shadow: 0 4px 12px rgba(59,130,246,0.15);
    border-color: rgba(59,130,246,0.3);
}

.feature-icon {
    font-size: 1.5em;
    color: #3b82f6;
    margin-bottom: 8px;
}

.feature-label {
    font-size: 0.85em;
    color: #475569;
    font-weight: 600;
    margin-bottom: 10px;
}

.feature-value {
    font-size: 1.2em;
    font-weight: 700;
    color: #1e293b;
    margin-top: 8px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
    color: #475569;
}

.legend-icon {
    width: 30px;
    text-align: center;
}

div[data-testid="stMetricValue"] {
    font-size: 1.8em;
    font-weight: 700;
    color: #1e293b;
}

h2, h3 {
    color: #1e293b;
}

/* Styles pour les selectbox et inputs */
div[data-baseweb="select"] > div {
    background: linear-gradient(135deg, #ffffff, #fafbfc) !important;
    border: 2px solid rgba(59,130,246,0.3) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(59,130,246,0.1) !important;
    transition: all 0.3s ease !important;
}

div[data-baseweb="select"]:hover > div {
    border-color: rgba(59,130,246,0.5) !important;
    box-shadow: 0 4px 12px rgba(59,130,246,0.15) !important;
}

/* Style pour le slider */
div[data-testid="stSlider"] > div > div > div {
    background: linear-gradient(90deg, #3b82f6, #8b5cf6) !important;
}

div[data-testid="stSlider"] [role="slider"] {
    background: #3b82f6 !important;
    border: 3px solid #ffffff !important;
    box-shadow: 0 2px 8px rgba(59,130,246,0.3) !important;
}

.filter-label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #1e293b;
    font-weight: 600;
    font-size: 1em;
    margin-bottom: 10px;
    padding: 8px 12px;
    background: rgba(255,255,255,0.7);
    border-radius: 8px;
    border-left: 4px solid #3b82f6;
}

.search-section {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    padding: 20px;
    border-radius: 16px;
    border: 2px solid rgba(139,92,246,0.2);
    box-shadow: 0 4px 15px rgba(139,92,246,0.1);
    margin-bottom: 24px;
}

.search-label {
    display: flex;
    align-items: center;
    gap: 10px;
    color: #1e293b;
    font-weight: 600;
    font-size: 1.1em;
    margin-bottom: 12px;
}

.search-label i {
    color: #8b5cf6;
    font-size: 1.2em;
}

.results-badge {
    background: linear-gradient(135deg, #8b5cf6, #6366f1);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85em;
    font-weight: 600;
}

/* Styles pour les tabs */
.stTabs [data-baseweb="tab-list"] {
    background: linear-gradient(90deg, #ffffff, #f8fafc);
    border-bottom: 2px solid rgba(59,130,246,0.2);
    gap: 12px;
    padding: 12px;
    border-radius: 12px 12px 0 0;
}

.stTabs [data-baseweb="tab"] {
    background: rgba(59,130,246,0.05);
    border: 1px solid rgba(59,130,246,0.2);
    border-radius: 8px;
    padding: 10px 20px;
    color: #1e293b;
    font-weight: 600;
    transition: all 0.3s ease;
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(59,130,246,0.1);
    border-color: rgba(59,130,246,0.4);
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6) !important;
    color: white !important;
    border-color: #3b82f6 !important;
    box-shadow: 0 4px 12px rgba(59,130,246,0.2);
}

.tab-content {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    padding: 24px;
    border-radius: 0 12px 12px 12px;
    border: 1px solid rgba(59,130,246,0.1);
    border-top: none;
}

</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="title-header"><i class="fas fa-music"></i> Music Recommendation System</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle"><i class="fas fa-database"></i> Neo4j • <i class="fas fa-project-diagram"></i> Graph Recommendation • <i class="fas fa-chart-line"></i> Streamlit</p>', unsafe_allow_html=True)

# ================= FILTRES =================
st.markdown('<div class="filter-card">', unsafe_allow_html=True)
st.markdown('<h3 class="icon-title"><i class="fas fa-filter"></i> Filtres de recherche</h3>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown('<div class="filter-label"><i class="fas fa-user-music"></i> Artiste</div>', unsafe_allow_html=True)
    artists = ["Tous les artistes"] + get_all_artists()
    selected_artist = st.selectbox("", artists, label_visibility="collapsed", key="artist_filter")

with col2:
    st.markdown('<div class="filter-label"><i class="fas fa-guitar"></i> Genre</div>', unsafe_allow_html=True)
    genres = ["Tous les genres"] + get_all_genres()
    selected_genre = st.selectbox("", genres, label_visibility="collapsed", key="genre_filter")

with col3:
    st.markdown('<div class="filter-label"><i class="fas fa-fire"></i> Popularité</div>', unsafe_allow_html=True)
    popularity_range = st.slider("", 0, 100, (0, 100), label_visibility="collapsed", key="popularity_filter")

st.markdown('</div>', unsafe_allow_html=True)

# ================= SELECTION =================
tracks = get_tracks(
    artist_filter=selected_artist,
    genre_filter=selected_genre,
    min_popularity=popularity_range[0],
    max_popularity=popularity_range[1]
)

if not tracks:
    st.warning("<i class='fas fa-exclamation-triangle'></i> Aucune chanson ne correspond à vos critères de filtrage.", icon="⚠️")
    st.stop()

st.markdown('<div class="search-section">', unsafe_allow_html=True)
st.markdown(f'''
<div class="search-label">
    <i class="fas fa-search"></i> 
    Rechercher une chanson
    <span class="results-badge">{len(tracks)} résultats</span>
</div>
''', unsafe_allow_html=True)
selected = st.selectbox("", tracks, format_func=lambda x: clean_text(x), label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

if selected:
    info = get_track_info(selected)

    st.markdown('<h2 class="icon-title"><i class="fas fa-play-circle"></i> Now Playing</h2>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="card">
      <h2 style="color:#3b82f6; margin-bottom:12px;"><i class="fas fa-music"></i> {clean_text(info['track'],80)}</h2>
      <p class="sub"><i class="fas fa-user"></i> {', '.join(clean_list(info['artists']))}</p>
      <p class="sub"><i class="fas fa-compact-disc"></i> {', '.join(clean_list(info['genres']))}</p>
    </div>
    """, unsafe_allow_html=True)

    # ================= TABS =================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Analyse Audio", 
        "🎵 Recommandations", 
        "🕸️ Graphe", 
        "📋 Détails"
    ])

    # ================= TAB 1: AUDIO ANALYSIS =================
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-gauge-high"></i> Métriques principales</h3>', unsafe_allow_html=True)
        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-fire metric-icon" style="color:#ef4444;"></i>
                <div class="metric-label">Popularité</div>
                <div class="metric-value">{info["popularity"]}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c2:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-bolt metric-icon" style="color:#f59e0b;"></i>
                <div class="metric-label">Énergie</div>
                <div class="metric-value">{round(info["energy"],2)}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c3:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-smile metric-icon" style="color:#10b981;"></i>
                <div class="metric-label">Valence</div>
                <div class="metric-value">{round(info["valence"],2)}</div>
            </div>
            ''', unsafe_allow_html=True)

        st.markdown('<h3 class="icon-title" style="margin-top:24px;"><i class="fas fa-sliders-h"></i> Caractéristiques détaillées</h3>', unsafe_allow_html=True)
        cols = st.columns(5)
        feats = ["danceability","acousticness",
                 "instrumentalness","liveness","speechiness"]
        icons = ["fa-walking", "fa-volume-off", "fa-guitar", "fa-microphone-alt", "fa-comment"]
        colors = ["#8b5cf6", "#06b6d4", "#f59e0b", "#ef4444", "#10b981"]
        labels = ["Danceability", "Acousticness", "Instrumentalness", "Liveness", "Speechiness"]
        
        for col, f, icon, color, label in zip(cols, feats, icons, colors, labels):
            value = float(info[f])
            percentage = int(value * 100)
            col.markdown(f'''
            <div class="feature-bar">
                <div class="feature-icon"><i class="fas {icon}" style="color:{color};"></i></div>
                <div class="feature-label">{label}</div>
                <div style="background:#e2e8f0; border-radius:20px; height:8px; overflow:hidden;">
                    <div style="background:{color}; width:{percentage}%; height:100%; border-radius:20px; transition:width 0.5s ease;"></div>
                </div>
                <div class="feature-value">{percentage}%</div>
            </div>
            ''', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 2: RECOMMENDATIONS =================
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        recs = get_recommendations(selected)
        if recs:
            st.markdown(f'<p style="color:#64748b; margin-bottom:16px;"><i class="fas fa-lightbulb"></i> Découvrez {len(recs)} chansons similaires basées sur cette sélection</p>', unsafe_allow_html=True)
            
            for idx, r in enumerate(recs, 1):
                st.markdown(f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <p style="font-size:1.1em; margin:0;"><i class="fas fa-music" style="color:#3b82f6;"></i> <b>{clean_text(r['track'])}</b></p>
                        <span style="background:#8b5cf6; color:white; padding:4px 12px; border-radius:20px; font-weight:600; font-size:0.85em;">#{idx}</span>
                    </div>
                    <p class="sub" style="margin-bottom:8px;"><i class="fas fa-user"></i> {', '.join(clean_list(r['artists']))}</p>
                    <div style="display:flex; gap:16px; margin-top:12px;">
                        <div style="flex:1;">
                            <i class="fas fa-fire" style="color:#ef4444;"></i> Popularité: <b>{r['popularity']}</b>
                        </div>
                        <div style="flex:1;">
                            <i class="fas fa-bolt" style="color:#f59e0b;"></i> Énergie: <b>{round(r['energy'],2)}</b>
                        </div>
                        <div style="flex:1;">
                            <i class="fas fa-smile" style="color:#10b981;"></i> Valence: <b>{round(r['valence'],2)}</b>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("🎵 Aucune recommandation disponible pour cette chanson.")
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 3: GRAPH =================
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-info-circle"></i> Clé de lecture</h3>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
            <div class="legend-item"><span class="legend-icon">⭐</span> <b>Chanson sélectionnée</b> - Le centre du graphe</div>
            <div class="legend-item"><span class="legend-icon">♪</span> <b>Chanson similaire</b> - Recommandations</div>
            <div class="legend-item"><span class="legend-icon">♫</span> <b>Artiste</b> - Qui performe la chanson</div>
            <div class="legend-item"><span class="legend-icon">♬</span> <b>Genre</b> - Classification musicale</div>
            <div class="legend-item"><span class="legend-icon">→</span> <b>Relations</b> - Connexions entre nœuds</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title" style="margin-top:20px;"><i class="fas fa-project-diagram"></i> Graphe local interactif</h3>', unsafe_allow_html=True)
        st.markdown('<p style="color:#64748b; font-size:0.9em;"><i class="fas fa-mouse"></i> Glissez pour déplacer les nœuds • Zoom pour zoomer</p>', unsafe_allow_html=True)
        render_graph(selected)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 4: DETAILS =================
    with tab4:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-file-alt"></i> Informations complètes</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div class="card">
                <h4><i class="fas fa-music"></i> Chanson</h4>
                <p style="font-size:1.1em; color:#3b82f6; font-weight:600; margin-bottom:8px;"></p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
            <div class="card">
                <p><b>Titre:</b> {clean_text(info['track'], 100)}</p>
                <p><b>Artistes:</b> {', '.join(clean_list(info['artists']))}</p>
                <p><b>Genres:</b> {', '.join(clean_list(info['genres']))}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="card">
                <h4><i class="fas fa-chart-bar"></i> Statistiques</h4>
            </div>
            """, unsafe_allow_html=True)
            
            stats = [
                ("Popularité", info["popularity"], "👥"),
                ("Énergie", round(info["energy"], 2), "⚡"),
                ("Valence", round(info["valence"], 2), "😊"),
                ("Danceability", int(float(info["danceability"]) * 100), "💃"),
                ("Acousticness", int(float(info["acousticness"]) * 100), "🎸"),
                ("Instrumentalness", int(float(info["instrumentalness"]) * 100), "🎹"),
            ]
            
            for stat_name, stat_value, emoji in stats:
                st.markdown(f"""
                <div style="background:rgba(59,130,246,0.05); padding:12px; border-radius:8px; margin-bottom:8px; border-left:4px solid #3b82f6;">
                    <p style="margin:0; color:#64748b; font-size:0.9em;"><b>{stat_name}</b></p>
                    <p style="margin:8px 0 0 0; font-size:1.3em; font-weight:700; color:#1e293b;">{stat_value}</p>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
