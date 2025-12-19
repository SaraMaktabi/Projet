import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Charger le CSV
df = pd.read_csv("tracks_embeddings_input.csv")

# Créer embeddings textuels
model = SentenceTransformer('all-MiniLM-L6-v2')
text_embeddings = model.encode(df['embedding_text'].tolist(), show_progress_bar=True)

# Normaliser les features audio
audio_features = df[['danceability','energy','speechiness','acousticness',
                     'instrumentalness','liveness','valence','tempo']].fillna(0).values
audio_features = (audio_features - audio_features.mean(axis=0)) / (audio_features.std(axis=0)+1e-9)

# Combiner texte + audio
combined_embeddings = np.hstack([text_embeddings, audio_features])

# Calculer similarité cosine
similarity_matrix = cosine_similarity(combined_embeddings)

# Pour chaque track, récupérer top 5 similaires
top_k = 5
similar_tracks = []

for idx, track_id in enumerate(df['track_id']):
    sim_scores = similarity_matrix[idx]
    # Ignorer soi-même
    sim_scores[idx] = -1
    top_indices = sim_scores.argsort()[-top_k:][::-1]
    for i in top_indices:
        similar_tracks.append({
            'track_id': track_id,
            'similar_track_id': df['track_id'].iloc[i],
            'score': sim_scores[i]
        })

similar_df = pd.DataFrame(similar_tracks)
similar_df.to_csv("tracks_similar.csv", index=False)
print("✅ CSV de similarité créé !")
